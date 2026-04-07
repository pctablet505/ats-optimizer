"""LaTeX resume renderer — generates .tex files and compiles to PDF.

Uses Jinja2 with LaTeX-safe delimiters to render selected resume content
into a professional LaTeX document, then compiles with tectonic (bundled)
or pdflatex (if on PATH).

Template delimiter convention (avoids clash with LaTeX braces):
  Variables : (( variable ))
  Blocks    : (% if ... %), (% for ... %), (% endfor %), (% endif %)
  Comments  : (# comment #)
"""

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.generator.content_selector import SelectedContent

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
# Bundled tectonic binary (downloaded during setup)
_TECTONIC_BUNDLED = Path(__file__).resolve().parents[2] / "data" / "tools" / "tectonic.exe"


# ── LaTeX character escaping ──────────────────────────────────

# Characters that have special meaning in LaTeX and must be escaped in data values.
_LATEX_ESCAPE_MAP = [
    ("\\", r"\textbackslash{}"),  # must be first
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
    ("<", r"\textless{}"),
    (">", r"\textgreater{}"),
]

# These characters appear in URLs that are passed inside \href{}{} — they're
# already LaTeX-legal there, so URL fields get a lighter escaping pass.
_URL_ESCAPE_MAP = [
    ("%", r"\%"),
    ("#", r"\#"),
]


def latex_escape(text: str) -> str:
    """Escape a plain-text string for safe inclusion in a LaTeX document.

    Does NOT escape already-valid LaTeX markup (\\textbf etc.) — callers must
    pass raw profile / LLM text, not hand-crafted LaTeX.
    """
    if not text:
        return ""
    # Replace in safe order (backslash first, then the rest)
    for char, replacement in _LATEX_ESCAPE_MAP:
        text = text.replace(char, replacement)
    return text


def latex_escape_url(url: str) -> str:
    """Light escaping for URLs inside \\href{}."""
    if not url:
        return ""
    for char, replacement in _URL_ESCAPE_MAP:
        url = url.replace(char, replacement)
    return url


def _make_env() -> Environment:
    """Create a Jinja2 environment with LaTeX-safe delimiters."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        block_start_string="(%",
        block_end_string="%)",
        variable_start_string="((",
        variable_end_string="))",
        comment_start_string="(#",
        comment_end_string="#)",
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,  # We do our own escaping for LaTeX
    )
    # Register the escaping filters so templates can use (( x | le )) etc.
    env.filters["le"] = latex_escape          # latex_escape shorthand
    env.filters["latex_escape"] = latex_escape
    env.filters["url_escape"] = latex_escape_url
    return env


# ── Compiler detection ────────────────────────────────────────

def _find_tectonic() -> str | None:
    """Return path to tectonic binary or None."""
    if _TECTONIC_BUNDLED.exists():
        return str(_TECTONIC_BUNDLED)
    found = shutil.which("tectonic")
    return found  # may be None


def _find_pdflatex() -> str | None:
    return shutil.which("pdflatex")


def _compile_tex(tex_path: Path, output_dir: Path) -> Path:
    """Compile a .tex file to PDF. Returns PDF path.

    Tries tectonic first (no TeX distro needed), falls back to pdflatex.
    """
    tectonic = _find_tectonic()
    if tectonic:
        return _compile_with_tectonic(tectonic, tex_path, output_dir)

    pdflatex = _find_pdflatex()
    if pdflatex:
        return _compile_with_pdflatex(pdflatex, tex_path, output_dir)

    raise RuntimeError(
        "No LaTeX compiler found. Tectonic binary not at data/tools/tectonic.exe "
        "and pdflatex is not on PATH. Run: python -m src.cli setup to download tectonic."
    )


def _compile_with_tectonic(binary: str, tex_path: Path, output_dir: Path) -> Path:
    """Run tectonic to compile tex_path → PDF in output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        binary,
        "--outdir", str(output_dir),
        "--keep-logs",          # keep .log for debugging
        str(tex_path),
    ]
    logger.info(f"Compiling with tectonic: {tex_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        logger.error(f"Tectonic stderr:\n{result.stderr[-2000:]}")
        raise RuntimeError(f"tectonic failed (exit {result.returncode}): {result.stderr[-500:]}")

    pdf_path = output_dir / tex_path.with_suffix(".pdf").name
    if not pdf_path.exists():
        raise RuntimeError(f"Tectonic ran OK but PDF not found at {pdf_path}")
    return pdf_path


def _compile_with_pdflatex(binary: str, tex_path: Path, output_dir: Path) -> Path:
    """Run pdflatex twice (for cross-refs) to compile tex_path → PDF."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        binary,
        "-interaction=nonstopmode",
        f"-output-directory={output_dir}",
        str(tex_path),
    ]
    logger.info(f"Compiling with pdflatex: {tex_path.name}")
    for _ in range(2):   # run twice for reliable cross-references
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    pdf_path = output_dir / tex_path.with_suffix(".pdf").name
    if not pdf_path.exists() or result.returncode not in (0, 1):
        log_path = output_dir / tex_path.with_suffix(".log").name
        log_tail = log_path.read_text(errors="ignore")[-1500:] if log_path.exists() else ""
        raise RuntimeError(f"pdflatex failed:\n{log_tail}")
    return pdf_path


# ── Renderer class ────────────────────────────────────────────

class LatexRenderer:
    """Render a Resume to a professional LaTeX PDF.

    Args:
        template_name: Jinja2 LaTeX template file inside src/generator/templates/.
                       Defaults to 'classic.tex.jinja'.
    """

    def __init__(self, template_name: str = "classic.tex.jinja"):
        self.env = _make_env()
        self.template_name = template_name

    def render_tex(self, content: SelectedContent) -> str:
        """Render selected content to a LaTeX string."""
        template = self.env.get_template(self.template_name)
        return template.render(
            personal_info=content.personal_info,
            summary=content.summary,
            skills=content.skills,
            experience=content.experience,
            education=content.education,
            certifications=content.certifications,
            projects=content.projects,
            honors=content.honors,
        )

    def save_tex(self, content: SelectedContent, output_path: str | Path) -> Path:
        """Render and save .tex source to a file."""
        tex_str = self.render_tex(content)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tex_str, encoding="utf-8")
        logger.info(f"Saved .tex: {path}")
        return path

    def render_pdf(self, content: SelectedContent, output_path: str | Path) -> Path:
        """Render content to LaTeX and compile to PDF.

        The .tex source is saved alongside the PDF for inspection/editing.
        """
        pdf_path = Path(output_path)
        tex_path = pdf_path.with_suffix(".tex")
        output_dir = pdf_path.parent

        self.save_tex(content, tex_path)
        compiled_pdf = _compile_tex(tex_path, output_dir)

        # tectonic may name the output after the .tex stem, rename if needed
        if compiled_pdf != pdf_path:
            compiled_pdf.replace(pdf_path)
        return pdf_path


def generate_latex_resume(
    content: SelectedContent,
    output_dir: str | Path,
    job_id: str = "unknown",
    template: str = "classic.tex.jinja",
) -> dict:
    """High-level entry point: generate .tex + PDF for a job.

    Returns:
        Dict with 'tex' and 'pdf' keys pointing to the output files.
        On compile failure, 'pdf' is None and 'error' contains the message.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    renderer = LatexRenderer(template_name=template)

    # Always save the .tex — this has zero risk of failure
    tex_path = output_dir / f"resume_{job_id}.tex"
    renderer.save_tex(content, tex_path)

    pdf_path = output_dir / f"resume_{job_id}.pdf"
    try:
        renderer.render_pdf(content, pdf_path)
        logger.info(f"PDF generated: {pdf_path}")
        return {"tex": str(tex_path), "pdf": str(pdf_path)}
    except Exception as e:
        logger.error(f"PDF compilation failed for job {job_id}: {e}")
        return {"tex": str(tex_path), "pdf": None, "error": str(e)}
