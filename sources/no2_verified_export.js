// GeoGuard: reproducible export matching geoguard/no2.py.
// Run in an authenticated Earth Engine Code Editor. No script is saved automatically.
var start = '2026-01-01', end = '2026-09-01'; // End is excluded.
var band = 'tropospheric_NO2_column_number_density';
var areas = ee.FeatureCollection([
  ee.Feature(ee.Geometry.Point([55.2708,25.2048]).buffer(5000), {site_id:'dubai'}),
  ee.Feature(ee.Geometry.Point([55.0875,25.0083]).buffer(5000), {site_id:'jebel-ali'})
]);
var source = ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_NO2')
  .filterBounds(areas.geometry()).filterDate(start,end).select(band)
  .map(function(im) {return im.updateMask(im.gte(-0.001));});
var empty = ee.Image.constant(0).rename(band).updateMask(ee.Image.constant(0));
var days = ee.List.sequence(0,ee.Date(end).difference(ee.Date(start),'day').subtract(1));
var daily = ee.ImageCollection.fromImages(days.map(function(offset) {
  var day = ee.Date(start).advance(offset,'day');
  var images = source.filterDate(day,day.advance(1,'day'));
  return ee.Image(ee.Algorithms.If(images.size().gt(0), images.mean(), empty))
    .rename('no2').set({'date':day.format('YYYY-MM-dd'),'system:time_start':day.millis()});
}));
var names=days.map(function(offset){return ee.String('d').cat(ee.Date(start).advance(offset,'day').format('YYYYMMdd'));});
var table=daily.toBands().rename(names).reduceRegions({collection:areas,
  reducer:ee.Reducer.mean().combine({reducer2:ee.Reducer.count(),sharedInputs:true}),
  scale:1113.2,crs:'EPSG:4326',tileScale:4}).map(function(f){return f.setGeometry(null);});
Map.setCenter(55.18,25.1,10);
Map.addLayer(daily.mean().clip(areas.geometry().bounds()),{min:0,max:0.0002,palette:['black','blue','purple','cyan','green','yellow','red']},'Mean daily NO2 column, mol/m²');
Map.addLayer(areas,{color:'white'},'5 km comparison areas');
print('Two areas; each has 243 dated mean/count pairs',table.size());
table.getDownloadURL({format:'JSON',filename:'geoguard_no2_daily',callback:function(url,error) {
  if(error) print('Export error',error);
  else print('Download measured daily area values',url);
}});
