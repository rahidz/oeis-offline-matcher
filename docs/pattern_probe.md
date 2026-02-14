# Pattern Probe Helper

`scripts/pattern_probe.py` is a small offline helper for “pattern-finding” workflows:

- Split an input sequence by index congruence classes (e.g. `n mod 4`).
- Print quick per-term `v2` / `v5` valuations and the remaining cofactor.
- Optionally try a normalization of the form `a(k*m+r) / m^(2m)` (useful for Hadamard-style determinant sequences).
- Run the offline OEIS exact/subsequence matcher on each derived sequence.

## Examples

```bash
# If you installed the package (pip install -e .), this works directly:
python scripts/pattern_probe.py "1,1,1,2,3,5,9,32,56,144,320,1458,3645,9477,25515,131072,327680,1114112,3411968,19531250,56640625,195312500" --k 4 --try-mpow

# Or, without installing, it also works (the script adds repo paths to sys.path):
python scripts/pattern_probe.py "0,1,1,2,3,5,8,13,21" --k 2
```

Notes:
- `--n0` controls the index of the first provided term (default `1`).
- `--subsequence` allows subsequence matches (slower, but can be useful for short derived sequences).

