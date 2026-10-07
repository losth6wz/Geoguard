# GeoGuard — Satellite Air Quality Intelligence

Team: GeoGuard · Theme: Air Quality Intelligence · Pilot: UAE

GeoGuard uses satellite observations to explore atmospheric pollution and screen for methane-like patterns. A shared map connects location-specific measurements, history charts and image evidence, with clear units, observation dates and usable coverage.

[Demo website](https://losth6wz.github.io/Geoguard/) · [PoC notebook](PoC.ipynb) · [Open interactive notebook in Colab](https://colab.research.google.com/github/losth6wz/Geoguard/blob/main/Geoguard.ipynb)

## Measurements and outputs

| Quantity | Satellite method | Display |
|---|---|---|
| Nitrogen dioxide (NO₂) | Sentinel-5P tropospheric column; NRTI/OFFL | µmol/m², area comparisons and monthly history |
| Carbon monoxide (CO) | Sentinel-5P total atmospheric column; NRTI/OFFL | mmol/m², map layer, area comparisons and monthly history |
| Sulfur dioxide (SO₂) | Sentinel-5P vertical column; NRTI/OFFL | µmol/m², map layer, area comparisons and monthly history |
| Regional methane (CH₄) | Sentinel-5P bias-corrected dry-air column mixing ratio; OFFL | ppb, map layer, area comparisons and monthly history |
| Detailed methane screening | Sentinel-2 imagery and the pretrained MARS-S2L model | Candidate, no candidate or not assessable, with dated image evidence |

Choose a UAE location, atmospheric quantity, date window and comparison radius. Satellite summaries use 2–20 km circles; the bundled Dubai and Jebel Ali studies use 5 km. Detailed methane screening examines approximately 2 × 2 km around a selected land or island location.

The website quantity selector updates the map layer, legend, chart, table, units, dates and coverage together. JSON exports carry every calculated quantity with its own observation window and location. Selecting a new point shows a result only when matching evidence is available.

## Run the PoC

Use Python 3.12:

```bash
git clone https://github.com/losth6wz/Geoguard.git
cd Geoguard
python -m venv .venv
# Activate .venv for your operating system, then:
python -m pip install -r requirements.txt
python scripts/run_submission.py
```

The runner executes every cell in `PoC.ipynb`. It recalculates daily, monthly and period summaries from bundled real Earth Engine exports, verifies the results, and packages a dated methane-screening record with evidence images. It works without sign-in, satellite downloads or manual widget interaction after installing the dependencies. Fresh methane inference runs through the interactive notebook.

Outputs are written to `outputs/submission/`:

- `PoC-executed.ipynb`: the executed notebook.
- `result.json`: measurements and evidence ready to import into the website.
- `no2_summary.csv` and `measurements_summary.csv`: numerical summaries.

The [examples folder](examples/) contains input settings, expected summaries and executed outputs. Each measurement retains its own dates; the bundled NO₂ study covers January–August 2026, while CO, SO₂ and regional CH₄ cover August–September 2026.

## Explore and calculate fresh results

1. Open `Geoguard.ipynb` in Colab and select Run all. Setup may take several minutes.
2. Enter your registered Earth Engine project ID in Step 3 and complete sign-in for fresh atmospheric measurements. Leave it blank to explore bundled measurements and use the public-imagery methane workflow.
3. Choose a UAE location on the shared map. Select a quantity and calculate its history, or run the detailed methane check.
4. Export the results and import the JSON file into the demo website.
5. Run Step 5A to use the website with the methane detector connected inside Colab. Keep the runtime open while checks run, and download the evidence/history ZIP before disconnecting.

The public website displays dated evidence. Fresh atmospheric calculations run in the notebook; methane checks can also run through the connected Colab website. Optional repeated checks look for newly available imagery and do not create new satellite observations.

For local Jupyter, install the interactive dependencies in your activated environment:

```bash
python -m pip install -e ".[notebook,methane]" jupyterlab
jupyter lab Geoguard.ipynb
```

Fresh atmospheric queries require an Earth Engine account and registered project. See [Google’s authentication guide](https://developers.google.com/earth-engine/guides/auth). Colab runtime storage is temporary; downloaded exports preserve the evidence.

## How to interpret the evidence

Satellite columns describe gas through the atmosphere above an area, rather than ground-level exposure. SO₂ uses an assumed ground-level vertical profile; this does not make its output a surface concentration. Regional CH₄ is a column-averaged mixing ratio and remains separate from detailed methane-screening scores.

Atmospheric processing averages available granules within each UTC day, reduces valid grid cells over each comparison circle, and gives usable daily area values equal weight in monthly and period summaries. Missing days remain unknown; valid negative columns are retained above the documented −0.001 mol/m² cutoff. Map pixels average their own valid days, so map and area-table weighting can differ. Colors are display scales, not safety thresholds, and transparent cells indicate missing data.

A methane candidate needs analyst review. No candidate does not establish zero methane, and usable coverage is not model accuracy. The detector uses score >0.5 and at least 100 connected processing pixels. Its 10 m processing grid does not add detail to native 20 m shortwave-infrared measurements.

Different observation dates, valid coverage and satellite footprints limit comparisons. GeoGuard does not produce AQI, an emission rate, source attribution or a health-safety verdict. PM, VOC and H₂S instruments are not connected. Independent UAE detection accuracy and forecasting remain unvalidated.

## Project resources

- [PoC notebook](PoC.ipynb): reproducible analysis using bundled inputs.
- [Interactive notebook](Geoguard.ipynb): map controls, fresh satellite queries and methane screening.
- [Source data and scripts](sources/): satellite exports and reproducible Earth Engine calculations.
- [Validation](VALIDATION.md): executed checks and scientific limitations.
- [Attribution and terms](THIRD_PARTY_NOTICES.md): data, model and software credits and reuse conditions.

Measurement references: [NO₂](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_NRTI_L3_NO2), [CO](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_NRTI_L3_CO), [SO₂](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_NRTI_L3_SO2), [regional CH₄](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_OFFL_L3_CH4) and [MARS-S2L](https://github.com/UNEP-IMEO-MARS/marss2l).
