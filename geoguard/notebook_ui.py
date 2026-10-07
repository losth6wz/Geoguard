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
from .measurements import METRICS, query_measurement

ROOT = Path(__file__).resolve().parents[1]

class CombinedLab(LatestDetectionApp):
    def __init__(self, workspace='runtime', ee_ready=False, engine=None):
        super().__init__(workspace=workspace,engine=engine)
        self.ee_ready = ee_ready
        self.no2_result = None
        self.measurements = {}
        self.metric = W.Dropdown(description='Quantity:',options=[(v['name'],k) for k,v in METRICS.items()],value='NO2')
        self.switching_metric = False
        self.no2_layer = None
        self.no2_status = W.HTML('<p>Run the NO₂ calculation, or use the saved study example below.</p>')
        self.no2_plot = W.Output()
        self.start_date = W.DatePicker(description='Start:',value=date(2026,1,1))
        self.end_date = W.DatePicker(description='End (excl.):',value=date(2026,9,1))
        self.product = W.Dropdown(description='Product:',options=['NRTI','OFFL'],value='NRTI')
        self.radius = W.IntSlider(description='Area radius km:',min=2,max=20,value=5,style={'description_width':'120px'})
        self.no2_check = W.Button(description='Calculate satellite history',button_style='primary')
        self.no2_check.on_click(self.calculate_no2)
        self.no2_demo = W.Button(description='Load saved study')
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
        self.metric.observe(self.metric_changed,names='value')
        no2_tab=W.VBox([W.HTML('<h3>1. Measure the wider atmospheric pattern</h3><p>Choose NO₂, CO, SO₂ or regional CH₄. The green circle is the comparison area. Columns are not ground concentrations; regional methane is column-averaged dry-air mixing ratio, distinct from the detailed detector. CH₄ uses OFFL only. The end date is excluded.</p>'),self.metric,
            W.HBox([self.start_date,self.end_date]),W.HBox([self.product,self.radius]),
            W.HTML('<p>Your selected circle is compared with the two Dubai comparison areas. Labels are study locations, not proven sources.</p>'),
            W.HBox([self.no2_check,self.no2_demo]),self.no2_status,self.no2_plot])
        methane_tab=W.VBox([W.HTML('<h3>2. Screen the detailed methane image</h3><p>The orange square is approximately 2 × 2 km. This runs the unchanged pretrained MARS-S2L model on available Sentinel-2 imagery. It may take several minutes. Read the acquisition date.</p>'),
            W.HBox([self.check,self.auto]),self.schedule,self.status,self.summary,self.figure,self.history_summary,
            self.save,self.download_status])
        # Keep the controls visible in Colab even when its Tab view fails to render.
        analyses=W.VBox([no2_tab,methane_tab],layout=W.Layout(width='100%'))
        self.widget=W.VBox([W.HTML('<h2>GeoGuard · One place, two views</h2><p>Choose a UAE location. The map is for navigation; it is not a pollution measurement. Atmospheric measurements and detailed screening use different quantities, satellites, dates and area sizes.</p>'),
            self.presets,W.HBox([self.lat,self.lon]),self.area,self.map,analyses,
            W.HTML('<h3>3. Share the evidence</h3><p>Export a JSON result file, then use Import notebook results on the website. All calculated quantities travel with their own units, dates and coverage. Download the separate methane evidence/history ZIP to keep the full scientific record.</p>'),
            self.json_export,self.export_status,
            W.HTML('<p>Forecasting: a UAE forecast remains unavailable until reviewed observations and chronological validation exist. Satellite histories show observations, not predictions. PM, VOC and H₂S sensors have not been connected.</p>')])
        self.lat.value,self.lon.value=SITES[0]['latitude'],SITES[0]['longitude']

    def choose_preset(self,change):
        site=next((s for s in SITES+[SAVED_SITE] if s['id']==change['new']),None)
        if site:
            self.lat.value=site['latitude'];self.lon.value=site['longitude']
            self.map.center=(site['latitude'],site['longitude']);self.map.zoom=10

    def no2_inputs_changed(self,_):
        if self.switching_metric: return
        self.no2_result=None
        self.measurements.clear()
        self.no2_status.value='<p>Selection changed. Calculate again; previous values are cleared.</p>'
        self.no2_plot.clear_output()
        self.export_status.clear_output()
        if self.no2_layer:
            self.map.remove(self.no2_layer);self.no2_layer=None
        self.no2_circle.location=(self.lat.value,self.lon.value)
        self.no2_circle.radius=self.radius.value*1000

    def metric_changed(self,_):
        self.switching_metric=True
        try:
            self.product.options=METRICS[self.metric.value]['products']
        finally:
            self.switching_metric=False
        self.no2_plot.clear_output()
        if self.no2_layer:
            self.map.remove(self.no2_layer);self.no2_layer=None
        cached=self.no2_result if self.metric.value=='NO2' else self.measurements.get(self.metric.value)
        if cached: self.show_no2(cached)
        else: self.no2_status.value='<p>Calculate this quantity or load its saved study. Previous quantities remain available for export.</p>'

    def show_no2(self,result):
        metric=self.metric.value;spec=METRICS[metric]
        if metric=='NO2': self.no2_result=result
        else: self.measurements[metric]=result
        unit=spec['display_units'];factor=spec['display_factor'];key='mean_mol_m2' if metric=='NO2' else 'mean_value'
        self.no2_status.value='<p>'+escape(spec['quantity'])+' · '+escape(result['status'])+' · '+escape(result['start'])+' to '+escape(result['end_exclusive'])+' (end excluded). Units: '+unit+'. Missing days remain gaps.</p>'
        with self.no2_plot:
            self.no2_plot.clear_output(wait=True)
            import pandas as pd
            import matplotlib.pyplot as plt
            rows=[{'Area':s['name'],'Mean '+unit:None if s[key] is None else s[key]*factor,'Valid days':s['valid_days'],'Days requested':s['total_days']} for s in result['sites']]
            display(pd.DataFrame(rows))
            fig,ax=plt.subplots(figsize=(8,3))
            for site in result['sites']:
                ax.plot([r['month'] for r in site['monthly']],[float('nan') if r['value'] is None else r['value']*factor for r in site['monthly']],marker='o',label=site['name'])
            ax.set_ylabel(spec['label']+' ('+unit+')');ax.set_title('Monthly means of usable daily area values');ax.legend(fontsize=8)
            ax.tick_params(axis='x',rotation=30);fig.tight_layout();display(fig);plt.close(fig)
        if self.no2_layer:
            self.map.remove(self.no2_layer);self.no2_layer=None
        if result.get('map'):
            m=result['map'];w,s,e,n=m['bounds']
            self.no2_layer=ImageOverlay(url=m['png_data'],bounds=((s,w),(n,e)),opacity=.65)
            self.map.add(self.no2_layer)

    def calculate_no2(self,_=None):
        if not self.ee_ready:
            self.no2_status.value='<p>Add your Earth Engine project ID in Step 3, run its sign-in cell, then reopen this lab. Saved satellite studies work without sign-in.</p>';return
        metric=self.metric.value
        if metric=='NO2': self.no2_result=None
        else: self.measurements.pop(metric,None)
        self.no2_check.disabled=True
        self.no2_plot.clear_output()
        if self.no2_layer:
            self.map.remove(self.no2_layer);self.no2_layer=None
        self.no2_status.value='<p>Calculating '+escape(METRICS[metric]['label'])+' values. This can take a few minutes.</p>'
        try:
            sites=[dict(s) for s in SITES]
            selected={'id':'selected','name':'Your selected area','latitude':self.lat.value,'longitude':self.lon.value}
            if not any(abs(s['latitude']-selected['latitude'])<1e-6 and abs(s['longitude']-selected['longitude'])<1e-6 for s in sites): sites.append(selected)
            if self.start_date.value is None or self.end_date.value is None: raise ValueError('Choose both dates.')
            args=(sites,self.start_date.value.isoformat(),self.end_date.value.isoformat(),self.product.value,self.radius.value*1000)
            result=query_no2(*args) if metric=='NO2' else query_measurement(metric,*args)
            self.show_no2(result)
            export_bundle(self.workspace/'satellite-latest.json',no2=self.no2_result,measurements=self.measurements)
        except Exception as exc:
            self.no2_status.value='<p>Satellite query failed: '+escape(str(exc))+'</p>'
        finally:
            self.no2_check.disabled=False

    def load_no2_example(self,_=None):
        data=json.loads((ROOT/'docs/data/demo.json').read_text(encoding='utf-8'))
        self.no2_result=data.get('no2');self.measurements=data.get('measurements',{})
        result=self.no2_result if self.metric.value=='NO2' else self.measurements.get(self.metric.value)
        if not result:
            self.no2_status.value='<p>No saved result for this quantity. Use an authenticated query.</p>';return
        self.show_no2(result)
        self.no2_status.value+='<p>Saved study: values belong to the named areas and dates, not an arbitrary map selection. NO₂ covers January–August; the additional quantities cover August–September 2026.</p>'

    def export_for_website(self,_=None):
        with self.export_status:
            self.export_status.clear_output()
            if self.no2_result is None and not self.measurements and self.result is None:
                print('Run one analysis or load the saved NO₂ study first.');return
            methane=None
            if self.result:
                image=self._artifact((self.result.get('paths') or {}).get('figure'),'.png')
                figure='data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode() if image else None
                located={**self.result,'latitude':self.result.get('latitude',self.lat.value),
                         'longitude':self.result.get('longitude',self.lon.value)}
                methane=public_methane(located,figure)
            path=export_bundle(self.workspace/'geoguard-results.json',self.no2_result,methane,self.measurements)
            try:
                from google.colab import files
                files.download(str(path))
            except ImportError:
                display(FileLink(str(path)))
            print('Import this file on the demo website. Its dates and locations travel with it.')
