# -*- coding: utf-8-sig -*-
"""KMA AWS 시간별 지상관측 수집기 — 표준 컬럼 출력"""
from __future__ import annotations

import argparse
import csv
import math
import time
import yaml
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

_MISSING = "-999"
_AWS_META_CSV = "/home/collect/collector/collect/obs/kma/config/aws_station_info_KMA.csv"
_MISSING_VALUES = {"-99", "-99.0", "-9.0", ""}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="KMA AWS hourly collector -> monthly CSV (표준 컬럼)")
    p.add_argument("--date",    required=True, help="YYYYMMDD")
    p.add_argument("--config",  default=str(Path(__file__).resolve().parents[1] / "config" / "aws_config.toml"))
    p.add_argument("--stn-ids", help="쉼표 구분 지점번호 (기본: 전체)")
    p.add_argument("--limit",   type=int, default=None)
    p.add_argument("--show-sample", action="store_true")
    return p.parse_args()


def load_config(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _load_aws_meta() -> dict:
    df = pd.read_csv(_AWS_META_CSV, encoding="utf-8-sig", dtype=str)
    out = {}
    for _, row in df.iterrows():
        sid = str(row.get("station_id", "")).strip()
        try:
            out[sid] = {
                "station_name_k": str(row.get("station_name_k", "")).strip(),
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
            }
        except (ValueError, KeyError):
            pass
    return out


def _fval(v):
    try:
        f = float(v)
        return None if f <= -99 else f
    except (ValueError, TypeError):
        return None


def _wind_uv(spd, drct):
    s, d = _fval(spd), _fval(drct)
    if s is None or d is None:
        return _MISSING, _MISSING
    r = math.radians(d)
    return str(round(-s * math.sin(r), 4)), str(round(-s * math.cos(r), 4))


def get_service_keys(api_cfg: dict) -> list[str]:
    keys = [str(k).strip() for k in api_cfg.get("service_keys", []) if str(k).strip()]
    if not keys:
        for name in ("service_key", "service_key_fallback"):
            key = str(api_cfg.get(name, "")).strip()
            if key:
                keys.append(key)
    if not keys:
        raise ValueError("No KMA API service keys configured")
    return keys


def request_with_retry(url_for_key, api_cfg: dict) -> requests.Response | None:
    keys       = get_service_keys(api_cfg)
    timeout    = int(api_cfg.get("request_timeout", 120))
    max_retry  = int(api_cfg.get("max_retry", 5))
    sleep_sec  = float(api_cfg.get("sleep_seconds", 0.2))
    retry_wait = float(api_cfg.get("retry_wait_seconds", 1800))
    while True:
        last_err = None
        for key in keys:
            url = url_for_key(key)
            for attempt in range(1, max_retry + 1):
                try:
                    resp = requests.get(url, timeout=timeout)
                    if resp.status_code == 200:
                        return resp
                    last_err = RuntimeError(f"HTTP {resp.status_code}")
                    if resp.status_code == 403:
                        print(f"[WARN] HTTP 403 (key ...{key[-4:]}) - trying next key")
                        break
                    print(f"[WARN] HTTP {resp.status_code} (key ...{key[-4:]}, {attempt}/{max_retry})")
                except requests.RequestException as e:
                    last_err = e
                    print(f"[WARN] {e} (key ...{key[-4:]}, {attempt}/{max_retry})")
                if attempt < max_retry:
                    time.sleep(sleep_sec)
        print(f"[ERROR] All keys failed: {last_err}. Retrying in {retry_wait/60:g}m...")
        time.sleep(retry_wait)


def fetch_aws(api_cfg: dict, tm: str, aws_meta: dict) -> list[dict] | None:
    base_url = api_cfg['base_url'].rstrip('/')
    resp = request_with_retry(
        lambda key: f"{base_url}/awsh.php?tm={tm}&stn=0&help=0&authKey={key}",
        api_cfg,
    )
    if resp is None:
        return None

    text = resp.content.decode("euc-kr", errors="replace")
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 10:
            continue
        try:
            raw_tm  = parts[0]
            raw_stn = parts[1]
            # 시간 변환: YYYYMMDDHHMM → 표준
            try:
                std_time = datetime.strptime(raw_tm, "%Y%m%d%H%M").strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                std_time = raw_tm

            def v(s):
                return _MISSING if s in _MISSING_VALUES else s

            meta = aws_meta.get(raw_stn, {})
            wu, wv = _wind_uv(v(parts[4]), v(parts[3]))  # ws, wd
            rows.append({
                "time":          std_time,
                "station_id":    raw_stn,
                "station_name_k": meta.get("station_name_k", ""),
                "lat":           str(meta.get("lat", _MISSING)),
                "lon":           str(meta.get("lon", _MISSING)),
                "air_temp":      v(parts[2]),
                "wind_dir":      v(parts[3]),
                "wind_speed":    v(parts[4]),
                "wind_u":        wu,
                "wind_v":        wv,
                "rn_day":        v(parts[5]),
                "rn_hr1":        v(parts[6]),
                "air_humi":      v(parts[7]),
                "station_pres":  v(parts[8]),
                "air_pres":      v(parts[9]),
            })
        except (ValueError, IndexError):
            continue
    return rows if rows else None


def load_station_ids(cfg: dict, args: argparse.Namespace) -> list[str] | None:
    if args.stn_ids:
        return [s.strip() for s in args.stn_ids.split(",") if s.strip()]
    ids = list(cfg.get("stations", {}).get("stn_ids", []))
    if ids:
        return ids
    csv_path = Path(cfg["stations"]["station_info_csv"])
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding="cp949")
    col = "station_id" if "station_id" in df.columns else df.columns[0]
    return [str(v) for v in df[col].tolist()]


def output_path(cfg: dict, yyyymm: str) -> Path:
    st = cfg["storage"]["monthly"]
    tokens = {"yyyy": yyyymm[:4], "yyyymm": yyyymm}
    return (Path(st["output_root"])
            / st["dir_layout"].format_map(tokens)
            / st["file_pattern"].format_map(tokens))


def read_existing(path: Path, fields: list[str]) -> dict[tuple, dict]:
    rows: dict[tuple, dict] = {}
    if not path.exists() or path.stat().st_size == 0:
        return rows
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row.get("station_id", ""), row.get("time", ""))
            rows[key] = row
    return rows


def main() -> None:
    args = parse_args()
    cfg  = load_config(args.config)
    api  = cfg["api"]
    req  = cfg["request"]
    fields = list(cfg["output"]["fields"])

    target   = datetime.strptime(args.date, req.get("req_date_format", "%Y%m%d"))
    yyyymm   = target.strftime("%Y%m")
    interval = int(req.get("interval_minutes", 60))

    stn_ids = load_station_ids(cfg, args)
    aws_meta = _load_aws_meta()

    out_path = output_path(cfg, yyyymm)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows_by_key = read_existing(out_path, fields)

    cur = target.replace(hour=0, minute=0)
    end = target.replace(hour=23, minute=0)
    while cur <= end:
        tm = cur.strftime("%Y%m%d%H%M")
        print(f"[INFO] {tm} 수집 중...")
        fetched = fetch_aws(api, tm, aws_meta)
        if fetched:
            for row in fetched:
                sid = row["station_id"]
                if stn_ids and sid not in stn_ids:
                    continue
                if args.limit:
                    existing_stns = {k[0] for k in rows_by_key}
                    if sid not in existing_stns and len(existing_stns) >= args.limit:
                        continue
                key = (sid, row["time"])
                # 메타 누락분 채우기
                if not row.get("station_name_k"):
                    row["station_name_k"] = aws_meta.get(sid, {}).get("station_name_k", "")
                rows_by_key[key] = {f: row.get(f, _MISSING) for f in fields}
        else:
            print(f"[INFO] {tm} 데이터 없음")
        cur += timedelta(minutes=interval)

    def _sid_int(r):
        try:
            return int(r.get("station_id", "0") or "0")
        except (ValueError, TypeError):
            return 999999999
    rows = sorted(rows_by_key.values(), key=lambda r: (_sid_int(r), r.get("time", "")))

    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"[INFO] 저장: {out_path}  ({len(rows)}행)")
    if args.show_sample:
        for r in rows[:3]:
            print(r)


if __name__ == "__main__":
    main()
