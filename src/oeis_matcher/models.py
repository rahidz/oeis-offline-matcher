from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SequenceRecord:
    """Minimal representation of an OEIS sequence for matching."""

    id: str
    terms: List[int] = field(default_factory=list)
    length: int = 0
    name: Optional[str] = None
    keywords: Optional[List[str]] = None
    metadata: Optional[dict] = None

    def truncated(self, max_terms: int) -> "SequenceRecord":
        """Return a shallow copy truncated to the first `max_terms` terms."""
        return SequenceRecord(
            id=self.id,
            terms=self.terms[:max_terms],
            length=min(self.length, max_terms),
            name=self.name,
            keywords=self.keywords,
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class SequenceQuery:
    terms: List[int | None]
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
    transformed_terms: Optional[list[int]] = None
    transform_desc: Optional[str] = None
    score: Optional[float] = None
    explanation: Optional[str] = None
    latex: Optional[str] = None


@dataclass(frozen=True)
class CombinationMatch:
    ids: tuple[str, ...]
    names: tuple[Optional[str], ...]
    coeffs: tuple[int, ...]
    shifts: tuple[int, ...]
    length: int
    score: float
    expression: str
    component_transforms: Optional[tuple[str, ...]] = None
    latex_expression: Optional[str] = None
    component_terms: Optional[tuple[list[int], ...]] = None
    combined_terms: Optional[list[int]] = None


@dataclass
class AnalysisResult:
    query: list[int]
    exact_matches: list[Match]
    transform_matches: list[Match]
    similarity: list[dict]
    combinations: list[CombinationMatch]
    triple_combinations: list[CombinationMatch] | None = None
    diagnostics: Optional[dict] = None

    def to_dict(self) -> dict:
        from dataclasses import asdict

        # asdict cannot handle non-serializable nested SequenceRecord; we already flatten similarity to dicts.
        return {
            "query": self.query,
            "exact_matches": [asdict(m) for m in self.exact_matches],
            "transform_matches": [asdict(m) for m in self.transform_matches],
            "similarity": self.similarity,
            "combinations": [asdict(m) for m in self.combinations],
            "triple_combinations": [asdict(m) for m in self.triple_combinations] if self.triple_combinations is not None else [],
            "diagnostics": self.diagnostics or {},
        }
