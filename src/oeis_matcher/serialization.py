from __future__ import annotations

from dataclasses import asdict
from fractions import Fraction

from .models import AnalysisResult, CombinationMatch, Match


SCHEMA_VERSION = 1


def format_coefficient(value) -> str:
    if isinstance(value, Fraction) and value.denominator != 1:
        return f"{value.numerator}/{value.denominator}"
    if isinstance(value, (int, float)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def match_to_dict(match: Match, *, show_formula: bool = True) -> dict:
    row = asdict(match)
    if match.seq_offset is not None:
        row["seq_offset"] = list(match.seq_offset)
    if match.transform_desc:
        row["transform"] = match.transform_desc
    if match.snippet is not None:
        row["terms"] = match.snippet
    if not show_formula:
        row.pop("formula", None)
    return row


def combination_to_dict(match: CombinationMatch) -> dict:
    row = asdict(match)
    row["ids"] = list(match.ids)
    row["names"] = list(match.names)
    row["coeffs"] = [format_coefficient(c) for c in match.coeffs]
    row["shifts"] = list(match.shifts)
    if match.component_transforms is not None:
        row["component_transforms"] = list(match.component_transforms)
    if match.component_terms is not None:
        row["component_terms"] = [list(terms) for terms in match.component_terms]
    if match.candidate_provenance is not None:
        row["candidate_provenance"] = [list(reasons) for reasons in match.candidate_provenance]
    return row


def explanation_to_dict(family: str, match: Match | CombinationMatch, *, show_formula: bool = True) -> dict:
    if family == "transform":
        return {"family": family, **match_to_dict(match, show_formula=show_formula)}
    return {"family": family, **combination_to_dict(match)}


def analysis_to_dict(result: AnalysisResult, *, show_formula: bool = True) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "query": result.query,
        "exact_matches": [match_to_dict(m, show_formula=show_formula) for m in result.exact_matches],
        "transform_matches": [match_to_dict(m, show_formula=show_formula) for m in result.transform_matches],
        "similarity": result.similarity,
        "combinations": [combination_to_dict(m) for m in result.combinations],
        "triple_combinations": [combination_to_dict(m) for m in result.triple_combinations or ()],
        "modclass_combinations": [combination_to_dict(m) for m in result.modclass_combinations or ()],
        "pointwise_combinations": [combination_to_dict(m) for m in result.pointwise_combinations or ()],
        "convolution_combinations": [combination_to_dict(m) for m in result.convolution_combinations or ()],
        "combined_combinations": [explanation_to_dict(f, m) for f, m in result.combined_combinations or ()],
        "ranked_explanations": [
            explanation_to_dict(f, m, show_formula=show_formula) for f, m in result.ranked_explanations or ()
        ],
        "diagnostics": result.diagnostics or {},
    }
