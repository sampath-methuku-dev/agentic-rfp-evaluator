from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Criterion:
    criterion_id: int
    name: str
    description: str
    weight: float
    max_score: float


@dataclass(frozen=True)
class SupplierUpload:
    """One uploaded proposal plus the metadata the user typed in."""
    supplier_name: str
    submission_date: date
    experience_rating: float
    filename: str
    pdf_bytes: bytes
