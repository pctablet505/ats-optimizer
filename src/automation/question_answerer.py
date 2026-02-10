"""Question answerer — match application form questions to Q&A bank answers."""

import re
from src.profile.manager import CandidateProfile
from src.llm.provider import get_llm_provider, BaseLLMProvider


class QuestionAnswerer:
    """Answer application form questions using the candidate's Q&A bank.

    Matches incoming questions against patterns in the Q&A bank using
    regex matching. Falls back to LLM generation for unmatched questions.
    """

    def __init__(
        self,
        profile: CandidateProfile,
        llm_provider: BaseLLMProvider | None = None,
    ):
        self.profile = profile
        self.llm = llm_provider or get_llm_provider()

    def answer(self, question: str) -> dict:
        """Attempt to answer a question.

        Args:
            question: The question text from the application form.

        Returns:
            Dict with keys:
                answer: The answer string.
                source: "qa_bank" | "llm" | "manual"
                confidence: float 0-1.
        """
        # 1. Try Q&A bank match
        qa_answer = self._match_qa_bank(question)
        if qa_answer:
            return {
                "answer": qa_answer,
                "source": "qa_bank",
                "confidence": 0.95,
            }

        # 2. Try LLM generation
        if self.llm.is_available():
            try:
                prompt = (
                    f"You are helping fill out a job application. "
                    f"Answer the following question concisely and professionally.\n\n"
                    f"Question: {question}\n\n"
                    f"Candidate info: {self.profile.full_name}, "
                    f"{self.profile.location}, "
                    f"{self.profile.total_years_experience()} years experience.\n\n"
                    f"Answer:"
                )
                response = self.llm.generate(prompt, max_tokens=100)
                return {
                    "answer": response.text,
                    "source": "llm",
                    "confidence": 0.6,
                }
            except Exception:
                pass

        # 3. Fallback — flag for manual review
        return {
            "answer": "",
            "source": "manual",
            "confidence": 0.0,
        }

    def answer_batch(self, questions: list[str]) -> list[dict]:
        """Answer multiple questions.

        Args:
            questions: List of question strings.

        Returns:
            List of answer dicts (same format as answer()).
        """
        return [self.answer(q) for q in questions]

    def _match_qa_bank(self, question: str) -> str | None:
        """Match question against Q&A bank patterns using regex.

        Args:
            question: The question text.

        Returns:
            The matched answer or None.
        """
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
                # Invalid regex — try simple substring match
                if pattern.lower() in question_lower:
                    return answer

        return None
