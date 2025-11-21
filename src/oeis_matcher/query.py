from __future__ import annotations

import re
from typing import List

from .models import SequenceQuery


def parse_query(text: str, *, min_match_length: int = 3, allow_subsequence: bool = False) -> SequenceQuery:
    """
    Parse a comma- or space-separated string of integers into SequenceQuery.
    """
    tokens = re.split(r"[,\s]+", text.strip())
    terms: List[int] = []
    for tok in tokens:
        if tok == "" or tok in {"?", "*"}:
            # Skip placeholders for now; could support later.
            continue
        try:
            terms.append(int(tok))
        except ValueError:
            continue

    return SequenceQuery(terms=terms, min_match_length=min_match_length, allow_subsequence=allow_subsequence)
