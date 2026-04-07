"""Question answerer — match application form questions to Q&A bank answers.

Answer strategy (in priority order):
1. Exact/regex match against the candidate's Q&A bank (zero LLM cost)
2. Answer from well-known fields (experience years, location, salary, etc.)
3. LLM generation with rich candidate context prompt (only for unknown questions)
"""

import re
import logging
from src.profile.manager import CandidateProfile
from src.llm.provider import get_llm_provider, BaseLLMProvider

logger = logging.getLogger(__name__)

# ── System prompt for question answering ─────────────────────

_QA_SYSTEM_PROMPT = (
    "You are filling out a job application form on behalf of a candidate. "
    "Answer each question concisely and professionally using ONLY the candidate "
    "information provided. For yes/no questions reply with Yes or No only. "
    "For numeric questions reply with just the number. "
    "For open-ended questions reply with 1-3 sentences maximum. "
    "Never fabricate information not present in the candidate profile."
)

# ── Known/derived question patterns ──────────────────────────

_DERIVED_PATTERNS: list[tuple[str, str]] = [
    # (regex_pattern, answer_key_in_candidate_info)
    (r"years? of experience|how many years", "years_experience"),
    (r"current (location|city|address)|where (are|do) you (live|located)", "location"),
    (r"authorized|authoris(ed|ation)|work (permit|visa)|eligib", "work_authorization"),
    (r"salary|compensation|pay expectation|ctc", "salary_expectation"),
    (r"notice period|how soon|availability|start date|when can you", "notice_period"),
    (r"remote|work from home|wfh preference", "remote_preference"),
    (r"linkedin", "linkedin"),
    (r"github|portfolio|code sample", "github"),
    (r"phone|mobile|contact number", "phone"),
    (r"email|e-mail", "email"),
    (r"full name|your name", "full_name"),
    (r"willing to relocate|open to relocation", "relocation"),
    (r"highest (education|degree|qualification)", "highest_education"),
    (r"current (employer|company)|where do you work", "current_employer"),
    (r"current (role|title|position)", "current_title"),
]


class QuestionAnswerer:
    """Answer application form questions using Q&A bank, derived facts, and LLM.

    Minimises LLM usage: the Q&A bank and derived patterns handle the vast
    majority of structured form questions at zero API cost.

    Args:
        profile: The candidate profile.
        llm_provider: LLM provider (defaults to configured provider).
        salary_expectation: Override; otherwise derived from profile.
        notice_period: Default notice period string (e.g. "30 days").
        work_authorization: Work auth status string.
        remote_preference: Preferred work style (e.g. "Remote/Hybrid").
        relocation: Whether open to relocation ("Yes" / "No").
    """

    def __init__(
        self,
        profile: CandidateProfile,
        llm_provider: BaseLLMProvider | None = None,
        salary_expectation: str = "Negotiable, based on total compensation",
        notice_period: str = "Immediate / 30 days",
        work_authorization: str = "Yes, authorized to work",
        remote_preference: str = "Remote or Hybrid preferred; open to on-site",
        relocation: str = "Open to discussion",
    ):
        self.profile = profile
        self.llm = llm_provider or get_llm_provider()
        self._salary = salary_expectation
        self._notice = notice_period
        self._auth = work_authorization
        self._remote = remote_preference
        self._relocation = relocation

        # Build candidate info dict for derived lookups and LLM context
        recent_exp = profile.experience[0] if profile.experience else {}
        edu = profile.education[0] if profile.education else {}
        self._candidate_info: dict[str, str] = {
            "full_name": profile.full_name,
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location or "India",
            "linkedin": profile.linkedin or "",
            "github": profile.github or "",
            "years_experience": str(profile.total_years_experience()),
            "current_title": recent_exp.get("title", ""),
            "current_employer": recent_exp.get("company", ""),
            "highest_education": (
                f"{edu.get('degree', '')} – {edu.get('institution', '')}".strip(" –")
            ),
            "salary_expectation": salary_expectation,
            "notice_period": notice_period,
            "work_authorization": work_authorization,
            "remote_preference": remote_preference,
            "relocation": relocation,
        }

    # ── Public API ───────────────────────────────────────────

    def answer(self, question: str) -> dict:
        """Attempt to answer a question.

        Returns:
            Dict with keys:
                answer: The answer string.
                source: "qa_bank" | "derived" | "llm" | "manual"
                confidence: float 0-1.
        """
        # 1. Q&A bank — exact/regex match (zero cost)
        qa_answer = self._match_qa_bank(question)
        if qa_answer:
            return {"answer": qa_answer, "source": "qa_bank", "confidence": 0.97}

        # 2. Derived from known profile fields (zero cost)
        derived = self._derive_answer(question)
        if derived:
            return {"answer": derived, "source": "derived", "confidence": 0.92}

        # 3. LLM — only for genuinely unknown questions
        if self.llm.is_available():
            try:
                llm_answer = self._llm_answer(question)
                if llm_answer:
                    return {"answer": llm_answer, "source": "llm", "confidence": 0.70}
            except Exception as e:
                logger.warning(f"LLM question answering failed: {e}")

        return {"answer": "", "source": "manual", "confidence": 0.0}

    def answer_batch(self, questions: list[str]) -> list[dict]:
        """Answer multiple questions, grouping LLM calls when possible."""
        return [self.answer(q) for q in questions]

    def build_answers_dict(self) -> dict:
        """Return a flat dict of common form field labels → answers.

        Used to pre-populate known form fields without per-question LLM calls.
        """
        return {
            "name": self._candidate_info["full_name"],
            "full name": self._candidate_info["full_name"],
            "first name": self._candidate_info["full_name"].split()[0],
            "last name": " ".join(self._candidate_info["full_name"].split()[1:]),
            "email": self._candidate_info["email"],
            "phone": self._candidate_info["phone"],
            "mobile": self._candidate_info["phone"],
            "linkedin": self._candidate_info["linkedin"],
            "github": self._candidate_info["github"],
            "location": self._candidate_info["location"],
            "city": self._candidate_info["location"].split(",")[0].strip(),
            "years of experience": self._candidate_info["years_experience"],
            "current company": self._candidate_info["current_employer"],
            "current role": self._candidate_info["current_title"],
            "salary": self._candidate_info["salary_expectation"],
            "notice period": self._candidate_info["notice_period"],
            "work authorization": self._candidate_info["work_authorization"],
            "education": self._candidate_info["highest_education"],
        }

    # ── Private helpers ──────────────────────────────────────

    def _match_qa_bank(self, question: str) -> str | None:
        question_lower = question.lower().strip()
        for qa in self.profile.qa_bank:
            pattern = qa.get("question_pattern", "")
            answer = qa.get("answer", "")
            if not pattern:
                continue
            try:
                if re.search(pattern, question_lower, re.IGNORECASE):
                    return answer
            except re.error:
                if pattern.lower() in question_lower:
                    return answer
        return None

    def _derive_answer(self, question: str) -> str | None:
        q_lower = question.lower().strip()
        for pattern, info_key in _DERIVED_PATTERNS:
            if re.search(pattern, q_lower, re.IGNORECASE):
                value = self._candidate_info.get(info_key, "")
                if value:
                    return value
        return None

    def _llm_answer(self, question: str) -> str:
        """Use Grok with rich candidate context to answer an unknown question."""
        from src.llm.provider import StubProvider
        if isinstance(self.llm, StubProvider):
            return ""

        top_skills = self.profile.get_all_skill_names()[:10]
        recent_exp = self.profile.experience[0] if self.profile.experience else {}

        prompt = f"""\
Answer this job application form question for the candidate below.

QUESTION: {question}

CANDIDATE PROFILE:
- Name: {self._candidate_info['full_name']}
- Location: {self._candidate_info['location']}
- Years of experience: {self._candidate_info['years_experience']}
- Current role: {self._candidate_info['current_title']} at {self._candidate_info['current_employer']}
- Top skills: {', '.join(top_skills)}
- Work authorization: {self._candidate_info['work_authorization']}
- Notice period: {self._candidate_info['notice_period']}
- Salary expectation: {self._candidate_info['salary_expectation']}
- Work preference: {self._candidate_info['remote_preference']}
- LinkedIn: {self._candidate_info['linkedin']}
- GitHub: {self._candidate_info['github']}

Provide a brief, professional answer (1-3 sentences for open-ended questions, \
a single word/number for factual questions). Reply with ONLY the answer text."""

        response = self.llm.generate(
            prompt,
            max_tokens=120,
            system_prompt=_QA_SYSTEM_PROMPT,
        )
        return response.text.strip()
