from __future__ import annotations

import re
from typing import List

from .models import SequenceQuery


class QueryParseError(ValueError):
    """Raised when query text violates parsing/validation rules (e.g., too many wildcards)."""


def parse_query(
    text: str,
    *,
    min_match_length: int = 3,
    allow_subsequence: bool = False,
    max_wildcards: int = 3,
    max_wildcard_ratio: float = 0.5,
) -> SequenceQuery:
    """
    Parse a comma- or space-separated string of integers into SequenceQuery.
    Supports '?' or '*' as single-term wildcards.
    Enforces simple guards to avoid over-broad wildcard queries.
    """
    tokens = re.split(r"[,\s]+", text.strip())
    terms: List[int | None] = []
    for tok in tokens:
        if tok == "":
            continue
        if tok in {"?", "*"}:
            terms.append(None)
        else:
            try:
                terms.append(int(tok))
            except ValueError:
                continue

    wildcard_count = sum(1 for t in terms if t is None)
    if wildcard_count > 0:
        if wildcard_count > max_wildcards:
            raise QueryParseError(f"Too many wildcards ({wildcard_count}); max allowed is {max_wildcards}.")
        if wildcard_count / max(1, len(terms)) > max_wildcard_ratio:
            raise QueryParseError("Wildcard fraction too high; please reduce '?' or provide more concrete terms.")

    return SequenceQuery(terms=terms, min_match_length=min_match_length, allow_subsequence=allow_subsequence)
