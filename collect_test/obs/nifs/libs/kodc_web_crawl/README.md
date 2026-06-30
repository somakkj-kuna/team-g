# nifs_buoy

국립수산과학원 해양수산환경 관측시스템의 **buoy 관측정보 검색 UI 동작**을 기준으로 만든 Python 수집기입니다.  
공식 OpenAPI는 사용하지 않고, 페이지의 실제 form/JS/AJAX 흐름을 재현했습니다.

## 1) 먼저 찾은 요청 구조(분석 요약)

대상 페이지:  
`https://www.nifs.go.kr/risa/risa/risaA/actionRisaInfo.do`

페이지 내부 JS(`fnSearch`, `fnSetObjectEvent`) 및 공통 JS(`lpCom.Ajax`, `lpCom.fileDownAjax`)를 기준으로 확인한 결과:

- 검색 버튼 (`#schBtn`)
  - **POST** `./searchRisaInfoList.do`
  - payload: `#schFrm`의 id 기반 직렬화 값
    - `obsrvnGroupNm`, `obsvtrCd`, `ord`, `ordType`, `obsFrom`, `obsTo`, `obsTimeFrom`, `obsTimeTo`
    - 페이징 사용 시 `selectPage`, `rowCountPage` 추가
  - content-type: `application/x-www-form-urlencoded`
  - response: `application/json`, `{"retList":[...]}`

- 텍스트저장 버튼 (`#textBtn`)
  - **POST** `./risaInfoTextDownload.do`
  - payload: 검색과 동일한 조건
  - response: 첨부 파일(`text/plain`, `content-disposition: attachment`)
  - 서버가 `fileDownload=true` 쿠키를 응답 헤더에 세팅

- 엑셀저장 버튼 (`#excelBtn`)
  - 별도 서버 파일 다운로드 API 호출이 아니라,
  - **POST** `./searchRisaInfoList.do` 재조회(행수 확장) 후
  - 브라우저에서 `xlsx.bundle.js` + `lpCom.downExcel(...)`로 **클라이언트 측 xlsx 생성**
  - 즉, 네트워크 관점에서 엑셀 버튼은 검색 API 재활용

추가 관찰:

- 초기 페이지에서 `SESSION` 쿠키 발급
- `schFrm` 내부 **hidden input/CSRF 토큰 필드는 확인되지 않음**
- 관측소 선택은 별도 코드 조회 API 사용:
  - **POST** `./getRisaStationCode.do`
  - payload: `obsrvnGroupNm`, `useY=T`
  - `obsvtrNm`(표시명)과 `obsvtrCd`(내부코드) 분리

## 2) 프로젝트 구조

```text
nifs_buoy/
  ├─ client.py
  ├─ parser.py
  ├─ models.py
  ├─ utils.py
  ├─ cli.py
  ├─ requirements.txt
  └─ README.md
```

## 3) 설치

```bash
cd nifs_buoy
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 4) 사용 예시

### CLI 검색

```bash
python cli.py search \
  --area 남해 \
  --station "강진 마량(fgmk6)" \
  --start-date 2026-03-30 \
  --end-date 2026-03-30 \
  --page-size 50 \
  --preview-rows 50
```

### CLI 텍스트저장

```bash
python cli.py text \
  --area 남해 \
  --station "강진 마량(fgmk6)" \
  --start-date 2026-03-30 \
  --end-date 2026-03-30 \
  --output out.txt
```

### CLI 엑셀저장

```bash
python cli.py excel \
  --area 남해 \
  --station "강진 마량(fgmk6)" \
  --start-date 2026-03-30 \
  --end-date 2026-03-30 \
  --output out.xlsx
```

### CLI 전체 수집 (모든 해역/모든 관측소)

```bash
python cli.py crawl-all \
  --start-date 2026-03-30 \
  --end-date 2026-03-30 \
  --page-size 200 \
  --request-interval-sec 0.3 \
  --output all_stations_20260330.csv
```

- 한 번 실행으로 `동해/남해/서해`의 모든 관측소를 순회합니다.
- 서버 부하를 줄이기 위해 관측소 간 짧은 대기(`--request-interval-sec`)를 기본 적용합니다.

### Python 함수 사용

```python
from client import (
    search_buoy_observation,
    download_buoy_observation_text,
    download_buoy_observation_excel,
)

df = search_buoy_observation(
    area="남해",
    station_name="강진 마량(fgmk6)",
    start_date="2026-03-30",
    end_date="2026-03-30",
    start_time="00:00",
    end_time="23:30",
    sort_field="station",
    sort_order="asc",
    use_browser_fallback=True,
)
print(df.head())

download_buoy_observation_text(
    area="남해",
    station_name="강진 마량(fgmk6)",
    start_date="2026-03-30",
    end_date="2026-03-30",
    output="out.txt",
)

download_buoy_observation_excel(
    area="남해",
    station_name="강진 마량(fgmk6)",
    start_date="2026-03-30",
    end_date="2026-03-30",
    output="out.xlsx",
)
```

## 5) DataFrame 표준 컬럼

- `station_name`
- `observed_at` (datetime)
- `surface_temp_c`
- `surface_depth_m`
- `middle_temp_c`
- `middle_depth_m`
- `bottom_temp_c`
- `bottom_depth_m`

원본 컬럼명 매핑은 `parser.py`의 `RAW_TO_STD_COLUMN_MAP`에 유지합니다.

## 6) 동작 전략 (requests -> Playwright fallback)

1. requests.Session으로 초기 페이지 접근(쿠키 확보)
2. `getRisaStationCode.do`로 관측소 코드 해석
3. `searchRisaInfoList.do` 재현 요청
4. JSON/HTML 응답을 DataFrame으로 정규화
5. 실패 또는 비정상 빈 결과 시 Playwright fallback:
   - 페이지 접속
   - 해역/관측소/일시/시간/정렬 설정
   - 검색 클릭
   - `searchRisaInfoList.do` 응답을 가로채 DataFrame 생성

## 7) 엑셀 저장 처리 기준

실제 사이트 엑셀 버튼은 서버 바이너리 다운로드가 아니라 브라우저 내 생성 방식입니다.  
본 구현은 다음 순서로 처리합니다.

1. `searchRisaInfoList.do`를 행수 확장으로 재조회
2. JSON이면 pandas로 `xlsx` 저장
3. 만약 서버가 향후 파일/HTML 테이블을 직접 반환하면 해당 형식도 처리

## 8) 한계점

- 사이트 구조(id/name/엔드포인트)가 바뀌면 코드 수정 필요
- 관측소명이 중복/부분일치일 때 첫 매칭을 선택
- 장기간/대량 조회는 서버 정책에 따라 제한될 수 있음
- 텍스트 파일의 열 간격 기반 파싱은 포맷 변경에 민감

## 9) 디버깅 팁

- `--log-level DEBUG`로 payload 확인
- `--no-browser-fallback`로 requests 경로만 강제 점검
- 응답 content-type이 예상과 다르면 사이트 점검 시간/에러 페이지 여부 확인
- Playwright 오류 시 `playwright install chromium` 재실행

## 10) 안전한 사용 권장

- 짧은 간격 반복 호출 대신 단건 조회 중심 사용
- robots.txt/이용약관을 준수하고 과도한 요청을 피하세요.
