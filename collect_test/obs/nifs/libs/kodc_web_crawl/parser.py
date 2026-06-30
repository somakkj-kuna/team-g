"""응답(JSON/HTML/텍스트)을 DataFrame으로 정규화하는 파서."""

from __future__ import annotations

import io
import re
from typing import Any

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

RAW_TO_STD_COLUMN_MAP = {
    "obsvtrNm": "station_name",
    "관측소명": "station_name",
    "obsrvnDt": "observed_at",
    "관측일시": "observed_at",
    "wtrTempS": "surface_temp_c",
    "표층 수온(°C)": "surface_temp_c",
    "sfclyrDpwt": "surface_depth_m",
    "표층 수심(m)": "surface_depth_m",
    "wtrTempM": "middle_temp_c",
    "중층 수온(°C)": "middle_temp_c",
    "mlyrDpwt": "middle_depth_m",
    "중층 수심(m)": "middle_depth_m",
    "wtrTempB": "bottom_temp_c",
    "저층 수온(°C)": "bottom_temp_c",
    "btmlyrDpwt": "bottom_depth_m",
    "저층 수심(m)": "bottom_depth_m",
}

STD_NUMERIC_COLUMNS = [
    "surface_temp_c",
    "surface_depth_m",
    "middle_temp_c",
    "middle_depth_m",
    "bottom_temp_c",
    "bottom_depth_m",
]


def _replace_empty_like(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace({r"^\s*$": np.nan, r"^\-$": np.nan}, regex=True)


def normalize_dataframe(df: pd.DataFrame, sort_ascending: bool = True) -> pd.DataFrame:
    if df.empty:
        columns = [
            "station_name",
            "observed_at",
            "surface_temp_c",
            "surface_depth_m",
            "middle_temp_c",
            "middle_depth_m",
            "bottom_temp_c",
            "bottom_depth_m",
        ]
        return pd.DataFrame(columns=columns)

    renamed = df.rename(columns={k: v for k, v in RAW_TO_STD_COLUMN_MAP.items() if k in df.columns})
    renamed = _replace_empty_like(renamed)

    for col in STD_NUMERIC_COLUMNS:
        if col in renamed.columns:
            renamed[col] = pd.to_numeric(renamed[col], errors="coerce")

    if "observed_at" in renamed.columns:
        renamed["observed_at"] = pd.to_datetime(renamed["observed_at"], errors="coerce")

    base_columns = [
        "station_name",
        "observed_at",
        "surface_temp_c",
        "surface_depth_m",
        "middle_temp_c",
        "middle_depth_m",
        "bottom_temp_c",
        "bottom_depth_m",
    ]
    for col in base_columns:
        if col not in renamed.columns:
            renamed[col] = np.nan

    normalized = renamed[base_columns].copy()
    if "observed_at" in normalized.columns:
        normalized = normalized.sort_values("observed_at", ascending=sort_ascending, na_position="last")
    return normalized.reset_index(drop=True)


def parse_search_json(data: dict[str, Any], sort_ascending: bool = True) -> pd.DataFrame:
    ret_list = data.get("retList", [])
    if not isinstance(ret_list, list):
        raise ValueError("검색 응답 형식이 예상과 다릅니다(retList 누락).")
    return normalize_dataframe(pd.DataFrame(ret_list), sort_ascending=sort_ascending)


def parse_html_table(html: str, sort_ascending: bool = True) -> pd.DataFrame:
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        raise ValueError(f"HTML 테이블 파싱 실패: {text[:200]}")
    if not tables:
        return normalize_dataframe(pd.DataFrame(), sort_ascending=sort_ascending)
    return normalize_dataframe(tables[0], sort_ascending=sort_ascending)


def parse_text_download(text: str, sort_ascending: bool = True) -> pd.DataFrame:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return normalize_dataframe(pd.DataFrame(), sort_ascending=sort_ascending)

    rows: list[list[str]] = []
    for line in lines[1:]:
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 2:
            continue
        rows.append(parts[:8])

    raw = pd.DataFrame(
        rows,
        columns=[
            "관측소명",
            "관측일시",
            "표층 수온(°C)",
            "표층 수심(m)",
            "중층 수온(°C)",
            "중층 수심(m)",
            "저층 수온(°C)",
            "저층 수심(m)",
        ],
    )
    return normalize_dataframe(raw, sort_ascending=sort_ascending)
