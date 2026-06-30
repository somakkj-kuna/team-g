#!/usr/bin/env python
# -*- coding: utf-8-sig -*-
"""
05_plot.py — QC 결과 시각화
result/flag/{agency}/{station_id}/{yyyy}/{yyyymm}_flag.csv 읽어
변수별 flag 시계열 그래프를 result/plots/{agency}/{station_id}/{yyyy}/{yyyymm}.png 로 저장.

사용법:
  python src/pipeline/05_plot.py --agency khoa --dataset tidal --yyyymm 202501          # 전체 관측소
  python src/pipeline/05_plot.py --agency khoa --station DT_0001 --yyyymm 202501        # 단일 관측소
  python src/pipeline/05_plot.py --agency khoa --station DT_0001 --yyyymm 202501 --var sur_temp
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["axes.unicode_minus"] = False

# 한글 폰트: 맑은 고딕 (Windows) → 없으면 기본값 유지
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
import numpy as np
import pandas as pd

QC_ROOT     = Path(__file__).resolve().parents[3]
STATION_DIR = QC_ROOT / "meta" / "stations"
sys.path.insert(0, str(QC_ROOT))

from src.libs.utils.config_loader import result_dir
# 실행 프로파일(QC_PROFILE)에 따라 result/ 또는 err_result/ 로 분기.
RESULT_DIR  = result_dir()

FLAG_COLOR = {
    1: "#2ca02c",   # good — 녹색
    2: "#f1c40f",   # suspect — 노랑
    3: "#d62728",   # bad — 빨강
    4: "#8e44ad",   # interpolated — 보라
    9: "#aaaaaa",   # missing — 회색
    0: "#cccccc",   # unset
}
FLAG_LABEL = {
    1: "good", 2: "suspect", 3: "bad",
    4: "interpolated", 9: "missing",
}

# 변수별 y축 레이블
VAR_UNIT = {
    "temp":          "수온 (°C)",
    "sur_temp":      "표층수온 (°C)",
    "mid_temp":      "중층수온 (°C)",
    "bot_temp":      "저층수온 (°C)",
    "sal":           "염분 (psu)",
    "tide_real":     "조위-실측 (cm)",
    "tide_pre":      "조위-예측 (cm)",
    "air_temp":      "기온 (°C)",
    "air_pres":      "기압 (hPa)",
    "air_humi":      "습도 (%)",
    "wind_speed":    "풍속 (m/s)",
    "wind_gust":     "순간최대풍속 (m/s)",
    "wind_dir":      "풍향 (°)",
    "wave_h":        "파고 (m)",
    "current_speed": "유속 (cm/s)",
    "current_dir":   "유향 (°)",
}

# 변수 subplot 제목: 한글 + 영문
VAR_LABEL = {
    "sur_temp":      "표층수온  sur_temp",
    "mid_temp":      "중층수온  mid_temp",
    "bot_temp":      "저층수온  bot_temp",
    "temp":          "수온  temp",
    "tide_real":     "조위(실측)  tide_real",
    "sal":           "염분  sal",
    "air_temp":      "기온  air_temp",
    "air_pres":      "기압  air_pres",
    "air_humi":      "습도  air_humi",
    "current_speed": "유속  current_speed",
    "current_dir":   "유향  current_dir",
    "wave_h":        "파고  wave_h",
    "wind_speed":    "풍속  wind_speed",
    "wind_dir":      "풍향  wind_dir",
    "wind_gust":     "순간최대풍속  wind_gust",
}

# 고정 변수 순서 (없는 변수는 skip, 목록에 없는 변수는 맨 뒤에 추가)
PLOT_ORDER = [
    "sur_temp", "mid_temp", "bot_temp", "tide_real", "sal",
    "air_temp", "air_pres", "air_humi",
    "current_speed", "current_dir",
    "wave_h", "wind_speed", "wind_dir", "wind_gust",
]

# 변수별 고정 y축 범위 (None → 자동)
VAR_YLIM: dict[str, tuple[float, float] | None] = {
    "temp":          (-2,  40),
    "sur_temp":      (-2,  40),
    "mid_temp":      (-2,  40),
    "bot_temp":      (-2,  40),
    "sal":           (0,   40),
    "tide_real":     None,
    "tide_pre":      None,
    "air_temp":      (-20, 40),
    "air_humi":      (0,   100),
    "air_pres":      (960, 1040),
    "wind_speed":    (0,   25),
    "wind_gust":     (0,   35),
    "wind_dir":      (0,   360),
    "wave_h":        (0,   10),
    "current_speed": (0,   200),
    "current_dir":   (0,   360),
}

def _load_station_meta(station_id: str, agency: str) -> tuple[dict, str]:
    """meta/stations/{AGENCY}/{station_id}.toml 읽어 (ylim dict, name_k) 반환."""
    path = STATION_DIR / agency.upper() / f"{station_id}.toml"
    if not path.exists():
        return {}, ""
    with open(path, "rb") as f:
        content = f.read()
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
    cfg = tomllib.loads(content.decode("utf-8"))
    raw = cfg.get("plot", {}).get("ylim", {})
    ylim = {k: tuple(v) for k, v in raw.items() if isinstance(v, list) and len(v) == 2}
    name_k = cfg.get("info", {}).get("name_k", "")
    return ylim, name_k

def _load_station_ylim(station_id: str, agency: str) -> dict[str, tuple[float, float]]:
    ylim, _ = _load_station_meta(station_id, agency)
    return ylim


# DEFAULT_VARS는 PLOT_ORDER로 대체됨


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agency",  required=True)
    p.add_argument("--dataset", default=None, help="전체 관측소 배치 처리")
    p.add_argument("--station", default=None, help="단일 관측소 지정")
    p.add_argument("--yyyymm",  default=None, help="단월 플롯 (YYYYMM)")
    p.add_argument("--year",    default=None, help="연간 플롯 (YYYY) — 해당 연도 전체 월 합산")
    p.add_argument("--var",     default=None, help="특정 변수만 (없으면 기본 변수 전체)")
    return p.parse_args()


def _scatter_flags(ax: plt.Axes, times: pd.Series, values: pd.Series,
                   flags: pd.Series, label_done: set, s: float = 12) -> None:
    """flag 코드별로 색상을 달리하여 scatter 플롯."""
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


def plot_station(csv_path: Path, var_filter: str | None = None,
                 yyyymm: str | None = None) -> Path:
    df = pd.read_csv(csv_path, dtype={"flag_final": int, "flag_aqc1": int})
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    # 연간 파일에서 특정 월만 추출 (월별 모드)
    if yyyymm:
        df = df[df["time"].dt.strftime("%Y%m") == yyyymm]
        if df.empty:
            print(f"  [plot] {yyyymm} 데이터 없음 — {csv_path.name}")
            return csv_path
    else:
        # 구버전 호환: 파일명에서 yyyymm 추출 시도
        m = re.search(r'_(\d{6})_qc_flag$', csv_path.stem)
        yyyymm = m.group(1) if m else df["time"].dt.strftime("%Y%m").mode()[0]

    agency     = str(df["agency"].iloc[0])
    station_id = str(df["station_id"].iloc[0])
    lat        = float(df["lat"].iloc[0])
    lon        = float(df["lon"].iloc[0])

    # 관측소별 ylim 오버라이드 (없으면 VAR_YLIM 기본값 사용)
    station_ylim = _load_station_ylim(station_id, agency)
    effective_ylim = {**VAR_YLIM, **station_ylim}

    # 플롯할 변수 목록
    _EXCLUDE = {"wind_u", "wind_v", "current_u", "current_v", "tide_pre", "temp"}
    available = set(df["var_id"].unique().tolist()) - _EXCLUDE
    if var_filter:
        plot_vars = [v for v in [var_filter] if v in available]
    else:
        plot_vars = [v for v in PLOT_ORDER if v in available]
        plot_vars += [v for v in available if v not in plot_vars]

    if not plot_vars:
        print(f"  [plot] {station_id}: 플롯할 변수 없음")
        return csv_path

    n_rows = len(plot_vars)
    fig, axes = plt.subplots(
        n_rows, 1,
        figsize=(16, 4.5 * n_rows),
        sharex=True,
    )
    if n_rows == 1:
        axes = [axes]

    label_done: set = set()

    for ax, var in zip(axes, plot_vars):
        sub = df[df["var_id"] == var].sort_values("time")
        times  = sub["time"]
        values = sub["value"]
        flags  = sub["flag_final"]

        # 배경선: good 값만 연결
        good_mask = flags == 1
        ax.plot(
            times[good_mask], values[good_mask],
            color="#cccccc", linewidth=0.5, zorder=1, alpha=0.6,
        )

        _scatter_flags(ax, times, values, flags, label_done, s=12)

        ylim = effective_ylim.get(var)
        if ylim is not None:
            ax.set_ylim(*ylim)

        # suspect/bad reason 텍스트 (bad만)
        bad_rows = sub[flags == 3].head(5)
        for _, row in bad_rows.iterrows():
            if pd.notna(row["value"]):
                ax.annotate(
                    str(row.get("reason_aqc1") or "bad")[:20],
                    xy=(row["time"], row["value"]),
                    xytext=(0, 10), textcoords="offset points",
                    fontsize=6, color="#d62728", ha="center",
                )

        ylabel = VAR_UNIT.get(var, var)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.yaxis.set_label_coords(-0.07, 0.5)
        ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.5)
        ax.xaxis.set_minor_locator(mdates.DayLocator(interval=1))
        ax.grid(axis="x", which="minor", linestyle=":", linewidth=0.4, alpha=0.35)
        ax.grid(axis="x", which="major", linestyle="-", linewidth=0.5, alpha=0.45)
        ax.set_title(VAR_LABEL.get(var, var), fontsize=9, loc="left", pad=3)
        ax.tick_params(labelsize=8)

        # 통계 텍스트
        n_good    = (flags == 1).sum()
        n_suspect = (flags == 2).sum()
        n_bad     = (flags == 3).sum()
        n_miss    = (flags == 9).sum()
        total     = len(flags)
        stat_txt  = (f"good {n_good}  suspect {n_suspect}  "
                     f"bad {n_bad}  missing {n_miss}  / {total}")
        ax.text(0.99, 0.97, stat_txt,
                transform=ax.transAxes,
                fontsize=7, ha="right", va="top", color="#555555")

    # x축 날짜 포맷
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    axes[-1].xaxis.set_major_locator(mdates.DayLocator(interval=3))

    # 범례 (첫 번째 축에)
    handles, labels = [], []
    for fv, color in FLAG_COLOR.items():
        lbl = FLAG_LABEL.get(fv)
        if lbl and lbl in label_done:
            from matplotlib.lines import Line2D
            handles.append(Line2D([0], [0], marker="o", color="w",
                                  markerfacecolor=color, markersize=7))
            labels.append(lbl)
    axes[-1].legend(handles, labels, loc="lower right",
                    fontsize=7, framealpha=0.8, ncol=len(labels),
                    markerscale=0.7, handletextpad=0.4, columnspacing=0.8)

    yyyy = yyyymm[:4]
    mm   = yyyymm[4:]
    _, name_k = _load_station_meta(station_id, agency)
    sid_label = f"{station_id} ({name_k})" if name_k else station_id
    fig.suptitle(
        f"{agency.upper()}  {sid_label}  ({lat:.3f}°N, {lon:.3f}°E)  "
        f"{yyyy}-{mm}  QC 결과",
        fontsize=11, y=1.002,
    )
    fig.tight_layout()
    plt.setp(axes[-1].xaxis.get_majorticklabels(), visible=True, rotation=0, ha="center", fontsize=8)

    yyyy    = yyyymm[:4]
    out_dir = RESULT_DIR / "plots" / agency / station_id / yyyy
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{yyyymm}.png"
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)

    print(f"  [plot] 저장: {out_path}")
    return out_path


def run_batch(agency: str, yyyymm: str,
              var_filter: str | None = None) -> None:
    """result/flag/{agency}/ 아래에 해당 월 flag.csv가 있는 관측소 전체 플롯."""
    yyyy      = yyyymm[:4]
    agency_dir = RESULT_DIR / "flag" / agency
    if not agency_dir.exists():
        print(f"[plot] 결과 폴더 없음: {agency_dir}")
        return

    csv_files = sorted(agency_dir.glob(f"*/{yyyy}/*_{yyyy}_qc_flag.csv"))
    if not csv_files:
        print(f"[plot] {agency}/{yyyymm} 에 해당하는 qc_flag.csv 없음")
        return

    print(f"[plot] {agency}/{yyyymm}  {len(csv_files)}개 관측소")
    for csv_path in csv_files:
        try:
            plot_station(csv_path, var_filter, yyyymm=yyyymm)
        except Exception as e:
            print(f"  [plot] 오류 {csv_path.parts[-3]}: {e}")


def plot_station_annual(station_id: str, agency: str, yyyy: str,
                        var_filter: str | None = None) -> None:
    """해당 연도의 모든 월 qc_flag.csv를 합산해 연간 플롯 저장."""
    annual_path = (RESULT_DIR / "flag" / agency / station_id / yyyy
                    / f"{agency}_{station_id}_{yyyy}_qc_flag.csv")
    if not annual_path.exists():
        print(f"  [plot] {station_id}/{yyyy}: qc_flag.csv 없음")
        return

    try:
        df = pd.read_csv(annual_path, dtype={"flag_final": int, "flag_aqc1": int})
    except Exception as e:
        print(f"  [plot] 읽기 오류 {annual_path.name}: {e}")
        return
    df["time"]  = pd.to_datetime(df["time"], utc=True)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.sort_values("time")

    lat        = float(df["lat"].iloc[0])
    lon        = float(df["lon"].iloc[0])
    available  = df["var_id"].unique().tolist()

    _EXCLUDE  = {"wind_u", "wind_v", "current_u", "current_v", "tide_pre", "temp"}
    available = [v for v in available if v not in _EXCLUDE]
    if var_filter:
        plot_vars = [v for v in [var_filter] if v in available]
    else:
        plot_vars = [v for v in PLOT_ORDER if v in available]
        plot_vars += [v for v in available if v not in plot_vars]
    if not plot_vars:
        return

    station_ylim  = _load_station_ylim(station_id, agency)
    effective_ylim = {**VAR_YLIM, **station_ylim}

    n_rows = len(plot_vars)
    fig, axes = plt.subplots(n_rows, 1, figsize=(26, 4.0 * n_rows), sharex=True)
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
        _scatter_flags(ax, times, values, flags, label_done, s=6)

        ylim = effective_ylim.get(var)
        if ylim is not None:
            ax.set_ylim(*ylim)

        ylabel = VAR_UNIT.get(var, var)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.yaxis.set_label_coords(-0.05, 0.5)
        ax.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.5)
        ax.set_title(VAR_LABEL.get(var, var), fontsize=9, loc="left", pad=3)
        ax.tick_params(labelsize=8)

        n_good = (flags == 1).sum(); n_bad = (flags == 3).sum()
        ax.text(0.99, 0.97, f"good {n_good}  bad {n_bad}  / {len(flags)}",
                transform=ax.transAxes, fontsize=7, ha="right", va="top", color="#555555")

    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator())

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

    _, name_k_a = _load_station_meta(station_id, agency)
    sid_label_a = f"{station_id} ({name_k_a})" if name_k_a else station_id
    fig.suptitle(
        f"{agency.upper()}  {sid_label_a}  ({lat:.3f}°N, {lon:.3f}°E)  {yyyy}  QC 결과",
        fontsize=11, y=1.002,
    )
    fig.tight_layout()
    plt.setp(axes[-1].xaxis.get_majorticklabels(), visible=True, rotation=0, ha="center", fontsize=8)

    out_dir  = RESULT_DIR / "plots" / agency / station_id / yyyy
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{yyyy}_annual.png"
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"  [plot] 저장: {out_path}")


def run(agency: str, yyyymm: str | None = None, yyyy: str | None = None,
        dataset: str | None = None,
        station: str | None = None,
        var_filter: str | None = None) -> None:
    if yyyy:
        # 연간 플롯 모드
        if station:
            plot_station_annual(station, agency, yyyy, var_filter)
        else:
            agency_dir = RESULT_DIR / "flag" / agency
            stations = sorted({p.parent.parent.name
                               for p in agency_dir.glob(f"*/{yyyy}/*_{yyyy}_qc_flag.csv")})
            print(f"[plot] {agency}/{yyyy} 연간  {len(stations)}개 관측소")
            for st in stations:
                try:
                    plot_station_annual(st, agency, yyyy, var_filter)
                except Exception as e:
                    print(f"  [plot] 오류 {st}: {e}")
    elif yyyymm:
        if station:
            yyyy_     = yyyymm[:4]
            csv_path  = (RESULT_DIR / "flag" / agency / station / yyyy_
                         / f"{agency}_{station}_{yyyy_}_qc_flag.csv")
            if not csv_path.exists():
                raise FileNotFoundError(f"CSV 없음: {csv_path}\n먼저 04_export.py 를 실행하세요.")
            print(f"[plot] {agency}/{station}/{yyyymm}")
            plot_station(csv_path, var_filter, yyyymm=yyyymm)
        else:
            run_batch(agency, yyyymm, var_filter)
    else:
        raise ValueError("--yyyymm 또는 --year 중 하나를 지정하세요.")


if __name__ == "__main__":
    args = parse_args()
    run(args.agency, args.yyyymm, args.year, args.dataset, args.station, args.var)
