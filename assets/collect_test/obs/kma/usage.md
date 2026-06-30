# KMA 해상관측 수집 사용법

## 개요
- 날짜 입력 시 KMA API에서 관측자료를 수신하고 월별 CSV로 저장합니다.
- 기본 동작은 API 응답을 관측소 CSV로 자르지 않고 그대로 저장합니다.
- 월별 파일은 `buoy` 폴더 아래에 생성됩니다.

## 실행
```bash
collect_kma_obs.sh
collect_kma_obs.sh YYYYMMDD
collect_kma_obs.sh YYYYMMDD YYYYMMDD
```

### 예시
```bash
collect_kma_obs.sh                : buoy mode (default date is yesterday)
collect_kma_obs.sh 20260315
collect_kma_obs.sh 20260315 --show-sample --limit 5
collect_kma_obs.sh 20260315 --obs-codes 22101,22102
collect_kma_obs.sh 20260301 20260315
```

## 출력 경로
- 월별 CSV: `/data/DATA/OBS/kma/buoy/{yyyy}/buoy_{yyyymm}.csv`
- 연간 CSV: `/data/DATA/OBS/kma/merge/{yyyy}/merge_kma_{yyyy}.csv`

## 연간 병합
```bash
python obs/kma/merge/merge_kma_year.py --year 2026
```

## 실행
```bash
collect_kma_merge.sh
collect_kma_merge.sh YYYY
collect_kma_merge.sh YYYY YYYY
```

### 예시
```bash
collect_kma_merge.sh            : default year is yesterday's year
collect_kma_merge.sh 2026       : target year 2026
collect_kma_merge.sh 2020 2025  : every year from 2020 to 2025
```

## 저장 규칙
- 기본 수집은 전체 관측소를 저장하고, `--obs-codes` 또는 `config.kma_config.toml` 의 `stations.obs_codes` 를 설정했을 때만 해당 관측소로 제한합니다.
- 동일한 `record_time + obs_post_id`가 존재하면 최신 수신값으로 갱신합니다.
- 새 수신값이 결측이면 기존 정상값을 유지합니다.
- raw,merge 데이터 결측값은 `-999`로 저장합니다.

## obs type
- B:BUOY
- C:파고BUOY 
- D:표류BUOY 
- L:등표
- N:조위관측소 
- F:연안방재 
- G:파랑계 
- J:기상1호
