# Attribution and source terms

- The original Dubai Sentinel-5P JavaScript and two study points are preserved in `sources/no2_original.js`. Labels are study hypotheses, not verified source classifications.
- The existing GeoGuard workflow supplies the public Sentinel-2 acquisition adapter, candidate-screening UI, dated history and earlier tested UAE result. The earlier project remains unchanged outside this new repository.
- UNEP IMEO MARS-S2L: https://github.com/UNEP-IMEO-MARS/marss2l and https://huggingface.co/datasets/UNEP-IMEO/MARS-S2L . Upstream code is LGPLv3; model/data terms are CC BY-NC-SA 4.0. Unchanged pretrained weights are downloaded at runtime, not included in this repository. Preserve upstream attribution and applicable non-commercial/share-alike obligations; public source availability is not a grant of unrestricted commercial use.
- Copernicus Sentinel data and the Google Earth Engine catalog supply NO₂, CO, SO₂ and regional CH₄ products. Public Sentinel-2 pixels are acquired from Google's Sentinel-2 archive, using Copernicus catalog discovery. Sentinel data terms apply. The original software is not a satellite instrument or ground monitor.
- CloudSEN12 supplies the cloud model through the existing adapter; see the model repository/license referenced in `live_detection/auxiliary.py`.
- Wind inputs use NASA GEOS-FP or an explicitly recorded experimental NOAA GFS / Open-Meteo fallback. They are modeled meteorology, not gas measurements.
- Notebook navigation imagery credits Esri and its contributors. Website navigation credits OpenStreetMap contributors under ODbL; background tiles are not measurement imagery.
- Leaflet 1.9.4 is distributed under its BSD-2-Clause license, preserved in `docs/vendor/LEAFLET-LICENSE`. Fonts are DM Sans and Manrope, requested from Google Fonts with fallback system fonts.
- The bundled boundary is the previously used UAE screening boundary; it is not a statement of legal borders. Source provenance is recorded in `sources/migration_manifest.json`.

No blanket license is asserted here over teammate contributions or upstream materials. This repository preserves their provenance and applicable terms.

- Element 84 Earth Search provides a public Sentinel-2 L1C catalogue fallback when the primary index is unavailable: https://github.com/Element84/earth-search . Image pixels still come from the same explicit SAFE product in the public Google archive. Catalogue source and item identity are recorded.


## Dataset and model references

- Sentinel-5P L3 products: [NO₂](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_NRTI_L3_NO2), [CO](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_NRTI_L3_CO), [SO₂](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_NRTI_L3_SO2), [regional CH₄](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S5P_OFFL_L3_CH4). Observation windows and processing levels are listed in the README; collection/band identities are retained in raw exports.
- Copernicus Sentinel data: [provider terms](https://dataspace.copernicus.eu/terms-and-conditions). Derived figures credit Copernicus Sentinel data (2026), processed by GeoGuard. Bundled methane evidence uses Sentinel-2 L1C on 22 September and 9 September 2026; other dated tests retain their own dates.
- [CloudSEN12 model card](https://huggingface.co/isp-uv-es/cloudsen12_models): UNetMobV2_V2 weights, revision `c2e98f254f90d57c34b2a7308864641584e89d80`; pretrained weights CC BY-NC 4.0, Python package LGPLv3. Credits: Aybar et al. (2022, 2024), Mateo-García et al. (2023). The CloudSEN12 training dataset is not downloaded for this PoC.
- [MARS-S2L model/data card](https://huggingface.co/datasets/UNEP-IMEO/MARS-S2L): pretrained weights and database CC BY-NC-SA 4.0; code LGPLv3. Credits: Mateo-Garcia, Allen, Irakulis-Loitxate et al., “Artificial intelligence for methane detection: from continuous monitoring to verified mitigation”, arXiv:2511.21777. No retraining or full dataset download is part of the credential-free PoC.
- [NASA GEOS-FP product information](https://gmao.gsfc.nasa.gov/gmao-products/): acquisition-time assimilated/model meteorology. [NOAA GFS](https://www.emc.ncep.noaa.gov/emc/pages/numerical_forecast_systems/gfs.php) is the experimental fallback accessed through [Open-Meteo](https://open-meteo.com/en/terms). Open-Meteo data are CC BY 4.0; its free API service has separate non-commercial/rate-limit conditions. Data licence and API service terms are distinct. Each result records the wind source and whether fallback was used.

Repository source availability does not replace a licence from its authors. A team-wide licence for original GeoGuard contributions has not been supplied; no consent from teammates is inferred. Existing upstream terms remain applicable.
