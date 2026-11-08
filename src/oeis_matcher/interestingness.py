"""Deterministic, uncalibrated research-priority and notability scores (0..100).

Discovery = (55*savings + 25*holdout/(holdout+3)) * nontriviality
            * crowding_weight + 20*max(0, min(domain_count-1, 3))/3.
Savings and prediction points require a complete held-out match; domain-hint
points require at least two detected domains. The cheapest training-fitting
model is selected before inspecting the holdout, including when it fails.
For validated nontrivial models with a supplied 16-term affine-prefix relative
count c, crowding_weight = 1/(1+min(log2(1+c)/8, .5)); otherwise it is 1.
These are exact affine-equivalent stored prefixes, not global duplications.
The adjustment discounts only structure points, never textual domain hints.
Savings = max(0, 1-description_bits/literal_bits), using signed integer codes
of 2*bit_length(abs(n))+2 bits. This coding-cost estimate includes parameters,
initial values, and an 8-bit family tag; rational parameters cost numerator
plus denominator, including denominator 1. It is not an actual bitstream.
Nontriviality is .25 for constant/linear/geometric models and 1 otherwise.
All models are fitted on the first two thirds of at most 48 terms; at least
three untouched terms must all match. Families tried: degree<=4 polynomials,
order<=3 homogeneous rational recurrences, and affine rational term ratios.
These are bounded probes, not a test of all possible mathematical structure.

Notability = 45*core + 10*nice + 30*log1p(inbound)/log(1001)
             + 10*log1p(reference_lines)/log(16)
             + 5*log1p(link_lines)/log(16), each log component capped at 1.
Balanced is their arithmetic mean. Missing metadata contributes no points,
but coverage is reported separately from an observed zero. Domain words are
connection hints, not verified independent interpretations; novelty relative
to the OEIS corpus is unknown. Scores are not probabilities or percentiles.
"""

from __future__ import annotations

import math
import re
from fractions import Fraction
from itertools import pairwise

SCORING_VERSION = "3"

DOMAINS = {
    "combinatorics": r"\b(?:permutations?|partitions?|combinations?|polyomino\w*|tilings?|trees?|graphs?)\b",
    "number theory": r"\b(?:primes?|divisors?|totient|modular|congruences?|factorizations?)\b",
    "algebra": r"\b(?:groups?|rings?|fields?|matrices|determinants?|polynomials?)\b",
    "geometry": r"\b(?:lattices?|polygons?|polyhedr\w*|triangles?|spheres?|dimensions?)\b",
    "analysis": r"\b(?:integrals?|differential|continued fractions?|transcendental|Bessel)\b",
    "computing": r"\b(?:algorithms?|automata|computers?|programs?|sorting|complexity)\b",
    "physics": r"\b(?:Ising|quantum|particles?|Hamiltonian|statistical mechanics)\b",
}
DOMAIN_PATTERNS = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in DOMAINS.items()}


def _bits(value: int | Fraction) -> int:
    if isinstance(value, Fraction):
        return _bits(value.numerator) + _bits(value.denominator)
    return 2 * abs(value).bit_length() + 2


def _solve(matrix: list[list[int]], rhs: list[int]) -> list[Fraction] | None:
    rows = [[Fraction(value) for value in row] + [Fraction(value)] for row, value in zip(matrix, rhs)]
    size = len(rhs)
    for col in range(size):
        pivot = next((i for i in range(col, size) if rows[i][col]), None)
        if pivot is None:
            return None
        rows[col], rows[pivot] = rows[pivot], rows[col]
        divisor = rows[col][col]
        rows[col] = [value / divisor for value in rows[col]]
        for i in range(size):
            if i != col:
                factor = rows[i][col]
                rows[i] = [a - factor * b for a, b in zip(rows[i], rows[col])]
    return [row[-1] for row in rows]


def _models(train: list[int], count: int):
    for degree in range(min(4, len(train) - 3) + 1):
        differences, initial = train[:], []
        for _ in range(degree + 1):
            initial.append(differences[0])
            differences = [b - a for a, b in pairwise(differences)]
        if not all(value == 0 for value in differences):
            continue
        generated = []
        state = initial[:]
        for _ in range(count):
            generated.append(state[0])
            for j in range(degree):
                state[j] += state[j + 1]
        yield f"polynomial degree {degree}", initial, generated, degree <= 1

    for order in range(1, min(3, (len(train) - 2) // 2) + 1):
        # First nonsingular training window determines the parameters; the rest
        # of the training prefix and every held-out term must agree exactly.
        coefficients = None
        for start in range(order, len(train) - order + 1):
            matrix = [[train[i - j - 1] for j in range(order)] for i in range(start, start + order)]
            coefficients = _solve(matrix, train[start:start + order])
            if coefficients is not None:
                break
        if coefficients is None or any(abs(c.numerator).bit_length() > 64 or c.denominator.bit_length() > 64 for c in coefficients):
            continue
        generated = train[:order]
        for i in range(order, count):
            value = sum(c * generated[i - j - 1] for j, c in enumerate(coefficients))
            if value.denominator != 1 or abs(value.numerator).bit_length() > 8192:
                break
            generated.append(int(value))
        if generated[:len(train)] == train:
            yield f"linear recurrence order {order}", [*coefficients, *train[:order]], generated, order == 1

    ratios = [(i, Fraction(train[i + 1], train[i])) for i in range(len(train) - 1) if train[i]]
    if len(ratios) >= 3:
        (i, a), (j, b) = ratios[:2]
        slope = (b - a) / (j - i)
        intercept = a - slope * i
        if all(ratio == slope * i + intercept for i, ratio in ratios):
            generated = [train[0]]
            for i in range(count - 1):
                value = generated[-1] * (slope * i + intercept)
                if value.denominator != 1 or abs(value.numerator).bit_length() > 8192:
                    break
                generated.append(int(value))
            if generated[:len(train)] == train:
                yield "affine term ratio", [slope, intercept, train[0]], generated, slope == 0


def score_sequence(record: dict) -> dict:
    terms = record.get("terms", [])[:48]
    train_count = len(terms) * 2 // 3
    holdout_count = len(terms) - train_count
    literal_bits = sum(_bits(value) for value in terms)
    structure = {
        "model": None, "parameters": [], "train_terms": train_count,
        "holdout_terms": holdout_count, "holdout_passed": 0,
        "validated": False, "literal_bits": literal_bits,
        "description_bits": None, "savings": 0.0,
        "status": "insufficient terms" if len(terms) < 9 else "no tested model fits",
    }
    savings = validation = 0.0
    nontriviality = 1.0
    if len(terms) >= 9 and all(abs(value).bit_length() <= 4096 for value in terms):
        candidates = []
        for name, parameters, generated, trivial in _models(terms[:train_count], len(terms)):
            cost = 8 + sum(_bits(value) for value in parameters)
            candidates.append((cost, name, parameters, generated, trivial))
        if candidates:
            cost, name, parameters, generated, trivial = min(candidates, key=lambda model: model[:2])
            passed = sum(a == b for a, b in zip(generated[train_count:], terms[train_count:]))
            failed = len(generated) != len(terms) or passed != holdout_count
            savings = max(0.0, 1.0 - cost / literal_bits) if not failed and literal_bits else 0.0
            validation = holdout_count / (holdout_count + 3) if not failed else 0.0
            nontriviality = .25 if trivial else 1.0
            structure.update(
                model=name, parameters=[str(value) for value in parameters],
                holdout_passed=passed, validated=not failed, description_bits=cost,
                savings=round(savings, 4), status="validated on held-out terms" if not failed else "held-out prediction failed",
            )
    elif len(terms) >= 9:
        structure["status"] = "terms exceed 4096-bit probe limit"

    text = "\n".join(record.get(key) or "" for key in ("name", "comments", "formula"))
    families = [name for name, pattern in DOMAIN_PATTERNS.items() if pattern.search(text)]
    connections = max(0, min(len(families) - 1, 3)) / 3
    relatives = record.get("affine_prefix_relatives")
    prefix_terms = record.get("affine_prefix_terms")
    crowding_weight = 1.0
    if structure["validated"] and nontriviality == 1 and relatives is not None and prefix_terms == 16:
        crowding_weight = 1 / (1 + min(math.log2(1 + relatives) / 8, .5))
    discovery = (55 * savings + 25 * validation) * nontriviality * crowding_weight + 20 * connections

    keywords = set(record.get("keywords") or [])
    components = {"core": 45.0 if "core" in keywords else 0.0, "nice": 10.0 if "nice" in keywords else 0.0}
    for key, weight, cap in (("inbound_links", 30, 1000), ("references", 10, 15), ("links", 5, 15)):
        value = record.get(key)
        count = max(0, value) if key == "inbound_links" and value is not None else len([line for line in (value or "").splitlines() if line.strip()])
        components[key] = round(weight * min(1.0, math.log1p(count) / math.log1p(cap)), 4)
    notability = sum(components.values())
    discovery, notability = round(min(100, discovery), 2), round(min(100, notability), 2)
    return {
        "discovery": discovery, "notability": notability,
        "balanced": round((discovery + notability) / 2, 2),
        "evidence": {
            "structure": structure,
            "connections": {"families": families, "status": "textual domain hints, not proven independent connections"},
            "novelty": {
                "corpus_novelty": "unknown", "nontriviality_weight": nontriviality,
                "affine_prefix_relatives": relatives, "affine_prefix_terms": prefix_terms,
                "crowding_weight": round(crowding_weight, 4),
                "status": "exact affine-equivalent stored prefixes, not proof of global duplication" if relatives is not None else "affine-prefix crowding unknown",
            },
            "notability": {"components": components, "coverage": {key: record.get(key) is not None for key in ("keywords", "inbound_links", "references", "links")}},
        },
    }
