"""Build the credential-free, end-to-end judge entry point."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
cells = []

def md(text):
    cells.append(nbf.v4.new_markdown_cell(text))

def code(text):
    cells.append(nbf.v4.new_code_cell(text))

md('''# GeoGuard — Air Quality Intelligence
**Team:** GeoGuard · **Country:** Yemen · **Pilot:** UAE

This submission runs from bundled inputs to a website-compatible result without credentials,
network queries, model downloads or manual widget clicks. Run every cell in order.

It **recomputes NO₂ daily/monthly/period summaries from an actual Earth Engine export**
and packages a **previously executed, dated methane result**. It does not rerun methane
inference. Use `Geoguard.ipynb` for new imagery and interactive model checks.

NO₂ columns and methane candidates remain separate. Neither proves overall air safety.''')
code('''from pathlib import Path
import json, sys, math, csv
root = Path.cwd().resolve()
if not (root / 'geoguard').is_dir() and (root.parent / 'geoguard').is_dir():
    root = root.parent
assert (root / 'geoguard').is_dir(), 'Run from the cloned Geoguard repository.'
sys.path.insert(0, str(root))
from geoguard.no2 import unpack_stacked, summarize
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
md('''## 2. Attach the existing methane evidence
This is a replay of the UAE check observed on 22 September 2026 against 9 September,
at 23.86479° N, 53.61893° E. It is a different location and date from the NO₂ study.
Zero candidate pixels does not mean zero methane. 96.04% is usable coverage, not accuracy.
No new model inference or forecast is claimed.''')
code('''saved = json.loads((root / config['methane_source']).read_text(encoding='utf-8'))
methane = public_methane(saved['methane'])
print(json.dumps(methane, indent=2, ensure_ascii=False))''')
md('''## 3. Verify the numerical result against the committed example
The expected file is supplied for comparison. The calculations above use the raw
GeoJSON, not the expected means. Checks cover daily and monthly parity, missing-day
counts, and the location/date of the methane record.''')
code('''expected = json.loads((root / 'examples/expected_summary.json').read_text(encoding='utf-8'))
assert no2['sites'] == saved['no2']['sites'], 'Daily/monthly values differ from archived evidence'
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
result = export_bundle(output / 'result.json', no2, methane)
with (output / 'no2_summary.csv').open('w', newline='', encoding='utf-8') as handle:
    writer = csv.DictWriter(handle, fieldnames=['id', 'mean_mol_m2', 'valid_days', 'total_days'])
    writer.writeheader()
    writer.writerows({key: site[key] for key in writer.fieldnames} for site in no2['sites'])
assert json.loads(result.read_text(encoding='utf-8'))['schema'] == 'geoguard-demo-v1'
print('Complete: outputs/submission/result.json and no2_summary.csv')''')
md('''## Interpretation and next steps
The two close NO₂ averages alone do not establish a significant difference or a source.
Clouds, observation dates and retrieval uncertainty affect comparisons. The saved methane
record is evidence about one screened observation, not an air-quality verdict.

For fresh queries, open `Geoguard.ipynb`: Earth Engine sign-in is required for new NO₂
queries; the experimental methane workflow downloads public imagery and pretrained weights.
See `README.md`, `VALIDATION.md` and `THIRD_PARTY_NOTICES.md` for scope and provenance.''')
for index, cell in enumerate(cells):
    cell['id'] = f'submission-{index + 1}'
notebook = nbf.v4.new_notebook(cells=cells, metadata={
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python', 'version': '3.12'},
})
nbf.write(notebook, ROOT / 'Submission.ipynb')
