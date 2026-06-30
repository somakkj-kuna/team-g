#!/usr/bin/env python
# -*- coding: utf-8-sig -*-
"""
07_plot_multiyr.py — 다년도 QC 결과 병합 시계열 플롯
result/flag/{agency}/{station_id}/{yyyy}/*_qc_flag.csv 를 여러 연도에 걸쳐 합산하여
result/plots/all_year/{agency}_{station_id}_{start_year}_{end_year}.png 로 저장.

사용법:
  python src/libs/pipeline/07_plot_multiyr.py \\
      --agency khoa --start_year 2023 --end_year 2026
  python src/libs/pipeline/07_plot_multiyr.py \\
      --agency khoa --start_year 2023 --end_year 2026 --station DT_0008
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["axes.unicode_minus"] = False

from pathlib import Path as _Path
import matplotlib.font_manager as _fm
_KOREAN_FONTS = [
    "/mnt/c/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
]
for _fp in _KOREAN_FONTS:
    if _Path(_fp).exists():
        _fm.fontManager.addfont(_fp)
        _prop = _fm.FontProperties(fname=_fp)
        matplotlib.rcParams["font.family"] = _prop.get_name()
        break

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

QC_ROOT    = Path(__file__).resolve().parents[3]
STATION_DIR = QC_ROOT / "meta" / "stations"

sys.path.insert(0, str(QC_ROOT))

from src.libs.utils.config_loader import result_dir
# 실행 프로파일(QC_PROFILE)에 따라 result/ 또는 err_result/ 로 분기.
RESULT_DIR = result_dir()

FLAG_COLOR = {
    1: "#2ca02c",
    2: "#f1c40f",
    3: "#d62728",
    4: "#8e44ad",
    9: "#aaaaaa",
    0: "#cccccc",
}
FLAG_LABEL = {1: "good", 2: "suspect", 3: "bad", 4: "interpolated", 9: "missing"}

VAR_UNIT = {
    "temp":          "수온 (°C)",
    "sur_temp":      "수온-표층 (°C)",
    "mid_temp":      "수온-중층 (°C)",
    "bot_temp":      "수온-저층 (°C)",
    "sal":           "염분 (psu)",
    "tide_real":     "조위-실측 (cm)",
    "tide_pre":      "조위-예측 (cm)",
    "air_temp":      "기온 (°C)",
    "air_pres":      "기압 (hPa)",
    "wind_speed":    "풍속 (m/s)",
    "wind_gust":     "순간최대풍속 (m/s)",
    "wind_dir":      "풍향 (°)",
    "wave_h":        "파고 (m)",
    "current_speed": "유속 (cm/s)",
    "current_dir":   "유향 (°)",
}

VAR_YLIM: dict[str, tuple[float, float] | None] = {
    "temp":          (-2,  40),
    "sur_temp":      (-2,  40),
    "mid_temp":      (-2,  40),
    "bot_temp":      (-2,  40),
    "sal":           (0,   40),
    "tide_real":     None,
    "tide_pre":      None,
    "air_temp":      (-20, 40),
    "air_pres":      (960, 1040),
    "wind_speed":    (0,   25),
    "wind_gust":     (0,   35),
    "wind_dir":      (0,   360),
    "wave_h":        (0,   10),
    "current_speed": (0,   200),
    "current_dir":   (0,   360),
}

DEFAULT_VARS = ["temp", "sur_temp", "sal", "tide_real",
                "wave_h", "air_temp", "air_pres", "wind_speed"]

_EXCLUDE = {"wind_u", "wind_v", "current_u", "current_v", "tide_pre"}


def _load_station_ylim(station_id: str, agency: str) -> dict[str, tuple[float, float]]:
    path = STATION_DIR / agency.upper() / f"{station_id}.toml"
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        content = f.read()
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
    cfg = tomllib.loads(content.decode("utf-8"))
    raw = cfg.get("plot", {}).get("ylim", {})
    return {k: tuple(v) for k, v in raw.items() if isinstance(v, list) and len(v) == 2}


def _scatter_flags(ax: plt.Axes, times: pd.Series, values: pd.Series,
                   flags: pd.Series, label_done: set, s: float = 5) -> None:
    # zorder: bad(3) > suspect(2) > 나머지(1) — 빨간점이 항상 위에 오도록
    _FLAG_ZORDER = {3: 5, 2: 4, 1: 3, 9: 2, 4: 3, 0: 2}
    for flag_val, color in FLAG_COLOR.items():
        mask = flags == flag_val
        if not mask.any():
            continue
        lbl = FLAG_LABEL.get(flag_val, str(flag_val))
        ax.scatter(
            times[mask], values[mask],
            color=color, s=s, linewidths=0,
            label=lbl if lbl not in label_done else "_nolegend_",
            zorder=_FLAG_ZORDER.get(flag_val, 3),
        )
        label_done.add(lbl)


def _load_station_years(agency: str, station_id: str,
                        start_year: int, end_year: int) -> pd.DataFrame:
    years = range(start_year, end_year + 1)
    dfs = []
    for yr in years:
        flag_dir = RESULT_DIR / "flag" / agency / station_id / str(yr)
        if not flag_dir.exists():
            continue
        # 연간 파일: {agency}_{station_id}_{yyyy}_qc_flag.csv
        for csv in sorted(flag_dir.glob(f"*_{yr}_qc_flag.csv")):
            try:
                dfs.append(pd.read_csv(csv, dtype={"flag_final": int, "reason_aqc2": str}, low_memory=False))
            except Exception as e:
                print(f"  [multiyr] 읽기 오류 {csv.name}: {e}")
    if not dfs:
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    df["time"]  = pd.to_datetime(df["time"], utc=True)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.sort_values("time").reset_index(drop=True)


def plot_station_multiyr(agency: str, station_id: str,
                         start_year: int, end_year: int) -> None:
    df = _load_station_years(agency, station_id, start_year, end_year)
    if df.empty:
        print(f"  [multiyr] {station_id}: 데이터 없음 ({start_year}~{end_year})")
        return

    lat = float(df["lat"].iloc[0])
    lon = float(df["lon"].iloc[0])

    available = [v for v in df["var_id"].unique() if v not in _EXCLUDE]
    plot_vars = [v for v in DEFAULT_VARS if v in available]
    plot_vars += [v for v in available if v not in plot_vars]
    if not plot_vars:
        return

    station_ylim  = _load_station_ylim(station_id, agency)
    effective_ylim = {**VAR_YLIM, **station_ylim}

    n_years = end_year - start_year + 1
    fig_w = max(26, 10 * n_years)
    n_rows = len(plot_vars)
    fig, axes = plt.subplots(n_rows, 1, figsize=(fig_w, 3.8 * n_rows), sharex=True)
    if n_rows == 1:
        axes = [axes]

    label_done: set = set()
    for ax, var in zip(axes, plot_vars):
        sub    = df[df["var_id"] == var].sort_values("time")
        times  = sub["time"]
        values = sub["value"]
        flags  = sub["flag_final"]

        good_mask = flags == 1
        ax.plot(times[good_mask], values[good_mask],
                color="#cccccc", linewidth=0.4, zorder=1, alpha=0.6)
        _scatter_flags(ax, times, values, flags, label_done, s=4)

        ylim = effective_ylim.get(var)
        if ylim is not None:
            ax.set_ylim(*ylim)

        ax.set_ylabel(VAR_UNIT.get(var, var), fontsize=9)
        ax.yaxis.set_label_coords(-0.04, 0.5)
        ax.set_title(var, fontsize=9, loc="left", pad=3)
        ax.tick_params(labelsize=8)
        ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.5)

        # 연도 경계선
        for yr in range(start_year, end_year + 1):
            ax.axvline(pd.Timestamp(f"{yr}-01-01", tz="UTC"),
                       color="#888888", linewidth=0.8, linestyle="--", alpha=0.5, zorder=2)

        n_good    = (flags == 1).sum()
        n_suspect = (flags == 2).sum()
        n_bad     = (flags == 3).sum()
        ax.text(0.99, 0.97,
                f"good {n_good}  suspect {n_suspect}  bad {n_bad}  / {len(flags)}",
                transform=ax.transAxes, fontsize=7, ha="right", va="top", color="#555555")

    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    axes[-1].xaxis.set_minor_locator(mdates.MonthLocator())
    axes[-1].tick_params(axis="x", labelsize=8)
    fig.autofmt_xdate(rotation=30, ha="right")

    handles, labels = [], []
    for fv, color in FLAG_COLOR.items():
        lbl = FLAG_LABEL.get(fv)
        if lbl and lbl in label_done:
            from matplotlib.lines import Line2D
            handles.append(Line2D([0], [0], marker="o", color="w",
                                  markerfacecolor=color, markersize=5))
            labels.append(lbl)
    axes[-1].legend(handles, labels, loc="lower right",
                    fontsize=7, framealpha=0.8, ncol=len(labels),
                    markerscale=0.7, handletextpad=0.4, columnspacing=0.8)

    fig.suptitle(
        f"{agency.upper()}  {station_id}  ({lat:.3f}°N, {lon:.3f}°E)  "
        f"{start_year}–{end_year}  QC 다년도 시계열",
        fontsize=11, y=1.002,
    )
    fig.tight_layout()

    out_dir = RESULT_DIR / "plots" / "all_year" / agency
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{station_id}_all_year.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [multiyr] 저장: {out_path}")


def run(agency: str, start_year: int, end_year: int,
        station: str | None = None) -> None:
    if station:
        stations = [station]
    else:
        flag_dir = RESULT_DIR / "flag" / agency
        if not flag_dir.exists():
            print(f"[multiyr] 결과 없음: {flag_dir}")
            return
        import re as _re
        _SID_PATTERNS = {
            "khoa": r"^[A-Za-z]{2,3}_[0-9]{4,}$",
            "kma":  r"^[0-9]+$",
            "nifs": r"^[a-z0-9]{4,}$",
        }
        _VALID_SID = _re.compile(_SID_PATTERNS.get(agency, r"^[A-Za-z0-9_]{2,}$"))
        stations = sorted({p.name for p in flag_dir.iterdir()
                           if p.is_dir() and _VALID_SID.match(p.name)})

    print(f"[multiyr] {agency}  {start_year}~{end_year}  {len(stations)}개 관측소")
    for st in stations:
        try:
            plot_station_multiyr(agency, st, start_year, end_year)
        except Exception as e:
            print(f"  [multiyr] 오류 {st}: {e}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agency",     required=True)
    p.add_argument("--start_year", required=True, type=int)
    p.add_argument("--end_year",   required=True, type=int)
    p.add_argument("--station",    default=None)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.agency, args.start_year, args.end_year, args.station)
