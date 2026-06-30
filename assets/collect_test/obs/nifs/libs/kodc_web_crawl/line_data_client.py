#!/home/collect/appl/miniconda3/envs/dataenv/bin/python
"""KODC 정선해양조사자료 관측자료검색 연도별 CSV 수집기."""

from __future__ import annotations

import argparse
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib  # type: ignore

try:
    from .utils import default_user_agent, ensure_parent_dir, retry
except ImportError:  # python line_data_client.py 직접 실행 호환
    from utils import default_user_agent, ensure_parent_dir, retry  # type: ignore


LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "ctd" / "config" / "config.toml"
BASE_PAGE_URL = "https://www.nifs.go.kr/kodc/observe/line/data"
LIST_API_URL = "https://www.nifs.go.kr/kodc/api/observe/line/data/list"
CSV_COLUMNS = [
    "해역",
    "정선",
    "정점",
    "정선-정점",
    "위도",
    "경도",
    "관측일시(KST)",
    "관측수심(m)",
    "수온(°C)",
    "염분(psu)",
    "용존산소(ml/L)",
    "인산염인(μmol/L)",
    "아질산질소(μmol/L)",
    "질산질소(μmol/L)",
    "규산규소(μmol/L)",
    "클로로필(µg/L)",
    "pH",
    "투명도(m)",
    "기압(hPa)",
    "조사선",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KODC 정선 CTD 연도별 CSV 저장")
    parser.add_argument("year", help="대상 연도 YYYY")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="CTD config.toml 경로",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="출력 CSV 경로. 생략 시 config.paths.source_glob를 사용",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=10000,
        help="목록 API 페이지 크기",
    )
    parser.add_argument(
        "--request-interval-sec",
        type=float,
        default=0.0,
        help="페이지 간 대기 시간(초)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout(초)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="DEBUG/INFO/WARNING/ERROR",
    )
    return parser.parse_args()


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    with path.open("rb") as file_obj:
        return tomllib.load(file_obj)


def build_year_source_path(source_template: str, year: str) -> Path:
    rendered = source_template
    if "{yyyy}" in rendered:
        rendered = rendered.replace("{yyyy}", year)
    else:
        rendered = rendered.replace("*", year, 1).replace("*", year, 1)
    return Path(rendered)


def year_to_date_range(year: str) -> tuple[str, str]:
    if not year.isdigit() or len(year) != 4:
        raise ValueError(f"연도 형식은 YYYY 이어야 합니다: {year}")
    return f"{year}-01-01", f"{year}-12-31"


def normalize_value(value: Any, missing_value: str) -> Any:
    if value is None:
        return missing_value
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else missing_value
    return value


def epoch_millis_to_kst_text(value: Any, missing_value: str) -> str:
    if value in (None, ""):
        return missing_value
    try:
        timestamp = float(value) / 1000.0
    except (TypeError, ValueError):
        return missing_value
    return datetime.fromtimestamp(timestamp, tz=KST).strftime("%Y-%m-%d %H:%M:%S")


def sort_code(value: Any) -> tuple[int, float, str]:
    if value in (None, ""):
        return (1, 0.0, "")
    text = str(value).strip()
    try:
        return (0, float(text), text)
    except ValueError:
        return (0, float("inf"), text)


def row_to_csv_record(row: dict[str, Any], missing_value: str) -> dict[str, Any]:
    line = normalize_value(row.get("lsta"), missing_value)
    point = normalize_value(row.get("staCd"), missing_value)
    return {
        "해역": normalize_value(row.get("rgnNm"), missing_value),
        "정선": line,
        "정점": point,
        "정선-정점": f"{line}-{point}" if line != missing_value and point != missing_value else missing_value,
        "위도": normalize_value(row.get("lat"), missing_value),
        "경도": normalize_value(row.get("lot"), missing_value),
        "관측일시(KST)": epoch_millis_to_kst_text(row.get("msrmtDt"), missing_value),
        "관측수심(m)": normalize_value(row.get("dpwt"), missing_value),
        "수온(°C)": normalize_value(row.get("wtem"), missing_value),
        "염분(psu)": normalize_value(row.get("slnty"), missing_value),
        "용존산소(ml/L)": normalize_value(row.get("doxn"), missing_value),
        "인산염인(μmol/L)": normalize_value(row.get("po4"), missing_value),
        "아질산질소(μmol/L)": normalize_value(row.get("no2Lab"), missing_value),
        "질산질소(μmol/L)": normalize_value(row.get("no3Lab"), missing_value),
        "규산규소(μmol/L)": normalize_value(row.get("silaLab"), missing_value),
        "클로로필(µg/L)": normalize_value(row.get("chla"), missing_value),
        "pH": normalize_value(row.get("ph"), missing_value),
        "투명도(m)": normalize_value(row.get("trncy"), missing_value),
        "기압(hPa)": normalize_value(row.get("arcsr"), missing_value),
        "조사선": normalize_value(row.get("rescvesl"), missing_value),
    }


def sort_and_deduplicate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, Any, Any, Any], dict[str, Any]] = {}
    for record in records:
        key = (
            record.get("정선"),
            record.get("정점"),
            record.get("관측일시(KST)"),
            record.get("관측수심(m)"),
        )
        deduped[key] = record

    return sorted(
        deduped.values(),
        key=lambda record: (
            record.get("관측일시(KST)", ""),
            sort_code(record.get("정선")),
            sort_code(record.get("정점")),
            sort_code(record.get("관측수심(m)")),
        ),
    )


class KODCLineDataClient:
    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": default_user_agent(),
                "Accept": "application/json, text/plain, */*",
                "Referer": BASE_PAGE_URL,
            }
        )
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        response = self.session.get(BASE_PAGE_URL, timeout=self.timeout)
        response.raise_for_status()
        self._initialized = True

    def fetch_page(
        self,
        start_date: str,
        end_date: str,
        page: int,
        size: int,
    ) -> dict[str, Any]:
        self.initialize()
        params = {
            "startDate": start_date,
            "endDate": end_date,
            "page": page,
            "size": size,
        }
        response = self.session.get(LIST_API_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def fetch_all_rows(
        self,
        start_date: str,
        end_date: str,
        page_size: int = 10000,
        request_interval_sec: float = 0.0,
    ) -> list[dict[str, Any]]:
        if page_size < 1:
            raise ValueError("page_size must be >= 1")

        page = 1
        total = None
        all_rows: list[dict[str, Any]] = []

        while True:
            payload = retry(
                lambda: self.fetch_page(start_date, end_date, page=page, size=page_size),
                retries=2,
                delay=1.0,
                backoff=2.0,
            )
            if not isinstance(payload, dict):
                raise ValueError("목록 API 응답이 dict가 아닙니다.")

            rows = payload.get("list", [])
            if not isinstance(rows, list) or not rows:
                break

            if total is None:
                total = int(payload.get("total", 0))
                LOGGER.info("KODC line data total rows=%s", total)

            all_rows.extend(rows)
            LOGGER.info("Fetched page=%s rows=%s accumulated=%s", page, len(rows), len(all_rows))

            if total is not None and len(all_rows) >= total:
                break
            if len(rows) < page_size:
                break

            page += 1
            if request_interval_sec > 0:
                import time

                time.sleep(request_interval_sec)

        return all_rows


def save_year_csv(
    year: str,
    output_path: str | Path | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    page_size: int = 10000,
    request_interval_sec: float = 0.0,
    timeout: float = 60.0,
) -> Path:
    config_file = Path(config_path)
    config = load_config(config_file)
    paths_cfg = config.get("paths", {})
    merge_cfg = config.get("merge", {})
    missing_value = str(merge_cfg.get("missing_value", "-999"))

    if output_path is None:
        source_template = str(paths_cfg["source_glob"])
        output_file = build_year_source_path(source_template, year)
        if not output_file.is_absolute():
            root_dir = Path(str(paths_cfg.get("root_dir", config_file.parent.parent))).expanduser()
            output_file = (root_dir / output_file).resolve()
    else:
        output_file = Path(output_path)

    ensure_parent_dir(output_file)

    start_date, end_date = year_to_date_range(year)
    LOGGER.info("KODC line CTD year=%s date_range=%s~%s", year, start_date, end_date)
    LOGGER.info("Output CSV=%s", output_file)

    client = KODCLineDataClient(timeout=timeout)
    rows = client.fetch_all_rows(
        start_date=start_date,
        end_date=end_date,
        page_size=page_size,
        request_interval_sec=request_interval_sec,
    )

    records = [row_to_csv_record(row, missing_value) for row in rows]
    records = sort_and_deduplicate(records)

    with output_file.open("w", encoding="utf-8-sig", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(records)

    LOGGER.info("Saved KODC line CTD CSV rows=%s path=%s", len(records), output_file)
    return output_file


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    path = save_year_csv(
        year=args.year,
        output_path=args.output,
        config_path=args.config,
        page_size=args.page_size,
        request_interval_sec=args.request_interval_sec,
        timeout=args.timeout,
    )
    print(f"saved: {path}")


if __name__ == "__main__":
    main()
