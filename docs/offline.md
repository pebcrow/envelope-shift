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

## Regenerating the replication

The 5.5 replication ([report section 10](../report/10-replication.md)) commits its
raw model output under `replication/raw/`, so every table it cites regenerates
offline. This scores every committed row under the current metrics and compares
each table in `report/data/replication/` byte for byte; it takes a few minutes:

```bash
uv run python -m envelope_shift.analysis.replication   # prints "replication tables reproduce"
uv run pytest -q -m replication                        # the same check, as a test (CI runs it)
```

## Regenerating the original sweeps' tables

The rows behind sections 3 to 7 are committed, sanitized, under `original/raw/`.
This pools and scores them under the current metrics and checks every table that
reads `results/` byte for byte; it takes a few minutes:

```bash
uv run python -m envelope_shift.analysis.original   # prints "every results/ table reproduces ..."
uv run pytest -q -m original                        # the same check, as a test (CI runs it)
```

## What skips, and why

About nine tests skip on a fresh clone. Each prints its reason with
`uv run pytest -q -rs`:

- the tests that check how the host's *unsanitized* `results/` tree pools. That
  directory is gitignored; the sanitized rows every table is built from are
  committed under `original/raw/` and checked by
  `uv run pytest -q -m original`.
- one test that checks a recorded CLI row against a validity oracle script that
  is not distributed (`ENVELOPE_SHIFT_VALIDITY_PY`).
- one permissions test that cannot run as root.

The commands that call a model (`sweep`) or need `results/` (`score`, `pool`,
`summary`, `analysis.regenerate`) are documented in the README. They are not
needed to run the tests, score a layout or check the parameter tables.
