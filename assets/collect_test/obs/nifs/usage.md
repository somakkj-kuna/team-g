# NIFS buoy 관측 수집 사용법

## 개요
- 날짜 입력 시 NIFS 관측 시스템에서 해역/관측소 데이터를 수집해 월별 buoy CSV로 저장합니다.
- 수집기는 `libs/nifs_collect.py`에 분리되어 있고, 운영 실행은 `collect_nifs_obs.sh`를 사용합니다.

## 실행
```bash
collect_nifs_obs.sh
collect_nifs_obs.sh YYYYMMDD
collect_nifs_obs.sh YYYYMMDD YYYYMMDD
```

### 예시
```bash
collect_nifs_obs.sh    # 어제 날짜 기준 모든 해역 모든 관측소 수집됨
collect_nifs_obs.sh 20260330 --show-sample
collect_nifs_obs.sh 20260330 --areas 남해 --station-codes fgmk6,fgsl6
collect_nifs_obs.sh 20260330 20260402 --limit 3
```

## 출력 경로
- 월별 CSV: `/data/DATA/OBS/raw/nifs/buoy/{yyyy}/buoy_{yyyymm}.csv`

## 저장 규칙
- 출력 경로와 파일명은 `/home/collect/collector/collect/obs/nifs/config/nifs_config.toml` 의 `[storage.monthly]` 설정을 따릅니다.
- 저장 컬럼 순서는 `/home/collect/collector/collect/obs/nifs/config/nifs_config.toml` 의 `[output].fields` 를 따릅니다.
- 동일한 `area_name + station_code + observed_at` 키가 있으면 최신 수집 결과로 덮어씁니다.
- 날짜별로 수집한 자료를 해당 월 파일에 누적 저장합니다.
- 결측값은 `-999`로 저장합니다.

## 저장 컬럼
- `area_name`
- `station_code`
- `station_name`
- `observed_at`
- `surface_temp_c`
- `surface_depth_m`
- `middle_temp_c`
- `middle_depth_m`
- `bottom_temp_c`
- `bottom_depth_m`

## 옵션 요약
- `--areas`: 대상 해역 목록(예: `동해,남해`)
- `--station-codes`: 관측소 코드 필터(예: `fgmk6,fgsl6`)
- `--limit`: 해역별 앞 N개 관측소만 테스트 수집
- `--show-sample`: 저장 후 샘플 5행 출력
