# Running envelope-shift offline

Everything below works on a fresh clone with no model, no API key and no
`results/` directory. It needs [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync                                            # install the locked dependencies
uv run pytest -q                                   # the test suite
uv run envelope-shift params                       # print the DEFAULT parameter table
uv run envelope-shift params --params strict --out-dir /tmp/params
                                                   # write params_strict.md (any directory)
uv run envelope-shift score-layout                 # score one committed layout, print its metrics
```

`score-layout` reads `tests/fixtures/layouts_smoke.jsonl` by default and scores
its first record. Pass a different file, `--row N` for another record, or
`--params strict` for the calibration parameter set. It writes nothing.

To check the committed parameter tables against the code, regenerate them into
a scratch directory and compare:

```bash
for p in default strict; do
  uv run envelope-shift params --params $p --out-dir /tmp/params
  cmp /tmp/params/params_$p.md report/data/params_$p.md && echo "params_$p.md matches"
done
```

## What skips, and why

About nine tests skip on a fresh clone. Each prints its reason with
`uv run pytest -q -rs`:

- the tests that re-derive committed tables from `results/`, which holds the
  raw model outputs of the original sweeps. That directory is gitignored and not
  distributed. Point `ENVELOPE_SHIFT_RESULTS` at a copy to run them.
- one test that checks a recorded CLI row against a validity oracle script that
  is not distributed (`ENVELOPE_SHIFT_VALIDITY_PY`).
- one permissions test that cannot run as root.

The commands that call a model (`sweep`) or need `results/` (`score`, `pool`,
`summary`, `analysis.regenerate`) are documented in the README. They are not
needed to run the tests, score a layout or check the parameter tables.
