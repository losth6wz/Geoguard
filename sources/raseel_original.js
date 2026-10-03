// 1. تحديد إحداثيات منطقتين في دبي (مثلاً: منطقة مرورية مزدحمة وسط المدينة + منطقة جبل علي الصناعية)
var trafficArea = ee.Geometry.Point([55.2708, 25.2048]); // وسط دبي / طريق الشيخ زايد (مرور)
var industrialArea = ee.Geometry.Point([55.0875, 25.0083]); // منطقة جبل علي الصناعية

// دمج المنطقتين في مجموعة واحدة للعرض
var areas = ee.FeatureCollection([
  ee.Feature(trafficArea, {name: 'Dubai Traffic Area'}),
  ee.Feature(industrialArea, {name: 'Dubai Industrial Area'})
]);

// ضبط خريطة العرض لتكون مركزة على دبي
Map.centerObject(trafficArea, 10);

// 2. استدعاء بيانات القمر الصناعي Sentinel-5P لغاز NO2
var dataset = ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_NO2')
                  .select('tropospheric_NO2_column_number_density')
                  .filterDate('2026-01-01', '2026-09-01');

var meanNO2 = dataset.mean();

// 3. خصائص الألوان (من الأزرق للأحمر للدلالة على شدة التلوث)
var visParams = {
  min: 0,
  max: 0.0002,
  palette: ['black', 'blue', 'purple', 'cyan', 'green', 'yellow', 'red']
};

// 4. إضافة الطبقة للخريطة وتحديد مواقع المناطق
Map.addLayer(meanNO2, visParams, 'Tropospheric NO2 (Dubai Pollution)');
Map.addLayer(areas, {color: 'red'}, 'Selected Dubai Study Areas');
