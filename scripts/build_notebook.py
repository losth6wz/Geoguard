"""Generate the single, readable Jupyter/Colab entry point."""
from pathlib import Path
import ast
import json

ROOT=Path(__file__).resolve().parents[1]
cells=[]
def add(kind,source):
    c={'cell_type':kind,'id':f'geoguard-{len(cells)+1}','metadata':{},'source':source.strip().splitlines(keepends=True)}
    if kind=='code':ast.parse(source.strip());c.update(outputs=[],execution_count=None)
    cells.append(c)

add('markdown','''# GeoGuard — Atmospheric measurements and methane screening

One notebook, two questions: how do NO₂, CO, SO₂ and regional CH₄ vary across larger areas, and does a detailed image contain a methane-like pattern?

The Sentinel-5P workflow supplies four separately measured atmospheric quantities. The Sentinel-2 workflow supplies the pretrained methane detector. We keep their measurements separate, like two instruments on one dashboard: they look at different gases and cannot be averaged into a meaningful “pollution score”.

Press Run all, then use the shared map in Step 5. The initial setup can take several minutes. A CPU runtime is enough. Saved results work without Earth Engine sign-in; new satellite queries need a registered Earth Engine project. Methane queries use public imagery without that account.

This is a research prototype. A red map colour is not a health threshold, and no methane candidate is not proof of clean air.''')
add('markdown','''## Step 1 — Get the project
If you cloned the repository, this uses your local files. When opened directly in Colab, it downloads the public repository. Your original notebooks stay unchanged.''')
add('code','''from pathlib import Path
import os, sys, urllib.request, zipfile

root=Path.cwd()
def current_checkout(path):
    service=path/'geoguard/server.py'
    return service.exists() and 'COLAB_PROXY_V5' in service.read_text(encoding='utf-8') and (path/'geoguard/measurements.py').exists()
if not current_checkout(root):
    if current_checkout(root.parent):
        root=root.parent
    else:
        import tempfile, time
        destination=Path(tempfile.mkdtemp(prefix='geoguard_checkout_'))
        archive=destination/'geoguard-main.zip'
        urllib.request.urlretrieve('https://github.com/losth6wz/Geoguard/archive/refs/heads/main.zip?fresh='+str(time.time_ns()),archive)
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if not (destination/name).resolve().is_relative_to(destination):
                    raise ValueError('Unsafe archive member')
            z.extractall(destination)
        root=destination/'Geoguard-main'
os.chdir(root)
sys.path.insert(0,str(root))
# Forget modules from an older checkout without deleting its files or history.
old_service=sys.modules.get('geoguard.server')
if old_service and getattr(old_service, '_service', None):
    old_service._service.shutdown()
    old_service._service.server_close()
for module in list(sys.modules):
    if module.split('.')[0] in ('geoguard', 'live_detection'):
        del sys.modules[module]
print('Project ready:',root.name)''')
add('markdown','''## Step 2 — Prepare the tools
This installs the map, Earth Engine interface and the pretrained methane-model software. It does not train a new AI. The model weights are downloaded only when needed and checked against a recorded fingerprint.''')
add('code','''import subprocess
# GEOGUARD_SKIP_INSTALL is only used by the repository's automated notebook check.
if os.environ.get('GEOGUARD_SKIP_INSTALL')!='1':
    subprocess.check_call([sys.executable,'-m','pip','install','-q','-e','.[notebook,methane]'])
try:
    from google.colab import output
    output.enable_custom_widget_manager()
except ImportError:
    pass  # Ordinary Jupyter supports widgets directly.
print('Tools ready.')''')
add('markdown','''## Step 3 — Enable fresh satellite calculations (optional)
Earth Engine is Google's service that processes satellite images. Its project ID identifies your registered workspace; it is not a password. Find it in the top-right project selector in the [Earth Engine Code Editor](https://code.earthengine.google.com/).

To query new satellite data, put your project ID between the quotes below and run this cell. Complete Google's sign-in when asked. Leave it blank to explore the saved study and use the public methane workflow. Do not paste passwords or service-account keys into the notebook. After changing this step, rerun Step 5.

[Official authentication instructions](https://developers.google.com/earth-engine/guides/auth)''')
add('code','''EE_PROJECT = ""  # Example shape: my-earth-engine-project. Use your own actual ID.
ee_ready=False
if EE_PROJECT.strip():
    import ee
    try:
        ee.Initialize(project=EE_PROJECT.strip())
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=EE_PROJECT.strip())
    ee_ready=True
    print('Earth Engine connected.')
else:
    print('Saved study mode. Fresh satellite queries are off; methane screening is still available.')''')
add('markdown','''## Step 4 — Understand the saved evidence
These are dated results at their recorded locations. They do not follow the map pointer.

GeoGuard averages valid Sentinel-5P granules within each UTC day, reduces them over the comparison circles, then gives usable daily values equal weight in monthly and period means. Bundled circles have 5 km radius. Missing days remain unknown; valid negative columns are retained above −0.001 mol/m². Raseel’s mapping script is preserved in `sources/no2_original.js` as source attribution. Satellite columns do not measure surface concentration or prove a source.

CO, SO₂ and regional CH₄ were retrieved through authenticated Earth Engine on 7 October 2026 for August–September in the same 5 km comparison areas. The saved NO₂ window remains January–August. Each quantity keeps its own units, dates and coverage.

The saved methane check observed its UAE location on 22 September 2026, compared it with 9 September, and flagged 0 candidate pixels with 96.04% usable coverage. That percentage is coverage, not accuracy.''')
add('code','''import json
from IPython.display import display, Image
saved=json.loads(Path('docs/data/demo.json').read_text(encoding='utf-8'))
if saved.get('no2'):
    import pandas as pd
    display(pd.DataFrame([{'Area':s['name'],'Mean NO2 (mol/m²)':s['mean_mol_m2'],'Usable days':s['valid_days']} for s in saved['no2']['sites']]))
else:
    print('NO₂ measurements are not bundled: the live Earth Engine retrieval was not verified. Use Step 3 to calculate them; no values have been invented.')
for metric, value in saved.get('measurements', {}).items():
    print(metric, value['start'], value['end_exclusive'], value['units'])
    display(pd.DataFrame([{'Area':s['name'],'Mean native units':s['mean_value'],'Usable days':s['valid_days']} for s in value['sites']]))
display(Image(filename='docs/assets/uae-example.png',width=950))''')
add('markdown','''## Step 5 — Choose a location and use both analyses
1. Click the map, type latitude/longitude, or choose one of the comparison areas. The green circle is for the selected atmospheric quantity; the orange square is for methane.
2. Under 1. Measure the wider atmospheric pattern, press Calculate satellite history after Step 3 sign-in. Or load the saved Dubai study if available.
3. Under 2. Screen the detailed methane image, press Check latest image. It downloads images, checks quality, compares an earlier reference, obtains modeled wind and runs the unchanged MARS-S2L model.
4. Press Export results for website and import that file on the [demo website](https://losth6wz.github.io/Geoguard/).
5. Also download the evidence + history ZIP before disconnecting. Jupyter/Colab runtime storage is not permanent backup.

The 15-minute option checks whether a new image is available; it does not create a new satellite observation every 15 minutes. Keep it off unless you want checks while this notebook remains connected.''')
add('code','''from geoguard.notebook_ui import CombinedLab
try:
    lab.close()
except NameError:
    pass
lab=CombinedLab(workspace='runtime',ee_ready=ee_ready)
lab.display()''')
add('markdown','''## Step 5A — Use the website with live AI
Run the next cell. The connected website appears inside this notebook. Select a UAE location, then press Check latest satellite image. Progress and dated results return to the page automatically; no JSON import is required for this check.

Keep the Colab runtime connected. This checks the latest available imagery when you press the button; it is not a continuous live camera or an automatic monitoring schedule. The public GitHub Pages link remains a launcher and saved-results demo. Colab's authenticated embedded page runs the AI. Download your evidence before ending the session.''')
add('code','''from geoguard.server import start_demo
start_demo()''')
add('markdown','''## Step 6 — Read the result correctly

| Result | What it tells you |
|---|---|
| NO₂ column in mol/m² | Amount above an area through the lower atmosphere. A mole is a way to count molecules. Multiply by 1,000,000 to display µmol/m². |
| CO column in mol/m² | Total atmospheric column; displayed in mmol/m² (×1,000). |
| SO₂ column in mol/m² | Vertical column with assumed ground-level profile, not surface concentration; displayed in µmol/m² (×1,000,000). |
| Regional CH₄ in ppb | Albedo-bias-corrected column-averaged dry-air mixing ratio, OFFL only. Sparse retrievals remain gaps; this is not the detailed detector score. |
| Methane candidate | A pattern passed the model's rule and needs analyst review. |
| No methane candidate | The detector did not flag the usable image. It does not establish zero methane or safe air. |
| Not assessable | A required image, valid area, earlier reference or wind input was missing. Keep it unknown. |
| Forecast unavailable | History is saved, but a UAE forecast has not been validated. |

### The calculations
For NO₂, CO and SO₂ columns and regional CH₄ mixing ratio, within each day we average the available source images at each valid grid cell. We then take the spatial mean of the valid cells inside each circle. The month/period mean is the sum of these valid daily area values divided by the number of usable days. Missing days are excluded and counted; negative retrieval values are retained except documented extreme outliers below −0.001 mol/m². Source masks come from Earth Engine ingestion; there is no invented `qa_value` band. The 0–0.0002 colour scale is a display choice, not a danger limit.

For methane, the model combines the two images and supporting inputs. Scores strictly above 0.5, in regions with at least 100 eight-connected processing pixels, produce a flag. The processing grid is 10 m, while native shortwave-infrared detail is 20 m. This is pattern detection, not a physical calculation of methane density or emission rate.

### What still needs work
Independent UAE validation, reviewed presence/absence labels, forecast evaluation on later unseen dates, and persistent hosting for unattended processing. Weather, clouds and unequal valid coverage affect satellite comparisons. CO/SO₂ columns and regional XCH₄ are implemented; PM, VOC and H₂S instruments are not connected. Aerosol index is not PM mass. A 5 km circle near a road or industrial area does not establish that source's contribution.

### Sources
[Sentinel-5P NRTI catalog](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_NRTI_L3_NO2) · [OFFL catalog](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_OFFL_L3_NO2) · [CO catalog](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_NRTI_L3_CO) · [SO₂ catalog](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_NRTI_L3_SO2) · [Regional CH₄ catalog](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_OFFL_L3_CH4) · [MARS-S2L](https://github.com/UNEP-IMEO-MARS/marss2l) · [Dataset and model terms](https://huggingface.co/datasets/UNEP-IMEO/MARS-S2L) · [Attribution](https://github.com/losth6wz/Geoguard/blob/main/THIRD_PARTY_NOTICES.md)

Words used here: column = gas through the atmosphere above an area; granule = one source-image piece; pretrained = learned weights supplied by the model authors; inference = applying those weights to a new input; forecast = a prediction of a future observation, which is not yet provided for this UAE workflow.''')
nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3'},'language_info':{'name':'python'},'colab':{'name':'Geoguard.ipynb'}},'cells':cells}
(ROOT/'Geoguard.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding='utf-8')
print('Built',len(cells),'readable cells')
