"""Offline catalog search. Filter first, rank the entire result set, then paginate."""
from __future__ import annotations

import heapq
import json
import math
import re
import shlex
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from .interestingness import SCORING_VERSION, score_sequence

RANKINGS = ("discovery", "notability", "balanced")
FIELDS = {"name": "s.name", "formula": "s.formula", "comment": "m.comments",
          "reference": "m.references_text", "link": "m.links", "related": "m.crossrefs"}
NUMBER_LIST = re.compile(r"[+-]?\d+(?:[\s,]+(?:[+-]?\d+|\?))*|\?(?:[\s,]+(?:[+-]?\d+|\?))*")


def _where(query: str) -> tuple[str, list]:
    query = query.strip()
    if not query:
        raise ValueError("Enter a search query, or * to browse all sequences.")
    if query == "*":
        return "1", []
    if NUMBER_LIST.fullmatch(query):
        query = "terms:" + ",".join(query.replace(",", " ").split())
    tokens = shlex.split(query)
    groups, clauses, params = [], [], []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if token == "OR":
            if not clauses:
                raise ValueError("OR needs a query on each side.")
            groups.append(" AND ".join(clauses))
            clauses = []
            continue
        negate = token.startswith("-")
        if negate:
            token = token[1:]
        field, sep, value = token.partition(":")
        if sep:
            field = field.lower()
            if not value and i < len(tokens) and tokens[i] != "OR":
                value = tokens[i]
                i += 1
            if not value:
                raise ValueError(f"{field}: needs a value.")
        else:
            value = token
            field = "id" if re.fullmatch(r"[aA]\d{6}", value) else "text"
        if field in FIELDS or field == "text":
            columns = list(FIELDS.values()) + ["s.id"] if field == "text" else [FIELDS[field]]
            clause = "(" + " OR ".join(f"instr(lower(coalesce({col},'')),?)>0" for col in columns) + ")"
            params.extend([value.lower()] * len(columns))
        elif field == "id":
            ids = value.upper().split(",")
            if not all(re.fullmatch(r"A\d{6}", item) for item in ids):
                raise ValueError("id: expects A-numbers, optionally comma-separated.")
            clause = f"s.id IN ({','.join('?' for _ in ids)})"
            params.extend(ids)
        elif field == "keyword":
            tags = value.lower().split(",")
            if not all(re.fullmatch(r"[a-z]+", tag) for tag in tags):
                raise ValueError("keyword: expects tags, optionally comma-separated (all required).")
            clause = "(" + " AND ".join("instr(','||lower(coalesce(s.keywords,''))||',',?)>0" for _ in tags) + ")"
            params.extend(f",{tag}," for tag in tags)
        elif field in {"terms", "prefix"}:
            if not NUMBER_LIST.fullmatch(value):
                raise ValueError(f"{field}: expects comma-separated integers or ? wildcards.")
            terms = [str(int(t)) if t != "?" else t for t in value.replace(",", " ").split()]
            if "?" in terms:
                pattern = ("^," if field == "prefix" else ",") + ",".join(r"-?\d+" if t == "?" else re.escape(t) for t in terms) + ","
                clause = "regexp(?, ','||s.terms||',')"
                params.append(pattern)
            else:
                clause = "instr(','||s.terms||',',?)" + ("=1" if field == "prefix" else ">0")
                params.append("," + ",".join(terms) + ",")
        elif field in {"minterms", "maxterms"}:
            if not value.isdigit():
                raise ValueError(f"{field}: expects a nonnegative integer.")
            clause = "s.length" + (">=?" if field == "minterms" else "<=?")
            params.append(int(value))
        elif field == "has" and value.lower() == "formula":
            clause = "coalesce(s.formula,'')<>''"
        else:
            raise ValueError(f"Unknown search field {field!r}. Use name, formula, comment, reference, link, related, id, keyword, terms, prefix, minterms, maxterms, or has:formula.")
        clauses.append(f"NOT ({clause})" if negate else clause)
    if not clauses:
        raise ValueError("OR needs a query on each side.")
    groups.append(" AND ".join(clauses))
    return " OR ".join(f"({group})" for group in groups), params


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.create_function("regexp", 2, lambda pattern, text: bool(re.search(pattern, text)))
    return conn


def _source(conn: sqlite3.Connection) -> tuple[str, bool]:
    enriched = conn.execute("SELECT 1 FROM sqlite_master WHERE name='search_metadata' AND type='table'").fetchone() is not None
    if enriched:
        return "sequences s LEFT JOIN search_metadata m ON m.id=s.id", True
    return "sequences s LEFT JOIN (SELECT NULL id, NULL comments, NULL references_text, NULL links, NULL crossrefs, NULL inbound_links) m ON 0", False


def _record(row: sqlite3.Row) -> dict:
    record = dict(row)
    record["terms"] = [int(t) for t in record["terms"].split(",") if t]
    record["keywords"] = record["keywords"].split(",") if record["keywords"] is not None else None
    record["references"] = record.pop("references_text")
    return record


SELECT = "s.id,s.name,s.terms,s.keywords,s.formula,m.comments,m.references_text,m.links,m.crossrefs,m.inbound_links"


def _affine_key(terms: list[int]) -> tuple[int, ...] | None:
    if len(terms) < 16 or any(abs(t).bit_length() > 4096 for t in terms[:16]):
        return None
    differences = [t - terms[0] for t in terms[1:16]]
    divisor = math.gcd(*differences)
    if not divisor:
        return (0,) * 15
    if next(t for t in differences if t) < 0:
        divisor = -divisor
    return tuple(t // divisor for t in differences)


def _affine_counts(conn: sqlite3.Connection) -> Counter:
    counts = Counter()
    for (text,) in conn.execute("SELECT terms FROM sequences"):
        key = _affine_key([int(t) for t in text.split(",", 16)[:16] if t])
        if key is not None:
            counts[key] += 1
    return counts


def _score(record: dict, affine_counts: Counter) -> dict:
    key = _affine_key(record["terms"])
    if key is not None:
        record["affine_prefix_relatives"] = affine_counts[key] - 1
        record["affine_prefix_terms"] = 16
    return score_sequence(record)


def build_search_profiles(db_path: Path) -> dict:
    """Explicit preprocessing; search itself never writes to the catalog."""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        source, enriched = _source(conn)
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            affine_counts = _affine_counts(conn)
            conn.execute("CREATE TABLE IF NOT EXISTS search_profiles (id TEXT PRIMARY KEY, discovery REAL, notability REAL, balanced REAL, evidence TEXT, version TEXT)")
            conn.execute("DELETE FROM search_profiles")
            count = 0
            batch = []
            for row in conn.execute(f"SELECT {SELECT} FROM {source} ORDER BY s.id"):
                scores = _score(_record(row), affine_counts)
                batch.append((row["id"], *(scores[key] for key in RANKINGS), json.dumps(scores["evidence"], separators=(",", ":")), SCORING_VERSION))
                count += 1
                if len(batch) == 1000:
                    conn.executemany("INSERT INTO search_profiles VALUES (?,?,?,?,?,?)", batch)
                    batch.clear()
            conn.executemany("INSERT INTO search_profiles VALUES (?,?,?,?,?,?)", batch)
            for ranking in RANKINGS:
                conn.execute(f"CREATE INDEX IF NOT EXISTS search_rank_{ranking} ON search_profiles({ranking} DESC,id)")
            for action in ("INSERT", "UPDATE", "DELETE"):
                conn.execute(f"DROP TRIGGER IF EXISTS search_profiles_{action.lower()}")
                # Affine-relative counts depend on other catalog entries too.
                conn.execute(f"CREATE TRIGGER search_profiles_{action.lower()} AFTER {action} ON sequences BEGIN DELETE FROM search_profiles; END")
            if enriched:
                for action in ("INSERT", "UPDATE", "DELETE"):
                    # Changing an inbound edge can affect another entry's score.
                    conn.execute(f"CREATE TRIGGER IF NOT EXISTS search_metadata_{action.lower()} AFTER {action} ON search_metadata BEGIN DELETE FROM search_profiles; END")
    return {"profiles": count, "enriched_metadata": enriched, "scoring_version": SCORING_VERSION}


def search_catalog(query: str, *, db_path: str | Path | None = None, rank: str = "balanced", limit: int = 20, offset: int = 0) -> dict:
    if rank not in RANKINGS:
        raise ValueError(f"rank must be one of {', '.join(RANKINGS)}")
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("limit must be 1..200 and offset must be nonnegative")
    if db_path is None:
        from .config import load_config
        db_path = load_config()["paths"]["db"]
    where, params = _where(query)
    with closing(_connect(Path(db_path))) as conn:
        conn.execute("BEGIN")
        source, enriched = _source(conn)
        total = conn.execute(f"SELECT count(*) FROM {source} WHERE {where}", params).fetchone()[0]
        indexed = conn.execute("SELECT 1 FROM sqlite_master WHERE name='search_profiles' AND type='table'").fetchone() is not None
        if indexed:
            valid = conn.execute(f"SELECT count(*) FROM {source} JOIN search_profiles p ON p.id=s.id WHERE ({where}) AND p.version=?", [*params, SCORING_VERSION]).fetchone()[0]
            indexed = valid == total
        if indexed:
            rows = conn.execute(f"SELECT {SELECT},p.discovery,p.notability,p.balanced,p.evidence FROM {source} JOIN search_profiles p ON p.id=s.id WHERE {where} ORDER BY p.{rank} DESC,s.id LIMIT ? OFFSET ?", [*params, limit, offset])
            selected = []
            for row in rows:
                record = _record(row)
                record["evidence"] = json.loads(record["evidence"])
                selected.append(record)
        else:
            affine_counts = _affine_counts(conn) if total else Counter()
            def scored():
                for row in conn.execute(f"SELECT {SELECT} FROM {source} WHERE {where}", params):
                    record = _record(row)
                    record.update(_score(record, affine_counts))
                    yield record
            selected = heapq.nsmallest(offset + limit, scored(), key=lambda r: (-r[rank], r["id"]))[offset:]
    results = []
    for position, record in enumerate(selected, offset + 1):
        results.append({key: record[key] for key in ("id", "name", "terms", "keywords", "formula", *RANKINGS, "evidence")})
        results[-1].update(score=record[rank], position=position)
    return {"query": query, "ranking": rank, "total": total, "offset": offset, "limit": limit, "results": results,
            "diagnostics": {"profiles_indexed": indexed, "enriched_metadata": enriched, "scoring_version": SCORING_VERSION,
                            "scope": "Stored catalog terms and available local metadata; scores are heuristics, not probabilities.",
                            "hint": None if indexed else "Run oeis search-index to precompute rankings for faster broad searches."}}
