"""요청 보조 유틸(검증/매핑/로깅/재시도/파일명 처리)."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

AREA_TO_CODE = {"동해": "E", "남해": "S", "서해": "W"}
SORT_FIELD_TO_CODE = {"station": "1", "datetime": "2"}
SORT_ORDER_TO_CODE = {"asc": "A", "desc": "D"}


def default_user_agent() -> str:
    return (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )


def map_area(area: str) -> str:
    if area not in AREA_TO_CODE:
        raise ValueError(f"area는 '남해'/'동해'/'서해' 중 하나여야 합니다: {area}")
    return AREA_TO_CODE[area]


def map_sort_field(sort_field: str) -> str:
    if sort_field not in SORT_FIELD_TO_CODE:
        raise ValueError(f"sort_field는 'station'/'datetime' 이어야 합니다: {sort_field}")
    return SORT_FIELD_TO_CODE[sort_field]


def map_sort_order(sort_order: str) -> str:
    if sort_order not in SORT_ORDER_TO_CODE:
        raise ValueError(f"sort_order는 'asc'/'desc' 이어야 합니다: {sort_order}")
    return SORT_ORDER_TO_CODE[sort_order]


def normalize_station_name(station_name: str | None) -> str | None:
    if station_name is None:
        return None
    cleaned = re.sub(r"\s+", " ", station_name).strip()
    return cleaned or None


def hhmm_to_compact(value: str) -> str:
    if not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ValueError(f"시간 형식은 HH:MM 이어야 합니다: {value}")
    hh, mm = value.split(":")
    if int(hh) > 23 or mm not in {"00", "30"}:
        raise ValueError(f"시간은 00:00~23:30(30분 단위) 이어야 합니다: {value}")
    return hh + mm


def validate_ymd(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"날짜 형식은 YYYY-MM-DD 이어야 합니다: {value}") from exc
    return value


def safe_filename(name: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    sanitized = re.sub(r"\s+", "_", sanitized)
    return sanitized or "download"


def now_kst_str(fmt: str = "%Y%m%d_%H%M%S") -> str:
    return datetime.now(KST).strftime(fmt)


def log_payload(payload: dict) -> None:
    masked = dict(payload)
    LOGGER.debug("request payload=%s", masked)


def retry(
    fn: Callable[[], object],
    retries: int = 2,
    delay: float = 0.8,
    backoff: float = 2.0,
) -> object:
    last_exc: Exception | None = None
    wait = delay
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:  # pragma: no cover
            last_exc = exc
            if attempt >= retries:
                break
            LOGGER.warning("요청 실패, 재시도 %s/%s: %s", attempt + 1, retries, exc)
            time.sleep(wait)
            wait *= backoff
    if last_exc:
        raise last_exc
    raise RuntimeError("retry 내부 오류")


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
