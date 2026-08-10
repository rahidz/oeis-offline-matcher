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
            prefix5_1 TEXT,                 -- terms[1:6] comma-joined (optional)
            prefix5_2 TEXT,                 -- terms[2:7] comma-joined (optional)
            prefix5_3 TEXT,                 -- terms[3:8] comma-joined (optional)
            prefix5_4 TEXT,                 -- terms[4:9] comma-joined (optional)
            prefix5_5 TEXT,                 -- terms[5:10] comma-joined (optional)
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
from contextlib import closing
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
    # Shifted prefixes support "start at index k" expanded combo searches.
    # Keep them small (5 terms) and fixed-shift (k<=5) so the DB stays portable
    # and query-time logic can remain fully offline and deterministic.
    prefix5_1 = ",".join(str(t) for t in rec.terms[1:6]) if len(rec.terms) >= 6 else None
    prefix5_2 = ",".join(str(t) for t in rec.terms[2:7]) if len(rec.terms) >= 7 else None
    prefix5_3 = ",".join(str(t) for t in rec.terms[3:8]) if len(rec.terms) >= 8 else None
    prefix5_4 = ",".join(str(t) for t in rec.terms[4:9]) if len(rec.terms) >= 9 else None
    prefix5_5 = ",".join(str(t) for t in rec.terms[5:10]) if len(rec.terms) >= 10 else None
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
        prefix5_1,
        prefix5_2,
        prefix5_3,
        prefix5_4,
        prefix5_5,
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


def init_db(db_path: Path, *, create_indexes: bool = True) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
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
                prefix5_1 TEXT,
                prefix5_2 TEXT,
                prefix5_3 TEXT,
                prefix5_4 TEXT,
                prefix5_5 TEXT,
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
        conn.commit()
    if create_indexes:
        ensure_db_indexes(db_path)


def ensure_db_indexes(db_path: Path, *, analyze: bool = False) -> dict[str, object]:
    """
    Create any missing SQLite indexes needed for good runtime performance.

    Safe to run repeatedly; uses CREATE INDEX IF NOT EXISTS.
    Returns a small diagnostics payload suitable for CLI/JSON output.
    """

    def _index_names(conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute("PRAGMA index_list(sequences)").fetchall()
        # row format: (seq, name, unique, origin, partial) for modern sqlite
        return {str(r[1]) for r in rows if len(r) > 1 and r[1]}

    with closing(sqlite3.connect(db_path)) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sequences)").fetchall()}

        def has_col(name: str) -> bool:
            return name in cols

        before = _index_names(conn)

        if has_col("prefix5"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prefix5 ON sequences(prefix5)")
        for shift in range(1, 6):
            if has_col(f"prefix5_{shift}"):
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_prefix5_{shift} ON sequences(prefix5_{shift})")
        if has_col("length"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_length ON sequences(length)")
        if has_col("gcd_val"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gcd ON sequences(gcd_val)")
        if has_col("sign_pattern"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sign ON sequences(sign_pattern)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sign_id ON sequences(sign_pattern, id)")
        if has_col("first_diff_sign"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_first_diff ON sequences(first_diff_sign)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_first_diff_id ON sequences(first_diff_sign, id)")
        if has_col("nonzero_count"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nonzero ON sequences(nonzero_count)")
        if has_col("growth_rate"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_growth ON sequences(growth_rate)")
        if has_col("var"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_var ON sequences(var)")
        if has_col("diff_var"):
            conn.execute("CREATE INDEX IF NOT EXISTS idx_diff_var ON sequences(diff_var)")

        if analyze:
            conn.execute("ANALYZE")

        conn.commit()
        after = _index_names(conn)

    created = sorted(after - before)
    missing_cols = sorted(
        [c for c in ("prefix5", "length", "gcd_val", "sign_pattern", "first_diff_sign", "nonzero_count", "growth_rate", "var", "diff_var") if c not in cols]
    )

    return {
        "db": str(Path(db_path)),
        "created": created,
        "already_present": sorted(before & after),
        "missing_columns": missing_cols,
        "analyzed": bool(analyze),
    }


def missing_recommended_indexes(db_path: Path) -> list[str]:
    """
    Return a list of recommended index names that are missing on `db_path`.

    This is a lightweight diagnostic helper used by the CLI to suggest running
    `oeis optimize-db` when the DB was built by an older version of the tool.
    It does NOT create any indexes (unlike `ensure_db_indexes`).
    """

    def _index_names(conn: sqlite3.Connection) -> set[str]:
        rows = conn.execute("PRAGMA index_list(sequences)").fetchall()
        return {str(r[1]) for r in rows if len(r) > 1 and r[1]}

    with closing(sqlite3.connect(db_path)) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sequences)").fetchall()}
        have = _index_names(conn)

    required: set[str] = set()
    if "prefix5" in cols:
        required.add("idx_prefix5")
    for shift in range(1, 6):
        if f"prefix5_{shift}" in cols:
            required.add(f"idx_prefix5_{shift}")
    if "length" in cols:
        required.add("idx_length")
    if "gcd_val" in cols:
        required.add("idx_gcd")
    if "sign_pattern" in cols:
        required.add("idx_sign")
        required.add("idx_sign_id")
    if "first_diff_sign" in cols:
        required.add("idx_first_diff")
        required.add("idx_first_diff_id")
    if "nonzero_count" in cols:
        required.add("idx_nonzero")
    if "growth_rate" in cols:
        required.add("idx_growth")
    if "var" in cols:
        required.add("idx_var")
    if "diff_var" in cols:
        required.add("idx_diff_var")

    missing = sorted(required - have)
    return missing


def ensure_prefix_shifts(db_path: Path, *, max_shift: int = 5, batch_size: int = 5000) -> dict[str, object]:
    """
    Ensure shifted prefix columns (prefix5_1..prefix5_k) exist and are populated.

    Why:
    Expanded "DB-wide" searches rely on an in-memory prefix index. For shifted
    pointwise/linear combinations ("use A starting at index k"), we need the
    ability to index terms[k:k+5] efficiently without parsing full term lists
    at query time.

    This is safe to run repeatedly:
    - Missing columns are added via ALTER TABLE.
    - Newly added columns are populated from the existing `terms` text.

    Notes:
    - Only supports 5-term prefix windows (matches the existing `prefix5` design).
    - Intended maximum shift is small (k<=5) to keep DB bloat modest.
    """
    db_path = Path(db_path)
    if max_shift <= 0:
        return {"db": str(db_path), "added_columns": [], "updated_rows": 0, "max_shift": int(max_shift)}

    max_shift = int(max_shift)
    cols_needed = [f"prefix5_{k}" for k in range(1, max_shift + 1)]

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sequences)").fetchall()}

        added: list[str] = []
        for col in cols_needed:
            if col in cols:
                continue
            conn.execute(f"ALTER TABLE sequences ADD COLUMN {col} TEXT")
            added.append(col)
            cols.add(col)

        updated_rows = 0
        if added:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=OFF")

            # Only compute the small prefix window we need: up to (max_shift+5) terms.
            max_needed = max_shift + 5

            def _first_terms(terms_text: str) -> list[int]:
                if not terms_text:
                    return []
                # Split only enough commas to get the first `max_needed` terms.
                parts = [p for p in terms_text.split(",", max_needed)[:max_needed] if p != ""]
                out: list[int] = []
                for p in parts:
                    try:
                        out.append(int(p))
                    except ValueError:
                        break
                return out

            update_cols = [c for c in cols_needed if c in cols]
            set_clause = ", ".join(f"{c} = ?" for c in update_cols)
            sql = f"UPDATE sequences SET {set_clause} WHERE id = ?"

            batch: list[tuple] = []
            for row in conn.execute("SELECT id, terms FROM sequences ORDER BY id ASC"):
                seq_id = str(row["id"])
                terms = _first_terms(row["terms"])
                values: list[str | None] = []
                for k in range(1, max_shift + 1):
                    if f"prefix5_{k}" not in update_cols:
                        continue
                    values.append(",".join(str(t) for t in terms[k : k + 5]) if len(terms) >= k + 5 else None)
                batch.append(tuple(values + [seq_id]))
                if len(batch) >= int(batch_size):
                    conn.executemany(sql, batch)
                    updated_rows += len(batch)
                    batch.clear()
            if batch:
                conn.executemany(sql, batch)
                updated_rows += len(batch)
            conn.commit()

        before_indexes = {
            str(row[1]) for row in conn.execute("PRAGMA index_list(sequences)") if row[1]
        }
        for k in range(1, max_shift + 1):
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_prefix5_{k} ON sequences(prefix5_{k})")
        conn.commit()
        created_indexes = sorted(
            str(row[1])
            for row in conn.execute("PRAGMA index_list(sequences)")
            if row[1] and str(row[1]) not in before_indexes
        )

        return {
            "db": str(db_path),
            "added_columns": added,
            "created_indexes": created_indexes,
            "updated_rows": updated_rows,
            "max_shift": max_shift,
        }


def write_records(records: Iterable[SequenceRecord], db_path: Path, *, batch_size: int = 5000) -> int:
    """
    Insert SequenceRecord items into SQLite. Returns count inserted.
    Overwrites existing rows with the same id.
    """
    total = 0
    with closing(sqlite3.connect(db_path)) as conn:
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
        INSERT INTO sequences (id, length, terms, name, formula, keywords, offset0, offset1, has_formula, prefix5,
                               prefix5_1, prefix5_2, prefix5_3, prefix5_4, prefix5_5,
                               min_val, max_val, gcd_val, is_nondecreasing, is_nonincreasing, sign_pattern, nonzero_count,
                               first_diff_sign, growth_rate, var, diff_var)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?)
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
            prefix5_1=excluded.prefix5_1,
            prefix5_2=excluded.prefix5_2,
            prefix5_3=excluded.prefix5_3,
            prefix5_4=excluded.prefix5_4,
            prefix5_5=excluded.prefix5_5,
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
        # Deterministic ordering matters for reproducibility and for "best-effort"
        # time-capped searches that may stop early.
        for row in conn.execute(f"SELECT {select} FROM sequences ORDER BY id ASC"):
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


def get_sequence_by_id(db_path: Path, seq_id: str) -> SequenceRecord | None:
    """
    Fetch a single SequenceRecord by OEIS id (e.g., "A000045"), or None if missing.

    Intended for CLI features like "seed these candidates" without requiring a full scan.
    """
    if not seq_id:
        return None
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
        row = conn.execute(f"SELECT {select} FROM sequences WHERE id = ?", (seq_id,)).fetchone()
        if not row:
            return None
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
        return SequenceRecord(
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
    order_by_length_distance_to: int | None = None,
    limit: int | None = None,
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
        has_sign = _has_column(conn, "sign_pattern")
        has_first_diff = _has_column(conn, "first_diff_sign")
        has_nonzero = _has_column(conn, "nonzero_count")
        # Drop variance/growth filters if columns not present (older DBs)
        if not has_var:
            var_min = var_max = None
        if not has_dvar:
            diff_var_min = diff_var_max = None
        if not has_growth:
            growth_min = growth_max = None
        if not has_sign:
            sign_pattern = None
        if not has_first_diff:
            first_diff_sign = None
        if not has_nonzero:
            nonzero_min = nonzero_max = None

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

        if order_by_length_distance_to is not None:
            # Deterministic ordering (id tie-break) is important for reproducibility/tests.
            query += " ORDER BY ABS(length - ?) ASC, id ASC"
            params.append(int(order_by_length_distance_to))
        else:
            # Keep output deterministic when using invariants-only filters.
            query += " ORDER BY id ASC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))

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
    Stream sequences whose prefix matches the provided terms.

    Implementation notes:
    - For prefix length >= 5, this uses exact equality on the stored `prefix5` column.
    - For shorter prefixes (1..4), this uses `prefix5 = ? OR prefix5 LIKE ?` to still
      leverage the `idx_prefix5` index (e.g., matching "1,1,1,1,%").
    """
    if not prefix_terms:
        yield from iter_sequences(db_path)
        return

    prefix_len = min(len(prefix_terms), 5)
    prefix_txt = ",".join(str(t) for t in prefix_terms[:prefix_len])
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
        if prefix_len >= 5:
            where = "prefix5 = ?"
            params = (prefix_txt,)
        else:
            # Include:
            # - short stored sequences where prefix5 == prefix_txt (length < 5),
            # - normal sequences where prefix5 starts with "prefix_txt,".
            start = prefix_txt + ","
            end = prefix_txt + ",\uffff"
            where = "(prefix5 = ? OR (prefix5 >= ? AND prefix5 < ?))"
            params = (prefix_txt, start, end)
        for row in conn.execute(f"SELECT {select} FROM sequences WHERE {where} ORDER BY id", params):
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


_INVARIANT_STATS_CACHE: dict[str, dict] = {}


def invariant_stats(db_path: Path) -> dict:
    """
    Return coarse histograms over a few stored invariants.

    Intended for scoring heuristics like "rarity of invariants" without scanning
    the full DB per query.
    """
    key = str(Path(db_path).resolve())
    cached = _INVARIANT_STATS_CACHE.get(key)
    if cached is not None:
        return cached

    stats: dict[str, object] = {"total": 0, "sign_pattern": {}, "first_diff_sign": {}}
    if not Path(db_path).exists():
        _INVARIANT_STATS_CACHE[key] = stats
        return stats

    with sqlite3.connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM sequences").fetchone()[0]
        stats["total"] = int(total or 0)

        if _has_column(conn, "sign_pattern"):
            sign_counts = {
                str(sp): int(n)
                for sp, n in conn.execute("SELECT sign_pattern, COUNT(*) FROM sequences GROUP BY sign_pattern")
                if sp is not None
            }
            stats["sign_pattern"] = sign_counts
        if _has_column(conn, "first_diff_sign"):
            diff_counts = {
                str(fd): int(n)
                for fd, n in conn.execute("SELECT first_diff_sign, COUNT(*) FROM sequences GROUP BY first_diff_sign")
                if fd is not None
            }
            stats["first_diff_sign"] = diff_counts

    _INVARIANT_STATS_CACHE[key] = stats
    return stats


def _has_column(conn: sqlite3.Connection, column: str) -> bool:
    cur = conn.execute("PRAGMA table_info(sequences)")
    return any(row[1] == column for row in cur.fetchall())
