# KHOA 조위(Recent) 수집 사용법

## 개요
- 날짜 입력 시 KHOA API에서 관측자료를 수신해 `tidal`, `buoy`, `hf` 형식으로 저장합니다.
- `tidal`, `buoy`는 월별 CSV, `hf`는 설정 파일 기준 경로로 저장됩니다.

## 실행
```bash
collect_khoa_obs.sh [tidal|buoy|hf]
collect_khoa_obs.sh [tidal|buoy|hf] YYYYMMDD
collect_khoa_obs.sh [tidal|buoy|hf] YYYYMMDD YYYYMMDD
```

### 예시
```bash
collect_khoa_obs.sh tidal                : tidal mode (default date is yesterday)
collect_khoa_obs.sh buoy                 : buoy mode (default date is yesterday)
collect_khoa_obs.sh hf                   : hf mode (default date is yesterday)
collect_khoa_obs.sh 20260315
collect_khoa_obs.sh tidal 20260315
collect_khoa_obs.sh buoy 20260315
collect_khoa_obs.sh hf 20260315
collect_khoa_obs.sh tidal 20260301 20260315
collect_khoa_obs.sh buoy 20260301 20260315
collect_khoa_obs.sh hf 20260301 20260315
```

## 옵션
- `--limit N` : 앞에서 N개 관측소만 수집 (테스트용)
- `--obs-codes CODE1,CODE2` : 특정 관측소만 수집
- `--show-sample` : 병합 후 샘플 행 출력

### 옵션 예시
```bash
collect_khoa_obs.sh tidal 20260315 --limit 3 --show-sample
collect_khoa_obs.sh buoy 20260315 --obs-codes TW_0089,KG_0021
collect_khoa_obs.sh hf 20260315 --obs-codes HF_0039,HF_0040
```

## 출력 경로
- tidal 월별 CSV: `/data/DATA/OBS/khoa/tidal/{yyyy}/tidal_{yyyymm}.csv`
- buoy 월별 CSV: `/data/DATA/OBS/khoa/buoy/{yyyy}/buoy_{yyyymm}.csv`
- hf CSV: `obs/khoa/config/khoa_config.toml`의 `[hf.storage.daily]` 설정값 사용
- tidal 연간 CSV: `/data/DATA/OBS/khoa/merge/tidal/{yyyy}/merge_tidal_{yyyy}.csv`
- buoy 연간 CSV: `/data/DATA/OBS/khoa/merge/buoy/{yyyy}/merge_buoy_{yyyy}.csv`

## 연간 병합
```bash
python obs/khoa/merge/merge_tidal_year.py --year 2026
python obs/khoa/merge/merge_buoy_year.py --year 2026
```

### 스크립트 실행
```bash
collect_khoa_merge.sh
collect_khoa_merge.sh YYYY
collect_khoa_merge.sh YYYY YYYY
collect_khoa_merge.sh [tidal|buoy]
collect_khoa_merge.sh [tidal|buoy] YYYY
collect_khoa_merge.sh [tidal|buoy] YYYY YYYY
```

### 스크립트 예시
```bash
collect_khoa_merge.sh                 : tidal + buoy, default year is yesterday's year
collect_khoa_merge.sh 2026            : tidal + buoy, target year 2026
collect_khoa_merge.sh 2020 2025       : tidal + buoy, every year from 2020 to 2025
collect_khoa_merge.sh tidal           : tidal only, default year is yesterday's year
collect_khoa_merge.sh tidal 2026      : tidal only, target year 2026
collect_khoa_merge.sh tidal 2020 2025 : tidal only, every year from 2020 to 2025
collect_khoa_merge.sh buoy 2026       : buoy only, target year 2026
```

## 설정 파일
- 공통 설정: `obs/khoa/config/khoa_config.toml`

## HF 월파일 일분할
```bash
python3 obs/khoa/split_khoa_hf_monthly_to_daily.py
python3 obs/khoa/split_khoa_hf_monthly_to_daily.py --year 2019
python3 obs/khoa/split_khoa_hf_monthly_to_daily.py --year 2020 --overwrite
```

- 기본 경로는 `/data/DATA/OBS/raw/khoa/hf`입니다.
- 월별 `hf_YYYYMM.csv`를 읽어 일별 `hf_YYYYMMDD.csv`로 저장합니다.
- 이미 있는 일파일은 기본적으로 건너뜁니다. 덮어쓰려면 `--overwrite`를 사용합니다.

## 저장 규칙
- `tidal`, `buoy`는 동일한 `record_time + obs_post_id`가 존재하면 최신 수신값으로 갱신합니다.
- `hf`는 동일한 `record_time + obs_post_id + obs_lat + obs_lon`가 존재하면 최신 수신값으로 갱신합니다.
- 새 수신값이 결측이면 기존 정상값을 유지합니다.
- raw,merge 데이터 결측값은 `-999`로 저장합니다.
