"""NIFS 실시간 관측 검색/다운로드 클라이언트 (requests 우선, Playwright 보조)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from .models import SearchCondition
    from .parser import normalize_dataframe, parse_html_table, parse_search_json
    from .utils import (
        default_user_agent,
        ensure_parent_dir,
        hhmm_to_compact,
        log_payload,
        map_area,
        map_sort_field,
        map_sort_order,
        normalize_station_name,
        now_kst_str,
        retry,
        safe_filename,
        validate_ymd,
    )
except ImportError:  # python client.py 직접 실행 호환
    from models import SearchCondition
    from parser import normalize_dataframe, parse_html_table, parse_search_json
    from utils import (
        default_user_agent,
        ensure_parent_dir,
        hhmm_to_compact,
        log_payload,
        map_area,
        map_sort_field,
        map_sort_order,
        normalize_station_name,
        now_kst_str,
        retry,
        safe_filename,
        validate_ymd,
    )

LOGGER = logging.getLogger(__name__)
ALL_AREAS = ("동해", "남해", "서해")


class NifsRealtimeClient:
    BASE_PAGE = "https://www.nifs.go.kr/risa/risa/risaA/actionRisaInfo.do"
    BASE_API = "https://www.nifs.go.kr/risa/risa/risaA"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": default_user_agent(),
                "Accept": "application/json, text/plain, */*",
                "Referer": self.BASE_PAGE,
            }
        )
        self._form_defaults: dict[str, str] = {}
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        response = self.session.get(self.BASE_PAGE, timeout=self.timeout)
        response.raise_for_status()
        self._form_defaults = self._extract_form_defaults(response.text)
        self._initialized = True
        LOGGER.info("초기 페이지 접근 완료: defaults=%s", self._form_defaults)

    @staticmethod
    def _extract_form_defaults(html: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        form = soup.select_one("form#schFrm")
        if not form:
            return {}
        defaults: dict[str, str] = {}
        for tag in form.select("input[id], select[id], textarea[id]"):
            key = tag.get("id")
            if not key:
                continue
            if tag.name == "select":
                selected = tag.select_one("option[selected]") or tag.select_one("option")
                defaults[key] = selected.get("value", "") if selected else ""
            elif tag.get("type") == "checkbox":
                defaults[key] = "Y" if tag.has_attr("checked") else "N"
            elif tag.get("type") == "radio":
                if tag.has_attr("checked"):
                    defaults[tag.get("name", key)] = tag.get("value", "")
            else:
                defaults[key] = tag.get("value", "")
        return defaults

    def _post(self, endpoint: str, payload: dict[str, Any]) -> requests.Response:
        self.initialize()
        url = f"{self.BASE_API}/{endpoint.lstrip('/')}"
        log_payload(payload)
        return self.session.post(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
            timeout=self.timeout,
        )

    def _post_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._post(endpoint, payload)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type:
            raise ValueError(f"JSON 응답 기대와 다름: {content_type}")
        return response.json()

    def get_station_options(self, area_code: str) -> list[dict[str, str]]:
        data = self._post_json("getRisaStationCode.do", {"obsrvnGroupNm": area_code, "useY": "T"})
        ret = data.get("retList", [])
        if not isinstance(ret, list):
            raise ValueError("관측소 코드 응답 형식이 예상과 다릅니다.")
        return ret

    def resolve_station_code(self, area_code: str, station_name: str | None) -> str:
        station_name = normalize_station_name(station_name)
        if not station_name:
            return "X"
        options = self.get_station_options(area_code)
        exact = [o for o in options if normalize_station_name(o.get("obsvtrNm")) == station_name]
        if exact:
            return str(exact[0]["obsvtrCd"])
        partial = [o for o in options if station_name in str(o.get("obsvtrNm", ""))]
        if partial:
            return str(partial[0]["obsvtrCd"])
        raise ValueError(f"관측소명을 찾을 수 없습니다: {station_name}")

    def _build_search_payload(
        self,
        condition: SearchCondition,
        station_code: str,
        row_count_page: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "obsrvnGroupNm": map_area(condition.area),
            "obsvtrCd": station_code,
            "ord": map_sort_field(condition.sort_field),
            "ordType": map_sort_order(condition.sort_order),
            "obsFrom": validate_ymd(condition.start_date),
            "obsTo": validate_ymd(condition.end_date),
            "obsTimeFrom": hhmm_to_compact(condition.start_time),
            "obsTimeTo": hhmm_to_compact(condition.end_time),
        }
        final_page = condition.page if condition.page >= 1 else 1
        final_page_size = row_count_page if row_count_page is not None else condition.page_size
        if final_page_size and final_page_size >= 1:
            payload["selectPage"] = final_page
            payload["rowCountPage"] = final_page_size
        return payload

    def search_requests(self, condition: SearchCondition) -> pd.DataFrame:
        area_code = map_area(condition.area)
        station_code = self.resolve_station_code(area_code, condition.station_name)
        payload = self._build_search_payload(condition, station_code)
        data = retry(lambda: self._post_json("searchRisaInfoList.do", payload), retries=2)
        if not isinstance(data, dict):
            raise ValueError("검색 응답이 비정상입니다.")
        return parse_search_json(data, sort_ascending=(condition.sort_order == "asc"))

    def search_all_pages(self, condition: SearchCondition, max_pages: int = 200) -> pd.DataFrame:
        area_code = map_area(condition.area)
        station_code = self.resolve_station_code(area_code, condition.station_name)

        page = condition.page if condition.page >= 1 else 1
        page_size = condition.page_size if condition.page_size >= 1 else 50
        fetched = 0
        total_count: int | None = None
        chunks: list[pd.DataFrame] = []

        while page <= max_pages:
            payload = self._build_search_payload(condition, station_code, row_count_page=page_size)
            payload["selectPage"] = page
            data = retry(lambda: self._post_json("searchRisaInfoList.do", payload), retries=2)
            if not isinstance(data, dict):
                break
            ret_list = data.get("retList", [])
            if not isinstance(ret_list, list) or not ret_list:
                break

            if total_count is None:
                try:
                    total_count = int(ret_list[0].get("allCnt", 0))
                except Exception:
                    total_count = None

            page_df = parse_search_json(data, sort_ascending=(condition.sort_order == "asc"))
            if page_df.empty:
                break
            chunks.append(page_df)
            fetched += len(page_df)

            if total_count and fetched >= total_count:
                break
            if len(page_df) < page_size:
                break
            page += 1

        if not chunks:
            return normalize_dataframe(pd.DataFrame(), sort_ascending=(condition.sort_order == "asc"))

        merged = pd.concat(chunks, ignore_index=True)
        merged = merged.drop_duplicates(subset=["station_name", "observed_at"], keep="first")
        merged = merged.sort_values("observed_at", ascending=(condition.sort_order == "asc"), na_position="last")
        return merged.reset_index(drop=True)

    def search(self, condition: SearchCondition) -> pd.DataFrame:
        try:
            df = self.search_requests(condition)
            if df.empty and condition.use_browser_fallback:
                LOGGER.warning("requests 검색 결과가 비어 Playwright fallback 시도")
                return self.search_playwright(condition)
            return df
        except Exception as exc:
            if not condition.use_browser_fallback:
                raise
            LOGGER.warning("requests 검색 실패, Playwright fallback: %s", exc)
            return self.search_playwright(condition)

    def search_playwright(self, condition: SearchCondition, timeout_ms: int = 30_000) -> pd.DataFrame:
        try:
            from playwright.sync_api import TimeoutError as PwTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Playwright가 설치되지 않았습니다. `playwright install`을 실행하세요.") from exc

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(self.BASE_PAGE, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector("#obsrvnGroupNm", timeout=timeout_ms)

            area_code = map_area(condition.area)
            page.select_option("#obsrvnGroupNm", area_code)
            page.wait_for_timeout(800)

            station_name = normalize_station_name(condition.station_name)
            if station_name:
                options = page.locator("#obsvtrCd option").all_text_contents()
                matched = None
                for name in options:
                    if station_name == normalize_station_name(name) or station_name in name:
                        matched = name
                        break
                if not matched:
                    raise ValueError(f"관측소명 불일치: {station_name}")
                page.select_option("#obsvtrCd", label=matched)

            page.select_option("#ord", map_sort_field(condition.sort_field))
            page.select_option("#ordType", map_sort_order(condition.sort_order))
            page.fill("#obsFrom", validate_ymd(condition.start_date))
            page.fill("#obsTo", validate_ymd(condition.end_date))

            if condition.start_time != "00:00" or condition.end_time != "23:30":
                page.check("#obsTimeDefault")
                page.select_option("#obsTimeFrom", hhmm_to_compact(condition.start_time))
                page.select_option("#obsTimeTo", hhmm_to_compact(condition.end_time))

            try:
                with page.expect_response(
                    lambda r: "searchRisaInfoList.do" in r.url and r.request.method == "POST",
                    timeout=timeout_ms,
                ) as resp_info:
                    page.click("#schBtn")
                payload = resp_info.value.json()
            except PwTimeoutError as exc:
                raise RuntimeError("Playwright 검색 응답 대기 실패") from exc
            finally:
                context.close()
                browser.close()

        return parse_search_json(payload, sort_ascending=(condition.sort_order == "asc"))

    def download_text(
        self,
        condition: SearchCondition,
        output_path: str | Path | None = None,
    ) -> Path:
        area_code = map_area(condition.area)
        station_code = self.resolve_station_code(area_code, condition.station_name)
        payload = self._build_search_payload(condition, station_code)
        response = self._post("risaInfoTextDownload.do", payload)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type:
            raise RuntimeError("텍스트 다운로드 응답이 HTML 오류 페이지입니다.")

        if output_path is None:
            output_path = Path(f"buoy_obs_{now_kst_str()}.txt")
        output_path = Path(output_path)
        ensure_parent_dir(output_path)
        output_path.write_bytes(response.content)
        return output_path

    def download_excel(
        self,
        condition: SearchCondition,
        output_path: str | Path | None = None,
    ) -> Path:
        area_code = map_area(condition.area)
        station_code = self.resolve_station_code(area_code, condition.station_name)
        payload = self._build_search_payload(condition, station_code, row_count_page=100000)

        response = self._post("searchRisaInfoList.do", payload)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()

        if output_path is None:
            station = safe_filename(condition.station_name or "all")
            output_path = Path(f"buoy_obs_{station}_{now_kst_str()}.xlsx")
        output_path = Path(output_path)
        ensure_parent_dir(output_path)

        if "application/json" in content_type:
            df = parse_search_json(response.json(), sort_ascending=(condition.sort_order == "asc"))
            if df.empty:
                raise ValueError("엑셀 저장 대상 데이터가 없습니다.")
            df.to_excel(output_path, index=False)
            return output_path

        if any(k in content_type for k in ["application/vnd.ms-excel", "application/octet-stream"]):
            output_path.write_bytes(response.content)
            return output_path

        text = response.text
        if "<table" in text.lower():
            df = parse_html_table(text, sort_ascending=(condition.sort_order == "asc"))
            df.to_excel(output_path, index=False)
            return output_path

        raise RuntimeError(f"엑셀 다운로드 응답 형식을 해석할 수 없습니다: {content_type}")

    def debug_request_profile(self) -> dict[str, Any]:
        return {
            "base_page": self.BASE_PAGE,
            "search_endpoint": f"{self.BASE_API}/searchRisaInfoList.do",
            "station_endpoint": f"{self.BASE_API}/getRisaStationCode.do",
            "text_endpoint": f"{self.BASE_API}/risaInfoTextDownload.do",
            "excel_note": "엑셀 버튼은 별도 파일 API 대신 searchRisaInfoList.do 재조회 후 클라이언트에서 xlsx 생성",
            "method": "POST(application/x-www-form-urlencoded)",
            "cookies": self.session.cookies.get_dict(),
        }


def _make_condition(
    area: str,
    station_name: str | None,
    start_date: str,
    end_date: str,
    start_time: str = "00:00",
    end_time: str = "23:30",
    sort_field: str = "station",
    sort_order: str = "asc",
    use_browser_fallback: bool = True,
    page: int = 1,
    page_size: int = 50,
) -> SearchCondition:
    return SearchCondition(
        area=area,  # type: ignore[arg-type]
        station_name=station_name,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        sort_field=sort_field,  # type: ignore[arg-type]
        sort_order=sort_order,  # type: ignore[arg-type]
        use_browser_fallback=use_browser_fallback,
        page=page,
        page_size=page_size,
    )


def search_buoy_observation(
    area: str,
    station_name: str | None,
    start_date: str,
    end_date: str,
    start_time: str = "00:00",
    end_time: str = "23:30",
    sort_field: str = "station",
    sort_order: str = "asc",
    use_browser_fallback: bool = True,
    page: int = 1,
    page_size: int = 50,
) -> pd.DataFrame:
    client = NifsRealtimeClient()
    condition = _make_condition(
        area=area,
        station_name=station_name,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        sort_field=sort_field,
        sort_order=sort_order,
        use_browser_fallback=use_browser_fallback,
        page=page,
        page_size=page_size,
    )
    return client.search(condition)


def download_buoy_observation_text(
    area: str,
    station_name: str | None,
    start_date: str,
    end_date: str,
    output: str | Path | None = None,
    start_time: str = "00:00",
    end_time: str = "23:30",
    sort_field: str = "station",
    sort_order: str = "asc",
    use_browser_fallback: bool = True,
    page: int = 1,
    page_size: int = 50,
) -> Path:
    client = NifsRealtimeClient()
    condition = _make_condition(
        area=area,
        station_name=station_name,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        sort_field=sort_field,
        sort_order=sort_order,
        use_browser_fallback=use_browser_fallback,
        page=page,
        page_size=page_size,
    )
    return client.download_text(condition, output_path=output)


def download_buoy_observation_excel(
    area: str,
    station_name: str | None,
    start_date: str,
    end_date: str,
    output: str | Path | None = None,
    start_time: str = "00:00",
    end_time: str = "23:30",
    sort_field: str = "station",
    sort_order: str = "asc",
    use_browser_fallback: bool = True,
    page: int = 1,
    page_size: int = 50,
) -> Path:
    client = NifsRealtimeClient()
    condition = _make_condition(
        area=area,
        station_name=station_name,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        sort_field=sort_field,
        sort_order=sort_order,
        use_browser_fallback=use_browser_fallback,
        page=page,
        page_size=page_size,
    )
    try:
        return client.download_excel(condition, output_path=output)
    except Exception:
        if not use_browser_fallback:
            raise
        LOGGER.warning("requests 엑셀 저장 실패, 브라우저 재조회 후 로컬 엑셀 생성")
        df = client.search_playwright(condition)
        if output is None:
            output = f"buoy_obs_{safe_filename(station_name or 'all')}_{now_kst_str()}.xlsx"
        out = Path(output)
        ensure_parent_dir(out)
        df.to_excel(out, index=False)
        return out


def crawl_all_buoy_observations(
    start_date: str,
    end_date: str,
    start_time: str = "00:00",
    end_time: str = "23:30",
    sort_field: str = "station",
    sort_order: str = "asc",
    page_size: int = 200,
    request_interval_sec: float = 0.3,
    use_browser_fallback: bool = False,
) -> pd.DataFrame:
    """전체 해역/관측소를 순회해 관측 데이터를 하나의 DataFrame으로 수집한다."""
    client = NifsRealtimeClient()
    all_frames: list[pd.DataFrame] = []

    for area in ALL_AREAS:
        area_code = map_area(area)
        stations = client.get_station_options(area_code)
        LOGGER.info("해역=%s 관측소수=%s", area, len(stations))

        for idx, station in enumerate(stations, start=1):
            station_name = station.get("obsvtrNm")
            station_code = station.get("obsvtrCd")
            if not station_name:
                continue

            condition = _make_condition(
                area=area,
                station_name=station_name,
                start_date=start_date,
                end_date=end_date,
                start_time=start_time,
                end_time=end_time,
                sort_field=sort_field,
                sort_order=sort_order,
                use_browser_fallback=use_browser_fallback,
                page=1,
                page_size=page_size,
            )
            LOGGER.info("[%s/%s] %s %s 수집 중", idx, len(stations), area, station_name)
            try:
                df = client.search_all_pages(condition)
            except Exception as exc:
                LOGGER.warning("관측소 수집 실패 area=%s station=%s err=%s", area, station_name, exc)
                continue

            if not df.empty:
                df = df.copy()
                df["area_name"] = area
                df["station_code"] = station_code
                all_frames.append(df)

            if request_interval_sec > 0:
                time.sleep(request_interval_sec)

    if not all_frames:
        return normalize_dataframe(pd.DataFrame())

    merged = pd.concat(all_frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["area_name", "station_code", "observed_at"], keep="first")
    merged = merged.sort_values(["area_name", "station_name", "observed_at"], ascending=True, na_position="last")
    return merged.reset_index(drop=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df_sample = search_buoy_observation(
        area="남해",
        station_name="강진 마량(fgmk6)",
        start_date="2026-03-30",
        end_date="2026-03-30",
    )
    print(df_sample.head().to_string(index=False))
    print(json.dumps(NifsRealtimeClient().debug_request_profile(), ensure_ascii=False, indent=2))
