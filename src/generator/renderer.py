"""Resume renderer — generates HTML and PDF from selected content.

Uses Jinja2 for HTML templating. PDF rendering is optional and requires
WeasyPrint (falls back to HTML-only if not installed).
"""

from dataclasses import asdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.generator.content_selector import SelectedContent


TEMPLATES_DIR = Path(__file__).parent / "templates"


class ResumeRenderer:
    """Render resumes from selected content using Jinja2 templates."""

    def __init__(self, template_name: str = "classic.html"):
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=True,
        )
        self.template_name = template_name

    def render_html(self, content: SelectedContent) -> str:
        """Render selected content to HTML string.

        Args:
            content: The selected resume content.

        Returns:
            Complete HTML string ready for saving or PDF conversion.
        """
        template = self.env.get_template(self.template_name)

        html = template.render(
            personal_info=content.personal_info,
            summary=content.summary,
            skills=content.skills,
            experience=content.experience,
            education=content.education,
            certifications=content.certifications,
            projects=content.projects,
        )
        return html

    def save_html(self, content: SelectedContent, output_path: str | Path) -> Path:
        """Render and save HTML to a file.

        Args:
            content: The selected resume content.
            output_path: Where to save the HTML file.

        Returns:
            Path to the saved file.
        """
        html = self.render_html(content)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return path

    def render_pdf(self, content: SelectedContent, output_path: str | Path) -> Path:
        """Render selected content to PDF using WeasyPrint.

        Args:
            content: The selected resume content.
            output_path: Where to save the PDF file.

        Returns:
            Path to the saved PDF file.

        Raises:
            ImportError: If WeasyPrint is not installed.
        """
        try:
            from weasyprint import HTML
        except ImportError:
            raise ImportError(
                "WeasyPrint is required for PDF generation. "
                "Install it with: pip install weasyprint"
            )

        html_str = self.render_html(content)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        HTML(string=html_str).write_pdf(str(path))
        return path


def generate_resume(
    content: SelectedContent,
    output_dir: str | Path,
    job_id: str = "unknown",
    template: str = "classic.html",
    pdf: bool = False,
) -> dict:
    """High-level function to generate a resume.

    Args:
        content: Selected content from ContentSelector.
        output_dir: Directory to save generated files.
        job_id: Identifier for naming files.
        template: Which template to use.
        pdf: Whether to also generate PDF.

    Returns:
        Dict with paths: {"html": Path, "pdf": Path | None}
    """
    renderer = ResumeRenderer(template_name=template)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / f"resume_{job_id}.html"
    renderer.save_html(content, html_path)

    pdf_path = None
    if pdf:
        try:
            pdf_path = output_dir / f"resume_{job_id}.pdf"
            renderer.render_pdf(content, pdf_path)
        except ImportError:
            pdf_path = None  # WeasyPrint not available

    return {"html": html_path, "pdf": pdf_path}
