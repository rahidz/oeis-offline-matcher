# FAQ

**Does this query the live OEIS?**  
No. After the initial download (`oeis sync` or `scripts/fetch_oeis_data.sh`) everything runs locally against the SQLite snapshot.

**How fresh is the data?**  
Use `oeis status` to see last-sync age and DB health.  
`oeis status --refresh-if-stale` can refresh non-interactively (sync + rebuild) when age exceeds your threshold (default 30 days).

If you are offline or OEIS is rate-limited, the refresh step fails cleanly, reports the error, and leaves your existing local files as-is.

**How do I sanity-check my local DB?**  
Use `oeis selfcheck` to run a small regression set and (optionally) a few random combo recovery trials:

```bash
oeis selfcheck --db data/processed/oeis.db
oeis selfcheck --db data/processed/oeis.db --random-trials 20 --seed 1
oeis selfcheck --db data/processed/oeis.db --pointwise-trials 20 --convolution-trials 20 --seed 1
```

**Can it stream results while searching?**  
Yes.
- `oeis analyze --preset max` streams by default.
- `oeis combo --preset max` streams by default (or pass `--stream`).
- `oeis tsearch --preset max` streams by default (or pass `--stream`).

`oeis analyze` and `oeis combo` also support a hard wall time cap via `--total-max-time` (seconds).
Use `--timings` to include per-stage timing diagnostics.

**What kinds of matches are supported?**  
Exact/prefix/subsequence, transform search (scale/shift/diff/partial sums/abs/gcd_norm/decimate, etc.), similarity (scale+offset fit), and small two- or three-sequence combinations (integer or rational coeffs) with forward/backward shifts. Pointwise (mul/gcd/lcm) and Cauchy/Dirichlet convolution combos are also available under strict caps.

Note: pointwise/convolution outputs include per-component transform names when enabled (e.g. `diff(Axxxxxx)`), and streaming output avoids redundant commutative self-pair duplicates.

**Why do pointwise results sometimes avoid “multiply by ones” style matches?**  
Pointwise `mul`/`lcm` identities like `A000012(n) * X(n) = X(n)` are valid but not very explanatory. The scorer down-ranks those so more meaningful decompositions (e.g. `n*(n+1)`) have a chance to appear within small `--pointwise-limit` values.

**Are negative shifts or three-sequence combos supported?**  
Yes. Combination search accepts backward shifts (`--max-shift-back`) and optional three-sequence search (`--triples`, guarded by candidate/time caps). It also supports “self-shift” two-sequence combos where the same OEIS id appears twice with different shifts. `--preset max` enables a small backward-shift window by default (still capped by time/check limits).

**Why might my sequence return no matches?**  
- Query too short (default min length 3).  
- Terms not present in snapshot (update your data).  
- Transform depth/coeff ranges too restrictive.  
- Combination search capped by candidate/`max_checks` limits.

**Performance tips**  
- Build the SQLite index on an SSD.  
- Narrow transform search (`--max-depth 1`, smaller scale list).  
- Lower `--similar` / `--combos` / candidate caps if queries slow down.  
- If the CLI warns that your DB is missing recommended indexes, run `oeis optimize-db --db ...` (one-time).  
- Use `scripts/bench.py` to measure on your machine.
- Use `--timings` to see per-stage time and `scripts/profile_matchers.py` for deeper profiling.
- If you just want “best effort within X seconds”, use `--total-max-time X` on `oeis analyze` or `oeis combo`.
- Expanded combo fallback (`--expanded` / `--preset max`) builds a small in-memory prefix index per run (typically sub-second on a full snapshot). It requires at least 5 query terms and is bounded by `--expanded-max-time` and `--total-max-time`. In streaming mode, expanded pair fallback is deferred until after the regular candidate-based stages (including triples) to improve time-to-first-hit.
- Short queries (4 terms) are still accelerated using the `prefix5` column via a partial prefix match, but very short inputs can naturally match many sequences.

**License reminder**  
OEIS data is CC BY-SA 4.0. Include attribution when sharing outputs.
