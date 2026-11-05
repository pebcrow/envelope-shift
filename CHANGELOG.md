# Changelog

## v1.2.0 — every number checkable from a fresh clone

### Added
- `original/raw/`: the raw output of the sweeps behind sections 3 to 7 (the
  `all` pool of `analysis/corpora.toml` and `e2b_default`), sanitized the same
  way as the replication's and refused by the sanitizer if any leak pattern
  remains.
- `envelope_shift.analysis.original`: `sanitize` copies those sweeps out of a
  host `results/` tree; the default action rebuilds every `report/provenance.json`
  table that reads `results/` from the committed rows alone and compares it byte
  for byte. CI runs it as its own step (`pytest -m original`).

### Changed
- README, report status, section 8 and the offline guide no longer say the
  original raw output is undistributed.

## v1.1.0 — replication on the 5.5 models

### Added
- Report section 10: the whole harness re-run on Claude Opus 5.5 and Sonnet 5.5
  (`opus55`, `sonnet55` in `models.toml`), same prompts, transport, effort and
  sampling as the original Claude arms. The T5 finding holds: 0.0 coverage lost
  to missing lines, 10.6 to the declared program, on both.
- `replication/raw/`: the replication's raw model output, committed and
  sanitized (session and message ids, host paths and account state removed;
  the condition-bearing CLI events kept). `replication/corpora.toml` pools it.
- `envelope_shift.analysis.replication`: rebuilds every `report/data/replication/`
  table from the committed rows under the current metrics, and checks them byte
  for byte. CI runs the check as its own step (`pytest -m replication`).
- `tests/test_replication.py`: the regenerate check, and a guard that no
  committed raw row carries a UUID-shaped id, a session id or a host path.

- Report section 11 and `metrics.coverage.coverage_brief`: brief-aware coverage,
  a proposed fix in two modes (tolerate, require), a no-op wherever a brief
  declares no program. `analysis/e5_brief_coverage.py` scores the E2 pairs
  (`report/data/e5_pairs.csv`) and the replication rows
  (`report/data/replication/e5_*.csv`); `tests/test_brief_coverage.py` covers it.

### Changed
- README leads with what the project is and what it found, in plain terms, with
  a worked example; status labels gain CURRENT for the replication.
- The STALE label on the original sweeps' navigability (sections 4 to 7) is
  withdrawn: rescored under the current metrics on the host holding the raw
  output, every committed table reproduced byte for byte.

### Fixed
- `tests/test_pool.py` pinned the derived scores of the original pooled corpus,
  so any metric fix failed it; it now pins the raw files and checks the scores
  against a fresh scoring.

## v1.0.0 — release-ready wrap-up

No model was re-run and no result table was regenerated for this release; the
report says which results held, which were withdrawn and which figures are stale.

### Fixed
- Navigability: a fixture whose footprint covers a door's interior point now
  makes that door-to-target pair unreached, instead of a reached pair with a
  zero-length path. The choice is a disclosed parameter,
  `nav_door_on_target_reached` (default `False`), in both parameter tables.
- Removed the unused `exp_eye_height_ft` parameter and its table rows.
- Corrected stale comments that described a navigability clamp which no longer
  exists; the per-pair ceiling is `nav_detour_cap`.

### Added
- `envelope-shift score-layout`: score one raw layout record and print its
  metrics, offline, defaulting to a committed fixture.
- `docs/offline.md`: the fresh-clone path (tests, parameter tables, scoring one
  layout) with no model, no key and no `results/`.
- A GitHub Actions workflow that runs the test suite on push.
- Guards: path length is never shorter than the straight line on any envelope;
  a fixture on the only door blocks it; no personal path, mailbox, internal repo
  name or UUID-shaped id in tracked text or fixtures.
- Report: a "Status of results" section (held, invalidated, stale), a matching
  note on each affected section, and two limitations (overlap & clearance
  depends on the placement convention; nothing was re-run after the last fixes).
- `docs/guild-case-study.md`: how the project was built and what that process
  got wrong and right.

### Changed
- The recorded Claude Code CLI fixture is replaced by a synthetic one of the
  same shape, with invented ids.
- An optional key file is now named by `ENVELOPE_SHIFT_KEYFILE` rather than a
  fixed path.
- Comments no longer carry tracker ids, personal names or internal project names.
- Every test that skips on a fresh clone says why.
- README rewritten around what the project is, its results status, a quickstart,
  and why it exists.

## Before v1.0.0

The harness, the six-tier test set, the metrics and the report were built in
September 2026, then rebuilt after adversarial review withdrew three of the first
draft's four headline results.
