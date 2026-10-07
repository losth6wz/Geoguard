'use strict';
const presets={dubai:{name:'Dubai comparison area',lat:25.2048,lon:55.2708},'jebel-ali':{name:'Jebel Ali comparison area',lat:25.0083,lon:55.0875},'uae-example':{name:'Example methane area',lat:23.86479,lon:53.61893}};
const $=id=>document.getElementById(id), text=(id,value)=>$(id).textContent=value;
let data=null, original=null, selected={...presets.dubai}, map, marker, areaLayers=[], overlay;
const near=(lat,lon)=>Number.isFinite(lat)&&Number.isFinite(lon)&&Math.abs(lat-selected.lat)<0.00001&&Math.abs(lon-selected.lon)<0.00001;
const finite=x=>typeof x==='number'&&Number.isFinite(x);
const metrics={NO2:{label:'NO₂',name:'Nitrogen dioxide',units:'mol/m²',unit:'µmol/m²',factor:1e6,band:'tropospheric_NO2_column_number_density',quantity:'Tropospheric NO₂ column'},CO:{label:'CO',name:'Carbon monoxide',units:'mol/m²',unit:'mmol/m²',factor:1e3,band:'CO_column_number_density',quantity:'Total atmospheric CO column'},SO2:{label:'SO₂',name:'Sulfur dioxide',units:'mol/m²',unit:'µmol/m²',factor:1e6,band:'SO2_column_number_density',quantity:'SO₂ vertical column; assumed ground-level profile'},CH4:{label:'CH₄ regional',name:'Regional methane',units:'ppb',unit:'ppb',factor:1,band:'CH4_column_volume_mixing_ratio_dry_air_bias_corrected',quantity:'Column-averaged dry-air CH₄ mixing ratio; albedo-bias-corrected'}};
const metric=()=>$('measurement-select').value, spec=()=>metrics[metric()];
const measurement=()=>metric()==='NO2'?data?.no2:data?.measurements?.[metric()];
const mean=s=>metric()==='NO2'?s.mean_mol_m2:s.mean_value;
const formatted=v=>finite(v)?(v*spec().factor).toFixed(2)+' '+spec().unit:'No data';
function coordinateOK(lat,lon){return finite(lat)&&finite(lon)&&lat>=22&&lat<=27&&lon>=51&&lon<=57;}
function select(lat,lon,name='Your selected point',move=true){
 if(!coordinateOK(lat,lon)){text('selection-feedback','Choose valid coordinates in the UAE study region (22–27 N, 51–57 E).');$('selection-feedback').classList.add('error');return;}
 selected={lat,lon,name};$('latitude').value=lat.toFixed(5);$('longitude').value=lon.toFixed(5);$('selection-feedback').classList.remove('error');text('selection-feedback',name+' · '+lat.toFixed(5)+'° N, '+lon.toFixed(5)+'° E');
 document.querySelectorAll('[data-site]').forEach(b=>b.classList.toggle('active',near(presets[b.dataset.site].lat,presets[b.dataset.site].lon)));
 if(map){marker.setLatLng([lat,lon]);if(move)map.setView([lat,lon],11);}render();
}
function render(){
 if(!data)return;
 const no2=measurement(),site=no2?.sites?.find(s=>near(s.latitude,s.longitude));
 text('measurement-gas',spec().label);text('measurement-name',spec().name.toUpperCase()+' · SENTINEL-5P');
 text('no2-value',site?formatted(mean(site)):'No result here');
 text('no2-description',site?spec().quantity+' over a '+(site.radius_m/1000)+' km radius area. This is not a ground-level concentration.':'Run this point in the notebook and import its result. Selecting a point does not manufacture a measurement.');
 text('no2-dates',site?no2.start+' → '+no2.end_exclusive+' (end excluded)':'');text('no2-coverage',site?site.valid_days+' / '+site.total_days+' days have usable values':'');
 const m=data.methane,match=m&&near(m.latitude,m.longitude);
 const labels={no_candidate:'No candidate flagged',candidate:'Candidate · review needed',not_assessable:'Not assessable',error:'Check failed'};
 text('methane-value',match?(labels[m.status]||'Result unavailable'):'Not run here');
 text('methane-description',match?(m.message||'Read the recorded result and its limitations.'):'Run a new methane check for this point in the notebook. The saved example belongs only to its recorded location.');
 text('methane-date',match?'Observed '+(m.current_acquired_at?.slice(0,10)||'unknown')+' · reference '+(m.background_acquired_at?.slice(0,10)||'unknown'):'');
 text('methane-coverage',match&&finite(m.common_valid_fraction)?(100*m.common_valid_fraction).toFixed(2)+'% usable coverage · '+m.candidate_pixels+' flagged pixels'+(m.wind_fallback_used?' · Experimental wind fallback used':''):'');
 const image=match?(m.figure_data||m.figure_path):null;
 const safeImage=image&&(image==='assets/uae-example.png'||/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(image));
 $('methane-evidence').hidden=!safeImage;
 if(safeImage){$('methane-image').src=image;text('figure-date',(m.current_acquired_at||'').slice(0,10));}
 text('forecast-status','UAE forecasting remains unavailable pending reviewed history and validation. Satellite histories are observations, not predictions.');
}
function svgEl(name,attrs={},label){const e=document.createElementNS('http://www.w3.org/2000/svg',name);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));if(label!==undefined)e.textContent=label;return e;}
function history(){
 const n=measurement();const sites=n?.sites||[],factor=spec().factor,unit=spec().unit;$('area-table').replaceChildren();$('chart').replaceChildren();$('chart-legend').replaceChildren();
 text('history-title','03 / Compare the '+spec().label+' history');text('chart-note','Units: '+unit+'. Missing days remain gaps; valid negative column retrievals are retained. These circles do not isolate a source. Regional methane is distinct from detailed screening.');
 $('chart').setAttribute('aria-label',spec().label+' monthly history in '+unit);
 text('history-description',n?'Observation window: '+n.start+' to '+n.end_exclusive+' (end excluded). Monthly means of usable daily area values. '+n.collection+'.':'No values loaded for this quantity. Authenticate in the notebook, run the calculation and import the result.');
 sites.forEach(s=>{const tr=document.createElement('tr');[s.name,formatted(mean(s)),s.valid_days+' / '+s.total_days].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td);});$('area-table').append(tr);});
 const months=[...new Set(sites.flatMap(s=>(s.monthly||[]).map(r=>r.month)))].sort();
 const values=sites.flatMap(s=>(s.monthly||[]).filter(r=>finite(r.value)).map(r=>r.value*factor));
 if(!values.length){text('chart','No measured history loaded. Missing data are not zero.');return;}
 const low=Math.min(...values),high=Math.max(...values),pad=Math.max((high-low)*.15,Math.abs(high)*.005,.001),lo=low-pad,hi=high+pad,svg=svgEl('svg',{viewBox:'0 0 680 220','aria-label':spec().label+' monthly values in '+unit});
 const x=i=>55+i*600/Math.max(1,months.length-1),y=v=>180-(v-lo)/(hi-lo)*150;
 for(let i=0;i<5;i++){let v=lo+(hi-lo)*i/4;svg.append(svgEl('line',{x1:55,x2:660,y1:y(v),y2:y(v),stroke:'#e4e9e2'}),svgEl('text',{x:45,y:y(v)+4,'text-anchor':'end',fill:'#65796d','font-size':10},v.toFixed(1)));}
 svg.append(svgEl('text',{x:5,y:14,fill:'#65796d','font-size':10},unit));
 months.forEach((m,i)=>svg.append(svgEl('text',{x:x(i),y:207,'text-anchor':'middle',fill:'#65796d','font-size':10},m.slice(5))));
 const colors=['#197b70','#5679bd','#b07e3b','#985d92','#75864b'];
 sites.forEach((s,i)=>{const rows=new Map((s.monthly||[]).map(r=>[r.month,r.value]));let path='',connected=false;months.forEach((m,j)=>{let v=rows.get(m);if(!finite(v)){connected=false;return;}path+=(connected?'L':'M')+x(j)+','+y(v*factor)+' ';connected=true;const circle=svgEl('circle',{cx:x(j),cy:y(v*factor),r:3.5,fill:colors[i%colors.length]});circle.append(svgEl('title',{},s.name+' · '+m+' · '+formatted(v)));svg.append(circle);});svg.prepend(svgEl('path',{d:path,fill:'none',stroke:colors[i%colors.length],'stroke-width':2.3}));let item=document.createElement('span');item.className='legend-item';let dot=document.createElement('span');dot.className='legend-dot';dot.style.background=colors[i%colors.length];item.append(dot,document.createTextNode(s.name));$('chart-legend').append(item);});$('chart').append(svg);
}
function drawAreas(){if(!map)return;areaLayers.forEach(l=>map.removeLayer(l));areaLayers=[];if(overlay){map.removeLayer(overlay);overlay=null;}
 (measurement()?.sites||[]).forEach(s=>{let circle=L.circle([s.latitude,s.longitude],{radius:s.radius_m,color:'#1a8376',fillColor:'#52a98c',fillOpacity:.12,weight:1.5});let label=document.createElement('div');label.textContent=s.name+' · '+formatted(mean(s));circle.bindPopup(label).addTo(map);areaLayers.push(circle);});
 const m=measurement()?.map;const valid=m&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(m.png_data);$('map-legend').hidden=false;if(!valid){text('map-legend-label','No raster overlay in this result. Area circles show locations; read the measured values and history.');text('map-min','');text('map-max','');$('map-ramp').style.background='none';}
 if(valid){const[w,s,e,n]=m.bounds;overlay=L.imageOverlay(m.png_data,[[s,w],[n,e]],{opacity:.65}).addTo(map);text('map-legend-label',spec().quantity+' · '+spec().unit);text('map-min',formatted(m.min));text('map-max',formatted(m.max));$('map-ramp').style.background='linear-gradient(to right,'+(m.palette||['222266','407bbb','77b9c7','e1eab9','f4be64','ce5942']).map(c=>'#'+c).join(',')+')';}
}
function validate(d){
 if(d?.schema!=='geoguard-demo-v1')throw Error('Use the JSON file from “Export results for website” in the notebook.');
 if(d.no2){if(d.no2.units!=='mol/m²'||d.no2.band!=='tropospheric_NO2_column_number_density'||!['COPERNICUS/S5P/NRTI/L3_NO2','COPERNICUS/S5P/OFFL/L3_NO2'].includes(d.no2.collection))throw Error('Incorrect NO₂ units, band or satellite product.');if(!Array.isArray(d.no2.sites)||d.no2.sites.length>5)throw Error('Invalid area list.');d.no2.sites.forEach(s=>{if(!coordinateOK(s.latitude,s.longitude)||!finite(s.radius_m)||s.radius_m<2000||s.radius_m>20000||typeof s.name!=='string'||!Array.isArray(s.monthly)||s.monthly.length>24)throw Error('Invalid NO₂ area.');if(s.mean_mol_m2!==null&&!finite(s.mean_mol_m2))throw Error('Invalid NO₂ value.');});if(d.no2.map&&(!Array.isArray(d.no2.map.bounds)||d.no2.map.bounds.length!==4||!d.no2.map.bounds.every(finite)))throw Error('Invalid map bounds.');}
 if(d.measurements!==undefined&&(!d.measurements||typeof d.measurements!=='object'||Array.isArray(d.measurements)))throw Error('Invalid measurements.');
 Object.entries(d.measurements||{}).forEach(([key,n])=>{
  const def=metrics[key];if(!def||key==='NO2'||!n||n.metric!==key||n.units!==def.units||n.band!==def.band||!Array.isArray(n.sites)||n.sites.length>5)throw Error('Unsupported quantity or incorrect units/band.');
  const products=key==='CH4'?['OFFL']:['NRTI','OFFL'];if(!products.some(p=>n.collection==='COPERNICUS/S5P/'+p+'/L3_'+key))throw Error('Incorrect satellite product.');
  if(!/^\d{4}-\d{2}-\d{2}$/.test(n.start)||!/^\d{4}-\d{2}-\d{2}$/.test(n.end_exclusive)||!(Date.parse(n.end_exclusive)>Date.parse(n.start)))throw Error('Invalid observation dates.');
  n.sites.forEach(s=>{if(!coordinateOK(s.latitude,s.longitude)||!finite(s.radius_m)||s.radius_m<2000||s.radius_m>20000||typeof s.name!=='string'||!Array.isArray(s.monthly)||s.monthly.length>24||!(s.mean_value===null||finite(s.mean_value))||!Number.isInteger(s.valid_days)||!Number.isInteger(s.total_days)||s.valid_days<0||s.valid_days>s.total_days||s.total_days<1||s.total_days>366)throw Error('Invalid measurement area/value/coverage.');s.monthly.forEach(r=>{if(!/^\d{4}-\d{2}$/.test(r.month)||!(r.value===null||finite(r.value)))throw Error('Invalid monthly observation.');});});
  if(n.map&&(!Array.isArray(n.map.bounds)||n.map.bounds.length!==4||!n.map.bounds.every(finite)||n.map.units!==def.units||!finite(n.map.min)||!finite(n.map.max)||n.map.max<=n.map.min||!Array.isArray(n.map.palette)||n.map.palette.length>12||!n.map.palette.every(c=>/^[0-9a-fA-F]{6}$/.test(c))))throw Error('Invalid map scale or units.');
 });
 if(d.methane&&(!coordinateOK(d.methane.latitude,d.methane.longitude)))throw Error('Methane result needs a valid recorded location.');return d;
}
function apply(d,mode){data=validate(d);if(!measurement())$('measurement-select').value=d.no2?'NO2':Object.keys(d.measurements||{})[0]||'NO2';text('result-mode',mode);text('snapshot-label',mode==='EXAMPLE EVIDENCE'?'Dated satellite evidence · explore below':'Your imported notebook evidence');history();drawAreas();render();}
$('measurement-select').addEventListener('change',()=>{history();drawAreas();render();});
document.querySelectorAll('[data-site]').forEach(b=>b.addEventListener('click',()=>{const s=presets[b.dataset.site];select(s.lat,s.lon,s.name);}));
$('coordinate-form').addEventListener('submit',e=>{e.preventDefault();select(Number($('latitude').value),Number($('longitude').value));});
$('copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(selected.lat.toFixed(5)+', '+selected.lon.toFixed(5));text('selection-feedback','Coordinates copied. Paste latitude and longitude into the notebook.');}catch{text('selection-feedback','Copy: '+selected.lat.toFixed(5)+', '+selected.lon.toFixed(5));}});
$('import-file').addEventListener('change',async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>10*1024*1024)throw Error('Choose a result file smaller than 10 MB.');const parsed=validate(JSON.parse(await f.text()));apply(parsed,'IMPORTED RESULTS');const s=measurement()?.sites?.find(s=>s.id==='selected')||measurement()?.sites?.[0]||parsed.methane;if(s)select(s.latitude,s.longitude,s.name||'Imported methane area');text('import-status','Loaded '+f.name+' locally. Results retain their original dates and locations.');$('import-status').classList.remove('error');}catch(err){text('import-status',err.message);$('import-status').classList.add('error');}finally{e.target.value='';}});
$('reset').addEventListener('click',()=>{apply(original,'EXAMPLE EVIDENCE');select(presets.dubai.lat,presets.dubai.lon,presets.dubai.name);text('import-status','Restored the bundled example evidence.');});
async function init(){try{if(window.L){map=L.map('map',{scrollWheelZoom:false}).setView([25.1,55.18],10);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);marker=L.circleMarker([selected.lat,selected.lon],{radius:7,color:'#fff',weight:3,fillColor:'#0c554e',fillOpacity:1}).addTo(map);map.on('click',e=>select(e.latlng.lat,e.latlng.lng,'Your selected point',false));}else text('map','Map unavailable. Use the coordinate inputs below.');const response=await fetch('data/demo.json');if(!response.ok)throw Error('Saved results could not load.');original=await response.json();apply(original,'EXAMPLE EVIDENCE');}catch(e){text('snapshot-label','Saved evidence unavailable');text('import-status',e.message);}}
init();

let liveToken=null;
async function liveRequest(path, options={}){
 const response=await fetch(path,{...options,headers:{'Content-Type':'application/json','X-Geoguard-Token':liveToken,...options.headers},signal:AbortSignal.timeout(20000)});
 const value=await response.json();if(!response.ok)throw Error(value.error||'AI service unavailable');return value;
}
async function connectLive(){
 try{
  const response=await fetch('api/config',{signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw Error('Not connected');const config=await response.json();
  if(typeof config.token!=='string')throw Error('Not connected');
  liveToken=config.token;$('live-check').disabled=false;$('live-start').hidden=true;
  text('live-status','AI service connected. Choose a location and run a check. Images can take several minutes to process.');
 }catch{text('live-status','Start AI in Colab, then run Step 5A. The connected website appears there while your runtime stays open.');}
}
$('live-check').addEventListener('click',async()=>{
 const point={...selected};$('live-check').disabled=true;
 if(data){data={...data,methane:null};render();}
 text('live-status','Submitting check for '+point.lat.toFixed(5)+', '+point.lon.toFixed(5)+'…');
 try{
  const job=await liveRequest('api/jobs',{method:'POST',body:JSON.stringify({latitude:point.lat,longitude:point.lon})});
  for(;;){
   const state=await liveRequest('api/jobs/'+encodeURIComponent(job.id));
   text('live-status',point.lat.toFixed(5)+', '+point.lon.toFixed(5)+' · '+state.message);
   if(state.state==='error')throw Error(state.message);
   if(state.state==='done'){
    apply({...state.result,no2:data?.no2||null,measurements:data?.measurements||{}},'LATEST CHECK');
    text('snapshot-label','New check returned · read the satellite acquisition date');
    if(!near(point.lat,point.lon))text('live-status',state.message+' Return to '+point.lat.toFixed(5)+', '+point.lon.toFixed(5)+' to view this result.');
    break;
   }
   await new Promise(resolve=>setTimeout(resolve,3000));
  }
 }catch(error){text('live-status','Check could not complete: '+error.message+' Keep Colab connected and retry.');}
 finally{$('live-check').disabled=false;}
});
connectLive();
