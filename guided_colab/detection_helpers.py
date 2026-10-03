"""GeoGuard's small, reproducible interface to the pretrained MARS-S2L detector.

This is historical prepared-data inference, not worldwide imagery retrieval.
The model architecture and MBMP function are read unchanged from the authors'
hash-checked source revision; only the two definitions needed here are loaded.
Upstream code: UNEP-IMEO-MARS/marss2l (LGPLv3). Weights/data: UNEP IMEO
MARS-S2L (CC BY-NC-SA 4.0). No reference label is supplied to the network.
"""
from pathlib import Path
from typing import Optional
import ast
import hashlib
import json
import math
import os
import re
import time
import urllib.request

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize, shapes
from rasterio.warp import transform_bounds, transform_geom
from scipy import ndimage
from shapely import wkt
from shapely.geometry import mapping
import torch
import torch.nn as nn
import torch.nn.functional as F

DATA_REVISION = "c26b1d7e31a0c5241fa37c9140802622c215eb32"
CODE_REVISION = "b6d3eaf89f39687f0beead1fd40b97d8e66cf7a9"
DATA_BASE = f"https://huggingface.co/datasets/UNEP-IMEO/MARS-S2L/resolve/{DATA_REVISION}/"
SOURCE_BASE = f"https://raw.githubusercontent.com/UNEP-IMEO-MARS/marss2l/{CODE_REVISION}/marss2l/"
DEFAULT_OBSERVATION_ID = "e1c76d3e-8e4f-4a2b-adbb-570e8e8daefe"  # Our S16 example.
DEFAULT_SITE_ID = "f3216fab-fccb-4035-8f05-b14d16c7b9a0"
THRESHOLD, MIN_PIXELS = 0.5, 100
SHA256 = {
    "test.csv": "add125547e0e0066216070ed61a8544e76e84f062f636390be5d2ef1808dbfaa",
    "best_epoch": "be634fb9e24dc4877f44c1ff9f69972e6f0453e30d70c0dc03677876340ef246",
    "config_experiment.json": "abeb92d01313fbb2939e6c5fc1c6281846b8102ea5edd7081668fe0db05bf79f",
    "models.py": "5c51cb3ee2fa0fa5912e145ade36c207e060d0c70dcf59e533b226d8138037d0",
    "mbmp_torch.py": "0c4eca25a40bf82f0a39a40c34650421fdef0d2bdc52898757fe67997ed3e932",
}


class GeoGuardDataError(ValueError):
    """An understandable input/data problem that the notebook can display."""


def _sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _download(url, path, expected_hash=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if expected_hash and _sha256(path) != expected_hash:
            raise GeoGuardDataError(f"Cached file {path.name} failed its integrity check. Remove that file and rerun setup.")
        return path
    temporary = path.with_name(path.name + ".part")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=90) as response, temporary.open("wb") as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
            if expected_hash and _sha256(temporary) != expected_hash:
                raise GeoGuardDataError(f"Downloaded {path.name} failed its integrity check.")
            temporary.replace(path)
            return path
        except GeoGuardDataError:
            raise
        except Exception as exc:
            if attempt == 2:
                raise GeoGuardDataError(f"Could not download {path.name}. Check the internet connection and rerun this step.") from exc
            time.sleep(1)


def _background_date(tile):
    # First YYYYMMDD in both Sentinel and Landsat IDs is acquisition date.
    match = re.search(r"(?:^|_)(20\d{6})(?:T\d{6})?(?:_|$)", str(tile))
    return pd.to_datetime(match.group(1), format="%Y%m%d", utc=True) if match else pd.NaT


def _boolean(series):
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().eq("true")


def _rgb(raw, offset=0):
    rgb = raw[[offset + 2, offset + 1, offset]].transpose(1, 2, 0).astype(float)
    rgb = np.nan_to_num(rgb, nan=0, posinf=0, neginf=0)
    lo, hi = np.percentile(rgb, [2, 98], axis=(0, 1))
    return np.clip((rgb - lo) / np.maximum(hi - lo, 1), 0, 1)


def _connected_mask(score, threshold=THRESHOLD):
    # Eight-neighbour connectivity matches the authors' skimage connectivity=2.
    labels, _ = ndimage.label(score > threshold, structure=np.ones((3, 3), dtype=int))
    sizes = np.bincount(labels.ravel())
    keep = sizes >= MIN_PIXELS
    keep[0] = False
    return keep[labels]


def _scene_score(score):
    # Same binary search and tolerance used in the earlier experiment.
    low, high = np.min(score), np.max(score)
    threshold = (low + high) / 2
    while high - low > 1e-4:
        if _connected_mask(score, threshold).sum() >= MIN_PIXELS:
            low = threshold
        else:
            high = threshold
        threshold = (low + high) / 2
    return float(threshold)


def _official_definition(path, name, namespace):
    """Execute one exact named definition from already hash-verified source."""
    source = Path(path).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(source).body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


class GeoGuardDetector:
    def __init__(self, cache_dir="geoguard_data", output_dir="geoguard_outputs"):
        self.cache_dir = Path(cache_dir)
        self.output_dir = Path(output_dir)
        self.catalog = None
        self.model = None
        self.config = None
        self.to_mbmp = None

    def load_catalog(self):
        """Load public metadata only (about 43 MB); do not load all imagery."""
        if self.catalog is None:
            path = _download(DATA_BASE + "test.csv", self.cache_dir / "test.csv", SHA256["test.csv"])
            df = pd.read_csv(path)
            df["parsed_date"] = pd.to_datetime(df.tile_date, utc=True, format="mixed")
            df["background_date"] = df.background_image_tile.map(_background_date)
            df["prior_background"] = df.background_date.notna() & (df.background_date < df.parsed_date.dt.normalize())
            df["eligible"] = (
                df.satellite.isin(["S2A", "S2B", "LC08", "LC09"])
                & ~_boolean(df.offshore) & df.observability.eq("clear")
                & pd.to_numeric(df.percentage_clear, errors="coerce").ge(99)
                & df.wind_u.notna() & df.wind_v.notna()
                & df.s2path.notna() & df.cloudmaskpath.notna()
                & df.split_name.eq("test_2023") & df.parsed_date.ge(pd.Timestamp("2024-01-01", tz="UTC"))
            )
            df["isplume"] = _boolean(df.isplume)
            self.catalog = df
        return self.catalog.copy()

    def sites(self, country=None):
        """Map markers show only sites with at least one supported earlier-background pair."""
        df = self.load_catalog()
        df = df[df.eligible & df.prior_background]
        if country and country != "All countries":
            df = df[df.country.eq(country)]
        sites = df.groupby("id_location", as_index=False).agg(
            location_name=("location_name", "first"), country=("country", "first"),
            latitude=("lat", "first"), longitude=("lon", "first"),
            observation_count=("id_loc_image", "size"),
            first_date=("parsed_date", "min"), last_date=("parsed_date", "max"),
        )
        return sites.sort_values(["country", "location_name"]).reset_index(drop=True)

    def observations(self, site_id, prior_only=True):
        """Available dates for an exact catalog site ID (or unique location name)."""
        df = self.load_catalog()
        subset = df[df.id_location.eq(str(site_id))]
        if subset.empty:
            subset = df[df.location_name.eq(str(site_id))]
            if subset.id_location.nunique() > 1:
                raise GeoGuardDataError("This name identifies several sites. Select the site's map marker or ID.")
        subset = subset[subset.eligible]
        if prior_only:
            subset = subset[subset.prior_background]
        return subset.sort_values(["parsed_date", "satellite"]).reset_index(drop=True)

    def select_coordinates(self, latitude, longitude):
        """Suggest a catalog site; never silently replace a clicked location."""
        try:
            lat, lon = float(latitude), float(longitude)
        except (ValueError, TypeError) as exc:
            raise GeoGuardDataError("Enter latitude and longitude as two numbers.") from exc
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise GeoGuardDataError("Latitude must be -90 to 90; longitude must be -180 to 180.")
        sites = self.sites()
        if sites.empty:
            return {"status": "no_prepared_coverage", "message": "No supported prepared sites are available."}
        lat1, lat2 = np.radians(lat), np.radians(sites.latitude.to_numpy())
        dlat = lat2 - lat1
        dlon = np.radians(sites.longitude.to_numpy() - lon)
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        distance = 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        nearest = sites.iloc[int(np.argmin(distance))]
        return {
            "status": "select_catalog_site", "requested_latitude": lat, "requested_longitude": lon,
            "nearest_site_id": str(nearest.id_location), "nearest_site_name": str(nearest.location_name),
            "nearest_country": str(nearest.country), "nearest_distance_km": float(np.min(distance)),
            "nearest_latitude": float(nearest.latitude), "nearest_longitude": float(nearest.longitude),
            "message": "This notebook cannot fetch imagery for an arbitrary coordinate. Select a catalog marker or explicitly choose the suggested site; its coordinates may differ from your click.",
        }

    def load_model(self):
        """Download ~163 MB of weights once; load the exact tested CPU network."""
        if self.model is not None:
            return self.model
        for name in ("best_epoch", "config_experiment.json"):
            _download(DATA_BASE + f"trained_models/MARSS2L_20250326/{name}", self.cache_dir / name, SHA256[name])
        for name in ("models.py", "mbmp_torch.py"):
            _download(SOURCE_BASE + name, self.cache_dir / "official_source" / name, SHA256[name])
        self.config = json.loads((self.cache_dir / "config_experiment.json").read_text())
        if self.config["model"] != "UnetOriginal" or self.config["classification_head"]:
            raise GeoGuardDataError("The checkpoint configuration does not match this notebook.")
        if not all(self.config[k] for k in ("multipass", "wind", "norm_wind", "cloud_mask", "cat_mbmp", "bands_l8", "batch_norm")):
            raise GeoGuardDataError("Unexpected input configuration in checkpoint.")
        scope = {"torch": torch, "nn": nn, "F": F, "np": np, "Optional": Optional, "FILL_VALUE_RATIO_IL": 0}
        model_class = _official_definition(self.cache_dir / "official_source/models.py", "UnetOriginal", scope)
        self.to_mbmp = _official_definition(self.cache_dir / "official_source/mbmp_torch.py", "to_mbmp", scope)
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        model = model_class(in_channels=16, out_channels=1, class_head=False, batch_norm=True)
        checkpoint = torch.load(self.cache_dir / "best_epoch", map_location="cpu", weights_only=True)
        state = {k.removeprefix("_orig_mod.").removeprefix("module."): v for k, v in checkpoint["model_state_dict"].items()}
        active = set(model.state_dict())
        expected_unused = {f"out_mlp.mlp.{layer}.{param}" for layer in ("0", "2.0", "3.0", "4.0", "5.0", "6") for param in ("weight", "bias")}
        if set(state) - active != expected_unused:
            raise GeoGuardDataError("Unexpected checkpoint parameters; stopping instead of using incompatible weights.")
        model.load_state_dict({k: v for k, v in state.items() if k in active}, strict=True)
        self.model = model.eval()
        return self.model

    def run(self, observation_id, prior_only=True):
        """Detect one prepared observation and save its scores, outline and evidence."""
        df = self.load_catalog()
        chosen = df[df.id_loc_image.eq(str(observation_id))]
        if len(chosen) != 1:
            raise GeoGuardDataError("That observation is not in this prepared-data catalog. Choose a date from the list.")
        row = chosen.iloc[0]
        if not row.eligible:
            raise GeoGuardDataError("This observation does not pass the notebook's satellite, date, cloud or input-data checks.")
        if prior_only and not row.prior_background:
            raise GeoGuardDataError("This prepared pair has no verified earlier background. Choose a different date; it cannot be used as an earlier-background example.")
        model = self.load_model()
        input_paths = []
        for key in ("s2path", "cloudmaskpath"):
            relative = str(row[key])
            if relative.startswith(("/", "\\")) or ".." in Path(relative).parts:
                raise GeoGuardDataError("Unexpected dataset path.")
            input_paths.append(_download(DATA_BASE + relative, self.cache_dir / relative))
        with rasterio.open(input_paths[0]) as src:
            raw, profile = src.read(), src.profile.copy()
            bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        with rasterio.open(input_paths[1]) as src:
            cloud = src.read(1)
            if src.transform != profile["transform"] or src.crs != profile["crs"]:
                raise GeoGuardDataError("The image and cloud mask do not align.")
        if raw.shape != (12, 200, 200) or cloud.shape != (200, 200):
            raise GeoGuardDataError(f"Unexpected prepared-image shape: {raw.shape}.")
        # Six current bands + six background bands; preserve the trained scaling.
        x = torch.tensor(raw.astype(np.float32))
        x[torch.isnan(x)] = 0
        x = torch.clamp(x / 5000, 0, 2)
        x[torch.isinf(x)] = 2
        mbmp = self.to_mbmp(x, 4, 5, 10, 11)
        wind = torch.tensor([row.wind_u, row.wind_v], dtype=torch.float32)[:, None, None]
        wind = (wind / 8).expand(2, 200, 200)
        cm = torch.tensor(cloud.astype(np.float32))
        cm[cm > 0], cm[torch.isnan(cm)], cm[torch.isinf(cm)] = 1, 0, 1
        x = torch.cat([mbmp[None], x, wind, cm[None]])
        if not torch.isfinite(x).all():
            raise GeoGuardDataError("Prepared measurements contain invalid values after preprocessing.")
        start = time.perf_counter()
        with torch.inference_mode():
            scores = torch.sigmoid(model({"y_context_ls0_0": x[None]}))[0].numpy()
        elapsed = time.perf_counter() - start
        if scores.shape != (200, 200) or not np.isfinite(scores).all():
            raise GeoGuardDataError("The model returned invalid scores.")
        scene_score = _scene_score(scores)
        mask = _connected_mask(scores)
        # Status and outline must use the same exact decision. The approximate
        # scene score is for ranking; its search tolerance can cross THRESHOLD.
        predicted = bool(mask.any())
        reference = np.zeros((200, 200), dtype=bool)
        # Read the answer only AFTER inference. It is for historical comparison.
        if row.isplume:
            geom = wkt.loads(row.plume)
            if not geom.is_empty:
                ref_geom = transform_geom("EPSG:4326", profile["crs"], mapping(geom))
                reference = rasterize([(ref_geom, 1)], out_shape=(200, 200), transform=profile["transform"], all_touched=True).astype(bool)
        union = int((mask | reference).sum())
        metrics = {
            "scene_score": scene_score, "predicted_pixels": int(mask.sum()),
            "reference_pixels": int(reference.sum()), "reference_plume": bool(row.isplume),
            "agrees_with_reference": predicted == bool(row.isplume),
            "mask_iou": float((mask & reference).sum() / union) if union else None,
            "clear_fraction": float((cloud == 0).mean()), "inference_seconds": elapsed,
        }
        features = []
        for geom, value in shapes(mask.astype(np.uint8), mask=mask, transform=profile["transform"]):
            if value:
                features.append({"type": "Feature", "geometry": transform_geom(profile["crs"], "EPSG:4326", geom),
                                 "properties": {"meaning": "Predicted methane-like pattern; not concentration"}})
        geojson = {"type": "FeatureCollection", "features": features}
        summary = {
            "status": "Suspected methane plume" if predicted else "No plume detected",
            "observation_id": str(row.id_loc_image), "site_id": str(row.id_location),
            "location_name": str(row.location_name), "country": str(row.country),
            "latitude": float(row.lat), "longitude": float(row.lon),
            "date": row.parsed_date.strftime("%Y-%m-%d"), "satellite": str(row.satellite),
            "background_date": row.background_date.strftime("%Y-%m-%d") if pd.notna(row.background_date) else None,
            "earlier_background": bool(row.prior_background), "predicted_plume": bool(predicted),
            "location_seen_during_training": str(row.location_name) in self.config.get("all_locs_train", []),
            **metrics,
            "meaning": "A flag needs analyst review. No detection does not prove clean air. Scores are not calibrated probabilities or methane concentration.",
            "dataset_revision": DATA_REVISION, "code_revision": CODE_REVISION,
            "threshold": THRESHOLD, "minimum_connected_pixels": MIN_PIXELS,
        }
        out = self.output_dir / str(row.id_loc_image)
        out.mkdir(parents=True, exist_ok=True)
        paths = {}
        for name, values in (("score", scores.astype(np.float32)), ("predicted_mask", mask.astype(np.uint8))):
            path = out / f"{name}.tif"
            meta = {**profile, "count": 1, "dtype": str(values.dtype), "nodata": None, "compress": "deflate"}
            with rasterio.open(path, "w", **meta) as dst:
                dst.write(values, 1)
            paths[name] = str(path)
        for name, content in (("result", summary), ("plume_outline", geojson)):
            path = out / f"{name}.json"
            path.write_text(json.dumps(content, indent=2), encoding="utf-8")
            paths[name] = str(path)
        manifest = {"dataset_revision": DATA_REVISION, "code_revision": CODE_REVISION,
                    "weights_sha256": SHA256["best_epoch"], "source_sha256": {k: SHA256[k] for k in ("models.py", "mbmp_torch.py")},
                    "input_files": [{"path": str(p.relative_to(self.cache_dir)), "sha256": _sha256(p)} for p in input_paths]}
        manifest_path = out / "input_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        paths["input_manifest"] = str(manifest_path)
        return {"status": summary["status"], "summary": summary, "metrics": metrics,
                "rgb": _rgb(raw), "background_rgb": _rgb(raw, 6), "scores": scores,
                "mask": mask, "reference": reference, "mbmp": mbmp.numpy(),
                "bounds": [[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
                "center": [float(row.lat), float(row.lon)], "plume_geojson": geojson, "paths": paths}
