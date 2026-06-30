# -*- coding: utf-8-sig -*-
"""
QC 설정 로더 — 우선순위: station > agency > qc_rules(기본값)
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

QC_ROOT    = Path(__file__).resolve().parents[3]
RULES_PATH = QC_ROOT / "src" / "config" / "qc_rules.toml"
AGENCY_DIR = QC_ROOT / "meta" / "agencies"
STATION_DIR = QC_ROOT / "meta" / "stations"


# ── 실행 프로파일(경로 라우팅) ───────────────────────────────────────
# 환경변수 QC_PROFILE=err 이면 입력/중간/출력 경로를 에러검증용으로 분리한다.
#   - 입력 raw  : <QC_ERR_RAW_ROOT 또는 test/raw>/{agency}/{dataset}
#   - 중간 sorted: src/tmp/sorted_err
#   - 중간 flags : src/tmp/flags_err
#   - 최종 결과  : err_result/  (일반은 result/)
def qc_profile() -> str:
    """현재 실행 프로파일. 'err' 또는 '' (기본)."""
    return os.environ.get("QC_PROFILE", "").strip().lower()


def result_dir() -> Path:
    """최종 결과 루트. err 프로파일이면 err_result/, 아니면 result/."""
    return QC_ROOT / ("err_result" if qc_profile() == "err" else "result")


def sorted_dir() -> Path:
    """sorted 중간 산출물 루트. err 프로파일이면 sorted_err/."""
    sub = "sorted_err" if qc_profile() == "err" else "sorted"
    return QC_ROOT / "src" / "tmp" / sub


def flags_dir() -> Path:
    """flag 중간 산출물 루트. err 프로파일이면 flags_err/."""
    sub = "flags_err" if qc_profile() == "err" else "flags"
    return QC_ROOT / "src" / "tmp" / sub


def err_raw_root() -> Path:
    """err 프로파일 입력 raw 루트 (기본 test/raw)."""
    return Path(os.environ.get("QC_ERR_RAW_ROOT") or str(QC_ROOT / "raw"))


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        content = f.read()
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
    return tomllib.loads(content.decode("utf-8"))


def _deep_merge(base: dict, override: dict) -> dict:
    """override가 base를 재귀적으로 덮어씀."""
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_rules() -> dict:
    return _load_toml(RULES_PATH)


def load_agency(agency: str) -> dict:
    return _load_toml(AGENCY_DIR / f"{agency}.toml")


def load_station(station_id: str, agency: str = "") -> dict:
    """meta/stations/{AGENCY}/{station_id}.toml 로드. agency 없으면 구버전 경로 fallback."""
    if agency:
        path = STATION_DIR / agency.upper() / f"{station_id}.toml"
    else:
        path = STATION_DIR / f"{station_id}.toml"
    return _load_toml(path)


def get_var_cfg(var_id: str, agency: str,
                station_id: str | None = None) -> dict:
    """
    변수 하나의 QC 설정 반환 (station > agency > rules 순 병합).
    """
    rules   = load_rules()
    agency_cfg = load_agency(agency)
    station_cfg = load_station(station_id, agency) if station_id else {}

    base = rules.get("variables", {}).get(var_id, {})

    agency_var = (agency_cfg.get("override", {})
                             .get("variables", {})
                             .get(var_id, {}))
    station_var = (station_cfg.get("override", {})
                               .get("variables", {})
                               .get(var_id, {}))

    merged = _deep_merge(base, agency_var)
    merged = _deep_merge(merged, station_var)
    return merged


def get_flag_codes(rules: dict | None = None) -> dict:
    if rules is None:
        rules = load_rules()
    return rules.get("flag", {
        "good": 1, "suspect": 2, "bad": 3,
        "interpolated": 4, "missing": 9,
    })


def get_dataset_path(agency: str, dataset: str) -> str:
    # err 프로파일: 입력 raw 를 test/raw 로 강제 (합성 에러 데이터)
    if qc_profile() == "err":
        return str(err_raw_root() / agency / dataset)
    # 1순위: qc_rules.toml [paths] 섹션
    rules = load_rules()
    raw_path = (rules.get("paths", {})
                     .get(agency, {})
                     .get(dataset, {})
                     .get("raw", ""))
    if raw_path:
        return raw_path
    # 2순위: meta/agencies/{agency}.toml fallback
    cfg = load_agency(agency)
    return cfg.get("datasets", {}).get(dataset, {}).get("prc_path", "")


def get_dataset_vars(agency: str, dataset: str) -> list[str]:
    cfg = load_agency(agency)
    return cfg.get("datasets", {}).get(dataset, {}).get("variables", [])


def infer_interval(df_station: "pd.DataFrame") -> str:  # type: ignore[name-defined]
    """시간 간격 추정: 'ten_min' | 'hourly' | 'other'"""
    import pandas as pd
    times = df_station["time"].dropna().sort_values()
    if len(times) < 2:
        return "other"
    median_min = pd.Series(times.diff().dropna()
                           ).dt.total_seconds().median() / 60
    if abs(median_min - 10) < 2:
        return "ten_min"
    if abs(median_min - 60) < 5:
        return "hourly"
    return "other"
