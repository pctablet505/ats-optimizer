"""Resume Builder — single-call LLM resume generation.

Takes the candidate profile (YAML) + a job description and returns
a complete, compile-ready LaTeX resume in one LLM call. No further
editing required.

Usage (CLI):
    python -m src.generator.resume_builder --jd path/to/jd.txt
    python -m src.generator.resume_builder --jd path/to/jd.txt --out data/output/resume_custom.tex
    python -m src.generator.resume_builder --jd-text "Senior ML Engineer at Stripe..."

Usage (Python):
    from src.generator.resume_builder import ResumeBuilder
    builder = ResumeBuilder()
    tex = builder.build(jd_text="...")
    Path("resume.tex").write_text(tex)
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROFILE_PATH = _PROJECT_ROOT / "data" / "profiles" / "candidate_profile.yaml"
_BASE_RESUME_PATH = _PROJECT_ROOT / "base_resume.tex"

# ── LaTeX macro reference (extracted from base_resume.tex) ────
# Inlined so the LLM always gets the exact macro signatures
# even if the base file changes structure.

_LATEX_PREAMBLE = r"""\documentclass[10pt, letterpaper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[default]{sourcesanspro}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{latexsym}
\usepackage[usenames,dvipsnames]{xcolor}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}
\usepackage{ragged2e}
\usepackage{geometry}
\usepackage{multicol}

\geometry{left=0.5in, top=0.5in, right=0.5in, bottom=0.5in}

\definecolor{midnightblue}{RGB}{25, 25, 112}
\definecolor{darkgray}{RGB}{70, 70, 70}

\urlstyle{same}
\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

\titleformat{\section}{
  \vspace{-8pt}\scshape\raggedright\large\color{midnightblue}\bfseries
}{}{0em}{}[\color{midnightblue}\titlerule \vspace{-5pt}]

\newcommand{\resumeItem}[1]{\item\small{{#1 \vspace{-2pt}}}}

\newcommand{\resumeSubheading}[4]{
  \vspace{-1pt}\item
    \begin{tabular*}{0.98\textwidth}[t]{l@{\extracolsep{\fill}}r}
      \textbf{#1} & {\small\color{darkgray} #2} \\
      \textit{\small#3} & \textit{\small\color{darkgray} #4} \\
    \end{tabular*}\vspace{-7pt}
}

\newcommand{\resumeProjectHeading}[2]{
    \item
    \begin{tabular*}{0.98\textwidth}{l@{\extracolsep{\fill}}r}
      \small#1 & #2 \\
    \end{tabular*}\vspace{-7pt}
}

\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}

\hypersetup{colorlinks=true, linkcolor=midnightblue, urlcolor=midnightblue}"""

# ── System prompt ─────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an elite resume writer and LaTeX expert specialising in tech-industry roles.
Your task: produce a COMPLETE, ATS-optimised, single-page LaTeX resume tailored to
a specific job description.

═══════════ ABSOLUTE RULES — NEVER VIOLATE ═══════════
1. NEVER fabricate experience, metrics, technologies, or outcomes.
   Every bullet point must trace back to a fact in the candidate profile.
2. You MAY: reorder bullets within a role, select a subset of bullets, rephrase
   bullets so JD keywords appear naturally — but ALL numbers and core facts must
   be preserved exactly.
3. OUTPUT ONLY valid, compilable LaTeX — no markdown fences, no commentary,
   no text before \\documentclass or after \\end{document}.
4. Use ONLY the custom macros listed in the LATEX TEMPLATE section.
   Do NOT invent new macros or \\newcommand definitions.
5. LaTeX special characters in plain text (%, &, $, #, _, {, }) MUST be escaped
   (e.g. & → \\&, % → \\%, $ → \\$) UNLESS they are inside a LaTeX command.
6. \\textbf{}, \\textit{}, \\href{}{} are allowed and encouraged for emphasis.
══════════════════════════════════════════════════════

QUALITY TARGETS:
• ATS score ≥ 85/100: the top keywords from the JD must appear in the resume text.
• Fit on ONE page: if content overflows, trim the least-relevant bullets.
• Summary: exactly 3 sentences, 65-80 words, third-person, no "I"/"my".
• Each experience bullet: starts with a strong past-tense action verb, contains
  at least one metric or concrete outcome where the profile provides one.
• Skills section: list JD-matched skills first within each category.
"""

# ── User prompt template ──────────────────────────────────────

USER_PROMPT_TEMPLATE = """\
══════════════════════════════════════════════════════
LATEX TEMPLATE (use these macros exactly)
══════════════════════════════════════════════════════
{latex_preamble}

══════════════════════════════════════════════════════
CANDIDATE PROFILE
══════════════════════════════════════════════════════
{profile_text}

══════════════════════════════════════════════════════
JOB DESCRIPTION
══════════════════════════════════════════════════════
{jd_text}

══════════════════════════════════════════════════════
TAILORING INSTRUCTIONS
══════════════════════════════════════════════════════

HEADER
  • Keep name, contact info, and links exactly as in the profile.
  • Update the subtitle tagline to match the target role from the JD.

PROFESSIONAL SUMMARY
  • 3 sentences, 65-80 words, third-person only.
  • Sentence 1: years of experience + primary specialisation matching the JD.
  • Sentence 2: 2-3 core technologies/skills explicitly required by the JD.
  • Sentence 3: single strongest quantified achievement from the profile.
  • Place inside \\section{{Professional Summary}} after the header.

PROFESSIONAL EXPERIENCE
  • Include ALL three roles (Google, Qualcomm, Samsung). Do not drop any.
  • For each role, select the 3-5 bullets most relevant to the JD.
  • Rephrase the TOP 2 bullets per role to weave in missing JD keywords
    naturally. Preserve every number and factual outcome.
  • Use \\resumeSubheading{{Company}}{{Date}}{{Title}}{{Location}} then
    \\resumeItemListStart / \\resumeItem{{...}} / \\resumeItemListEnd.

SKILLS
  • Reorder skill categories: put the most JD-relevant categories first.
  • Within each category, list JD-matching skills before others.
  • Use the \\textbf{{Category:}} item format as in the template.
  • Limit to 7 categories maximum.

EDUCATION
  • Include both degrees exactly as in the profile.

HONORS & AWARDS + CERTIFICATIONS
  • Include all entries; no changes needed.

OPEN SOURCE & PROJECTS
  • Include only projects relevant to the JD (drop irrelevant ones).

SECTION ORDER (top to bottom):
  Header → Summary → Experience → Skills → Education →
  Honors & Awards → Certifications → Open Source & Projects

OUTPUT: The complete LaTeX document from \\documentclass to \\end{{document}}.
No preamble text, no markdown fences, no explanations. Just the .tex content.
"""


# ── Profile formatter ─────────────────────────────────────────

def _fmt_profile(profile: dict) -> str:
    """Convert the YAML profile dict into a compact, LLM-readable text block.

    Uses plain prose rather than raw YAML to reduce tokens and improve
    LLM comprehension.
    """
    lines: list[str] = []

    # Personal info
    pi = profile.get("personal_info", {})
    lines += [
        "--- PERSONAL INFO ---",
        f"Name: {pi.get('full_name', '')}",
        f"Email: {pi.get('email', '')}",
        f"Phone: {pi.get('phone', '')}",
        f"Location: {pi.get('location', '')}",
        f"LinkedIn: {pi.get('linkedin', '')}",
        f"GitHub: {pi.get('github', '')}",
        f"Portfolio: {pi.get('portfolio', '')}",
        "",
    ]

    # Pre-written summaries (useful context even though we'll generate a new one)
    summaries = profile.get("summaries", [])
    if summaries:
        lines.append("--- PRE-WRITTEN SUMMARIES (for reference only — you will write a new tailored one) ---")
        for s in summaries:
            lines.append(f"[{s.get('target_role', '')}]: {s.get('text', '').strip()}")
        lines.append("")

    # Skills
    lines.append("--- SKILLS ---")
    for cat in profile.get("skills", []):
        cat_name = cat.get("category", "")
        items = cat.get("items", [])
        item_strs = [
            f"{i['name']} ({i.get('proficiency','')}, {i.get('years','')}yr)"
            for i in items
        ]
        lines.append(f"{cat_name}: {', '.join(item_strs)}")
    lines.append("")

    # Experience
    lines.append("--- EXPERIENCE ---")
    for exp in profile.get("experience", []):
        start = exp.get("start_date", "")
        end = exp.get("end_date") or "Present"
        lines.append(
            f"\n[{exp.get('company','')}] — {exp.get('title','')} | "
            f"{exp.get('location','')} | {start} – {end}"
        )
        for b in exp.get("bullets", []):
            text = b.get("text", "")
            tags = b.get("tags", [])
            lines.append(f"  • {text}")
            if tags:
                lines.append(f"    Tags: {', '.join(tags)}")
    lines.append("")

    # Education
    lines.append("--- EDUCATION ---")
    for edu in profile.get("education", []):
        lines.append(
            f"  • {edu.get('degree','')} — {edu.get('institution','')} "
            f"({edu.get('graduation_date','')}) [{edu.get('location','')}]"
        )
        notes = edu.get("notes", "")
        if notes:
            lines.append(f"    Note: {notes}")
    lines.append("")

    # Certifications
    lines.append("--- CERTIFICATIONS ---")
    for cert in profile.get("certifications", []):
        lines.append(
            f"  • {cert.get('name','')} — {cert.get('issuer','')} "
            f"({cert.get('date','')}) URL: {cert.get('url','')}"
        )
    lines.append("")

    # Projects
    lines.append("--- PROJECTS ---")
    for proj in profile.get("projects", []):
        lines.append(f"  • {proj.get('name','')}: {proj.get('description','')}")
        lines.append(f"    Stack: {', '.join(proj.get('tech_stack', []))}")
        for h in proj.get("highlights", []):
            lines.append(f"      – {h}")
        if proj.get("url"):
            lines.append(f"    URL: {proj['url']}")
    lines.append("")

    # Honors
    lines.append("--- HONORS & AWARDS ---")
    for honor in profile.get("honors", []):
        lines.append(f"  • {honor}")

    return "\n".join(lines)


# ── ResumeBuilder ─────────────────────────────────────────────

class ResumeBuilder:
    """Generate a complete, tailored LaTeX resume in a single LLM call.

    Args:
        profile_path: Path to candidate_profile.yaml. Defaults to the
                      project-standard location.
        llm_provider: Override the default LLM provider. Useful for testing.
        max_output_tokens: Token budget for the LLM output. Full LaTeX resume
                           is typically 2000-3000 tokens. Default 3500.
    """

    def __init__(
        self,
        profile_path: str | Path | None = None,
        llm_provider=None,
        max_output_tokens: int = 3500,
    ):
        self._profile_path = Path(profile_path) if profile_path else _PROFILE_PATH
        self._llm = llm_provider
        self._max_tokens = max_output_tokens

    def _get_llm(self):
        if self._llm is None:
            from src.llm.provider import get_llm_provider
            self._llm = get_llm_provider()
        return self._llm

    def _load_profile(self) -> dict:
        with open(self._profile_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def build(self, jd_text: str) -> str:
        """Generate a complete LaTeX resume tailored to the given JD.

        Args:
            jd_text: Full job description text.

        Returns:
            Complete LaTeX source string, ready to compile with tectonic/pdflatex.

        Raises:
            RuntimeError: If the LLM call fails or returns invalid output.
        """
        profile = self._load_profile()
        profile_text = _fmt_profile(profile)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            latex_preamble=_LATEX_PREAMBLE,
            profile_text=profile_text,
            jd_text=jd_text.strip(),
        )

        llm = self._get_llm()
        logger.info(
            f"Generating resume via {llm.__class__.__name__} "
            f"(max_tokens={self._max_tokens})"
        )

        response = llm.generate(
            prompt=user_prompt,
            max_tokens=self._max_tokens,
            system_prompt=SYSTEM_PROMPT,
        )

        tex = response.text.strip()
        tex = _strip_markdown_fences(tex)

        if not _looks_like_latex(tex):
            raise RuntimeError(
                f"LLM output does not look like valid LaTeX "
                f"(first 200 chars: {tex[:200]!r}). "
                f"Provider: {response.provider}, model: {response.model}."
            )

        logger.info(
            f"Resume generated — {response.tokens_used} tokens used "
            f"(provider={response.provider}, model={response.model})"
        )
        return tex

    def build_and_save(self, jd_text: str, output_path: str | Path) -> Path:
        """Generate resume and save to a .tex file.

        Args:
            jd_text: Full job description text.
            output_path: Path to write the .tex file.

        Returns:
            Path to the saved .tex file.
        """
        tex = self.build(jd_text)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(tex, encoding="utf-8")
        logger.info(f"Resume saved to {out}")
        return out


# ── Helpers ───────────────────────────────────────────────────

def _strip_markdown_fences(text: str) -> str:
    """Remove ```latex ... ``` or ``` ... ``` wrappers if the LLM added them."""
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _looks_like_latex(text: str) -> bool:
    """Sanity-check that the output starts with \\documentclass."""
    return text.lstrip().startswith(r"\documentclass")


# ── CLI entry point ───────────────────────────────────────────

def _main() -> None:
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Generate a tailored LaTeX resume from a job description."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--jd", metavar="FILE", help="Path to a .txt file containing the job description")
    group.add_argument("--jd-text", metavar="TEXT", help="Job description as a direct string argument")

    parser.add_argument(
        "--out",
        metavar="FILE",
        default="data/output/resume_tailored.tex",
        help="Output .tex file path (default: data/output/resume_tailored.tex)",
    )
    parser.add_argument(
        "--profile",
        metavar="FILE",
        default=None,
        help=f"Path to candidate_profile.yaml (default: {_PROFILE_PATH})",
    )
    parser.add_argument(
        "--provider",
        choices=["grok", "anthropic", "ollama", "openai", "stub"],
        default=None,
        help="Override LLM provider",
    )
    args = parser.parse_args()

    # Read JD
    if args.jd:
        jd_path = Path(args.jd)
        if not jd_path.exists():
            print(f"ERROR: JD file not found: {jd_path}", file=sys.stderr)
            sys.exit(1)
        jd_text = jd_path.read_text(encoding="utf-8")
    else:
        jd_text = args.jd_text

    # Optionally override provider
    llm_provider = None
    if args.provider:
        llm_provider = _get_provider_by_name(args.provider)

    builder = ResumeBuilder(
        profile_path=args.profile,
        llm_provider=llm_provider,
    )

    try:
        out_path = builder.build_and_save(jd_text, args.out)
        print(f"✓ Resume written to: {out_path}")
        print(f"  Compile with: tectonic {out_path}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def _get_provider_by_name(name: str):
    """Resolve a provider name string to an instance."""
    import os
    from src.llm.provider import (
        AnthropicProvider, GrokProvider, OllamaProvider,
        OpenAIProvider, StubProvider,
    )

    if name == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY env var not set")
        return AnthropicProvider(api_key=key)
    if name == "grok":
        key = os.environ.get("GROK_API_KEY", "")
        if not key:
            raise RuntimeError("GROK_API_KEY env var not set")
        return GrokProvider(api_key=key)
    if name == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("OPENAI_API_KEY env var not set")
        return OpenAIProvider(api_key=key)
    if name == "ollama":
        return OllamaProvider()
    return StubProvider()


if __name__ == "__main__":
    _main()
