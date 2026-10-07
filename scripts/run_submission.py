"""Execute all submission cells; fail on errors, without requiring a global kernel."""
from pathlib import Path
import os
import sys
import tempfile
import nbformat
from nbclient import NotebookClient
from ipykernel.kernelspec import install

ROOT = Path(__file__).resolve().parents[1]
output = ROOT / 'outputs/submission'
output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='geoguard-kernel-') as folder:
    install(prefix=folder, kernel_name='geoguard-submission', display_name='GeoGuard submission')
    previous = os.environ.get('JUPYTER_PATH')
    os.environ['JUPYTER_PATH'] = str(Path(folder) / 'share/jupyter') + (os.pathsep + previous if previous else '')
    try:
        notebook = nbformat.read(ROOT / 'Submission.ipynb', as_version=4)
        NotebookClient(notebook, timeout=120, kernel_name='geoguard-submission',
                       resources={'metadata': {'path': str(ROOT)}}).execute()
        nbformat.write(notebook, output / 'Submission-executed.ipynb')
    finally:
        if previous is None:
            os.environ.pop('JUPYTER_PATH', None)
        else:
            os.environ['JUPYTER_PATH'] = previous
print('Submission complete: outputs/submission/')
