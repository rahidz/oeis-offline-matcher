# FAQ

**Does this query the live OEIS?**  
No. After the initial download (`scripts/fetch_oeis_data.sh`) everything runs locally against the SQLite snapshot.

**How fresh is the data?**  
Only as recent as your last `fetch_oeis_data.sh` + `oeis build-index` run. Re-run to refresh.

**What kinds of matches are supported?**  
Exact/prefix/subsequence, transform search (scale/shift/diff/partial sums/abs/gcd_norm/decimate), similarity (scale+offset fit), and small two-sequence integer combinations with forward shifts.

**Are negative shifts or three-sequence combos supported?**  
Not yet. Current combos only drop terms (non-negative shifts) and use small integer coefficients.

**Why might my sequence return no matches?**  
- Query too short (default min length 3).  
- Terms not present in snapshot (update your data).  
- Transform depth/coeff ranges too restrictive.  
- Combination search capped by candidate/`max_checks` limits.

**Performance tips**  
- Build the SQLite index on an SSD.  
- Narrow transform search (`--max-depth 1`, smaller scale list).  
- Lower `--similar` / `--combos` / candidate caps if queries slow down.  
- Use `scripts/bench.py` to measure on your machine.

**License reminder**  
OEIS data is CC BY-SA 4.0. Include attribution when sharing outputs.
