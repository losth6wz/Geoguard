"""Real cloud masks and scene-time meteorology for experimental live screening.

No missing cloud pixels or weather observations are replaced with clear sky or
zero wind. SAFE acquisition is separate; matching the public upstream steps
does not establish exact GEE pixel parity or validate the detector in the UAE.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import threading

import numpy as np
import requests
import rasterio
from georeader.geotensor import GeoTensor


CLOUD_REVISION = "c2e98f254f90d57c34b2a7308864641584e89d80"
CLOUD_REPO = "isp-uv-es/cloudsen12_models"
CLOUD_MODEL = "UNetMobV2_V2"
S2_BANDS = ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B10", "B11", "B12"]
DETECTOR_BANDS = ["B02", "B03", "B04", "B08", "B11", "B12"]
_CLOUD_LOCK = threading.Lock()
_CLOUD_MODELS = {}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _download(url, destination, timeout=(15, 90)):
    """Public HTTPS download, preserving TLS verification and partial cleanup."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return destination
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with requests.get(url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            with partial.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        output.write(chunk)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    return destination


def _write_geotiff(path, values, template, nodata, bands=None):
    if values.ndim == 2:
        values = values[None]
    with rasterio.open(path, "w", driver="GTiff", height=values.shape[-2],
                       width=values.shape[-1], count=values.shape[0],
                       dtype=values.dtype, crs=template.crs, transform=template.transform,
                       compress="deflate", nodata=nodata) as output:
        output.write(values)
        if bands:
            for i, name in enumerate(bands, 1):
                output.set_band_description(i, name)


def prepare_crop(crop, cache_dir):
    """Return detector image, actual cloud mask and validity for a SAFE crop.

    Input: acquisition.fetch_crop result with toa13_path, valid13_path,
    band_names, scene_id and exact acquired_at. Native 20/60 m bands must still
    have nearest sampling on the aligned 10 m grid. Public CloudSEN12 runs
    before the upstream 20 m bilinear interpolation. Clear fraction includes
    raw invalid and nonpositive harmonized pixels as unavailable, not clear.
    """
    if list(crop["band_names"]) != S2_BANDS:
        raise ValueError("CloudSEN12 requires all 13 Sentinel-2 L1C bands in the documented order.")
    if crop.get("product_level") != "L1C TOA":
        raise ValueError("Latest screening requires L1C TOA, not surface reflectance.")
    source_hashes = {name: _sha(crop[name]) for name in ["toa13_path", "valid13_path"]}
    key = hashlib.sha256(json.dumps({"version": 1, "sources": source_hashes,
                                     "cloud_revision": CLOUD_REVISION}, sort_keys=True).encode()).hexdigest()[:20]
    folder = Path(cache_dir) / "prepared" / key
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / "auxiliary.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        if all(Path(saved[k]).exists() and _sha(saved[k]) == saved["hashes"][k]
               for k in ["image_path", "valid_path", "cloud_path"]):
            return saved
    with rasterio.open(crop["toa13_path"]) as source:
        values = source.read()
        image = GeoTensor(values, source.transform, source.crs, fill_value_default=0)
    with rasterio.open(crop["valid13_path"]) as source:
        raw_valid = source.read()
        if source.crs != image.crs or source.transform != image.transform or raw_valid.shape != image.shape:
            raise ValueError("Raw validity and reflectance grids do not agree.")
    if values.dtype != np.uint16 or values.shape[0] != 13 or image.res != (10.0, 10.0):
        raise ValueError("Expected 13 uint16 TOA×10000 bands on a 10 m grid.")
    if any(size % 2 for size in values.shape[-2:]):
        raise ValueError("Use even crop dimensions to preserve the native 20 m grid.")
    # This matches upstream compute_cloud_mask's invalidity rule while also
    # retaining explicit raw DN no-data/defective-pixel validity from SAFE.
    invalid = (~np.all(raw_valid > 0, axis=0)
               | ~np.all(np.isfinite(values), axis=0)
               | np.any(values == 0, axis=0))
    image.values[:, invalid] = 0
    weights_dir = Path(cache_dir) / "cloud_weights" / CLOUD_REVISION
    weights_file = weights_dir / (CLOUD_MODEL + ".pt")
    weights_url = f"https://huggingface.co/{CLOUD_REPO}/resolve/{CLOUD_REVISION}/{weights_file.name}"
    # Both model download/loading and mutable PyTorch inference are serialized.
    with _CLOUD_LOCK:
        _download(weights_url, weights_file)
        from cloudsen12_models import cloudsen12
        import torch
        model_key = str(weights_file.resolve())
        if model_key not in _CLOUD_MODELS:
            _CLOUD_MODELS[model_key] = cloudsen12.load_model_by_name(
                CLOUD_MODEL, weights_folder=str(weights_dir), device=torch.device("cpu")
            )
        cloud_model = _CLOUD_MODELS[model_key]
        if list(cloud_model.bands) != S2_BANDS:
            raise ValueError("Cloud model band contract changed.")
        with torch.inference_mode():
            cloud = cloud_model.predict(image.astype(np.float32) / 10000)
    cloud.values[invalid] = 4
    cloud.fill_value_default = 4
    if not np.isin(cloud.values, [0, 1, 2, 3, 4]).all():
        raise ValueError("Unexpected cloud model classes.")
    # Use the exact public upstream interpolation function after cloud scoring.
    from georeader.readers.ee_image import interpolate_20mbands_s2ee
    processed = interpolate_20mbands_s2ee(image, S2_BANDS, inplace=False)
    band_indexes = [S2_BANDS.index(name) for name in DETECTOR_BANDS]
    detector = processed.isel({"band": band_indexes})
    detector.values[:, invalid] = 0
    valid = (cloud.values == 0) & ~invalid & np.all(detector.values > 0, axis=0)
    image_path = folder / "detector_toa6_x10000_10m.tif"
    valid_path = folder / "clear_valid_10m.tif"
    cloud_path = folder / "cloudsen12_classes_10m.tif"
    _write_geotiff(image_path, detector.values, detector, 0, DETECTOR_BANDS)
    _write_geotiff(valid_path, valid.astype(np.uint8), detector, 0)
    _write_geotiff(cloud_path, cloud.values.astype(np.uint8), detector, 4)
    metadata = {
        "adapter_version": "official-cloudsen12-and-georeader-v1",
        "scene_id": crop["scene_id"], "acquired_at": crop["acquired_at"],
        "image_path": str(image_path), "valid_path": str(valid_path),
        "cloud_path": str(cloud_path), "currentcloud_path": str(cloud_path),
        "clear_fraction": float(valid.mean()), "raw_invalid_fraction": float((~np.all(raw_valid > 0, axis=0)).mean()),
        "invalid_or_nonpositive_fraction": float(invalid.mean()),
        "class_pixel_counts": {str(k): int((cloud.values == k).sum()) for k in range(5)},
        "class_names": ["clear", "thick cloud", "thin cloud", "cloud shadow", "invalid"],
        "cloud_model": CLOUD_MODEL, "cloud_model_revision": CLOUD_REVISION,
        "cloud_weights_url": weights_url, "cloud_weights_sha256": _sha(weights_file),
        "source_hashes": source_hashes, "band_names": DETECTOR_BANDS,
        "metadata_path": str(manifest), "source_metadata_path": crop["metadata_path"],
        "processing": "CloudSEN12 on nearest 10 m 13-band TOA; then official georeader 20 m bilinear interpolation; six detector bands retained.",
        "parity_limit": "Official cloud model and interpolation used; direct SAFE-vs-GEE pixel parity and new-location model performance remain unvalidated.",
    }
    metadata["hashes"] = {k: _sha(metadata[k]) for k in ["image_path", "valid_path", "cloud_path"]}
    manifest.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def _wind_geos_fp(latitude, longitude, acquired_at, cache_dir):
    """Real NASA GEOS-FP U10M/V10M at scene hour, matching upstream lookup.

    The hourly file is labeled HH:30; bilinearly interpolate its 10 m eastward
    and northward winds at the scene center. No nearest-day substitution or
    zero-wind fallback is permitted. Network/data failures raise a clear error.
    """
    import xarray as xr
    import pandas as pd
    acquired = pd.Timestamp(acquired_at)
    acquired = acquired.tz_localize("UTC") if acquired.tzinfo is None else acquired.tz_convert("UTC")
    if not (-90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180):
        raise ValueError("Invalid latitude or longitude.")
    if acquired < pd.Timestamp("2014-02-21", tz="UTC"):
        raise ValueError("Scene predates this GEOS-FP archive.")
    nominal = acquired.floor("h") + pd.Timedelta(minutes=30)
    filename = f"GEOS.fp.asm.tavg1_2d_slv_Nx.{acquired.strftime('%Y%m%d_%H')}30.V01.nc4"
    url = ("https://portal.nccs.nasa.gov/datashare/gmao/geos-fp/das/"
           + acquired.strftime("Y%Y/M%m/D%d/") + filename)
    path = Path(cache_dir) / "wind" / filename
    try:
        _download(url, path, timeout=(8, 30))
        with xr.open_dataset(path, cache=False) as dataset:
            if not {"U10M", "V10M"}.issubset(dataset.data_vars):
                raise ValueError("NASA file lacks the required wind variables.")
            if dataset.sizes.get("time") != 1:
                raise ValueError("NASA hourly file has an unexpected time axis.")
            file_time = pd.Timestamp(dataset.time.values[0]).tz_localize("UTC")
            if abs((file_time - nominal).total_seconds()) > 1:
                raise ValueError("Downloaded wind timestamp differs from the requested hour.")
            wind = dataset[["U10M", "V10M"]].squeeze("time").interp(lon=float(longitude), lat=float(latitude)).load()
            u, v = float(wind.U10M), float(wind.V10M)
        if not np.isfinite([u, v]).all():
            raise ValueError("Scene-time wind is missing at this location.")
    except Exception as exc:
        raise RuntimeError(
            "Real scene-time GEOS-FP wind could not be retrieved; no zero/default wind was inserted. "
            + type(exc).__name__ + ": " + str(exc)
        ) from exc
    result = {
        "u": u, "v": v, "units": "m/s", "height_m": 10,
        "source": "NASA GEOS-FP tavg1_2d_slv_Nx", "source_url": url,
        "timestamp": file_time.isoformat(), "scene_timestamp": acquired.isoformat(),
        "latitude": float(latitude), "longitude": float(longitude),
        "spatial_method": "bilinear interpolation", "temporal_method": "acquisition-hour field labeled HH:30, matching upstream marss2l",
        "artifact_path": str(path), "sha256": _sha(path),
        "fetched_or_read_at": datetime.now(timezone.utc).isoformat(),
    }
    record = path.with_name(path.stem + f"_{latitude:.6f}_{longitude:.6f}.json")
    record.write_text(json.dumps(result, indent=2), encoding="utf-8")
    result["metadata_path"] = str(record)
    return result


def _wind_open_meteo_gfs(latitude, longitude, acquired_at, cache_dir):
    """Real NOAA GFS model winds via Open-Meteo, explicitly not GEOS parity."""
    import pandas as pd
    acquired = pd.Timestamp(acquired_at)
    acquired = acquired.tz_localize("UTC") if acquired.tzinfo is None else acquired.tz_convert("UTC")
    now = pd.Timestamp.now(tz="UTC")
    if acquired > now + pd.Timedelta(minutes=5):
        raise ValueError("A future acquisition cannot be assessed as an observed image.")
    if acquired < pd.Timestamp("2021-03-23", tz="UTC"):
        raise ValueError("Scene predates documented Open-Meteo GFS archive coverage.")
    lower, upper = acquired.floor("h"), acquired.ceil("h")
    # The recent Forecast endpoint supports past days. Older dates use the
    # documented historical-forecast endpoint, not the ERA5 archive endpoint.
    endpoint = ("https://api.open-meteo.com/v1/forecast"
                if now - acquired < pd.Timedelta(days=7)
                else "https://historical-forecast-api.open-meteo.com/v1/forecast")
    query = {
        "latitude": float(latitude), "longitude": float(longitude),
        "hourly": "wind_speed_10m,wind_direction_10m", "models": "gfs_global",
        "wind_speed_unit": "ms", "timezone": "UTC",
        "start_date": lower.strftime("%Y-%m-%d"), "end_date": upper.strftime("%Y-%m-%d"),
        "cell_selection": "nearest", "elevation": "nan",
    }
    response = requests.get(endpoint, params=query, timeout=(8, 30))
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError("Open-Meteo rejected the scene-time query: " + str(payload.get("reason")))
    if payload.get("utc_offset_seconds") != 0 or payload["hourly_units"].get("wind_speed_10m") != "m/s":
        raise ValueError("Unexpected weather timezone or wind units.")
    times = pd.to_datetime(payload["hourly"]["time"], utc=True)
    speeds = np.asarray(payload["hourly"]["wind_speed_10m"], dtype=float)
    directions = np.asarray(payload["hourly"]["wind_direction_10m"], dtype=float)
    if not (len(times) == len(speeds) == len(directions)) or times.duplicated().any():
        raise ValueError("Malformed hourly weather data.")
    wanted = sorted(set([lower, upper]))
    indexes = []
    for timestamp in wanted:
        match = np.flatnonzero(times == timestamp)
        if len(match) != 1:
            raise ValueError("No weather value brackets the exact scene time.")
        indexes.append(int(match[0]))
    speed = speeds[indexes]
    direction = directions[indexes]
    if not np.isfinite(speed).all() or not np.isfinite(direction).all() or (speed < 0).any() or ((direction < 0) | (direction > 360)).any():
        raise ValueError("Missing or invalid scene-hour weather; no default wind was inserted.")
    # Meteorological direction is the direction FROM which wind blows.
    u_values = -speed * np.sin(np.deg2rad(direction))
    v_values = -speed * np.cos(np.deg2rad(direction))
    fraction = 0.0 if lower == upper else (acquired - lower).total_seconds() / 3600
    u = float(u_values[0] if len(indexes) == 1 else (1 - fraction) * u_values[0] + fraction * u_values[1])
    v = float(v_values[0] if len(indexes) == 1 else (1 - fraction) * v_values[0] + fraction * v_values[1])
    folder = Path(cache_dir) / "wind"
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(response.url.encode() + response.content).hexdigest()[:20]
    raw_path = folder / ("open_meteo_gfs_" + key + ".json")
    # Preserve the exact downloaded response once; result references its hash.
    if not raw_path.exists():
        raw_path.write_bytes(response.content)
    return {
        "u": u, "v": v, "units": "m/s", "height_m": 10,
        "source": "NOAA GFS via Open-Meteo (experimental substitute for GEOS-FP)",
        "model": "gfs_global", "source_url": response.url,
        "timestamp": acquired.isoformat(), "scene_timestamp": acquired.isoformat(),
        "source_times": [t.isoformat() for t in wanted],
        "source_speed_m_s": speed.tolist(), "source_direction_from_degrees": direction.tolist(),
        "latitude": float(latitude), "longitude": float(longitude),
        "grid_latitude": float(payload["latitude"]), "grid_longitude": float(payload["longitude"]),
        "spatial_method": "provider nearest model grid cell; elevation downscaling disabled",
        "temporal_method": "linear interpolation of east/north components between the bracketing hourly fields",
        "interpolation_fraction": float(fraction), "provider_first_availability": None,
        "provider_model_run_time": None,
        "availability_note": "The response does not report original model run or first publication time; original real-time availability is unknown.",
        "artifact_path": str(raw_path), "sha256": _sha(raw_path),
        "fetched_or_read_at": datetime.now(timezone.utc).isoformat(),
        "parity_limit": "Real GFS model meteorology replaces GEOS-FP; equivalent detector accuracy has not been validated. No emission-rate estimate is produced.",
    }


def wind_for_scene(latitude, longitude, acquired_at, cache_dir):
    """Try real GEOS-FP, then explicitly label a real GFS-model substitute.

    The scene-time values and source timestamps are mandatory. A network or
    missing-data failure from both providers stops assessment. Cached records
    preserve the exact source already used for a reproducible rerun.
    """
    if not (-90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180):
        raise ValueError("Invalid latitude or longitude.")
    import pandas as pd
    acquired = pd.Timestamp(acquired_at)
    acquired = acquired.tz_localize("UTC") if acquired.tzinfo is None else acquired.tz_convert("UTC")
    if pd.isna(acquired) or acquired > pd.Timestamp.now(tz="UTC") + pd.Timedelta(minutes=5):
        raise ValueError("Wind for an observed scene requires a valid past acquisition time.")
    key = hashlib.sha256(json.dumps([float(latitude), float(longitude), str(acquired_at), "v2"]).encode()).hexdigest()[:20]
    folder = Path(cache_dir) / "wind"
    folder.mkdir(parents=True, exist_ok=True)
    record = folder / ("scene_wind_" + key + ".json")
    if record.exists():
        saved = json.loads(record.read_text(encoding="utf-8"))
        if Path(saved["artifact_path"]).exists() and _sha(saved["artifact_path"]) == saved["sha256"]:
            return saved
    try:
        result = _wind_geos_fp(latitude, longitude, acquired_at, cache_dir)
        result["fallback_used"] = False
        result["provider_first_availability"] = None
    except Exception as geos_error:
        try:
            result = _wind_open_meteo_gfs(latitude, longitude, acquired_at, cache_dir)
        except Exception as gfs_error:
            raise RuntimeError("No real scene-time wind is available; assessment stopped. GEOS-FP: "
                               + str(geos_error) + "; GFS: " + str(gfs_error)) from gfs_error
        result["fallback_used"] = True
        result["geos_failure"] = str(geos_error)
    result["metadata_path"] = str(record)
    record.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
