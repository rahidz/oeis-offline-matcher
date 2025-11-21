from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SequenceRecord:
    """Minimal representation of an OEIS sequence for matching."""

    id: str
    terms: List[int] = field(default_factory=list)
    length: int = 0
    name: Optional[str] = None
    metadata: Optional[dict] = None

    def truncated(self, max_terms: int) -> "SequenceRecord":
        """Return a shallow copy truncated to the first `max_terms` terms."""
        return SequenceRecord(
            id=self.id,
            terms=self.terms[:max_terms],
            length=min(self.length, max_terms),
            name=self.name,
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class SequenceQuery:
    terms: List[int]
    min_match_length: int = 3
    allow_subsequence: bool = False


@dataclass(frozen=True)
class Match:
    id: str
    name: Optional[str]
    match_type: str  # "prefix" or "subsequence"
    offset: int
    length: int
    snippet: Optional[list[int]] = None
    transform_desc: Optional[str] = None
    score: Optional[float] = None
