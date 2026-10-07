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

The published d830e23 notebook was executed in Google Colab with dependency installation enabled. Its embedded website loaded and showed AI service connected. GitHub Pages links are pinned to this corrected notebook version to avoid a previously cached main notebook.

## Colab catalogue failure repair — 2026-10-04

Reproduced the reported failure: CDSE returned HTTP 200 HTML Request Rejected to Colab; its OData endpoint returned 403. No model inference had begun. Verified Earth Search returns valid GeoJSON for the same explicit L1C product from Colab. Added a provenance-recorded fallback and clear unavailable-catalogue errors. No model, thresholds or radiometric preprocessing were changed. All 24 local tests pass, including HTML-response fallback, exact SAFE identity, no L2A substitution, empty-result handling and both-providers-unavailable handling. The original migration manifest is a historical baseline; acquisition.py and engine.py have now changed to repair catalogue access.

Earth Search returned a next link even for a 23-item page; its following page was empty. Added bounded same-provider GET pagination instead of treating a next link as failure. All 25 local tests pass, including this exact short-page case.

Full repaired Colab website-to-model run completed successfully at 25.2048 N, 55.2708 E: candidate, 115 flagged pixels, 96.04% usable coverage, current 2026-09-29 and reference 2026-09-19. Result was observed in the actual embedded website. This is an unreviewed candidate, not confirmed emissions; it differs from the previous local run and no identical environmental inputs are assumed.
# Submission packaging — 7 October 2026

- Added a separate credential-free `PoC.ipynb`; every cell executed successfully under Python 3.12.14. It recalculates actual archived NO₂ data and replays dated methane evidence, without claiming fresh inference.
- All 25 existing tests passed. Submission assertions checked exact daily/monthly parity with the archived NO₂ evidence, expected means/counts and methane location/date/result.
- Added example input, numerical reference, actual exported JSON and executed notebook. The notebook exports both JSON and CSV.
- Common credential-signature scan of tracked text and new submission artifacts found no matches. This is not proof against every possible secret. No raw satellite images or model weights were added.
- Repository visibility was confirmed PUBLIC. The portal's linked submission guide and presentation PDF were not supplied; no portal submission or new scientific validation was performed.

Clean-environment check: created a new Python 3.12 virtual environment, installed the pinned runner requirements, and executed the complete submission notebook successfully. The full resolved runner environment is pinned in requirements.txt. Optional interactive/live inference dependencies are separate.

## Feasible pollution measurements — 7 October 2026

Added CO and SO₂ atmospheric columns and albedo-bias-corrected regional CH₄ dry-air mixing ratio, using documented Sentinel-5P products. CH₄ uses OFFL only. Ground PM, VOC and H₂S instruments/data have not been connected; aerosol index is not treated as direct PM mass. Existing NO₂ and experimental Sentinel-2 methane screening remain separate.

The authenticated Earth Engine calculation retrieves 61 daily slots during 2026-08-01 to before 2026-10-01 in the Dubai/Jebel Ali 5 km circles. Actual raw reductions and map PNGs are committed, rather than generated demonstration numbers. The shared Python parser reproduces complete daily/monthly/period outputs. Means and usable days are:

| Quantity | Dubai | Jebel Ali |
|---|---|---|
| CO | 0.03633414750830455 mol/m²; 52/61 | 0.0376982856798005 mol/m²; 60/61 |
| SO₂ | 0.00014582788242312894 mol/m²; 60/61 | 0.0001439617467042297 mol/m²; 60/61 |
| Regional CH₄ | 1966.9282903751287 ppb; 33/61 | 1969.5609751337006 ppb; 37/61 |

NO₂ keeps its January–August example window. Display conversions are ×1,000,000 for NO₂/SO₂ columns and ×1,000 for CO; regional CH₄ stays ppb. New map legends state native quantity, converted display scale and missing-data meaning. Map pixels average their own usable days; area tables weight usable daily spatial means equally, so maps and tables can have different weights.

Executed checks:

- All 30 local software tests pass, including actual-export parity, negative/missing values, zero-pixel exclusions, product/provenance rejection and widget state changes. Optional widget tests skip in lightweight CI.
- All PoC notebook cells execute in the existing clean Python 3.12 runner environment, recomputing raw inputs, checking expected results and exporting all quantities to JSON/CSV. This replays dated methane evidence without fresh inference.
- All interactive notebook cells execute locally with optional sign-in skipped and installation skipped. The existing full methane environment supplies its dependencies; no new independent inference is claimed.
- Browser checks confirm each added quantity's value, unit, dates, coverage, map overlay, scale and chart; website import of the PoC output, rejection of incorrect quantity units, legacy NO₂-only import and explicit empty results at arbitrary new coordinates work.

Remote retrieval used the exact published JavaScript equivalent in an authenticated Code Editor. A fresh authenticated Python query was not executed: it still requires the user's registered Earth Engine account/project. Independent UAE accuracy, uncertainty intervals, source attribution, surface exposure and forecasting are not established by software checks. Different valid days and native footprints limit comparisons. The final shared report preserves the earlier AI section and figure and places the integrated case study on its last page.
