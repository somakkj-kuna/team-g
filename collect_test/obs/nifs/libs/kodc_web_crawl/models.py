"""검색 조건/결과 구조를 정의하는 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AreaName = Literal["남해", "동해", "서해"]
SortField = Literal["station", "datetime"]
SortOrder = Literal["asc", "desc"]


@dataclass(slots=True)
class SearchCondition:
    area: AreaName
    station_name: str | None
    start_date: str
    end_date: str
    start_time: str = "00:00"
    end_time: str = "23:30"
    sort_field: SortField = "station"
    sort_order: SortOrder = "asc"
    use_browser_fallback: bool = True
    page: int = 1
    page_size: int = 50


@dataclass(slots=True)
class ObservationRow:
    station_name: str
    observed_at: str
    surface_temp_c: float | None
    surface_depth_m: float | None
    middle_temp_c: float | None
    middle_depth_m: float | None
    bottom_temp_c: float | None
    bottom_depth_m: float | None
