#!/usr/bin/env python
# -*- coding: utf-8-sig -*-
"""
03_mqc.py — 수동 품질 검사 (MQC)
이벤트(태풍, 센서 교체 등) 기간에 대해 수동으로 flag를 부여.
이벤트 목록: meta/mqc_events.toml (없으면 실행하지 않음)
sorted 산출물은 월별 CSV(tmp/sorted/{dataset}/{agency}_{yyyymm}.csv)를 읽는다.

mqc_events.toml 예시:
  [[events]]
  label       = "태풍 KHANUN"
  start       = "2023-08-10T00:00:00"
  end         = "2023-08-12T23:59:59"
  agency      = "khoa"
  station_ids = ["DT_0001", "DT_0008"]
  var_ids     = []          # 빈 리스트면 전체 변수
  flag        = 2           # suspect
  reason      = "typhoon_KHANUN"

사용법:
  python src/pipeline/03_mqc.py --agency khoa --dataset tidal --yyyymm 202501
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

QC_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(QC_ROOT))

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from src.libs.utils.flag_io import FLAG_GOOD, load_flags, save_flags
from src.libs.utils.config_loader import sorted_dir

EVENTS_PATH = QC_ROOT / "meta" / "mqc_events.toml"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agency",  required=True)
    p.add_argument("--dataset", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--yyyymm",   help="월별 처리 (YYYYMM)")
    g.add_argument("--yyyymmdd", help="일별 처리 (YYYYMMDD)")
    p.add_argument("--station", default=None)
    return p.parse_args()


def load_events() -> list[dict]:
    if not EVENTS_PATH.exists():
        return []
    with open(EVENTS_PATH, "rb") as f:
        content = f.read()
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
    data = tomllib.loads(content.decode("utf-8"))
    return data.get("events", [])


def run_station(station_id: str, agency: str, key: str,
                events: list[dict]) -> None:
    relevant = [
        e for e in events
        if e.get("agency", agency) == agency
        and (not e.get("station_ids") or station_id in e["station_ids"])
    ]
    if not relevant:
        return

    flag_df = load_flags(agency, station_id, key)
    if flag_df.empty:
        return

    flag_df = flag_df.copy()
    flag_df["time"] = pd.to_datetime(flag_df["time"], utc=True)
    changed = 0

    for ev in relevant:
        start  = pd.Timestamp(ev["start"], tz="UTC")
        end    = pd.Timestamp(ev["end"],   tz="UTC")
        f_val  = int(ev.get("flag",   2))
        reason = str(ev.get("reason", ev.get("label", "mqc")))
        var_ids = ev.get("var_ids", [])

        time_mask = (flag_df["time"] >= start) & (flag_df["time"] <= end)
        var_mask  = (flag_df["var_id"].isin(var_ids) if var_ids
                     else pd.Series([True] * len(flag_df), index=flag_df.index))

        target = time_mask & var_mask
        flag_df.loc[target, "flag_mqc"]   = f_val
        flag_df.loc[target, "reason_mqc"] = reason
        changed += target.sum()

    if changed:
        # unset → good
        unset = flag_df["flag_mqc"] == 0
        flag_df.loc[unset, "flag_mqc"] = FLAG_GOOD
        save_flags(flag_df, agency, station_id, key)
        print(f"  [mqc] {station_id}: {changed}행 flag 부여")


def run(agency: str, dataset: str, yyyymm: str,
        station_filter: str | None = None,
        yyyymmdd: str | None = None) -> None:
    key         = yyyymmdd if yyyymmdd else yyyymm
    events = load_events()
    if not events:
        print("[mqc] mqc_events.toml 없음 또는 이벤트 없음 — 건너뜀")
        return

    # sorted 산출물은 월별 CSV (key가 8자리 일별이어도 yyyymm 파일을 읽음)
    yyyymm_key  = key[:6]
    sorted_path = (sorted_dir() / dataset
                   / f"{agency}_{yyyymm_key}.csv")
    if not sorted_path.exists():
        print(f"[skip] sorted 파일 없음: {sorted_path} — 유효 데이터 없음")
        return

    df       = pd.read_csv(sorted_path, dtype={"station_id": str})
    stations = df["station_id"].unique().tolist()
    if station_filter:
        stations = [s for s in stations if s == station_filter]

    print(f"[mqc] {agency}/{dataset}/{key}  이벤트 {len(events)}건")
    for stn in stations:
        run_station(stn, agency, key, events)


if __name__ == "__main__":
    args = parse_args()
    run(args.agency, args.dataset, args.yyyymm, args.station, getattr(args, "yyyymmdd", None))
