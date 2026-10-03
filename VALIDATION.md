# Integration validation

Recorded 4 October 2026, Asia/Dubai. These checks establish software behavior, not environmental detection accuracy.

## Executed

- The equivalent NO₂ calculation in `sources/no2_verified_export.js` ran against real Sentinel-5P NRTI data in an authenticated Earth Engine Code Editor. The raw two-area export is preserved in `sources/no2_earthengine_export.geojson`.
- Each area has 243 requested daily entries for 2026-01-01 through 2026-08-31. Dubai has 226 usable days and a period mean of 0.00020785140195749016 mol/m²; Jebel Ali has 224 usable days and 0.0002066659235326792 mol/m². These are means of valid daily area values, not ground-level measurements. Unequal observation days and retrieval uncertainty prevent a source or significance conclusion from these averages alone.
- The shared Python parser regenerated the saved site's complete daily/monthly results from that raw export. A regression check compares the values exactly.
- **15 local tests passed**, including date bounds, missing/negative values, area validation, private-field exclusion, saved-evidence provenance, notebook validity and widget state changes. Lightweight CI skips three widget tests when optional map dependencies are absent.
- The entire notebook executed in the existing Python 3.12 methane environment with Earth Engine sign-in skipped and dependency installation skipped. The shared interface instantiated successfully. The executed copy is retained locally, not published with runtime state.
- Website browser checks passed for Dubai and Jebel Ali values, the saved methane location, arbitrary-coordinate empty results and JSON import. A new point never inherits the saved methane finding.
- Seven migrated source/boundary files match the earlier tested project byte-for-byte. The unchanged methane checkpoint remains hash-pinned. The saved Colab result from September 23 is 0 flagged pixels / 96.04% common usable coverage for the September 22 observation; its image date is shown explicitly.

## Boundaries of this verification

- The authenticated NO₂ backend run used the JavaScript equivalent. Fresh authentication and a complete new NO₂ query through this Python notebook were not executed in this integration session. They require the user's Earth Engine project and sign-in. The Python implementation uses the same stacked-daily-band reduction that produced the saved export.
- A naive reduction per day exceeded Earth Engine's concurrent-aggregation quota. The final implementation stacks daily bands and performs one multi-band reduction per area instead.
- A fresh clean-environment dependency install and a fresh methane image inference were not repeated. The previous working inference modules were preserved, and the new notebook was exercised in their existing environment.
- No UAE methane accuracy, pollution-source attribution, health classification or operational forecasting claim has been validated. Forecast history is retained; no future probability is invented.
- The website is static. Fresh calculations occur in Jupyter/Colab, with export/import to the website. No unattended backend service or every-few-minutes satellite measurement is claimed.

## Connected service — 2026-10-04

Added same-origin website requests, asynchronous job status, bounded one-job execution, location-aware result rendering, public-field filtering and Colab embedded service startup. All 20 local tests pass, including unauthorized-request rejection, invalid-host and invalid-coordinate rejection, concurrent-job rejection and job/result transport. The job transport test uses an explicit test engine, not scientific inference. Local browser integration is tested separately with the real detector. Colab session startup and a successful fresh model inference must not be inferred from these tests.

Colab integration follows Google's `serve_kernel_port_as_iframe` implementation: https://github.com/googlecolab/colabtools/blob/main/google/colab/output/_util.py . The old window-opening helper is deprecated.

The real local browser check at 25.2048 N, 55.2708 E completed through the API: candidate, 206 flagged pixels, 96.04% common usable coverage, current image 2026-09-29 and reference 2026-09-19. This is a model candidate requiring review, not confirmation of a methane release. The actual result and evidence are retained in ignored runtime/web/.

The local test used the existing experimental NOAA GFS wind fallback after GEOS-FP timed out; equivalent detector accuracy has not been validated. The website now displays a fallback label when recorded.
