# PoC inputs and outputs

- `input.json`: reproducible study configuration and source paths.
- `../sources/no2_earthengine_export.geojson`: actual two-area Earth Engine export, archived 4 October 2026; source collection and date range are in the configuration. No authentication is needed to read it.
- `../docs/data/demo.json`: previously published dated evidence, including the methane result. The submission replays this result; it does not rerun the detector.
- `expected_summary.json`: committed reference means, coverage counts, location and dates used for assertions.
- `result.json`: actual submission-run export, importable through the website's JSON import control.
- `PoC-executed.ipynb`: actual execution with outputs for inspection.

Run `python scripts/run_submission.py` from the repository root to regenerate outputs under `outputs/submission/`. Export/retrieval timestamps reflect the processing run, not new satellite observations. The original observation dates remain in the evidence.

See `../THIRD_PARTY_NOTICES.md` for source attribution and reuse terms. The example carries derived numerical records, not raw imagery or model weights.
