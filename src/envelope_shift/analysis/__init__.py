"""Analysis scripts over the scores.jsonl written by `envelope-shift score`.

    uv run python -m envelope_shift.analysis.e1_degradation  results/scores.jsonl out/
    uv run python -m envelope_shift.analysis.e3_disagreement results/scores.jsonl out/
    uv run python -m envelope_shift.analysis.e4_correlation  results/scores.jsonl out/
    uv run python -m envelope_shift.analysis.e2b_bestofn     results/scores.jsonl out/

Each writes one CSV and one PNG into the output directory and prints a short
summary. matplotlib + numpy only. `make_tiny_fixture` regenerates the
synthetic fixtures under tests/fixtures/ used by tests/test_analysis.py.
"""
