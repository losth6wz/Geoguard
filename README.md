# GeoGuard — Air Quality Intelligence

**Team:** GeoGuard · **Country:** Yemen · **Theme:** Air Quality Intelligence
**Project title:** GeoGuard: Satellite Air Quality Evidence for the UAE

**One-line summary:** GeoGuard combines Sentinel-5P nitrogen dioxide histories with experimental Sentinel-2 methane screening to present dated, location-specific evidence for environmental investigation, while keeping missing data and uncertainty visible.

**[Demo website](https://losth6wz.github.io/Geoguard/) · [Submission notebook](Submission.ipynb) · [Interactive notebook](Geoguard.ipynb)**

## Reproduce the submission end to end

Use Python 3.12. Clone this public repository, then run:

```bash
git clone https://github.com/losth6wz/Geoguard.git
cd Geoguard
python -m venv .venv
# Activate .venv for your operating system, then:
python -m pip install -r requirements.txt
python scripts/run_submission.py
```

The runner executes every cell in `Submission.ipynb` and writes an executed notebook, `result.json` and `no2_summary.csv` to `outputs/submission/`. Open the notebook in any Jupyter-compatible editor to inspect or run individual steps. No sign-in, API key, imagery download or manual UI interaction is required after installing the runner dependencies.

This reproducible path recalculates NO₂ summaries from the bundled actual Earth Engine export and packages an existing dated methane result. **It does not perform fresh methane inference.** The separate `Geoguard.ipynb` supports new model checks and interactive NO₂ queries; see the live workflow below.

## Submission checklist

| Form requirement | Repository evidence / status |
|---|---|
| README.md | This page: purpose, setup, workflow, outputs and limitations |
| End-to-end Jupyter notebook | [Submission.ipynb](Submission.ipynb), executable with the command above |
| Pinned requirements.txt | [requirements.txt](requirements.txt): exact runner dependencies, including resolved transitive packages |
| Example input | [examples/input.json](examples/input.json) and [actual NO₂ export](sources/no2_earthengine_export.geojson) |
| Example output | [expected numerical summary](examples/expected_summary.json), [website-compatible output](examples/result.json) and [executed notebook](examples/Submission-executed.ipynb) |
| No credentials or restricted imagery | Submission uses public Sentinel-derived numerical records; no raw satellite imagery or model weights are bundled. See source terms below. |
| Organizer access | Public repository: https://github.com/losth6wz/Geoguard |
| Presentation slides | Upload a PDF (maximum 50 MB) separately in the submission form; not provided by this repository update |
| Optional supporting archive | Form permits a ZIP up to 200 MB; GitHub source ZIP is available from Code → Download ZIP |

The screenshot is the checklist used here. Its linked submission guide was not supplied, so guide-specific requirements and whether judges require fresh inference in the noninteractive notebook remain unverified. Team membership/registration and final form submission must be completed in the organizer portal.

## Example results and provenance

| Area / observation | Result |
|---|---|
| Dubai NO₂, January–August 2026 | 0.00020785140195749016 mol/m²; 226/243 usable days |
| Jebel Ali NO₂, January–August 2026 | 0.0002066659235326792 mol/m²; 224/243 usable days |
| Saved UAE methane check, 22 September 2026 | 0 candidate pixels; 96.04% usable coverage; reference 9 September |

NO₂ is an atmospheric column, not AQI or ground-level exposure. Methane screening is experimental; no candidate does not prove absence. The methane example is at its own recorded location, not either NO₂ comparison point. These products are not combined into a safety score. Original exports and source scripts are in `sources/`; attribution and reuse conditions are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Interactive and fresh-imagery workflow

A single guided notebook and a small website combining **the Sentinel-5P nitrogen dioxide analysis** with **the existing Sentinel-2 methane screening workflow** for the UAE.

**[Open the demo](https://losth6wz.github.io/Geoguard/) · [Open the notebook in Colab](https://colab.research.google.com/github/losth6wz/Geoguard/blob/cea5cfc/Geoguard.ipynb)**

## Start

1. Open the notebook and press **Run all**. Initial software/model setup may take several minutes.
2. Leave the Earth Engine project blank for saved examples, or enter your registered project ID and complete sign-in to calculate fresh NO₂ values.
3. Choose a UAE point on the shared map. The NO₂ and methane controls appear directly below the map.
4. Run **Step 5A** to open the website connected to the AI inside Colab. Choose a point and press **Check latest satellite image**. Results return automatically. Manual JSON export/import remains available.
5. Download the methane evidence/history ZIP before closing Colab. Runtime storage is temporary.

The public GitHub Pages website offers saved evidence and a **Start AI in Colab** link. Step 5A serves the same website through Colab's authenticated output frame with a Python AI service behind it. Colab must remain connected. This is an on-demand latest-image check, not unattended monitoring. A selected location is never silently moved to a prepared example. NO₂ calculations remain in the notebook.

## What the original NO₂ code does

It marks two Dubai points and draws the mean Sentinel-5P tropospheric NO₂ column from 1 January through 31 August 2026. The end date `2026-09-01` is excluded. It does not calculate the two area means, train a model, or identify pollution sources. The original supplied Arabic-commented code is unchanged in [sources/no2_original.js](sources/no2_original.js).

Our extension adds selectable areas, 5 km comparison circles, daily and monthly histories, missing-data counts, and an export the website understands. Available granules are averaged per day before area reduction; valid days receive equal weight in summaries. This aggregation differs deliberately from the original direct collection mean. Negative retrievals are preserved except the catalog's documented extreme-outlier cutoff; valid masks are inherited from the catalog.

## What each result means

| View | Output | What it does not establish |
|---|---|---|
| Sentinel-5P NO₂ | Atmospheric column in mol/m²; area/time comparison | Ground-level concentration, AQI, source attribution, health safety |
| Sentinel-2 MARS-S2L | Experimental candidate / no candidate / not assessable | Methane density, emission rate, independently validated UAE accuracy |
| History | Dated observations and unknowns | A trained or validated UAE forecast |

The two gases are not merged into one pollution score. NO₂'s L3 grid is about 1.1 km but this is not native instrument resolving power. Methane's 20 m SWIR measurements are processed on a 10 m grid, adding no measurement detail. Model flags require score >0.5 and at least 100 connected processing pixels. The earlier reference is not independently proven methane-free.

## Local Jupyter

Python 3.10+ (the existing methane workflow was tested with Python 3.12):

```bash
git clone https://github.com/losth6wz/Geoguard.git
cd Geoguard
python -m venv .venv
# Activate .venv for your operating system, then:
python -m pip install -e ".[notebook,methane]" jupyterlab
jupyter lab Geoguard.ipynb
```

An Earth Engine account and registered project are required for fresh NO₂ queries. [Official setup](https://developers.google.com/earth-engine/guides/auth). A shared Code Editor script URL does not itself grant another user account/project access. No account secrets are included in this repository.

## Website and tests

```bash
python -m http.server 8767 --directory docs --bind 127.0.0.1
python -m unittest discover -s tests -v
```

GitHub Pages serves `docs/` on `main`. Python runs in Jupyter/Colab, not on GitHub Pages. Larger model weights, satellite crops, local runtime history and credentials are excluded from Git. The runtime downloads the unchanged upstream checkpoint and verifies its fingerprint.

## Files

- `Geoguard.ipynb`: one guided entry point; generated by `scripts/build_notebook.py`.
- `geoguard/`: NO₂ calculations, shared export format and notebook interface.
- `live_detection/`, `guided_colab/`: previously tested methane acquisition, preprocessing, model, history and UI.
- `docs/`: static website and clearly dated saved evidence.
- `sources/`: the supplied NO₂ code and reproducible Earth Engine export script.
- `tests/`: missing-data, date, export, notebook and application checks.
- `VALIDATION.md`: what was executed in this integration and what remains unverified.

See [third-party attribution and terms](THIRD_PARTY_NOTICES.md). This hackathon prototype is not a validated environmental enforcement or health advisory system.

## Connected AI service

Step 5A starts an asynchronous Python service with the unchanged MARS-S2L detector. One job runs at a time; the page polls progress and displays only results matching the selected coordinates. Session tokens protect requests, no cross-origin access is enabled, and only public result fields leave the service. Model evidence/history lives under `runtime/web/` in this mode; copy that folder before disconnecting to preserve it. Runtime restarts clear in-memory job status.

For a local equivalent: `python -m geoguard.server`, then open http://127.0.0.1:8768. This binds only to your computer. Colab uses `serve_kernel_port_as_iframe`; its separately opened-window helper is deprecated by Google. No public tunnel or cloud account is required. The embedded page is for your active Colab session, not an always-on shared public backend.
