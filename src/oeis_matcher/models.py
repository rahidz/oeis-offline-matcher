from dataclasses import dataclass, field
from fractions import Fraction
from typing import List, Optional, Union


@dataclass
class SequenceRecord:
    """Minimal representation of an OEIS sequence for matching."""

    id: str
    terms: List[int] = field(default_factory=list)
    length: int = 0
    name: Optional[str] = None
    keywords: Optional[List[str]] = None
    offset: Optional[tuple[int, int]] = None  # (offset_start, offset_second) from OEIS OFFSET
    formula: Optional[str] = None
    has_formula: Optional[bool] = None
    metadata: Optional[dict] = None

    def truncated(self, max_terms: int) -> "SequenceRecord":
        """Return a shallow copy truncated to the first `max_terms` terms."""
        return SequenceRecord(
            id=self.id,
            terms=self.terms[:max_terms],
            length=min(self.length, max_terms),
            name=self.name,
            keywords=self.keywords,
            offset=self.offset,
            formula=self.formula,
            has_formula=self.has_formula,
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
    keywords: Optional[list[str]] = None
    seq_offset: Optional[tuple[int, int]] = None
    formula: Optional[str] = None
    has_formula: Optional[bool] = None
    transformed_terms: Optional[list[int]] = None
    transform_desc: Optional[str] = None
    score: Optional[float] = None
    explanation: Optional[str] = None
    latex: Optional[str] = None
    symbolic: Optional[str] = None
    symbolic_latex: Optional[str] = None


@dataclass(frozen=True)
class CombinationMatch:
    ids: tuple[str, ...]
    names: tuple[Optional[str], ...]
    coeffs: tuple[Union[int, Fraction], ...]
    shifts: tuple[int, ...]
    length: int
    score: float
    expression: str
    component_transforms: Optional[tuple[str, ...]] = None
    latex_expression: Optional[str] = None
    component_terms: Optional[tuple[list[int], ...]] = None
    combined_terms: Optional[list[int]] = None
    candidate_provenance: Optional[tuple[tuple[str, ...], ...]] = None


@dataclass
class AnalysisResult:
    query: list[int]
    exact_matches: list[Match]
    transform_matches: list[Match]
    similarity: list[dict]
    combinations: list[CombinationMatch]
    triple_combinations: list[CombinationMatch] | None = None
    pointwise_combinations: list[CombinationMatch] | None = None
    convolution_combinations: list[CombinationMatch] | None = None
    diagnostics: Optional[dict] = None

    def to_dict(self) -> dict:
        from dataclasses import asdict

        def _coeffs_to_json(coeffs):
            out = []
            for c in coeffs:
                try:
                    from fractions import Fraction
                    if isinstance(c, Fraction) and c.denominator != 1:
                        out.append(f"{c.numerator}/{c.denominator}")
                        continue
                except Exception:
                    pass
                if isinstance(c, (int, float)) and float(c).is_integer():
                    out.append(str(int(c)))
                else:
                    out.append(str(c))
            return out

        def _combo_to_dict(m):
            d = asdict(m)
            d["coeffs"] = _coeffs_to_json(m.coeffs)
            return d

        # asdict cannot handle non-serializable nested SequenceRecord; we already flatten similarity to dicts.
        diag = self.diagnostics or {}
        return {
            "query": self.query,
            "exact_matches": [asdict(m) for m in self.exact_matches],
            "transform_matches": [asdict(m) for m in self.transform_matches],
            "similarity": self.similarity,
            "combinations": [_combo_to_dict(m) for m in self.combinations],
            "triple_combinations": [_combo_to_dict(m) for m in self.triple_combinations] if self.triple_combinations is not None else [],
            "pointwise_combinations": [_combo_to_dict(m) for m in self.pointwise_combinations] if self.pointwise_combinations is not None else [],
            "convolution_combinations": [_combo_to_dict(m) for m in self.convolution_combinations] if self.convolution_combinations is not None else [],
            "diagnostics": diag,
        }
