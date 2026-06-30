# NIFS CTD 병합 사용법

## 개요
- `collect_nifs_ctd.sh` 가 KODC 정선 관측자료를 먼저 연도별로 수집한 뒤, 바로 연간 병합 파일 `merge_ctd_YYYY.csv`를 만듭니다.
- 실제 처리 코드는 원본 수집용 `libs/kodc_web_crawl/line_data_client.py` 와 병합용 `libs/nifs_tools.py`를 사용합니다.
- 기본 원본 경로와 저장 경로는 `config/config.toml`에서 읽습니다.

## 실행
```bash
collect_nifs_ctd.sh
collect_nifs_ctd.sh YYYY
collect_nifs_ctd.sh START_YYYY END_YYYY
collect_nifs_ctd.sh YYYY --crawl-only
collect_nifs_ctd.sh YYYY --merge-only
```

## 예시
```bash
collect_nifs_ctd.sh
collect_nifs_ctd.sh 2025
collect_nifs_ctd.sh 2017 2025
collect_nifs_ctd.sh 2025 --output-dir /tmp/nifs_ctd_test
collect_nifs_ctd.sh 2024 2025 --config /home/collect/collector/collect/obs/nifs/ctd/config/config.toml
collect_nifs_ctd.sh 2025 --crawl-only
collect_nifs_ctd.sh 2025 --merge-only
collect_nifs_ctd.sh 2025 --output /tmp/ctd_2025.csv --output-dir /tmp/nifs_ctd_test
```

## 실행 규칙
- 연도를 생략하면 현재 날짜 기준 전년도에 대해 `크롤링 -> merge`를 차례로 실행합니다.
- 연도를 1개 넣으면 해당 연도만 처리합니다.
- 연도를 2개 넣으면 시작 연도부터 종료 연도까지 순차 처리합니다.
- 각 연도는 `config.toml`의 `paths.source_glob` 템플릿을 사용해 `{yyyy}`에 해당하는 연도 파일로 해석됩니다.
- 예를 들어 현재 날짜가 2026-05-07 이면 `bash collect_nifs_ctd.sh` 는 `2025` 자료를 먼저 수집하고, 이어서 merge 파일을 생성합니다.

## KODC 원본 수집
- `collect_nifs_ctd.sh YYYY` 는 `https://www.nifs.go.kr/kodc/observe/line/data` 기준으로 해역/정선/정점/수심을 모두 `전체`로 두고 연도 범위만 조회합니다.
- 예를 들어 `collect_nifs_ctd.sh 2026` 은 `2026-01-01` 부터 `2026-12-31` 까지 조회해서 `/data/DATA/OBS/nifs/ctd/2026/ctd_2026.csv` 를 만든 뒤, 이어서 merge 결과를 저장합니다.
- 실제 저장 경로는 `config.toml` 의 `paths.source_glob` 를 사용합니다.
- 원본 수집만 따로 필요하면 `collect_nifs_ctd_source.sh` 를 계속 쓸 수 있고, 내부적으로 `collect_nifs_ctd.sh --crawl-only` 를 호출합니다.

## 기본 경로
- 설정 파일: `/home/collect/collector/collect/obs/nifs/ctd/config/config.toml`
- 원본 파일 템플릿: `/data/DATA/OBS/nifs/ctd/{yyyy}/ctd_{yyyy}.csv`
- 기본 저장 경로: `/data/DATA/OBS/nifs/merge/ctd/{yyyy}/merge_ctd_{yyyy}.csv`

## 저장 컬럼
- 출력 컬럼 순서:
  `record_time, line, point, obs_lat, obs_lon, depth, temp, sal, DO, PO4, NO2, NO3, SIL, pH, Transp, air_pres, sea_name`

## 저장 규칙
- 정렬 순서: `record_time`, `line`, `point`, `depth` 오름차순
- 중복 제거 키: `line + point + record_time + depth`
- 결측값은 `-999`로 저장합니다.
- `sea_name`은 `EAST`, `WEST`, `SOUTH`로 저장합니다.
- 기존 산출물에 예전 컬럼명(`time`, `transect`, `station` 등)이 있어도 현재 컬럼명으로 맞춰 병합합니다.

## 원본 파일 메모
- 2017~2023 파일은 UTF-8이며 BOM이 없습니다.
- 2025 파일은 UTF-8 BOM이며 파일 앞부분에 안내문 6줄이 포함되어 있습니다.
- 스크립트는 위 차이를 자동 처리하도록 맞춰져 있습니다.
