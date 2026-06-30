import argparse
import csv
import json
import math
import time
import yaml
from datetime import datetime
from pathlib import Path

import requests

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

_MISSING = "-999"
_STATIONS_YAML = "/data/DATA/OBS/meta/stations/khoa.yaml"
ID_FIELD   = "station_id"
TIME_FIELD = "time"


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def parse_args():
    parser = argparse.ArgumentParser(description="KHOA HF current collector -> daily CSV")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "config" / "khoa_config.toml"))
    parser.add_argument("--obs-codes")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--show-sample", action="store_true")
    return parser.parse_args()


def _load_stn_meta() -> dict:
    with open(_STATIONS_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {
        str(s["id"]): {
            "station_name_k": s.get("name_k", ""),
            "station_type":   s.get("type", ""),
            "area_name":      s.get("sea", ""),
        }
        for s in data.get("stations", [])
    }


def _fval(v):
    try:
        f = float(v)
        return None if f == -999 else f
    except (ValueError, TypeError):
        return None


def _current_uv(spd, drct):
    s, d = _fval(spd), _fval(drct)
    if s is None or d is None:
        return _MISSING, _MISSING
    r = math.radians(d)
    return str(round(s * math.sin(r), 4)), str(round(s * math.cos(r), 4))


def parse_json_items(json_text: str):
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError:
        return [], None
    if not isinstance(payload, dict):
        return [], None
    if isinstance(h := payload.get("header"), dict):
        rc = str(h.get("resultCode", "")).strip()
        if rc and rc != "00":
            return [], None
    body = payload.get("body")
    if not isinstance(body, dict):
        return [], None
    items_block = body.get("items")
    data = []
    if isinstance(items_block, dict):
        item_value = items_block.get("item")
        if isinstance(item_value, list):
            data = item_value
        elif isinstance(item_value, dict):
            data = [item_value]
    items = []
    for item in data:
        if isinstance(item, dict):
            items.append({str(k): "" if v is None else str(v).strip() for k, v in item.items()})
    return items, body.get("totalCount")


def normalize_time(value: str) -> str:
    if not value:
        return ""
    return f"{value}:00" if len(value) == 16 else value


def build_output_path(storage_cfg, target_date):
    tokens = {"yyyy": target_date.strftime("%Y"), "yyyymmdd": target_date.strftime("%Y%m%d")}
    return Path(storage_cfg["output_root"]) / storage_cfg["dir_layout"].format_map(tokens) / storage_cfg["file_pattern"].format_map(tokens)


def is_missing(value) -> bool:
    return value in ("", None, _MISSING)


def normalize_value(value) -> str:
    return "" if value is None else str(value).strip()


def request_with_retry(url, params, timeout, max_retry, sleep_seconds):
    retry_wait = float(params.pop("__retry_wait__", 1800))
    while True:
        last_error = None
        for attempt in range(1, max_retry + 1):
            try:
                r = requests.get(url, params=params, timeout=timeout)
                if r.status_code == 200:
                    return r
                last_error = RuntimeError(f"HTTP {r.status_code}")
                print(f"[WARN] HTTP {r.status_code} ({attempt}/{max_retry})")
                if r.text:
                    print(f"[WARN] {r.text[:300]}")
            except requests.RequestException as exc:
                last_error = exc
                print(f"[WARN] {exc} ({attempt}/{max_retry})")
            if attempt < max_retry:
                time.sleep(sleep_seconds)
        print(f"[ERROR] {last_error}. Retrying in {retry_wait/60:g}m...")
        time.sleep(retry_wait)


def fetch_items(api_cfg, req_cfg, obs_code, req_date):
    params = {
        "pageNo": req_cfg.get("page_no", 1),
        "numOfRows": req_cfg.get("num_of_rows", 300),
        "type": api_cfg.get("result_type", "json"),
        "obsCode": obs_code, "reqDate": req_date,
        "serviceKey": api_cfg["service_key"],
        "__retry_wait__": float(api_cfg.get("retry_wait_seconds", 1800)),
    }
    r = request_with_retry(api_cfg["base_url"], params,
                           int(api_cfg.get("request_timeout", 120)),
                           int(api_cfg.get("max_retry", 5)),
                           float(api_cfg.get("sleep_seconds", 0.2)))
    return parse_json_items(r.text) if r else ([], None)


def build_row(obs_code, item, mapping, output_fields):
    row = {f: "" for f in output_fields}
    row[ID_FIELD] = obs_code
    row[TIME_FIELD] = normalize_time(normalize_value(item.get(mapping[TIME_FIELD], "")))
    for out_key, in_key in mapping.items():
        if out_key in (TIME_FIELD, ID_FIELD) or not in_key:
            continue
        row[out_key] = normalize_value(item.get(in_key, ""))
    return row


def build_row_key(row):
    return (row.get(ID_FIELD, ""), row.get(TIME_FIELD, ""),
            row.get("lat", ""), row.get("lon", ""))


def merge_rows(existing, incoming, output_fields):
    merged = dict(existing)
    for field in output_fields:
        if field in (TIME_FIELD, ID_FIELD):
            continue
        old_val = merged.get(field, "")
        new_val = incoming.get(field, "")
        if is_missing(new_val):
            merged[field] = old_val if not is_missing(old_val) else _MISSING
        else:
            merged[field] = new_val
    return merged


def main():
    args   = parse_args()
    cfg    = load_config(Path(args.config))["hf"]
    daily_cfg     = cfg["storage"]["daily"]
    output_fields = list(cfg["output"]["fields"])
    mapping       = dict(cfg["mapping"])
    date_fmt      = cfg["request"].get("req_date_format", "%Y%m%d")
    target_date   = datetime.strptime(args.date, date_fmt)
    req_date_base = target_date.strftime(date_fmt)

    obs_codes = ([c.strip() for c in args.obs_codes.split(",") if c.strip()]
                 if args.obs_codes else list(cfg["stations"]["obs_codes"]))
    if args.limit is not None:
        obs_codes = obs_codes[:args.limit]

    output_path = build_output_path(daily_cfg, target_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    existing_rows: dict[tuple, dict] = {}
    if output_path.exists():
        with output_path.open("r", newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                existing_rows[build_row_key(row)] = row

    api_cfg   = cfg["api"]
    req_cfg   = cfg["request"]
    api_counts = []

    for obs_code in obs_codes:
        for hour in range(24):
            req_date = f"{req_date_base}{hour:02d}"
            print(f"[INFO] {obs_code} {req_date}...")
            items, total_count = fetch_items(api_cfg, req_cfg, obs_code, req_date)
            if total_count is not None:
                api_counts.append(total_count)
            for item in items:
                row = build_row(obs_code, item, mapping, output_fields)
                if not row[TIME_FIELD]:
                    continue
                key = build_row_key(row)
                if key in existing_rows:
                    existing_rows[key] = merge_rows(existing_rows[key], row, output_fields)
                else:
                    for field in output_fields:
                        if field not in (TIME_FIELD, ID_FIELD) and is_missing(row[field]):
                            row[field] = _MISSING
                    existing_rows[key] = row

    rows = list(existing_rows.values())
    for row in rows:
        for field in output_fields:
            if field not in (TIME_FIELD, ID_FIELD) and is_missing(row.get(field, "")):
                row[field] = _MISSING
    rows.sort(key=lambda r: (r.get(ID_FIELD, ""), r.get(TIME_FIELD, ""),
                              r.get("lat", ""), r.get("lon", "")))

    # 메타 보강
    stn_meta = _load_stn_meta()
    for row in rows:
        sid = str(row.get(ID_FIELD, "")).strip()
        m   = stn_meta.get(sid, {})
        if not row.get("station_name_k"):
            row["station_name_k"] = m.get("station_name_k", "")
        row["station_type"] = m.get("station_type", "")
        row["area_name"]    = m.get("area_name", "")
        cu, cv = _current_uv(row.get("current_speed", _MISSING), row.get("current_dir", _MISSING))
        row["current_u"] = cu
        row["current_v"] = cv

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"[INFO] Saved: {output_path} (rows={len(rows)})")
    if args.show_sample and rows:
        for r in rows[:5]:
            print(r)


if __name__ == "__main__":
    main()
