"""Content selector — intelligently picks resume content for a specific job.

Given a candidate profile and a job description, this module selects the
most relevant skills, experience bullets, projects, and certifications
to include in a tailored resume.

When a GrokProvider is configured (GROK_API_KEY set), the selector will:
- Generate a tailored professional summary using the LLM
- Optionally rephrase the top 2 bullets per role to match JD keywords

Set use_llm=False on ContentSelector() to disable LLM calls (e.g. in tests).
"""

import logging
from dataclasses import dataclass, field

from src.analyzer.keywords import extract_keywords, normalize_keyword
from src.profile.manager import CandidateProfile

logger = logging.getLogger(__name__)


@dataclass
class SelectedContent:
    """The selected content to use when generating a resume."""
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    certifications: list[dict] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    honors: list[str] = field(default_factory=list)
    personal_info: dict = field(default_factory=dict)
    target_keywords: list[str] = field(default_factory=list)


# ── Prompt templates ─────────────────────────────────────────

_SUMMARY_SYSTEM_PROMPT = (
    "You are an expert resume writer specialising in tech industry roles. "
    "Write targeted, factual professional summaries. "
    "Use only information explicitly provided — never fabricate experience, "
    "metrics, or technologies. Keep language active and quantified where possible."
)

_SUMMARY_USER_TEMPLATE = """\
Write a targeted professional summary for a job application.

CANDIDATE:
- Name: {name}
- Total Experience: {years} years
- Most Recent Role: {recent_title} at {recent_company}
- Core Skills: {top_skills}
- A key achievement: {top_achievement}

TARGET JOB:
- Role: {job_title}
- Company: {company}
- Key Requirements: {jd_keywords}

INSTRUCTIONS:
- Exactly 3 sentences, ~65-80 words total
- Sentence 1: Experience level + primary specialisation + years of experience
- Sentence 2: 2-3 most directly relevant skills/technologies from the JD requirements
- Sentence 3: One quantified achievement from the candidate's background
- Do NOT mention soft skills (teamwork, communication) unless in JD keywords
- Do NOT use first person ("I", "my")
- Reply with ONLY the summary text — no preamble, no quotation marks
"""

_BULLET_SYSTEM_PROMPT = (
    "You are a resume expert optimising experience bullet points for ATS and human readers. "
    "Only use facts explicitly stated in the original bullet. Do not invent numbers, "
    "technologies, or outcomes not already present."
)

_BULLET_USER_TEMPLATE = """\
Optimise this resume bullet to better match the job description while keeping it factually accurate.

ORIGINAL BULLET:
{bullet}

JD KEYWORDS TO WEAVE IN (only those truly relevant to this bullet):
{keywords}

RULES:
- Begin with a strong action verb
- Keep or strengthen any existing metrics/numbers
- Do not add technologies or results not in the original
- One line only — no trailing punctuation changes unless clearly wrong
- Reply with ONLY the optimised bullet text
"""


class ContentSelector:
    """Select the best resume content for a given job description.

    Args:
        use_llm: Use the configured LLM provider to generate tailored
                 summaries and optimise bullets. Defaults to True.
                 Set False in tests to avoid API calls.
        llm_provider: Override the default LLM provider (useful for testing).
    """

    def __init__(self, use_llm: bool = True, llm_provider=None):
        self.use_llm = use_llm
        self._llm = llm_provider  # lazy-loaded via _get_llm()

    def _get_llm(self):
        if self._llm is None:
            from src.llm.provider import get_llm_provider
            self._llm = get_llm_provider()
        return self._llm

    def select(
        self,
        profile: CandidateProfile,
        jd_text: str,
        max_skills: int = 15,
        max_bullets_per_role: int = 4,
        max_projects: int = 2,
    ) -> SelectedContent:
        """Select and rank content from profile for the given JD.

        Args:
            profile: The candidate's full profile.
            jd_text: The job description text.
            max_skills: Maximum skills to include.
            max_bullets_per_role: Maximum bullet points per job.
            max_projects: Maximum projects to include.

        Returns:
            SelectedContent with the best-fit items.
        """
        jd_kw_result = extract_keywords(jd_text, max_keywords=25)
        jd_keywords = {k.canonical.lower() for k in jd_kw_result.keywords}
        jd_keyword_list = [k.canonical for k in jd_kw_result.keywords]

        # Enrich personal_info with derived title from most recent role
        personal_info = dict(profile.personal_info)
        if "title" not in personal_info and profile.experience:
            personal_info["title"] = profile.experience[0].get("title", "")

        result = SelectedContent(
            personal_info=personal_info,
            honors=profile.honors,
            target_keywords=jd_keyword_list,
        )

        # 2. Skills — rank by relevance to JD
        result.skills = self._select_skills(profile, jd_keywords, max_skills)

        # 3. Experience — rank bullets by relevance (optionally LLM-rephrase top bullets)
        result.experience = self._select_experience(
            profile, jd_keywords, jd_keyword_list, max_bullets_per_role
        )

        # 4. Education — include all
        result.education = profile.education

        # 5. Certifications — include all
        result.certifications = profile.certifications

        # 6. Projects — rank by relevance
        result.projects = self._select_projects(
            profile, jd_keywords, max_projects
        )

        # 1. Summary — LLM-generated if available, otherwise best pre-written match
        result.summary = self._build_summary(profile, jd_text, jd_keyword_list, result)

        return result

    # ── Summary ──────────────────────────────────────────────

    def _build_summary(
        self,
        profile: CandidateProfile,
        jd_text: str,
        jd_keyword_list: list[str],
        content: SelectedContent,
    ) -> str:
        """Generate a tailored summary using LLM, or fall back to pre-written."""
        if self.use_llm:
            llm = self._get_llm()
            from src.llm.provider import StubProvider
            if not isinstance(llm, StubProvider) and llm.is_available():
                try:
                    return self._llm_generate_summary(profile, jd_text, jd_keyword_list, content)
                except Exception as e:
                    logger.warning(f"LLM summary generation failed, using fallback: {e}")

        return self._select_summary_fallback(profile, jd_text)

    def _llm_generate_summary(
        self,
        profile: CandidateProfile,
        jd_text: str,
        jd_keyword_list: list[str],
        content: SelectedContent,
    ) -> str:
        """Call Grok to generate a JD-tailored professional summary."""
        llm = self._get_llm()

        # Extract job title/company from JD heuristically
        jd_lines = [l.strip() for l in jd_text.splitlines() if l.strip()]
        job_title = jd_lines[0][:80] if jd_lines else "the role"
        company = "the company"  # May be passed by callers that have it

        # Best achievement = first bullet of most recent experience
        top_achievement = ""
        if profile.experience:
            bullets = profile.experience[0].get("bullets", [])
            if bullets:
                top_achievement = bullets[0].get("text", "")

        recent_title = profile.experience[0].get("title", "") if profile.experience else ""
        recent_company = profile.experience[0].get("company", "") if profile.experience else ""

        prompt = _SUMMARY_USER_TEMPLATE.format(
            name=profile.full_name,
            years=profile.total_years_experience(),
            recent_title=recent_title,
            recent_company=recent_company,
            top_skills=", ".join(content.skills[:8]),
            top_achievement=top_achievement[:200],
            job_title=job_title,
            company=company,
            jd_keywords=", ".join(jd_keyword_list[:12]),
        )

        response = llm.generate(
            prompt,
            max_tokens=150,
            system_prompt=_SUMMARY_SYSTEM_PROMPT,
        )
        text = response.text.strip()
        # Sanity check — should be non-empty and not too long
        if text and len(text) > 20:
            logger.info(f"LLM generated summary ({response.tokens_used} tokens)")
            return text

        return self._select_summary_fallback(profile, jd_text)

    def _select_summary_fallback(self, profile: CandidateProfile, jd_text: str) -> str:
        """Pick the most relevant pre-written summary."""
        jd_lower = jd_text.lower()
        best_summary = ""
        best_score = -1

        for summary_item in profile.summaries:
            role = summary_item.get("target_role", "").lower()
            text = summary_item.get("text", "")
            role_words = role.split()
            score = sum(1 for w in role_words if w in jd_lower)

            if score > best_score:
                best_score = score
                best_summary = text

        # If no match at all, use first summary
        if not best_summary and profile.summaries:
            best_summary = profile.summaries[0].get("text", "")

        return best_summary.strip()

    # ── Skills ───────────────────────────────────────────────

    def _select_skills(
        self,
        profile: CandidateProfile,
        jd_keywords: set[str],
        max_skills: int,
    ) -> list[str]:
        """Rank and select skills by JD relevance."""
        all_skills = []
        for cat in profile.skills:
            for item in cat.get("items", []):
                name = item["name"]
                normalized = normalize_keyword(name).lower()
                # Score: is this in JD keywords?  Weight by proficiency
                prof_weight = {
                    "Expert": 3,
                    "Advanced": 2,
                    "Intermediate": 1,
                }.get(item.get("proficiency", ""), 1)

                relevance = 10 if normalized in jd_keywords else 0
                score = relevance + prof_weight

                all_skills.append((name, score))

        # Sort by score descending, then alphabetically
        all_skills.sort(key=lambda x: (-x[1], x[0]))
        return [s[0] for s in all_skills[:max_skills]]

    # ── Experience ────────────────────────────────────────────

    def _select_experience(
        self,
        profile: CandidateProfile,
        jd_keywords: set[str],
        jd_keyword_list: list[str],
        max_bullets_per_role: int,
    ) -> list[dict]:
        """Select experience entries with ranked bullets, optionally LLM-rephrased."""
        selected = []

        for exp in profile.experience:
            bullets = exp.get("bullets", [])

            # Score each bullet by tag overlap with JD keywords + text overlap
            scored_bullets = []
            for bullet in bullets:
                tags = {t.lower() for t in bullet.get("tags", [])}
                text_lower = bullet.get("text", "").lower()
                text_matches = sum(1 for kw in jd_keywords if kw in text_lower)
                tag_matches = len(tags & jd_keywords)
                score = tag_matches * 2 + text_matches
                scored_bullets.append((bullet, score))

            scored_bullets.sort(key=lambda x: -x[1])
            top_bullets = [b[0] for b in scored_bullets[:max_bullets_per_role]]

            # LLM-rephrase the top 2 bullets only (keep cost minimal)
            if self.use_llm and jd_keyword_list:
                top_bullets = self._maybe_rephrase_bullets(
                    top_bullets, jd_keyword_list, max_rephrase=2
                )

            selected.append({
                "company": exp["company"],
                "title": exp["title"],
                "location": exp.get("location", ""),
                "start_date": exp.get("start_date", ""),
                "end_date": exp.get("end_date"),
                "bullets": top_bullets,
            })

        return selected

    def _maybe_rephrase_bullets(
        self,
        bullets: list[dict],
        jd_keyword_list: list[str],
        max_rephrase: int = 2,
    ) -> list[dict]:
        """Use LLM to rephrase the top N bullets for better JD alignment.

        Only rephrases bullets that don't already have strong keyword coverage.
        Falls back to original if LLM call fails.
        """
        llm = self._get_llm()
        from src.llm.provider import StubProvider
        if isinstance(llm, StubProvider) or not llm.is_available():
            return bullets

        rephrased = list(bullets)
        rephrase_count = 0

        for i, bullet in enumerate(rephrased[:max_rephrase]):
            original_text = bullet.get("text", "")
            if not original_text:
                continue

            # Find keywords not yet in this bullet
            text_lower = original_text.lower()
            missing_kws = [kw for kw in jd_keyword_list[:8] if kw.lower() not in text_lower]

            if not missing_kws:
                continue  # Bullet already well-matched

            try:
                prompt = _BULLET_USER_TEMPLATE.format(
                    bullet=original_text,
                    keywords=", ".join(missing_kws[:5]),
                )
                response = llm.generate(
                    prompt,
                    max_tokens=80,
                    system_prompt=_BULLET_SYSTEM_PROMPT,
                )
                new_text = response.text.strip()
                if new_text and len(new_text) > 20:
                    rephrased[i] = {**bullet, "text": new_text}
                    rephrase_count += 1
                    logger.info(f"Bullet rephrased ({response.tokens_used} tokens)")
            except Exception as e:
                logger.debug(f"Bullet rephrase failed: {e}")

        return rephrased

    # ── Projects ──────────────────────────────────────────────

    def _select_projects(
        self,
        profile: CandidateProfile,
        jd_keywords: set[str],
        max_projects: int,
    ) -> list[dict]:
        """Select projects by relevance to JD."""
        scored = []
        for proj in profile.projects:
            tech = {t.lower() for t in proj.get("tech_stack", [])}
            desc_lower = proj.get("description", "").lower()

            score = len(tech & jd_keywords)
            score += sum(1 for kw in jd_keywords if kw in desc_lower)
            scored.append((proj, score))

        scored.sort(key=lambda x: -x[1])
        return [p[0] for p in scored[:max_projects]]
