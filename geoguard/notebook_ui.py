"""Shared map controls for the two satellite workflows."""
import base64
from datetime import date
from html import escape
import json
from pathlib import Path

import ipywidgets as W
from IPython.display import display, FileLink
from ipyleaflet import Circle, ImageOverlay
from live_detection.app import LatestDetectionApp
from .core import SITES, SAVED_SITE, public_methane, export_bundle
from .no2 import query_no2

ROOT = Path(__file__).resolve().parents[1]

class CombinedLab(LatestDetectionApp):
    def __init__(self, workspace='runtime', ee_ready=False, engine=None):
        super().__init__(workspace=workspace,engine=engine)
        self.ee_ready = ee_ready
        self.no2_result = None
        self.no2_layer = None
        self.no2_status = W.HTML('<p>Run the NO₂ calculation, or use the saved study example below.</p>')
        self.no2_plot = W.Output()
        self.start_date = W.DatePicker(description='Start:',value=date(2026,1,1))
        self.end_date = W.DatePicker(description='End (excl.):',value=date(2026,9,1))
        self.product = W.Dropdown(description='Product:',options=['NRTI','OFFL'],value='NRTI')
        self.radius = W.IntSlider(description='NO₂ radius km:',min=2,max=20,value=5,style={'description_width':'120px'})
        self.no2_check = W.Button(description='Calculate NO₂ history',button_style='primary')
        self.no2_check.on_click(self.calculate_no2)
        self.no2_demo = W.Button(description='Load saved Dubai NO₂ study')
        self.no2_demo.on_click(self.load_no2_example)
        self.json_export = W.Button(description='Export results for website',button_style='success')
        self.json_export.on_click(self.export_for_website)
        self.export_status = W.Output()
        self.presets = W.Dropdown(description='Start from:',options=[('Choose on map','custom')]+[(s['name'],s['id']) for s in SITES]+[(SAVED_SITE['name'],SAVED_SITE['id'])])
        self.presets.observe(self.choose_preset,names='value')
        self.no2_circle=Circle(location=(self.lat.value,self.lon.value),radius=5000,color='#1b9a8c',fill_opacity=.06)
        self.map.add(self.no2_circle)
        for field in [self.lat,self.lon,self.start_date,self.end_date,self.product,self.radius]:
            field.observe(self.no2_inputs_changed,names='value')
        no2_tab=W.VBox([W.HTML('<h3>1. Read the wider NO₂ pattern</h3><p>NO₂ means nitrogen dioxide. The green circle is the comparison area; values describe the gas through the atmosphere above it. NRTI is the faster product; OFFL is the offline product. The end date is excluded.</p>'),
            W.HBox([self.start_date,self.end_date]),W.HBox([self.product,self.radius]),
            W.HTML('<p>Your selected circle is compared with the two Dubai comparison areas. Labels are study locations, not proven sources.</p>'),
            W.HBox([self.no2_check,self.no2_demo]),self.no2_status,self.no2_plot])
        methane_tab=W.VBox([W.HTML('<h3>2. Screen the detailed methane image</h3><p>The orange square is approximately 2 × 2 km. This runs the unchanged pretrained MARS-S2L model on available Sentinel-2 imagery. It may take several minutes. Read the acquisition date.</p>'),
            W.HBox([self.check,self.auto]),self.schedule,self.status,self.summary,self.figure,self.history_summary,
            self.save,self.download_status])
        tabs=W.Tab(children=[no2_tab,methane_tab]);tabs.set_title(0,'NO₂ context');tabs.set_title(1,'Methane screening')
        self.widget=W.VBox([W.HTML('<h2>GeoGuard · One place, two views</h2><p>Choose a UAE location. The map is for navigation; it is not a pollution measurement. The two gases use different satellites, dates and area sizes.</p>'),
            self.presets,W.HBox([self.lat,self.lon]),self.area,self.map,tabs,
            W.HTML('<h3>3. Share the evidence</h3><p>Export a JSON result file, then use <b>Import notebook results</b> on the website. The file contains dated results, not account credentials. Download the separate methane evidence/history ZIP to keep the full scientific record.</p>'),
            self.json_export,self.export_status,
            W.HTML('<p><b>Forecasting:</b> the methane history is preserved. A UAE forecast remains unavailable until suitable reviewed observations and chronological validation exist. NO₂ charts show past observations, not predictions.</p>')])
        self.lat.value,self.lon.value=SITES[0]['latitude'],SITES[0]['longitude']

    def choose_preset(self,change):
        site=next((s for s in SITES+[SAVED_SITE] if s['id']==change['new']),None)
        if site:
            self.lat.value=site['latitude'];self.lon.value=site['longitude']
            self.map.center=(site['latitude'],site['longitude']);self.map.zoom=10

    def no2_inputs_changed(self,_):
        self.no2_result=None
        self.no2_status.value='<p>Selection changed. Calculate again; previous values are cleared.</p>'
        self.no2_plot.clear_output()
        self.export_status.clear_output()
        if self.no2_layer:
            self.map.remove(self.no2_layer);self.no2_layer=None
        self.no2_circle.location=(self.lat.value,self.lon.value)
        self.no2_circle.radius=self.radius.value*1000

    def show_no2(self,result):
        self.no2_result=result
        self.no2_status.value='<p><b>'+escape(result['status'])+'</b> · '+escape(result['start'])+' to '+escape(result['end_exclusive'])+' (end excluded). Units: mol/m². Missing days remain gaps.</p>'
        with self.no2_plot:
            self.no2_plot.clear_output(wait=True)
            import pandas as pd
            import matplotlib.pyplot as plt
            rows=[{'Area':s['name'],'Mean mol/m²':s['mean_mol_m2'],'Valid days':s['valid_days'],'Days requested':s['total_days']} for s in result['sites']]
            display(pd.DataFrame(rows))
            fig,ax=plt.subplots(figsize=(8,3))
            for site in result['sites']:
                ax.plot([r['month'] for r in site['monthly']],[float('nan') if r['value'] is None else r['value']*1e6 for r in site['monthly']],marker='o',label=site['name'])
            ax.set_ylabel('NO₂ column (µmol/m²)');ax.set_title('Monthly means of usable daily area values');ax.legend(fontsize=8)
            ax.tick_params(axis='x',rotation=30);fig.tight_layout();display(fig);plt.close(fig)
        if self.no2_layer:
            self.map.remove(self.no2_layer);self.no2_layer=None
        if result.get('map'):
            m=result['map'];w,s,e,n=m['bounds']
            self.no2_layer=ImageOverlay(url=m['png_data'],bounds=((s,w),(n,e)),opacity=.65)
            self.map.add(self.no2_layer)

    def calculate_no2(self,_=None):
        if not self.ee_ready:
            self.no2_status.value='<p>Add your Earth Engine project ID in Step 3, run its sign-in cell, then reopen this lab. The saved NO₂ study works without sign-in.</p>';return
        self.no2_inputs_changed(None)
        self.no2_check.disabled=True
        self.no2_status.value='<p>Calculating dated NO₂ values. This can take a few minutes.</p>'
        try:
            sites=[dict(s) for s in SITES]
            selected={'id':'selected','name':'Your selected area','latitude':self.lat.value,'longitude':self.lon.value}
            if not any(abs(s['latitude']-selected['latitude'])<1e-6 and abs(s['longitude']-selected['longitude'])<1e-6 for s in sites): sites.append(selected)
            if self.start_date.value is None or self.end_date.value is None: raise ValueError('Choose both dates.')
            result=query_no2(sites,self.start_date.value.isoformat(),self.end_date.value.isoformat(),self.product.value,self.radius.value*1000)
            self.show_no2(result)
            export_bundle(self.workspace/'no2-latest.json',no2=result)
        except Exception as exc:
            self.no2_status.value='<p>NO₂ query failed: '+escape(str(exc))+'</p>'
        finally:
            self.no2_check.disabled=False

    def load_no2_example(self,_=None):
        data=json.loads((ROOT/'docs/data/demo.json').read_text(encoding='utf-8'))
        if not data.get('no2'):
            self.no2_status.value='<p>No saved NO₂ measurements are bundled yet. Use an authenticated query.</p>';return
        self.show_no2(data['no2'])
        self.no2_status.value+='<p><b>Saved Dubai study:</b> these values belong to its named areas and dates, not an arbitrary current map selection.</p>'

    def export_for_website(self,_=None):
        with self.export_status:
            self.export_status.clear_output()
            if self.no2_result is None and self.result is None:
                print('Run one analysis or load the saved NO₂ study first.');return
            methane=None
            if self.result:
                image=self._artifact((self.result.get('paths') or {}).get('figure'),'.png')
                figure='data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode() if image else None
                located={**self.result,'latitude':self.result.get('latitude',self.lat.value),
                         'longitude':self.result.get('longitude',self.lon.value)}
                methane=public_methane(located,figure)
            path=export_bundle(self.workspace/'geoguard-results.json',self.no2_result,methane)
            try:
                from google.colab import files
                files.download(str(path))
            except ImportError:
                display(FileLink(str(path)))
            print('Import this file on the demo website. Its dates and locations travel with it.')
