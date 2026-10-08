"""Build the credential-free, end-to-end judge entry point."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
cells = []

def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))

def code(text):
    cells.append(nbf.v4.new_code_cell(text))

md('''# GeoGuard — PoC Notebook
Team: GeoGuard · Theme: Air Quality Intelligence · Pilot: UAE

This submission runs from bundled inputs to a website-compatible result without credentials,
network queries, model downloads or manual widget clicks. Run every cell in order.

It recomputes NO₂, CO, SO₂ and regional CH₄ daily/monthly/period summaries from actual Earth Engine exports
and packages a previously executed, dated methane result. It does not rerun methane
inference. Use `Geoguard.ipynb` for new imagery and interactive model checks.

Atmospheric columns, regional methane and detailed methane candidates remain separate. Neither proves overall air safety.''')
code('''from pathlib import Path
import json, sys, math, csv, base64, random
random.seed(0)  # The bundled calculations are deterministic; no training is performed.
root = Path.cwd().resolve()
if not (root / 'geoguard').is_dir() and (root.parent / 'geoguard').is_dir():
    root = root.parent
assert (root / 'geoguard').is_dir(), 'Run from the cloned Geoguard repository.'
sys.path.insert(0, str(root))
from geoguard.no2 import unpack_stacked, summarize
from geoguard.measurements import summarize_export, METRICS
from geoguard.core import SITES, public_methane, export_bundle
config = json.loads((root / 'examples/input.json').read_text(encoding='utf-8'))
print(json.dumps(config, indent=2))''')
md('''## 1. Read the example input and calculate NO₂ history
The source contains daily spatial reductions for two 5 km circles, January–August 2026.
Missing days stay unknown. Negative valid retrievals are retained. Each usable day
has equal weight in the period mean. Units are mol/m² through the atmospheric column,
not ground-level concentration or AQI.''')
code('''raw = json.loads((root / config['no2_source']).read_text(encoding='utf-8'))
rows = unpack_stacked(raw['features'], config['start'], config['end_exclusive'])
no2 = summarize(rows, SITES, config['start'], config['end_exclusive'],
                config['radius_m'], config['collection'])
for site in no2['sites']:
    print(f"{site['name']}: {site['mean_mol_m2']:.12g} mol/m²; "
          f"{site['valid_days']}/{site['total_days']} usable days")''')
md('''## 1A. Calculate CO, SO₂ and regional CH₄
CO and SO₂ are atmospheric columns; regional CH₄ is a column-averaged dry-air
mixing ratio in ppb. These measured quantities use August–September 2026,
not the January–August NO₂ window. The raw source includes their identities,
coordinates, radius, dates and valid-pixel counts. CH₄ uses OFFL only.
PM, VOC and H₂S measurements require inputs or sensors that have not been connected.
Satellite aerosol index is an indirect aerosol indicator, not measured PM mass.''')
code('''raw_extra = json.loads((root / config['measurements_source']).read_text(encoding='utf-8'))
measurements = {}
for metric in ['CO', 'SO2', 'CH4']:
    features = [f for f in raw_extra['features'] if f['properties']['metric'] == metric]
    value = summarize_export(features, metric, SITES, config['measurements_start'],
        config['measurements_end_exclusive'], config['radius_m'], 'OFFL' if metric == 'CH4' else 'NRTI')
    measurements[metric] = value
    spec = METRICS[metric]
    for site in value['sites']:
        mean = site['mean_value']
        print(metric, site['name'], None if mean is None else mean * spec['display_factor'],
            spec['display_units'], f"{site['valid_days']}/{site['total_days']} usable days")''')
md('''## 2. Display the dated methane evidence
This is a replay of the UAE check observed on 22 September 2026 against 9 September,
at 23.86479° N, 53.61893° E. It is a different location and date from the NO₂ study.
Zero candidate pixels does not mean zero methane. 96.04% is usable coverage, not accuracy.
No new model inference or forecast is claimed.''')
code('''saved = json.loads((root / config['methane_source']).read_text(encoding='utf-8'))
figure = 'data:image/png;base64,' + base64.b64encode((root / 'docs/assets/uae-example.png').read_bytes()).decode()
methane = public_methane(saved['methane'], figure)
print(json.dumps({k:v for k,v in methane.items() if k != 'figure_data'}, indent=2, ensure_ascii=False))
from IPython.display import display, Image
display(Image(filename=str(root / 'docs/assets/uae-example.png'), width=900))''')
md('''## 3. Verify the numerical result against the committed example
The expected file is supplied for comparison. The calculations above use the raw
GeoJSON, not the expected means. Checks cover daily and monthly parity, missing-day
counts, and the location/date of the methane record.''')
code('''expected = json.loads((root / 'examples/expected_summary.json').read_text(encoding='utf-8'))
assert no2['sites'] == saved['no2']['sites'], 'Daily/monthly values differ from archived evidence'
for metric, value in measurements.items():
    assert value['sites'] == saved['measurements'][metric]['sites']
    assert value['units'] == METRICS[metric]['units']
    for site, reference in zip(value['sites'], expected['measurements'][metric]):
        assert site['id'] == reference['id']
        assert math.isclose(site['mean_value'], reference['mean_value'], rel_tol=1e-12)
        assert site['valid_days'] == reference['valid_days']
        assert site['total_days'] == reference['total_days']
    # Maps are archived real Earth Engine outputs; recalculation above is numerical.
    value['map'] = saved['measurements'][metric]['map']
    value['source_export'] = config['measurements_source']
    value['retrieved_at'] = saved['measurements'][metric]['retrieved_at']
for site, reference in zip(no2['sites'], expected['no2']):
    assert site['id'] == reference['id']
    assert math.isclose(site['mean_mol_m2'], reference['mean_mol_m2'], rel_tol=1e-12)
    assert site['valid_days'] == reference['valid_days']
    assert site['total_days'] == reference['total_days']
for key, value in expected['methane'].items():
    assert methane[key] == value, key
print('Example checks passed.')''')
md('''## 4. Export the output
`outputs/submission/result.json` can be imported into the demo website.
The CSV provides a compact table. Generation timestamps change each run;
the source observation dates and numerical results do not.''')
code('''output = root / 'outputs/submission'
output.mkdir(parents=True, exist_ok=True)
result = export_bundle(output / 'result.json', no2, methane, measurements)
with (output / 'no2_summary.csv').open('w', newline='', encoding='utf-8') as handle:
    writer = csv.DictWriter(handle, fieldnames=['id', 'mean_mol_m2', 'valid_days', 'total_days'])
    writer.writeheader()
    writer.writerows({key: site[key] for key in writer.fieldnames} for site in no2['sites'])
with (output / 'measurements_summary.csv').open('w', newline='', encoding='utf-8') as handle:
    fields = ['metric', 'id', 'mean_value', 'units', 'start', 'end_exclusive', 'valid_days', 'total_days']
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    for metric, value in measurements.items():
        for site in value['sites']:
            writer.writerow({**{k: site[k] for k in ['id', 'mean_value', 'valid_days', 'total_days']},
                **{k: value[k] for k in ['units', 'start', 'end_exclusive']}, 'metric': metric})
assert json.loads(result.read_text(encoding='utf-8'))['schema'] == 'geoguard-demo-v1'
print('Complete: result.json, no2_summary.csv and measurements_summary.csv')''')
md('''## Interpretation and next steps
The two close NO₂ averages alone do not establish a significant difference or a source.
Clouds, observation dates and retrieval uncertainty affect comparisons. The saved methane
record is evidence about one screened observation, not an air-quality verdict.

For fresh queries, open `Geoguard.ipynb`: Earth Engine sign-in is required for fresh satellite
queries; the experimental methane workflow downloads public imagery and pretrained weights.
See `README.md`, `VALIDATION.md` and `THIRD_PARTY_NOTICES.md` for scope and provenance.''')
md('''## Investigation demonstration and proposed validation
Import `outputs/submission/result.json` into the website. Select Dubai and NO₂,
review units, January–August dates and 226/243 usable days, and compare Jebel Ali
and the monthly history. The mean difference alone is inconclusive. Select the
separate methane example to inspect its dated no-candidate record.

Use Download current evidence to save the selected location, quantity and matching
records with a follow-up note. An unmeasured point remains unknown. Candidates
need analyst review before calibrated, gas-specific observations matched to
satellite time and footprint.

The team's contribution is source-aware evidence integration and investigation
handoff. Copernicus supplies the observations; UNEP IMEO supplies the pretrained
detector. Easier evidence assembly is a proposed benefit, not measured time savings.

Proposed pilot: one willing monitoring partner, one agreed area and four weeks after
data access is arranged. Independently review positive/no-plume and confounder
cases, freeze thresholds, and evaluate held-out dates/locations. Report event counts,
precision/recall and not-assessable cases where labels support them. Three intended
users should compare review/export with their existing workflow; record time,
completion and interpretation errors. Agree scientific acceptance targets first.
No partner commitment, independent UAE detection accuracy or completed user
feedback is established. Full protocol and success gates are in `VALIDATION.md`.''')
for index, cell in enumerate(cells):
    cell['id'] = f'submission-{index + 1}'
notebook = nbf.v4.new_notebook(cells=cells, metadata={
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python', 'version': '3.12'},
})
destination = ROOT / 'PoC.ipynb'
# Retain visible execution only when every cell still has the same source.
# A changed analysis must be run again before publishing its outputs.
if destination.exists():
    previous = nbf.read(destination, as_version=4)
    if [(c.cell_type, c.source) for c in previous.cells] == [(c.cell_type, c.source) for c in notebook.cells]:
        for cell, old in zip(notebook.cells, previous.cells):
            if cell.cell_type == 'code':
                cell.outputs = old.outputs
                cell.execution_count = old.execution_count
nbf.write(notebook, destination)
