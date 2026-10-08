# Validation and interpretation

These checks establish reproducibility and software behavior, not independent scientific accuracy.

## Atmospheric observations

Actual authenticated Earth Engine exports are committed under `sources/`, with the exact scripts, collections, dates, area coordinates and radius. NO₂ covers 1 January to before 1 September 2026; CO/SO₂/regional CH₄ cover 1 August to before 1 October 2026. Atmospheric summaries average granules within each UTC day, reduce over 5 km circles and give each usable daily area mean equal weight. Missing days remain unknown; valid negative columns ≥ −0.001 mol/m² are retained. The shared Python parsers reproduce all daily, monthly and period values from the raw exports.

| Quantity | Dubai mean · usable days | Jebel Ali mean · usable days |
|---|---|---|
| NO₂ | 207.85140 µmol/m² · 226/243 | 206.66592 µmol/m² · 224/243 |
| CO | 36.33415 mmol/m² · 52/61 | 37.69829 mmol/m² · 60/61 |
| SO₂ | 145.82788 µmol/m² · 60/61 | 143.96175 µmol/m² · 60/61 |
| Regional CH₄ | 1966.92829 ppb · 33/61 | 1969.56098 ppb · 37/61 |

Different valid days and retrieval uncertainty prevent significance or source claims from these means alone. Map pixels average their own valid days, so map/table weighting may differ. Bundled NO₂ has area/history values without a raster overlay; the other three quantities include archived map outputs. Display colors are not safety thresholds.

## Methane evidence

The dated UAE record at 23.86479° N, 53.61893° E compares 22 September 2026 with 9 September: 0 candidate pixels and 96.04% common usable coverage. Coverage is not accuracy; no candidate does not establish zero methane. The public imagery adapter, reference selection and wind inputs remain experimental. The unchanged pretrained checkpoint is hash-pinned.

A distinct Dubai 29 September / 19 September local check flagged 206 pixels using a recorded GFS fallback; the repaired Colab check flagged 115 pixels. These are separate unreviewed candidates, not confirmed releases. Identical environmental inputs are not assumed. No claim of equivalent detector accuracy follows from the fallback.

## Reproducibility checks

- All 30 full-environment local software tests passed on 7 October 2026, including raw-export parity, missing/negative values, product/provenance checks, location handling and job transport. Lightweight CI skips optional widget checks when map dependencies are absent.
- Every PoC notebook cell executed with a fresh kernel in the pinned Python 3.12 environment, recomputing atmospheric inputs, checking expected results and exporting JSON/CSV. The methane record is replayed, not freshly inferred. Root notebook outputs and the evidence figure are visible.
- GitHub CI executes the credential-free PoC on Ubuntu using `requirements.txt`. The interactive notebook executed in saved-data mode in the full methane environment. Optional live dependencies are separate from the pinned runner.
- Website checks cover the four quantities, units, dates, coverage, available overlays and charts; actual PoC import and invalid NO₂ unit rejection work. Arbitrary points do not inherit a different location’s finding.

Run from the repository root:

```bash
python scripts/run_submission.py
python -m unittest discover -s tests -v
```

The PoC command needs the pinned root requirements. The full widget/inference checks require optional dependencies.

## Scientific and operational limits

Archived remote retrievals used the authenticated Earth Engine JavaScript equivalent. Fresh authenticated Python atmospheric queries still require a registered account/project and were not established by these checks. Software tests do not establish UAE accuracy, uncertainty intervals, source attribution, surface exposure, emissions or forecasting performance. Independent field validation needs gas-specific observations and held-out dates/locations.

The public website displays dated evidence. Fresh atmospheric calculations run in the notebook; methane checks can run through the active Colab embedded service. Unattended operation needs persistent hosting. Optional repeated image searches do not provide new satellite measurements every 15 minutes.

## Proposed scientific and user validation pilot

Status: planned, not completed. No reviewed methane-positive benchmark, detector precision/recall, three-user feedback record or partner commitment is established by the current evidence.

Scope: one willing environmental monitoring partner, one agreed area and four weeks after access is arranged. Extend collection if usable imagery or independent labels are insufficient. Ask for reviewed plume/no-plume cases, gas-specific field observations with acquisition times, and analyst participation. No field instrument is currently connected.

1. Agree the intended investigation decision, labeling protocol and numeric precision/recall and false-alarm acceptance thresholds before evaluation. Independent labels must not come from the detector itself. Retain uncertainty and exclude ambiguous labels from accuracy denominators while reporting their count.
2. Include positive cases and negative/cloud/surface confounders. Preserve acquisition dates, products, masks, wind and reference provenance. Define events and matching tolerances before scoring; avoid counting neighboring pixels or repeated checks as independent events.
3. Freeze preprocessing, reference-selection rules and engineering thresholds before the held-out evaluation. Separate development and evaluation dates/locations. If the cases cannot support this separation, report that limitation instead of claiming generalization.
4. Report reviewed event counts, true/false positives and negatives, event precision/recall where defined, and not-assessable counts separately. A zero denominator yields an undefined metric. No candidate and missing evidence must remain distinct. Compare atmospheric summaries on common usable dates as a sensitivity check before inferring differences.
5. Have at least three intended users complete the same review/export task with GeoGuard and their existing workflow; counterbalance task order where practical. Record task completion, review time and unit/date/unknown interpretation errors. Request consent for feedback and store identifiable records privately. Report actual counts and findings, including failures, without manufacturing interviews or benefit estimates.
6. Advance only after the pre-agreed scientific thresholds are met, every export can be traced to its original observation, and all three participants interpret the evidence correctly. Measured time savings, if any, remain pilot findings rather than guaranteed benefits. Persistent hosting and acquisition latency need separate operational checks before unattended use.

The team contribution is source-aware evidence integration and investigation handoff, not creation of Copernicus measurements or training the upstream MARS-S2L model. Hyperspectral data would be considered only if a comparison demonstrates a relevant improvement; it is not implemented or required for the current workflow.
