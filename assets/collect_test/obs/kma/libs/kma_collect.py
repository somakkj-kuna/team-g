import argparse
import csv
import io
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

# API 응답 컬럼 순서 (고정)
_API_COL_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 0, 15]
_MISSING = "-999"
_STATIONS_YAML = "/data/DATA/OBS/meta/stations/kma.yaml"

_OBS_TYPE_FALLBACK = {
    "B": "기상청_해양기상부이", "C": "기상청_파고부이",
    "D": "표류부이", "L": "등표", "N": "조위관측소",
    "F": "연안방재", "G": "파랑계", "J": "기상1호",
}


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def parse_args():
    parser = argparse.ArgumentParser(description="KMA sea observation collector -> monthly CSV")
    parser.add_argument("--date", required=True)
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "config" / "kma_config.toml"))
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
        return None if f <= -99 else f
    except (ValueError, TypeError):
        return None


def _wind_uv(spd, drct):
    s, d = _fval(spd), _fval(drct)
    if s is None or d is None:
        return _MISSING, _MISSING
    r = math.radians(d)
    return str(round(-s * math.sin(r), 4)), str(round(-s * math.cos(r), 4))


def is_missing(value) -> bool:
    return value in ("", None, _MISSING) or (hasattr(pd, "isna") and pd.isna(value))


def normalize_value(value) -> str:
    if value is None or (hasattr(pd, "isna") and pd.isna(value)):
        return ""
    return str(value).strip()


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


def fetch_frame(api_cfg: dict, tm: str) -> pd.DataFrame | None:
    base_url = api_cfg["base_url"].rstrip("/")
    keys = get_service_keys(api_cfg)
    timeout     = int(api_cfg.get("request_timeout", 120))
    max_retry   = int(api_cfg.get("max_retry", 5))
    sleep_sec   = float(api_cfg.get("sleep_seconds", 0.2))
    retry_wait  = float(api_cfg.get("retry_wait_seconds", 1800))

    while True:
        response = None
        for key in keys:
            url = f"{base_url}/sea_obs.php?tm={tm}&stn=0&help=0&authKey={key}"
            for attempt in range(1, max_retry + 1):
                try:
                    r = requests.get(url, timeout=timeout)
                    if r.status_code == 200:
                        response = r
                        break
                    if r.status_code == 403:
                        print(f"[WARN] HTTP 403 (key ...{key[-4:]}) — trying next key")
                        break
                    print(f"[WARN] HTTP {r.status_code} ({attempt}/{max_retry})")
                except requests.RequestException as exc:
                    print(f"[WARN] {exc} ({attempt}/{max_retry})")
                if attempt < max_retry:
                    time.sleep(sleep_sec)
            if response is not None:
                break
        if response is not None:
            break
        print(f"[ERROR] All keys failed for {tm}. Retrying in {retry_wait/60:g}m...")
        time.sleep(retry_wait)

    text = response.content.decode("euc-kr", errors="replace")
    try:
        df = pd.read_csv(io.StringIO(text), header=None, engine="python",
                         skiprows=3, skipfooter=1, na_values=[-99, -99.0, "-99"])
    except Exception as exc:
        print(f"[WARN] Parse failed for {tm}: {exc}")
        return None
    if df.empty:
        return None
    df = df[_API_COL_ORDER]
    df.columns = [str(c) for c in df.columns]
    return df


def get_obs_codes(args, cfg: dict) -> list[str]:
    if args.obs_codes:
        return [c.strip() for c in args.obs_codes.split(",") if c.strip()]
    obs_codes = list(cfg.get("stations", {}).get("obs_codes", []))
    if obs_codes:
        return obs_codes
    stn_csv = cfg["stations"]["station_info_csv"]
    try:
        df = pd.read_csv(stn_csv, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(stn_csv, encoding="cp949")
    return [str(c) for c in df["obs_post_id"].tolist()]


def build_output_path(storage_cfg: dict, month: str) -> Path:
    tokens = {"yyyy": month[:4], "yyyymm": month}
    return (Path(storage_cfg["output_root"])
            / storage_cfg["dir_layout"].format_map(tokens)
            / storage_cfg["file_pattern"].format_map(tokens))


def _has_standard_header(path: Path, output_fields: list[str]) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        header = next(csv.reader(f), [])
    return header == output_fields


def read_existing_rows(path: Path, output_fields: list[str]) -> dict[tuple, dict]:
    rows: dict[tuple, dict] = {}
    if not _has_standard_header(path, output_fields):
        return rows
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row.get("station_id", ""), row.get("time", ""))
            if key != ("", ""):
                rows[key] = row
    return rows


def build_standard_row(df_row: pd.Series, mapping: dict, output_fields: list[str]) -> dict:
    row = {f: _MISSING for f in output_fields}
    for std_name, col_idx in mapping.items():
        if std_name.startswith("_"):
            continue
        value = normalize_value(df_row.get(col_idx, ""))
        if std_name == "time" and value:
            try:
                value = datetime.strptime(value, "%Y%m%d%H%M").strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        row[std_name] = _MISSING if is_missing(value) else value
    return row


def main():
    args = parse_args()
    cfg  = load_config(Path(args.config))

    api_cfg     = cfg["api"]
    req_cfg     = cfg["request"]
    storage_cfg = cfg["storage"]["monthly"]
    mapping     = {k: str(v) for k, v in cfg["mapping"].items()}
    output_fields = list(cfg["output"]["fields"])

    date_fmt    = req_cfg.get("req_date_format", "%Y%m%d")
    target_date = datetime.strptime(args.date, date_fmt)
    month       = target_date.strftime("%Y%m")

    obs_codes   = get_obs_codes(args, cfg)

    output_path = build_output_path(storage_cfg, month)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows_by_key = read_existing_rows(output_path, output_fields)

    interval_minutes = int(req_cfg.get("interval_minutes", 30))
    cur = target_date.replace(hour=0, minute=0, second=0)
    end = target_date.replace(hour=23, minute=30, second=0)

    while cur <= end:
        tm = cur.strftime("%Y%m%d%H%M")
        print(f"[INFO] {tm}...")
        df = fetch_frame(api_cfg, tm)
        if df is not None:
            if obs_codes:
                df = df[df[mapping["station_id"]].astype(str).isin(obs_codes)]
            if args.limit is not None:
                order = df[mapping["station_id"]].astype(str).drop_duplicates().tolist()
                df = df[df[mapping["station_id"]].astype(str).isin(order[:args.limit])]
            if not df.empty:
                for _, df_row in df.iterrows():
                    std_row = build_standard_row(df_row, mapping, output_fields)
                    if not std_row.get("time") or std_row["time"] == _MISSING:
                        continue
                    key = (std_row.get("station_id", ""), std_row.get("time", ""))
                    rows_by_key[key] = std_row
        cur += timedelta(minutes=interval_minutes)

    rows = list(rows_by_key.values())
    def _sid_int(r):
        try:
            return int(r.get("station_id", "0") or "0")
        except (ValueError, TypeError):
            return 999999999
    rows.sort(key=lambda r: (_sid_int(r), r.get("time", "")))

    # 메타 보강
    stn_meta = _load_stn_meta()
    raw_type_col = mapping.get("_raw_type", "0")
    for row in rows:
        sid = str(row.get("station_id", "")).strip()
        m   = stn_meta.get(sid, {})
        row["station_name_k"] = row.get("station_name_k") or m.get("station_name_k", "")
        # station_type는 이미 build_standard_row에서 _raw_type으로 채워져 있음
        # YAML에 있으면 덮어쓰기
        if m.get("station_type"):
            row["station_type"] = m["station_type"]
        elif row.get("station_type") in (None, "", _MISSING):
            raw_t = row.get("_raw_type", "")
            row["station_type"] = _OBS_TYPE_FALLBACK.get(raw_t, raw_t)
        row["area_name"] = m.get("area_name", "")
        wu, wv = _wind_uv(row.get("wind_speed", _MISSING), row.get("wind_dir", _MISSING))
        row["wind_u"] = wu
        row["wind_v"] = wv

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
