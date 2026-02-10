"""Resume import parser — extract text from PDF/DOCX files."""

from pathlib import Path


def extract_text_from_pdf(file_path: str | Path) -> str:
    """Extract raw text from a PDF file using pdfminer.six.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text as a single string.
    """
    from pdfminer.high_level import extract_text

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {path.suffix}")

    return extract_text(str(path)).strip()


def extract_text_from_docx(file_path: str | Path) -> str:
    """Extract raw text from a DOCX file using python-docx.

    Args:
        file_path: Path to the DOCX file.

    Returns:
        Extracted text, paragraphs joined by newlines.
    """
    import docx

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"DOCX file not found: {path}")
    if path.suffix.lower() != ".docx":
        raise ValueError(f"Expected a .docx file, got: {path.suffix}")

    doc = docx.Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_text(file_path: str | Path) -> str:
    """Extract text from a file based on its extension.

    Supports .pdf and .docx files.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    elif suffix == ".docx":
        return extract_text_from_docx(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Supported: .pdf, .docx")
