"""Checks on what the user supplies, before any LLM call.

Hard problems (not a PDF, no text, clearly not an RFP response) exclude that file with a
reason. Soft problems (some expected sections missing) keep the file, flag the gap in the
results and tell the model which sections are absent.
"""
import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import date

from src.config import MAX_NAME_LENGTH, MAX_SUPPLIERS, MIN_SECTIONS_FOUND
from src.models import SupplierUpload
from src.tools.document_tool import DocumentError, extract_text

# The proposal template the app expects: six sections, each recognised by any keyword.
SECTION_PATTERNS = {
    "Executive summary": r"executive summary|understanding of (the )?(requirement|rfp|need)",
    "Proposed solution": r"proposed solution|implementation approach|architecture|solution",
    "Timeline and milestones": r"timeline|milestone|schedule|delivery plan",
    "Pricing": r"\bprice\b|pricing|\bcosts?\b|\bfees?\b|\busd\b|\$",
    "Security and compliance": r"security|compliance|iso 27001|soc 2|gdpr|privacy",
    "Support and experience": r"support|references?|experience|\bsla\b",
}


@dataclass
class FileReport:
    status: str                      # "ok" | "warning" | "rejected"
    text: str = ""
    messages: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    sections_found: int = 0


def check_template(text: str) -> tuple[int, list[str]]:
    """Return (number of expected sections found, names of the missing ones)."""
    lowered = text.lower()
    missing = [name for name, pattern in SECTION_PATTERNS.items() if not re.search(pattern, lowered)]
    return len(SECTION_PATTERNS) - len(missing), missing


def inspect_pdf(pdf_bytes: bytes) -> FileReport:
    """Readability plus template check for one uploaded file."""
    try:
        text, notes = extract_text(pdf_bytes)
    except DocumentError as exc:
        return FileReport("rejected", messages=[str(exc)])

    found, missing = check_template(text)
    if found < MIN_SECTIONS_FOUND:
        return FileReport(
            "rejected", messages=[
                f"Does not look like an RFP response: only {found} of {len(SECTION_PATTERNS)} "
                f"expected sections found (missing: {', '.join(missing)})."],
            missing_sections=missing, sections_found=found)
    if missing or notes:
        messages = list(notes)
        if missing:
            messages.append(f"Expected sections not found: {', '.join(missing)}. "
                            "Criteria that depend on them will likely score low.")
        return FileReport("warning", text, messages, missing, found)
    return FileReport("ok", text, [], [], found)


def fingerprint(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def validate_metadata(name: str, submission_date, rating, today: date | None = None
                      ) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for one supplier's typed-in details."""
    errors, warnings = [], []
    clean = (name or "").strip()
    if not clean:
        errors.append("Supplier name is required.")
    elif len(clean) > MAX_NAME_LENGTH:
        errors.append(f"Supplier name is longer than {MAX_NAME_LENGTH} characters.")
    elif not clean.isprintable():
        errors.append("Supplier name contains control characters.")

    if not isinstance(submission_date, date):
        errors.append("Submission date is required.")
    elif submission_date > (today or date.today()):
        warnings.append(f"Submission date {submission_date.isoformat()} is in the future.")

    try:
        number = float(rating)
    except (TypeError, ValueError):
        number = math.nan
    if not math.isfinite(number) or not 0 <= number <= 10:
        errors.append("Experience rating must be a number from 0 to 10.")
    return errors, warnings


def validate_batch(uploads: list[SupplierUpload]) -> list[str]:
    """Problems that involve several uploads together (all are blocking)."""
    errors = []
    if not uploads:
        return ["No supplier proposals were provided."]
    if len(uploads) > MAX_SUPPLIERS:
        errors.append(f"Too many proposals: {len(uploads)} provided, maximum is {MAX_SUPPLIERS}.")
    seen_names: dict[str, str] = {}
    seen_files: dict[str, str] = {}
    for u in uploads:
        key = u.supplier_name.strip().casefold()
        if key in seen_names:
            errors.append(f"Supplier name '{u.supplier_name}' is used more than once.")
        seen_names[key] = u.filename
        digest = fingerprint(u.pdf_bytes)
        if digest in seen_files:
            errors.append(f"'{u.filename}' has the same content as '{seen_files[digest]}'.")
        seen_files[digest] = u.filename
    return errors
