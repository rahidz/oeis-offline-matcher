"""
Storage utilities for OEIS data.

Currently uses a simple SQLite file with one table:
  sequences(id TEXT PRIMARY KEY,
            length INTEGER NOT NULL,
            terms TEXT NOT NULL,            -- comma-separated ints
            name TEXT,
            formula TEXT,                   -- optional combined FORMULA text
            keywords TEXT,                  -- comma-separated keywords (optional)
            prefix5 TEXT,                   -- first 5 terms comma-joined
            min_val TEXT,
            max_val TEXT,
            gcd_val TEXT,
            is_nondecreasing INTEGER,
            is_nonincreasing INTEGER,
            sign_pattern TEXT,
            nonzero_count INTEGER,
            first_diff_sign TEXT)

The design keeps things easy to inspect and change; we can migrate to
memory-mapped arrays or a richer schema later.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .models import SequenceRecord
from .similarity import growth_rate


def _compute_gcd(values: list[int]) -> int:
    g = 0
    for v in values:
        g = math.gcd(g, abs(v))
    return g


def _variance(values: list[int]) -> float | None:
    if len(values) < 2:
        return None
    try:
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)
    except OverflowError:
        return None


def _monotonic_flags(values: list[int]) -> tuple[int, int]:
    """
    Returns (is_nondecreasing, is_nonincreasing) as ints (0/1).
    """
    if not values:
        return (0, 0)
    nondecr = all(values[i] <= values[i + 1] for i in range(len(values) - 1))
    nonincr = all(values[i] >= values[i + 1] for i in range(len(values) - 1))
    return (1 if nondecr else 0, 1 if nonincr else 0)


def _sign_pattern(values: list[int]) -> str:
    if not values:
        return "empty"
    all_nonneg = all(v >= 0 for v in values)
    all_nonpos = all(v <= 0 for v in values)
    if all_nonneg:
        return "nonneg"
    if all_nonpos:
        return "nonpos"
    # alternating sign?
    alt = all(values[i] == 0 or values[i + 1] == 0 or (values[i] > 0) != (values[i + 1] > 0) for i in range(len(values) - 1))
    if alt:
        return "alternating"
    return "mixed"


def _first_diff_sign(values: list[int]) -> str:
    if len(values) < 2:
        return "na"
    diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    pos = sum(1 for d in diffs if d > 0)
    neg = sum(1 for d in diffs if d < 0)
    zero = len(diffs) - pos - neg
    if pos == len(diffs):
        return "pos"
    if neg == len(diffs):
        return "neg"
    if pos > 0 and neg == 0:
        return "nonneg"
    if neg > 0 and pos == 0:
        return "nonpos"
    if zero == len(diffs):
        return "flat"
    return "mixed"


def _record_to_row(rec: SequenceRecord) -> tuple:
    terms_text = ",".join(str(t) for t in rec.terms)
    prefix5 = ",".join(str(t) for t in rec.terms[:5])
    min_val = str(min(rec.terms)) if rec.terms else None
    max_val = str(max(rec.terms)) if rec.terms else None
    gcd_val = str(_compute_gcd(rec.terms)) if rec.terms else None
    nondecr, nonincr = _monotonic_flags(rec.terms)
    sign_pat = _sign_pattern(rec.terms)
    first_diff = _first_diff_sign(rec.terms)
    nonzero_count = sum(1 for t in rec.terms if t != 0)
    var_val = _variance(rec.terms)
    diff_var = _variance([rec.terms[i + 1] - rec.terms[i] for i in range(len(rec.terms) - 1)]) if len(rec.terms) > 1 else None
    offset0 = rec.offset[0] if rec.offset else None
    offset1 = rec.offset[1] if rec.offset and len(rec.offset) > 1 else None
    has_formula = 1 if rec.has_formula else 0 if rec.has_formula is not None else None
    if rec.formula:
        has_formula = 1
    return (
        rec.id,
        rec.length,
        terms_text,
        rec.name,
        rec.formula,
        ",".join(rec.keywords) if rec.keywords else None,
        offset0,
        offset1,
        has_formula,
        prefix5,
        min_val,
        max_val,
        gcd_val,
        nondecr,
        nonincr,
        sign_pat,
        nonzero_count,
        first_diff,
        growth_rate(rec.terms),
        var_val,
        diff_var,
    )


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS sequences")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sequences (
                id TEXT PRIMARY KEY,
                length INTEGER NOT NULL,
                terms TEXT NOT NULL,
                name TEXT,
                formula TEXT,
                keywords TEXT,
                offset0 INTEGER,
                offset1 INTEGER,
                has_formula INTEGER,
                prefix5 TEXT,
                min_val TEXT,
                max_val TEXT,
                gcd_val TEXT,
                is_nondecreasing INTEGER,
                is_nonincreasing INTEGER,
                sign_pattern TEXT,
                nonzero_count INTEGER,
                first_diff_sign TEXT,
                growth_rate REAL,
                var REAL,
                diff_var REAL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prefix5 ON sequences(prefix5)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_length ON sequences(length)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gcd ON sequences(gcd_val)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sign ON sequences(sign_pattern)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_first_diff ON sequences(first_diff_sign)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nonzero ON sequences(nonzero_count)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_growth ON sequences(growth_rate)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_var ON sequences(var)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_diff_var ON sequences(diff_var)")
        conn.commit()


def write_records(records: Iterable[SequenceRecord], db_path: Path, *, batch_size: int = 5000) -> int:
    """
    Insert SequenceRecord items into SQLite. Returns count inserted.
    Overwrites existing rows with the same id.
    """
    total = 0
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")

        batch: list[tuple] = []
        for rec in records:
            batch.append(_record_to_row(rec))
            if len(batch) >= batch_size:
                _insert_batch(conn, batch)
                total += len(batch)
                batch.clear()

        if batch:
            _insert_batch(conn, batch)
            total += len(batch)

        conn.commit()
    return total


def _insert_batch(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(
        """
        INSERT INTO sequences (id, length, terms, name, formula, keywords, offset0, offset1, has_formula, prefix5, min_val, max_val, gcd_val,
                               is_nondecreasing, is_nonincreasing, sign_pattern, nonzero_count, first_diff_sign, growth_rate,
                               var, diff_var)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            length=excluded.length,
            terms=excluded.terms,
            name=excluded.name,
            formula=excluded.formula,
            keywords=excluded.keywords,
            offset0=excluded.offset0,
            offset1=excluded.offset1,
            has_formula=excluded.has_formula,
            prefix5=excluded.prefix5,
            min_val=excluded.min_val,
            max_val=excluded.max_val,
            gcd_val=excluded.gcd_val,
            is_nondecreasing=excluded.is_nondecreasing,
            is_nonincreasing=excluded.is_nonincreasing,
            sign_pattern=excluded.sign_pattern,
            nonzero_count=excluded.nonzero_count,
            first_diff_sign=excluded.first_diff_sign,
            growth_rate=excluded.growth_rate,
            var=excluded.var,
            diff_var=excluded.diff_var
        """,
        rows,
    )


def iter_sequences(db_path: Path) -> Iterator[SequenceRecord]:
    """
    Stream sequences from SQLite as SequenceRecord objects.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        has_kw = _has_column(conn, "keywords")
        has_off = _has_column(conn, "offset0")
        has_formula_flag = _has_column(conn, "has_formula")
        has_formula_text = _has_column(conn, "formula")
        select_fields = ["id", "terms", "length", "name"]
        if has_formula_text:
            select_fields.append("formula")
        if has_kw:
            select_fields.append("keywords")
        if has_off:
            select_fields.extend(["offset0", "offset1"])
        if has_formula_flag:
            select_fields.append("has_formula")
        select = ", ".join(select_fields)
        for row in conn.execute(f"SELECT {select} FROM sequences"):
            terms = [int(x) for x in row["terms"].split(",")] if row["terms"] else []
            offset = None
            if has_off and row["offset0"] is not None:
                offset = (int(row["offset0"]), int(row["offset1"]) if "offset1" in row.keys() else None)
            formula_val = row["formula"] if has_formula_text else None
            has_formula_val = None
            if has_formula_flag and "has_formula" in row.keys() and row["has_formula"] is not None:
                has_formula_val = bool(row["has_formula"])
            elif formula_val:
                has_formula_val = True
            yield SequenceRecord(
                id=row["id"],
                terms=terms,
                length=row["length"],
                name=row["name"],
                formula=formula_val,
                keywords=row["keywords"].split(",") if has_kw and row["keywords"] else None,
                offset=offset,
                has_formula=has_formula_val,
            )


def iter_sequences_filtered(
    db_path: Path,
    *,
    sign_pattern: str | None = None,
    first_diff_sign: str | None = None,
    nonzero_min: int | None = None,
    nonzero_max: int | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    var_min: float | None = None,
    var_max: float | None = None,
    diff_var_min: float | None = None,
    diff_var_max: float | None = None,
    growth_min: float | None = None,
    growth_max: float | None = None,
) -> Iterator[SequenceRecord]:
    """
    Stream sequences filtered by stored invariants.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        has_kw = _has_column(conn, "keywords")
        has_var = _has_column(conn, "var")
        has_dvar = _has_column(conn, "diff_var")
        has_growth = _has_column(conn, "growth_rate")
        has_off = _has_column(conn, "offset0")
        has_formula_flag = _has_column(conn, "has_formula")
        has_formula_text = _has_column(conn, "formula")
        # Drop variance/growth filters if columns not present (older DBs)
        if not has_var:
            var_min = var_max = None
        if not has_dvar:
            diff_var_min = diff_var_max = None
        if not has_growth:
            growth_min = growth_max = None

        clauses = []
        params: list = []
        if sign_pattern:
            clauses.append("sign_pattern = ?")
            params.append(sign_pattern)
        if first_diff_sign:
            clauses.append("first_diff_sign = ?")
            params.append(first_diff_sign)
        if nonzero_min is not None:
            clauses.append("nonzero_count >= ?")
            params.append(nonzero_min)
        if nonzero_max is not None:
            clauses.append("nonzero_count <= ?")
            params.append(nonzero_max)
        if min_length is not None:
            clauses.append("length >= ?")
            params.append(min_length)
        if max_length is not None:
            clauses.append("length <= ?")
            params.append(max_length)
        if var_min is not None:
            clauses.append("var >= ?")
            params.append(var_min)
        if var_max is not None:
            clauses.append("var <= ?")
            params.append(var_max)
        if diff_var_min is not None:
            clauses.append("diff_var >= ?")
            params.append(diff_var_min)
        if diff_var_max is not None:
            clauses.append("diff_var <= ?")
            params.append(diff_var_max)
        if growth_min is not None:
            clauses.append("growth_rate >= ?")
            params.append(growth_min)
        if growth_max is not None:
            clauses.append("growth_rate <= ?")
            params.append(growth_max)

        where = ""
        if clauses:
            where = "WHERE " + " AND ".join(clauses)

        select_fields = ["id", "terms", "length", "name"]
        if has_formula_text:
            select_fields.append("formula")
        if has_kw:
            select_fields.append("keywords")
        if has_off:
            select_fields.extend(["offset0", "offset1"])
        if has_formula_flag:
            select_fields.append("has_formula")
        select = ", ".join(select_fields)
        query = f"SELECT {select} FROM sequences {where}"

        for row in conn.execute(query, params):
            terms = [int(x) for x in row["terms"].split(",")] if row["terms"] else []
            offset = None
            if has_off and row["offset0"] is not None:
                offset = (int(row["offset0"]), int(row["offset1"]) if "offset1" in row.keys() else None)
            formula_val = row["formula"] if has_formula_text else None
            has_formula_val = None
            if has_formula_flag and "has_formula" in row.keys() and row["has_formula"] is not None:
                has_formula_val = bool(row["has_formula"])
            elif formula_val:
                has_formula_val = True
            yield SequenceRecord(
                id=row["id"],
                terms=terms,
                length=row["length"],
                name=row["name"],
                formula=formula_val,
                keywords=row["keywords"].split(",") if has_kw and row["keywords"] else None,
                offset=offset,
                has_formula=has_formula_val,
            )


def iter_sequences_by_prefix(db_path: Path, prefix_terms: list[int]) -> Iterator[SequenceRecord]:
    """
    Stream sequences whose first 5 terms match the provided prefix (length>=5).
    Falls back to iter_sequences if prefix is too short.
    """
    if len(prefix_terms) < 5:
        yield from iter_sequences(db_path)
        return

    prefix5 = ",".join(str(t) for t in prefix_terms[:5])
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        has_kw = _has_column(conn, "keywords")
        has_off = _has_column(conn, "offset0")
        has_formula_flag = _has_column(conn, "has_formula")
        has_formula_text = _has_column(conn, "formula")
        select_fields = ["id", "terms", "length", "name"]
        if has_formula_text:
            select_fields.append("formula")
        if has_kw:
            select_fields.append("keywords")
        if has_off:
            select_fields.extend(["offset0", "offset1"])
        if has_formula_flag:
            select_fields.append("has_formula")
        select = ", ".join(select_fields)
        for row in conn.execute(
            f"SELECT {select} FROM sequences WHERE prefix5 = ?", (prefix5,)
        ):
            terms = [int(x) for x in row["terms"].split(",")] if row["terms"] else []
            offset = None
            if has_off and row["offset0"] is not None:
                offset = (int(row["offset0"]), int(row["offset1"]) if "offset1" in row.keys() else None)
            formula_val = row["formula"] if has_formula_text else None
            has_formula_val = None
            if has_formula_flag and "has_formula" in row.keys() and row["has_formula"] is not None:
                has_formula_val = bool(row["has_formula"])
            elif formula_val:
                has_formula_val = True
            yield SequenceRecord(
                id=row["id"],
                terms=terms,
                length=row["length"],
                name=row["name"],
                formula=formula_val,
                keywords=row["keywords"].split(",") if has_kw and row["keywords"] else None,
                offset=offset,
                has_formula=has_formula_val,
            )


def db_stats(db_path: Path) -> Optional[dict]:
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT COUNT(*), MIN(length), MAX(length) FROM sequences")
        count, min_len, max_len = cur.fetchone()
        return {"count": count, "min_length": min_len, "max_length": max_len}


def _has_column(conn: sqlite3.Connection, column: str) -> bool:
    cur = conn.execute("PRAGMA table_info(sequences)")
    return any(row[1] == column for row in cur.fetchall())
