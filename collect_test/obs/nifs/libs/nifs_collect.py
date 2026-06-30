import argparse
import csv
import time
import yaml
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


AREA_TO_CODE = {"동해": "E", "남해": "S", "서해": "W"}
SORT_FIELD_TO_CODE = {"station": "1", "datetime": "2"}
SORT_ORDER_TO_CODE = {"asc": "A", "desc": "D"}
_MISSING = "-999"
_STATIONS_YAML = "/data/DATA/OBS/meta/stations/nifs.yaml"


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def parse_args():
    parser = argparse.ArgumentParser(description="NIFS buoy observation collector -> monthly CSV")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "config" / "nifs_config.toml"))
    parser.add_argument("--areas")
    parser.add_argument("--station-codes")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--show-sample", action="store_true")
    return parser.parse_args()


def _load_stn_meta() -> dict:
    with open(_STATIONS_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {
        str(s["id"]): {
            "station_name_k": s.get("name_k", ""),
            "lat":            float(s.get("lat", -999)),
            "lon":            float(s.get("lon", -999)),
            "station_type":   s.get("type", ""),
            "area_name":      s.get("sea", ""),
        }
        for s in data.get("stations", [])
    }


def request_with_retry(session, method, url, timeout, max_retry, sleep_seconds, retry_wait_seconds, **kwargs):
    while True:
        last_error = None
        for attempt in range(1, max_retry + 1):
            try:
                r = session.request(method=method, url=url, timeout=timeout, **kwargs)
                if r.status_code == 200:
                    return r
                last_error = RuntimeError(f"HTTP {r.status_code}")
                print(f"[WARN] HTTP {r.status_code} ({attempt}/{max_retry})")
            except requests.RequestException as exc:
                last_error = exc
                print(f"[WARN] {exc} ({attempt}/{max_retry})")
            if attempt < max_retry:
                time.sleep(sleep_seconds)
        print(f"[ERROR] {last_error}. Retrying in {retry_wait_seconds/60:g}m...")
        time.sleep(retry_wait_seconds)


def build_session(api_cfg: dict) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": api_cfg.get("user_agent", "Mozilla/5.0"),
        "Accept": "application/json, text/plain, */*",
        "Referer": api_cfg["base_page"],
    })
    return session


def initialize_session(session, api_cfg):
    request_with_retry(session=session, method="GET", url=api_cfg["base_page"],
                       timeout=int(api_cfg.get("request_timeout", 30)),
                       max_retry=int(api_cfg.get("max_retry", 5)),
                       sleep_seconds=float(api_cfg.get("sleep_seconds", 0.3)),
                       retry_wait_seconds=float(api_cfg.get("retry_wait_seconds", 1800)))


def fetch_station_options(session, api_cfg, area_code):
    url = api_cfg["base_api"].rstrip("/") + "/getRisaStationCode.do"
    r = request_with_retry(session=session, method="POST", url=url,
                           timeout=int(api_cfg.get("request_timeout", 30)),
                           max_retry=int(api_cfg.get("max_retry", 5)),
                           sleep_seconds=float(api_cfg.get("sleep_seconds", 0.3)),
                           retry_wait_seconds=float(api_cfg.get("retry_wait_seconds", 1800)),
                           data={"obsrvnGroupNm": area_code, "useY": "T"},
                           headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    try:
        data = r.json()
    except ValueError:
        return []
    ret_list = data.get("retList", [])
    return ret_list if isinstance(ret_list, list) else []


def to_float_or_missing(value):
    if value in (None, "", "-", " "):
        return _MISSING
    try:
        return str(float(value))
    except (TypeError, ValueError):
        return _MISSING


def is_missing(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    if isinstance(value, str) and value.strip() in ("", "-", _MISSING, "nan", "NaN"):
        return True
    return False


def normalize_rows(station_code: str, rows: list[dict]) -> list[dict]:
    """API 응답 → 표준 컬럼 dict (station_meta는 main에서 보강)"""
    out = []
    for row in rows:
        obs = row.get("obsrvnDt", "")
        try:
            time_val = datetime.strptime(obs, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            time_val = obs
        out.append({
            "time":         time_val,
            "station_id":   station_code,
            "station_name_k": "",   # main에서 YAML로 채움
            "lat":          _MISSING,
            "lon":          _MISSING,
            "sur_temp":     to_float_or_missing(row.get("wtrTempS")),
            "sur_depth_m":  to_float_or_missing(row.get("sfclyrDpwt")),
            "mid_temp":     to_float_or_missing(row.get("wtrTempM")),
            "mid_depth_m":  to_float_or_missing(row.get("mlyrDpwt")),
            "bot_temp":     to_float_or_missing(row.get("wtrTempB")),
            "bot_depth_m":  to_float_or_missing(row.get("btmlyrDpwt")),
            "station_type": "",
            "area_name":    "",
        })
    return out


def fetch_station_day_rows(session, api_cfg, req_cfg, station_code, target_date, area_code=None):
    url = api_cfg["base_api"].rstrip("/") + "/searchRisaInfoList.do"
    payload_base = {
        "obsvtrCd": station_code,
        "ord": SORT_FIELD_TO_CODE[req_cfg.get("sort_field", "station")],
        "ordType": SORT_ORDER_TO_CODE[req_cfg.get("sort_order", "asc")],
        "obsFrom": target_date, "obsTo": target_date,
        "obsTimeFrom": req_cfg.get("start_time", "00:00").replace(":", ""),
        "obsTimeTo": req_cfg.get("end_time", "23:30").replace(":", ""),
    }
    if area_code:
        payload_base["obsrvnGroupNm"] = area_code
    timeout = int(api_cfg.get("request_timeout", 30))
    max_retry = int(api_cfg.get("max_retry", 5))
    sleep_sec = float(api_cfg.get("sleep_seconds", 0.3))
    retry_wait = float(api_cfg.get("retry_wait_seconds", 1800))
    page_size = int(req_cfg.get("page_size", 200))

    rows = []
    page = 1
    total = None
    while True:
        payload = dict(payload_base)
        payload["selectPage"] = page
        payload["rowCountPage"] = page_size
        r = request_with_retry(session=session, method="POST", url=url,
                               timeout=timeout, max_retry=max_retry,
                               sleep_seconds=sleep_sec, retry_wait_seconds=retry_wait,
                               data=payload,
                               headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        try:
            data = r.json()
        except ValueError:
            print(f"[WARN] parse fail station={station_code}")
            break
        ret_list = data.get("retList", [])
        if not isinstance(ret_list, list) or not ret_list:
            break
        if total is None:
            try:
                total = int(ret_list[0].get("allCnt", 0))
            except (ValueError, TypeError):
                total = None
        rows.extend(normalize_rows(station_code, ret_list))
        if total is not None and len(rows) >= total:
            break
        if len(ret_list) < page_size:
            break
        page += 1
    return rows


def build_output_path(storage_cfg, month):
    tokens = {"yyyy": month[:4], "yyyymm": month}
    return Path(storage_cfg["output_root"]) / storage_cfg["dir_layout"].format_map(tokens) / storage_cfg["file_pattern"].format_map(tokens)


def get_target_areas(args, req_cfg) -> list[str]:
    if args.areas:
        areas = [a.strip() for a in args.areas.split(",") if a.strip()]
    else:
        areas = list(req_cfg.get("areas", ["동해", "남해", "서해"]))
    invalid = [a for a in areas if a not in AREA_TO_CODE]
    if invalid:
        raise ValueError(f"지원하지 않는 해역: {invalid}")
    return areas


def load_existing_rows(path: Path, fields: list[str]) -> dict[tuple, dict]:
    rows: dict[tuple, dict] = {}
    if not path.exists() or path.stat().st_size == 0:
        return rows
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row.get("station_id", ""), row.get("time", ""))
            rows[key] = row
    return rows


def main():
    args    = parse_args()
    cfg     = load_config(Path(args.config))
    api_cfg = cfg["api"]
    req_cfg = cfg["request"]
    storage_cfg = cfg["storage"]["monthly"]
    fields  = list(cfg["output"]["fields"])

    req_date_fmt = req_cfg.get("req_date_format", "%Y%m%d")
    api_date_fmt = req_cfg.get("api_date_format", "%Y-%m-%d")
    target_date  = datetime.strptime(args.date, req_date_fmt)
    target_date_api = target_date.strftime(api_date_fmt)
    month   = target_date.strftime("%Y%m")
    areas   = get_target_areas(args, req_cfg)

    station_code_filter = (
        {c.strip() for c in args.station_codes.split(",") if c.strip()}
        if args.station_codes else None
    )

    output_path = build_output_path(storage_cfg, month)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows_by_key = load_existing_rows(output_path, fields)

    stn_meta = _load_stn_meta()
    session  = build_session(api_cfg)
    initialize_session(session, api_cfg)

    interval_seconds = float(req_cfg.get("interval_seconds", 0.3))
    total_added = 0

    for area_name in areas:
        area_code = AREA_TO_CODE[area_name]
        stations  = fetch_station_options(session, api_cfg, area_code)
        stations  = [s for s in stations if str(s.get("obsvtrCd", "")).strip() in stn_meta]
        if args.limit is not None:
            stations = stations[:args.limit]
        print(f"[INFO] area={area_name}, stations={len(stations)}")

        for station in stations:
            station_code = str(station.get("obsvtrCd", "")).strip()
            if not station_code:
                continue
            if station_code_filter and station_code not in station_code_filter:
                continue
            print(f"[INFO] collecting station={station_code}")
            fetched = fetch_station_day_rows(session, api_cfg, req_cfg, station_code, target_date_api, area_code=area_code)

            # YAML 메타 보강
            meta = stn_meta.get(station_code, {})
            for row in fetched:
                row["station_name_k"] = meta.get("station_name_k", "")
                row["lat"]            = str(meta.get("lat", _MISSING))
                row["lon"]            = str(meta.get("lon", _MISSING))
                row["station_type"]   = meta.get("station_type", "")
                row["area_name"]      = meta.get("area_name", "")
                key = (row["station_id"], row["time"])
                rows_by_key[key] = row

            total_added += len(fetched)
            if interval_seconds > 0:
                time.sleep(interval_seconds)

    def _normalize(row):
        out = {}
        for f in fields:
            v = row.get(f, "")
            if f in ("station_id", "time", "station_name_k", "station_type", "area_name"):
                out[f] = "" if is_missing(v) else str(v).strip()
            else:
                out[f] = _MISSING if is_missing(v) else str(v).strip()
        return out

    rows = [_normalize(row) for row in rows_by_key.values()]
    rows.sort(key=lambda r: (r.get("station_id", ""), r.get("time", "")))

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"[INFO] Saved: {output_path} (rows={len(rows)}, newly_fetched={total_added})")
    if args.show_sample and rows:
        for r in rows[:5]:
            print(r)


if __name__ == "__main__":
    main()
