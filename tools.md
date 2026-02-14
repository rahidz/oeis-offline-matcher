The following should be verified in this environment and can be used directly [let User know if you try to use one and it doesn't work!].

### Compilers and toolchains
- `gcc`, `g++`
- `java`, `javac` (for `BigInteger` workflows)
- Boost headers are available (verified by compiling a `boost::multiprecision::cpp_int` snippet).

### Math / algebra systems
- `gp` (PARI/GP)
- `sage`
- `gap`
- `Singular` [has to be capitalized]

### Native libraries and binaries
- FLINT/GMP/MPFR via linker flags; note below on `pkg-config` behavior.
- `fftw3` (`pkg-config --libs fftw3` -> `-lfftw3`)
- `eigen3` headers (`pkg-config --cflags eigen3` -> `-I/usr/include/eigen3`)
- `fftw-wisdom`
- `fplll`

### Extra verified tooling (currently installed)
- Prime analytics:
  - `primecount` (v7.10)
  - `primesieve` (v12.0)
- Primality/factoring:
  - `pfgw` (v4.1.7)
  - `yafu`
  - `msieve` (v1.46)
  - `ecm` (GMP-ECM)
- Build/runtime/perf:
  - `cmake`, `ninja`, `make`
  - `hyperfine` (benchmarking)
  - `taskset` (CPU pinning)
  - `tmux` (long-running sessions)
  - `sqlite3` (local result/query storage)
- Additional systems language toolchain:
  - `rustc` (1.91.1), `cargo` (1.91.1)

### Additional tools
- Extra compilers/toolchains:
  - `clang`, `clang++` (LLVM 18.1.3)
  - `gfortran` (13.3.0)
- Dev shell/data utilities:
  - `git` (2.43.0)
  - `rg` (ripgrep 14.1.1)
  - `jq` (1.7.1)
  - `curl` (8.5.0), `wget` (1.21.4)
  - `tar` (1.35), `zip` (3.0), `unzip` (6.00)
  - `parallel` (GNU parallel 20260122)
- JavaScript / TypeScript ecosystem:
  - `node` (v22.22.0)
  - `npm` (11.8.0), `npx` (11.8.0)
  - `pnpm` (10.28.1), `yarn` (1.22.22), `bun` (1.3.9)
- Additional math/language runtimes:
  - `julia` (1.12.4)
  - `Rscript` (R 4.5.2)
  - `octave` (8.4.0)
  - `sbcl` (2.2.9)
  - `perl` (5.38.2), `ruby` (3.2.3)
- Python tooling:
  - `uv` (0.9.16)
  - `pip` (24.0)

### Python
- Python 3 with stdlib (`int`, `decimal`, `fractions`, `itertools`, etc.)
- Verified common libs: `sympy`, `numpy`, `scipy`, `mpmath`, `gmpy2`