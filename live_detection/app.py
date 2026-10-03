"""Guided Colab map for latest-available UAE satellite detection.

Usage: app = LatestDetectionApp(workspace); app.display()
The map stays mounted. One background worker handles detection and history.
Automatic checks are off until explicitly enabled and need a live runtime.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import contextvars
import hashlib
from datetime import datetime, timezone
from html import escape
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import threading
import zipfile
import uuid

import ipywidgets as W
from ipyleaflet import Map, Marker, Rectangle, basemaps
from IPython.display import display, Javascript, JSON
from pyproj import Geod


CHECK_INTERVAL_SECONDS = 15 * 60
_GEOD = Geod(ellps="WGS84")


def _selection(latitude, longitude):
    if not all(math.isfinite(v) for v in (latitude, longitude)):
        raise ValueError("Enter valid latitude and longitude numbers.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Latitude must be between -90 and 90; longitude between -180 and 180.")
    # A coarse input guard, not a legal UAE land-boundary classifier. The
    # engine applies the actual UAE area/coverage checks before inference.
    if not (22 <= latitude <= 27 and 51 <= longitude <= 57):
        raise ValueError("Choose a location in the UAE. This point is outside the UAE study region.")
    west = _GEOD.fwd(longitude, latitude, 270, 1000)[0]
    east = _GEOD.fwd(longitude, latitude, 90, 1000)[0]
    south = _GEOD.fwd(longitude, latitude, 180, 1000)[1]
    north = _GEOD.fwd(longitude, latitude, 0, 1000)[1]
    return (float(latitude), float(longitude)), (west, south, east, north)


class LatestDetectionApp:
    def __init__(self, workspace="geoguard_live", engine=None):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        if engine is None:
            try:
                from .engine import LatestDetector
            except ImportError:
                from engine import LatestDetector
            engine = LatestDetector(self.workspace)
        self.engine = engine
        self.result = None
        self.history_result = None
        self.last_archive = None
        self._generation = 0
        self._schedule_generation = 0
        self._closed = False
        self._busy = False
        self._changing_coordinates = False
        self._timer = None
        self._lock = threading.RLock()
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="geoguard-detection")
        self._future = None
        self._loop = None
        self._callback_context = contextvars.copy_context()
        try:
            from IPython import get_ipython
            self._loop = getattr(getattr(get_ipython(), "kernel", None), "io_loop", None)
        except Exception:
            pass

        self.lat = W.FloatText(value=23.86479, description="Latitude:", layout=W.Layout(width="240px"))
        self.lon = W.FloatText(value=53.61893, description="Longitude:", layout=W.Layout(width="240px"))
        self.check = W.Button(description="Check latest image", icon="search", button_style="primary",
                              layout=W.Layout(width="210px"))
        self.auto = W.Checkbox(value=False, description="Check for new images every 15 minutes",
                              indent=False, layout=W.Layout(width="370px"))
        self.save = W.Button(description="Download evidence + history", icon="download", disabled=True,
                             layout=W.Layout(width="260px"))
        self.area = W.HTML()
        self.status = W.HTML("<p>Choose a location, then press <b>Check latest image</b>.</p>")
        self.summary = W.HTML()
        self.history_summary = W.HTML()
        self.schedule = W.HTML("<p>Automatic checks are off.</p>")
        self.download_status = W.HTML()
        self.figure = W.Image(format="png", layout=W.Layout(display="none", width="100%", max_width="1050px"))
        self.map = Map(center=(24.15, 54.1), zoom=7, basemap=basemaps.Esri.WorldImagery,
                       scroll_wheel_zoom=True, layout=W.Layout(height="430px"))
        self.marker = Marker(location=(self.lat.value, self.lon.value), draggable=False)
        self.box = Rectangle(bounds=((23.85, 53.60), (23.88, 53.64)), color="#e59a24",
                             weight=3, fill_opacity=0.08)
        self.map.add(self.box)
        self.map.add(self.marker)
        self.map.on_interaction(self._map_event)
        self.lat.observe(self._input_changed, names="value")
        self.lon.observe(self._input_changed, names="value")
        self.check.on_click(self.start)
        self.auto.observe(self._auto_changed, names="value")
        self.save.on_click(self.download)
        self._update_selection()
        self.widget = W.VBox([
            W.HTML("<h2>GeoGuard · Latest available satellite check</h2>"
                   "<p><b>1. Choose your area.</b> Click the map or enter coordinates. The outlined square is approximately <b>2 km × 2 km</b>. "
                   "The starting point is only a test location; choose any supported UAE location.</p>"
                   "<p>The background map is for navigation. Its imagery is not the dated satellite image being analyzed.</p>"),
            W.HBox([self.lat, self.lon], layout=W.Layout(flex_flow="row wrap")),
            self.area, self.map,
            W.HTML("<p><b>2. Check the newest available image.</b> GeoGuard checks the catalog and processes a supported image when available. "
                   "The displayed acquisition date tells you when the satellite observed the area; this is not continuous live air measurement.</p>"),
            W.HBox([self.check, self.auto], layout=W.Layout(flex_flow="row wrap")), self.schedule,
            self.status, self.summary, self.figure,
            W.HTML("<p><b>3. Keep the evidence and history.</b> A candidate is an experimental detector flag needing review. "
                   "No candidate does not mean clean air or zero methane. Unusable or missing data stay unknown.</p>"
                   "<p><b>Download before disconnecting:</b> new detection history is stored in this Colab runtime and can be lost when the runtime ends. "
                   "Download the evidence and history to keep it. Your earlier saved provider-history files remain separate.</p>"),
            self.history_summary, self.save, self.download_status,
        ])

    def _post(self, callback, *args):
        if self._closed:
            return
        # Colab tags widget-originated requests with context variables. Carry
        # that context into delayed updates; a fresh copy avoids re-entry.
        context = self._callback_context.copy()
        if self._loop is not None:
            self._loop.add_callback(lambda: None if self._closed else context.run(callback, *args))
        else:
            context.run(callback, *args)

    def _update_selection(self):
        try:
            center, bounds = _selection(self.lat.value, self.lon.value)
            self.marker.location = center
            west, south, east, north = bounds
            self.box.bounds = ((south, west), (north, east))
            self.area.value = (f"<p><b>Selected center:</b> {center[0]:.6f}, {center[1]:.6f} · "
                               "approximately 2 km × 2 km. Data and UAE coverage are checked when you run.</p>")
            return center
        except ValueError as exc:
            self.area.value = "<p><b>Location needs attention:</b> " + escape(str(exc)) + "</p>"
            return None

    def _map_event(self, **event):
        if event.get("type") != "click" or not event.get("coordinates"):
            return
        self._changing_coordinates = True
        try:
            self.lat.value, self.lon.value = event["coordinates"]
        finally:
            self._changing_coordinates = False
        self._input_changed({})

    def _input_changed(self, change):
        if self._changing_coordinates:
            return
        with self._lock:
            self._generation += 1
            self.result = None
            self.history_result = None
            if hasattr(self, "_bridge_states"): self._bridge_states.clear()
        self.save.disabled = True
        self.summary.value = ""
        self.history_summary.value = ""
        self.figure.value = b""
        self.figure.layout.display = "none"
        self.download_status.value = ""
        self._update_selection()
        self.status.value = ("<p><b>Location changed.</b> Press Check latest image for this area. "
                             "Any check already running belongs to the earlier location.</p>")

    def _progress(self, generation, message):
        if generation == self._generation:
            self.status.value = "<p><b>Checking:</b> " + escape(str(message)) + "</p>"

    def start(self, _=None):
        if self._closed:
            return
        center = self._update_selection()
        if center is None:
            return
        with self._lock:
            if self._busy:
                return
            self._callback_context = contextvars.copy_context()
            self._busy = True
            generation = self._generation
            self.result = None
            self.history_result = None
            if hasattr(self, "_bridge_states"): self._bridge_states.clear()
        self.check.disabled = True
        self.save.disabled = True
        self.summary.value = ""
        self.history_summary.value = ""
        self.figure.value = b""
        self.figure.layout.display = "none"
        self.download_status.value = ""
        self.status.value = "<p>Checking available satellite images. The first download can take a few minutes.</p>"
        self.map.center = center
        self.map.zoom = max(self.map.zoom, 10)
        self._future = self._worker.submit(self._run, generation, center)
        return self._future

    def _run(self, generation, center):
        try:
            result = self.engine.run(center[0], center[1], progress=lambda message:
                                     self._post(self._progress, generation, message))
            if not isinstance(result, dict):
                raise ValueError("The detector did not return a result record.")
            try:
                history = self.engine.history(center[0], center[1])
            except Exception as exc:
                history = {"records": [], "history_error": str(exc), "forecast": {"status": "unavailable"}}
            self._post(self._finished, generation, result, history)
        except Exception as exc:
            self._post(self._finished, generation, {"status": "error", "message": str(exc)}, None)

    def _finished(self, generation, result, history):
        with self._lock:
            self._busy = False
            current = generation == self._generation
        self.check.disabled = False
        if not current:
            self.status.value = "<p>The previous area's check finished. Press <b>Check latest image</b> to process your current selection.</p>"
            return
        self.result, self.history_result = result, history
        titles = {
            "candidate": "Possible plume candidate flagged — review needed",
            "no_candidate": "No candidate flagged in this image",
            "not_assessable": "This image could not be assessed",
            "error": "The check could not be completed",
            "no_new_image": "No new image to process",
        }
        status = result.get("status", "error")
        self.status.value = "<h3>" + escape(titles.get(status, "Check completed")) + "</h3><p>" + escape(str(result.get("message", ""))) + "</p>"
        labels = [("Newest catalog acquisition (datatake time)", "newest_catalog_acquired_at"),
                  ("Image used for this check (tile acquisition time)", "current_acquired_at"),
                  ("Comparison image acquisition", "background_acquired_at"),
                  ("Provider availability timestamp", "provider_available_at"),
                  ("Catalog checked", "checked_at")]
        self.summary.value = "<p>" + "<br>".join("<b>" + label + ":</b> " + escape(str(result.get(key) or "Not available"))
                                                 for label, key in labels) + "</p>"
        newest = result.get("newest_catalog_id")
        used = result.get("current_product_id")
        if newest and used and newest != used:
            self.summary.value += ("<p><b>An older image was used.</b> The newest catalog image was not the image processed in this result. "
                                   "Use the image dates above when interpreting the flag.</p>")
        wind = result.get("wind") or {}
        if wind.get("fallback_used"):
            wind_text = "GFS model via Open-Meteo (NASA source unavailable)."
        else:
            wind_text = str(wind.get("source") or "Not available; no wind source reported for this result.")
        self.summary.value += "<p><b>Wind:</b> " + escape(wind_text) + "</p>"
        paths = result.get("paths") or {}
        figure = self._artifact(paths.get("figure"), ".png")
        if figure:
            self.figure.value = figure.read_bytes()
            self.figure.layout.display = "block"
        if history is not None and not history.get("history_error"):
            count = len(history.get("records") or [])
            self.history_summary.value = f"<p><b>History saved:</b> {count} product/model result(s) for this exact area.</p>"
        else:
            reason = (history or {}).get("history_error", "History was not available for this failed check.")
            self.history_summary.value = "<p><b>History unavailable:</b> " + escape(str(reason)) + "</p>"
        forecast = (history or {}).get("forecast") or {}
        reasons = forecast.get("reasons") or ["A forecast for this area needs reviewed history and chronological validation."]
        self.history_summary.value += ("<p><b>Forecast unavailable.</b> History is retained for future validated forecasting; "
            "no probability is invented.<br>" + "<br>".join(escape(str(reason)) for reason in reasons[:3]) + "</p>")
        self.save.disabled = False

    def _artifact(self, value, suffix):
        if not value:
            return None
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        candidate = candidate.resolve()
        if candidate.is_relative_to(self.workspace) and candidate.suffix.lower() == suffix and candidate.is_file():
            return candidate
        return None

    def _auto_changed(self, change):
        self._schedule_generation += 1
        token = self._schedule_generation
        if self._timer:
            self._timer.cancel()
        if change["new"] and not self._closed:
            self.schedule.value = ("<p>Automatic checks enabled: every <b>15 minutes</b>, only while this runtime is connected and running. "
                                   "The next check is in 15 minutes. Refreshing the catalog does not create a new satellite observation.</p>")
            self._schedule_next(token)
        else:
            self.schedule.value = "<p>Automatic checks are off. Any check already running will finish.</p>"

    def _schedule_next(self, token):
        if self._closed or not self.auto.value or token != self._schedule_generation:
            return
        self._timer = threading.Timer(CHECK_INTERVAL_SECONDS, lambda: self._post(self._scheduled_check, token))
        self._timer.daemon = True
        self._timer.start()

    def _scheduled_check(self, token):
        if self._closed or not self.auto.value or token != self._schedule_generation:
            return
        self.start()
        self._schedule_next(token)

    def download(self, _=None):
        if self.result is None or self.save.disabled:
            return
        folder = self.workspace / "ui_exports"
        folder.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive = folder / f"geoguard-latest-evidence-{stamp}.zip"
        try:
            bundle = self._artifact((self.result.get("paths") or {}).get("bundle"), ".zip")
            database = self._artifact(getattr(self.engine, "db", self.workspace / "history.sqlite"), ".sqlite")
            with tempfile.TemporaryDirectory(prefix="history-backup-", dir=folder) as temporary:
                backup = Path(temporary) / "history.sqlite"
                if database:
                    # SQLite's backup API includes committed rows consistently
                    # even if another connection is appending new attempts.
                    # Never copy only the main file of a live/WAL database.
                    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
                        with closing(sqlite3.connect(backup)) as destination:
                            source.backup(destination)
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                    z.writestr("selected_result.json", json.dumps(self.result, indent=2, allow_nan=False, default=str))
                    z.writestr("selected_area_history.json", json.dumps(self.history_result, indent=2, allow_nan=False, default=str))
                    if bundle:
                        z.write(bundle, "detector_evidence.zip")
                    if backup.is_file():
                        z.write(backup, "history.sqlite")
                    restore = ("history.sqlite is a consistent backup of every area and attempt stored in this runtime, not only the current selection.\n"
                               "To restore: stop automatic checks and close the app/runtime's database connections first. Keep an extra copy of any existing history.\n"
                               "Place history.sqlite in geoguard_asap_history/ before reopening the map. Do not overwrite a database while the app is running.\n"
                               "Only restore your own trusted backup. This notebook does not automatically import downloaded files.\n"
                               if backup.is_file() else "No SQLite history file existed for this check; the archive contains the selected result/history JSON only.\n")
                    z.writestr("README.txt", "Experimental methane candidate detection on dated satellite imagery.\n"
                               "The map background is navigation only. No candidate is not a clean-air claim.\n"
                               "Missing or unassessable observations stay unknown. Forecast is unavailable pending validation.\n\n" + restore)
            self.last_archive = archive
            try:
                from google.colab import files
                files.download(str(archive))
                self.download_status.value = "<p>Evidence and history download requested.</p>"
            except ImportError:
                self.download_status.value = "<p>Saved: " + escape(str(archive)) + "</p>"
            return archive
        except Exception as exc:
            self.download_status.value = "<p>Download could not be prepared: " + escape(str(exc)) + "</p>"

    def display(self):
        display(self.widget)
        self._install_colab_bridge()
        return self

    def _refresh_colab_widgets(self):
        if self._closed:
            return JSON({"closed": True, "busy": False})
        # Colab may drop unsolicited background comm updates. Explicitly
        # resync changed traits from a frontend-originated callback instead.
        specs = [(self.status, ("value",)), (self.summary, ("value",)),
                 (self.history_summary, ("value",)), (self.area, ("value",)),
                 (self.schedule, ("value",)), (self.download_status, ("value",)),
                 (self.check, ("disabled",)), (self.save, ("disabled",)),
                 (self.lat, ("value",)), (self.lon, ("value",)), (self.auto, ("value",)),
                 (self.figure, ("value", "format")), (self.figure.layout, ("display",)),
                 (self.marker, ("location",)), (self.box, ("bounds",)),
                 (self.map, ("center", "zoom"))]
        for widget, keys in specs:
            values = [getattr(widget, key) for key in keys]
            state = tuple(hashlib.sha256(value).hexdigest() if isinstance(value, (bytes, bytearray, memoryview))
                          else json.dumps(value, sort_keys=True, default=str) for value in values)
            ident = (widget.model_id, keys)
            if self._bridge_states.get(ident) != state:
                widget.send_state(list(keys))
                self._bridge_states[ident] = state
        return JSON({"closed": False, "busy": self._busy})

    def _install_colab_bridge(self):
        try:
            from google.colab import output
        except ImportError:
            return
        previous = getattr(self, "_bridge_name", None)
        if previous:
            try:
                output.unregister_callback(previous)
            except ValueError:
                pass
        self._bridge_states = {}
        self._bridge_name = "geoguard.refresh." + uuid.uuid4().hex
        output.register_callback(self._bridge_name, self._refresh_colab_widgets)
        # One outstanding request at a time; stop when this output unloads,
        # the app closes, or the callback disappears after a runtime reset.
        script = r"""(() => {
          const name = __CALLBACK__;
          const marker = document.createElement('span');
          marker.style.display = 'none'; document.body.appendChild(marker);
          let stopped = false, timer = null, errors = 0;
          const stop = () => { stopped = true; clearTimeout(timer); marker.remove(); };
          window.addEventListener('pagehide', stop, {once: true});
          window.addEventListener('unload', stop, {once: true});
          const refresh = async () => {
            if (stopped || !marker.isConnected) return stop();
            let delay = 5000;
            try {
              const kernel = (typeof colab !== 'undefined' && colab.kernel)
                || (typeof google !== 'undefined' && google.colab && google.colab.kernel);
              if (!kernel) return stop();
              const reply = await kernel.invokeFunction(name, [], {});
              let state = reply && reply.data && reply.data['application/json'];
              if (typeof state === 'string') state = JSON.parse(state);
              if (state && state.closed) return stop();
              delay = state && state.busy ? 2000 : 5000; errors = 0;
            } catch (error) {
              if (/not found|not registered/i.test(String(error)) || ++errors >= 3) return stop();
            }
            if (!stopped && marker.isConnected) timer = setTimeout(refresh, delay);
          };
          refresh();
        })();""".replace("__CALLBACK__", json.dumps(self._bridge_name))
        display(Javascript(script))

    def close(self):
        self._closed = True
        self._schedule_generation += 1
        if self._timer:
            self._timer.cancel()
        if getattr(self, "_bridge_name", None):
            try:
                from google.colab import output
                output.unregister_callback(self._bridge_name)
            except (ImportError, ValueError):
                pass
            self._bridge_name = None
        self._worker.shutdown(wait=False, cancel_futures=True)


# Short alias for notebook authors.
LiveDetectionApp = LatestDetectionApp
