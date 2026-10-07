// Reproducible satellite measurements. Run in your registered Earth Engine project.
// Does not save a script, upload private observations, or create paid resources.
var start = '2026-08-01', end = '2026-10-01';
var specs = [
  {metric:'CO',product:'NRTI',band:'CO_column_number_density',min:0,max:0.05},
  {metric:'SO2',product:'NRTI',band:'SO2_column_number_density',min:-0.0001,max:0.0005},
  {metric:'CH4',product:'OFFL',band:'CH4_column_volume_mixing_ratio_dry_air_bias_corrected',min:1800,max:2000}
];
var points = [{id:'dubai',lat:25.2048,lon:55.2708},{id:'jebel-ali',lat:25.0083,lon:55.0875}];
var days = ee.List.sequence(0,ee.Date(end).difference(ee.Date(start),'day').subtract(1));
var names = days.map(function(i){return ee.String('d').cat(ee.Date(start).advance(i,'day').format('YYYYMMdd'));});
var tables = [];
specs.forEach(function(spec){
  var collection = 'COPERNICUS/S5P/'+spec.product+'/L3_'+spec.metric;
  var areas = ee.FeatureCollection(points.map(function(s){return ee.Feature(
    ee.Geometry.Point([s.lon,s.lat]).buffer(5000),{site_id:s.id,metric:spec.metric,collection:collection,
    start:start,end_exclusive:end,radius_m:5000,latitude:s.lat,longitude:s.lon});}));
  var source = ee.ImageCollection(collection).filterBounds(areas.geometry()).filterDate(start,end).select(spec.band)
    .map(function(im){return im.updateMask(spec.metric==='CH4'?im.gt(0):im.gte(-0.001));});
  var empty = ee.Image.constant(0).rename(spec.band).updateMask(ee.Image.constant(0));
  var daily = ee.ImageCollection.fromImages(days.map(function(i){
    var day=ee.Date(start).advance(i,'day'), images=source.filterDate(day,day.advance(1,'day'));
    return ee.Image(ee.Algorithms.If(images.size().gt(0),images.mean(),empty)).rename('value')
      .set('system:time_start',day.millis());
  }));
  var table = daily.toBands().rename(names).reduceRegions({collection:areas,
    reducer:ee.Reducer.mean().combine({reducer2:ee.Reducer.count(),sharedInputs:true}),
    scale:1113.2,crs:'EPSG:4326',tileScale:4}).map(function(f){return f.setGeometry(null);});
  tables.push(table);
  Map.addLayer(daily.mean().clip(areas.geometry().bounds()),
    {min:spec.min,max:spec.max,palette:['222266','407bbb','77b9c7','e1eab9','f4be64','ce5942']},spec.metric+' atmospheric quantity');
  print(spec.metric+' map (native units)',daily.mean().clip(areas.geometry().bounds()).getThumbURL({
    min:spec.min,max:spec.max,palette:['222266','407bbb','77b9c7','e1eab9','f4be64','ce5942'],
    region:areas.geometry().bounds(),dimensions:900,crs:'EPSG:4326',format:'png'}));
});
Map.setCenter(55.18,25.1,10);
var combined=ee.FeatureCollection(tables).flatten();
print('Measurements: August–September 2026; two 5 km areas; 61 day slots',combined.size());
combined.getDownloadURL({format:'JSON',filename:'geoguard_measured_columns',callback:function(url,error){
  if(error) print('Export error',error); else print('Download actual measurement export',url);
}});
