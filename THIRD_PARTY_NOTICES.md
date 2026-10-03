# Attribution and source terms

- **Raseel** supplied the Dubai Sentinel-5P JavaScript idea and two study points. Her original comments and code are preserved in `sources/raseel_original.js`. Labels are study hypotheses, not verified source classifications.
- **Abdulaziz / GeoGuard** supplied the existing public Sentinel-2 acquisition adapter, candidate-screening UI, dated history and earlier tested UAE result. The earlier project remains unchanged outside this new repository.
- **UNEP IMEO MARS-S2L**: https://github.com/UNEP-IMEO-MARS/marss2l and https://huggingface.co/datasets/UNEP-IMEO/MARS-S2L . Upstream code is LGPLv3; model/data terms are CC BY-NC-SA 4.0. Unchanged pretrained weights are downloaded at runtime, not included in this repository. Preserve upstream attribution and applicable non-commercial/share-alike obligations; public source availability is not a grant of unrestricted commercial use.
- **Copernicus Sentinel data** and the **Google Earth Engine catalog** supply NO₂ products. Public Sentinel-2 pixels are acquired from Google's Sentinel-2 archive, using Copernicus catalog discovery. Sentinel data terms apply. The original software is not a satellite instrument or ground monitor.
- **CloudSEN12** supplies the cloud model through the existing adapter; see the model repository/license referenced in `live_detection/auxiliary.py`.
- Wind inputs use **NASA GEOS-FP** or an explicitly recorded experimental **NOAA GFS / Open-Meteo** fallback. They are modeled meteorology, not gas measurements.
- Notebook navigation imagery credits **Esri** and its contributors. Website navigation credits **OpenStreetMap** contributors under ODbL; background tiles are not measurement imagery.
- **Leaflet 1.9.4** is distributed under its BSD-2-Clause license, preserved in `docs/vendor/LEAFLET-LICENSE`. Fonts are DM Sans and Manrope, requested from Google Fonts with fallback system fonts.
- The bundled boundary is the previously used UAE screening boundary; it is not a statement of legal borders. Source provenance is recorded in `sources/migration_manifest.json`.

No blanket license is asserted here over teammate contributions or upstream materials. This repository preserves their provenance and applicable terms.
