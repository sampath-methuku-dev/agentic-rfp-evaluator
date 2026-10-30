"""PDF to clean text."""
import io
import re

from langchain_community.document_loaders.parsers import PyPDFParser
from langchain_core.documents.base import Blob
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from src.config import MAX_DOC_CHARS, MAX_PDF_BYTES, MAX_PDF_PAGES, MIN_DOC_CHARS


class DocumentError(Exception):
    """The PDF cannot be used (unreadable, encrypted, or no extractable text)."""


def extract_text(pdf_bytes: bytes) -> tuple[str, list[str]]:
    """Return (clean text, warnings). Raises DocumentError if unusable."""
    warnings: list[str] = []
    if b"%PDF-" not in pdf_bytes[:1024]:
        raise DocumentError("The file is not a PDF (no PDF header); it may be another format renamed to .pdf.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise DocumentError(f"The PDF is larger than {MAX_PDF_BYTES // (1024 * 1024)} MB.")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            raise DocumentError("The PDF is password protected.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentError(f"The PDF has {len(reader.pages)} pages; the maximum is {MAX_PDF_PAGES}.")
        # LangChain's PDF parser does the text extraction; pypdf is only used for the checks above.
        pages = [doc.page_content for doc in PyPDFParser().lazy_parse(Blob.from_data(pdf_bytes))]
    except DocumentError:
        raise
    except (PyPdfError, ValueError, OSError, KeyError) as exc:
        raise DocumentError(f"The file could not be read as a PDF ({type(exc).__name__}).") from exc

    text = "\n\n".join(pages)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    if len(text) < MIN_DOC_CHARS:
        raise DocumentError(
            "No usable text found (the PDF may be scanned images). OCR is not supported.")
    if len(text) > MAX_DOC_CHARS:
        warnings.append(
            f"Proposal text truncated from {len(text):,} to {MAX_DOC_CHARS:,} characters.")
        text = text[:MAX_DOC_CHARS]
    return text, warnings
