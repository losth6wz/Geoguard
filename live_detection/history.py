"""Persistent, auditable satellite detection history (Python standard library).

HistoryStore(path).record(record) accepts the flat fields below. Required:
  requested_bounds: [west, south, east, north], in geographic degrees
  product_id, product_version, sensor, model_id, model_hash: nonempty strings
  acquired_at, fetched_at: timezone-aware ISO-8601 timestamps
  status: candidate | no_candidate | not_assessable
  quality_status: usable | unusable | unknown
Optional: aoi_id (otherwise SHA256 of exact bounds), provider_available_at,
  inferred_at, details (JSON object), reviewed_label (0/1), reviewed_at,
  review_available_at, review_source. Reviewed labels are independent evidence.

Successful detector outputs require usable input and an inference timestamp.
No-candidate means this detector found no candidate in this usable observation;
it never means zero methane or clean air. Unknown quality stays unknown.
All times are normalized to UTC. Actual local storage time is recorded too.

The canonical view keeps the newest successful inference for an exact AOI,
product/version, sensor and model/hash. Failed reruns cannot erase a successful
result. Every distinct attempt remains in SQLite; identical retries deduplicate.
This module does not fit, load or issue a forecast probability.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3


STATUSES = {"candidate", "no_candidate", "not_assessable"}
SUCCESS = {"candidate", "no_candidate"}
QUALITIES = {"usable", "unusable", "unknown"}
UTC = timezone.utc
REVIEW_FIELDS = ("reviewed_label", "reviewed_at", "review_available_at", "review_source")
TARGET = ("Reviewed methane plume present on the next usable satellite observation "
          "acquired after the forecast issue time and within 14 days, conditional "
          "on such an observation arriving; not continuous emissions or concentration.")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _time(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a timezone-aware ISO timestamp")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid {field}") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return stamp.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def aoi_hash(requested_bounds):
    """Exact normalized numeric bounds define an area; no snapping/rounding."""
    if not isinstance(requested_bounds, (list, tuple)) or len(requested_bounds) != 4:
        raise ValueError("requested_bounds must be [west, south, east, north]")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
           for x in requested_bounds):
        raise ValueError("All bounds must be finite numbers")
    west, south, east, north = map(float, requested_bounds)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Invalid or antimeridian-crossing bounds")
    return _hash([west, south, east, north])


def _normalize(source):
    if not isinstance(source, dict):
        raise ValueError("record must be a dictionary")
    # Round-trip copies nested details and rejects non-JSON/non-finite values.
    row = json.loads(_json(source))
    bounds_hash = aoi_hash(row.get("requested_bounds"))
    row["requested_bounds"] = [float(x) for x in row["requested_bounds"]]
    row["aoi_bounds_hash"] = bounds_hash
    row.setdefault("aoi_id", bounds_hash)
    for field in ("aoi_id", "product_id", "product_version", "sensor", "model_id", "model_hash"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
    if row.get("status") not in STATUSES:
        raise ValueError("Unknown detection status")
    if row.get("quality_status") not in QUALITIES:
        raise ValueError("quality_status must be usable, unusable or unknown")
    for field in ("acquired_at", "fetched_at"):
        row[field] = _time(row.get(field), field)
    for field in ("provider_available_at", "inferred_at", "reviewed_at", "review_available_at"):
        row[field] = _time(row[field], field) if row.get(field) is not None else None
    if row["fetched_at"] < row["acquired_at"]:
        raise ValueError("fetched_at cannot precede acquisition")
    if row["provider_available_at"] is not None and not (
            row["acquired_at"] <= row["provider_available_at"] <= row["fetched_at"]):
        raise ValueError("provider_available_at must fall between acquisition and fetch")
    if row["inferred_at"] is not None and row["inferred_at"] < row["fetched_at"]:
        raise ValueError("inferred_at cannot precede input fetch")
    if row["status"] in SUCCESS and (row["quality_status"] != "usable" or row["inferred_at"] is None):
        raise ValueError("A detector result requires usable input and inferred_at")
    label = row.get("reviewed_label")
    if label is not None and (type(label) not in (int, bool) or label not in (0, 1)):
        raise ValueError("reviewed_label must be 0, 1 or null")
    row["reviewed_label"] = int(label) if label is not None else None
    row.setdefault("review_source", None)
    if label is not None:
        if not row["reviewed_at"] or not row["review_available_at"] or not row["review_source"]:
            raise ValueError("A reviewed label needs review time, availability and source")
        if not row["acquired_at"] <= row["reviewed_at"] <= row["review_available_at"]:
            raise ValueError("Review timestamps are not chronological")
    elif any(row[field] is not None for field in REVIEW_FIELDS[1:]):
        raise ValueError("Review metadata requires an explicit reviewed label")
    row.setdefault("details", {})
    if not isinstance(row["details"], dict):
        raise ValueError("details must be a JSON object")
    # Never permit a caller to spoof receipt time or database-generated IDs.
    for field in ("recorded_at", "clock_at", "record_id", "record_action", "first_recorded_at", "last_updated_at", "review_recorded_at"):
        row.pop(field, None)
    row["record_id"] = _hash([row[k] for k in (
        "aoi_id", "aoi_bounds_hash", "product_id", "product_version", "sensor", "model_id", "model_hash")])
    row["schema_version"] = 1
    return row


def _rank(row):
    return (row["status"] in SUCCESS, row["inferred_at"] or row["fetched_at"], row["fetched_at"])


def _combine(old, new):
    """Select the newest successful inference and newest independent review."""
    if old is None:
        return dict(new)
    if old["acquired_at"] != new["acquired_at"]:
        raise ValueError("Same product/version cannot have contradictory acquisition times")
    chosen = dict(new if _rank(new) >= _rank(old) else old)
    reviews = [r for r in (old, new) if r["reviewed_label"] is not None]
    if reviews:
        latest = max(reviews, key=lambda r: (r["review_available_at"], r["recorded_at"]))
        for field in REVIEW_FIELDS:
            chosen[field] = latest[field]
        chosen["review_recorded_at"] = latest["review_recorded_at"]
    chosen["first_recorded_at"] = min(old.get("first_recorded_at", old["recorded_at"]), new["recorded_at"])
    chosen["last_updated_at"] = max(old.get("last_updated_at", old["recorded_at"]), new["recorded_at"])
    return chosen


class HistoryStore:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS areas (
                aoi_id TEXT PRIMARY KEY, bounds_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY, digest TEXT NOT NULL UNIQUE,
                record_id TEXT NOT NULL, aoi_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS attempts_area_time ON attempts(aoi_id, recorded_at);
            CREATE TABLE IF NOT EXISTS canonical (
                record_id TEXT PRIMARY KEY, aoi_id TEXT NOT NULL, payload TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def record(self, source):
        """Append a distinct attempt; return the canonical record and action.

        A failed retry is saved for audit, while its return value retains any
        earlier successful inference with record_action='preserved_success'.
        """
        row = _normalize(source)
        digest = _hash(row)
        row["recorded_at"] = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        row["clock_at"] = row["recorded_at"]
        # Future-dated inputs are not historical measurements known now.
        for field in ("fetched_at", "inferred_at", "review_available_at"):
            if row[field] is not None and row[field] > row["recorded_at"]:
                raise ValueError(f"{field} cannot be in the future")
        with self.db:
            # Serialize the read/choose/write sequence across concurrent
            # requests, so a failed rerun cannot win a write race.
            self.db.execute("BEGIN IMMEDIATE")
            # Some Windows clocks return the same microsecond for successive
            # inserts. Keep raw clock_at and a strictly ordered recorded_at,
            # otherwise an as-of cutoff at the first insert could include a
            # later review with an identical timestamp. No acquisition or
            # provider/review time is changed by this ordering adjustment.
            last = self.db.execute("SELECT MAX(recorded_at) FROM attempts").fetchone()[0]
            if last is not None and row["recorded_at"] <= last:
                row["recorded_at"] = (datetime.fromisoformat(last.replace("Z", "+00:00"))
                    + timedelta(microseconds=1)).isoformat(timespec="microseconds").replace("+00:00", "Z")
            row["first_recorded_at"] = row["recorded_at"]
            row["last_updated_at"] = row["recorded_at"]
            row["review_recorded_at"] = row["recorded_at"] if row["reviewed_label"] is not None else None
            area = self.db.execute("SELECT bounds_hash FROM areas WHERE aoi_id=?", (row["aoi_id"],)).fetchone()
            if area and area[0] != row["aoi_bounds_hash"]:
                raise ValueError("aoi_id already represents different requested bounds")
            old_result = self.db.execute("SELECT payload FROM canonical WHERE record_id=?", (row["record_id"],)).fetchone()
            old = json.loads(old_result[0]) if old_result else None
            if self.db.execute("SELECT 1 FROM attempts WHERE digest=?", (digest,)).fetchone():
                return {**old, "record_action": "duplicate"}
            selected = _combine(old, row)
            self.db.execute("INSERT OR IGNORE INTO areas VALUES (?,?)", (row["aoi_id"], row["aoi_bounds_hash"]))
            self.db.execute("INSERT INTO attempts(digest,record_id,aoi_id,recorded_at,payload) VALUES (?,?,?,?,?)",
                            (digest, row["record_id"], row["aoi_id"], row["recorded_at"], _json(row)))
            self.db.execute("INSERT OR REPLACE INTO canonical VALUES (?,?,?)",
                            (row["record_id"], row["aoi_id"], _json(selected)))
        action = "recorded"
        if old and old["status"] in SUCCESS and row["status"] not in SUCCESS:
            action = "preserved_success"
        elif old and _rank(row) < _rank(old):
            action = "preserved_newer_result"
        return {**selected, "record_action": action}

    def records(self, aoi_id, as_of=None):
        """Return chronological canonical results, optionally as locally known.

        As-of replay uses local recorded_at, not historical acquisition time.
        This is strictly ordered at microsecond resolution; clock_at preserves
        the raw local clock when multiple writes share the same clock tick.
        Retroactively downloaded observations/reviews are therefore excluded.
        """
        if as_of is None:
            rows = [json.loads(r[0]) for r in self.db.execute(
                "SELECT payload FROM canonical WHERE aoi_id=?", (aoi_id,))]
        else:
            cutoff = _time(as_of, "as_of")
            chosen = {}
            for (payload,) in self.db.execute(
                    "SELECT payload FROM attempts WHERE aoi_id=? AND recorded_at<=? ORDER BY id",
                    (aoi_id, cutoff)):
                row = json.loads(payload)
                chosen[row["record_id"]] = _combine(chosen.get(row["record_id"]), row)
            rows = list(chosen.values())
        return sorted(rows, key=lambda r: (r["acquired_at"], r["product_id"], r["model_hash"]))

    def forecast_readiness(self, aoi_id):
        rows = self.records(aoi_id)
        # Count observations, not model reruns, and surface label conflicts.
        visits = {}
        for row in rows:
            if row["quality_status"] == "usable" and row["reviewed_label"] is not None:
                # Pipeline/product revisions and model reruns are audit rows,
                # not extra physical satellite visits. Conflicting review
                # labels across revisions remain visible below.
                key = (row["sensor"], row["product_id"], row["acquired_at"])
                visits.setdefault(key, set()).add(row["reviewed_label"])
        present = sum(labels == {1} for labels in visits.values())
        absent = sum(labels == {0} for labels in visits.values())
        conflicts = sum(len(labels) > 1 for labels in visits.values())
        reasons = []
        if not rows:
            reasons.append("No detection history has been recorded for this exact requested area.")
        if not present or not absent:
            reasons.append("Need a series of usable observations with reviewed presence and absence; detector candidates and missing catalog entries are not reviewed labels.")
        if conflicts:
            reasons.append("Conflicting reviewed labels exist for the same observation; resolve them before training.")
        reasons.append("No chronological UAE forecast validation, baseline comparison, or validated model for this area and sensor configuration has been completed.")
        return {
            "status": "unavailable", "probability": None, "model_fitted": False,
            "aoi_id": aoi_id, "proposed_target": TARGET,
            "counts": {
                "stored_product_model_results": len(rows),
                "candidate": sum(r["status"] == "candidate" for r in rows),
                "no_candidate": sum(r["status"] == "no_candidate" for r in rows),
                "not_assessable": sum(r["status"] == "not_assessable" for r in rows),
                "usable_reviewed_present_observations": present,
                "usable_reviewed_absent_observations": absent,
                "conflicting_reviewed_observations": conflicts,
            },
            "reasons": reasons,
            "history_use": "Retained for future validated training; missing data and unassessable observations remain unknown.",
        }

    def export_json(self, aoi_id):
        return json.dumps({"records": self.records(aoi_id), "forecast": self.forecast_readiness(aoi_id)}, indent=2, allow_nan=False)

    def export_csv(self, aoi_id):
        fields = ["aoi_id", "requested_bounds", "product_id", "product_version", "sensor",
                  "model_id", "model_hash", "acquired_at", "provider_available_at", "fetched_at",
                  "inferred_at", "status", "quality_status", *REVIEW_FIELDS, "recorded_at", "review_recorded_at", "last_updated_at"]
        out = io.StringIO(newline="")
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in self.records(aoi_id):
            writer.writerow({**row, "requested_bounds": _json(row["requested_bounds"])})
        return out.getvalue()
