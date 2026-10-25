# Changelog

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
