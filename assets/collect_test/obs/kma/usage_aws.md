# KMA AWS 시간별 지상관측 수집기

## 파일 구성

| 파일 | 설명 |
|---|---|
| `collect_kma_aws.sh` | 셸 진입점 (dataenv 활성화 후 Python 호출) |
| `libs/kma_aws_collect.py` | 수집 본체 |
| `config/aws_config.toml` | API키·경로·필드 설정 |
| `config/aws_station_info_KMA.csv` | KMA AWS 지점 메타 (745개) |

## API 정보

- 엔드포인트: https://apihub.kma.go.kr/api/typ01/url/awsh.php
- 인코딩: EUC-KR
- 요청 간격: 1시간 (interval_minutes = 60)
- 결측값: -99 / -99.0 -> -999 으로 저장

## 저장 경로

    /data/DATA/OBS/raw/kma/aws/{yyyy}/aws_{yyyymm}.csv

월별 누적 (기존 행 유지, (stn_id, record_time) 키로 중복 제거)

## 수집 필드

| 컬럼 | 설명 | 단위 |
|---|---|---|
| record_time | 관측시각 YYYY-MM-DD HH:MM:SS | - |
| stn_id | 지점번호 | - |
| air_temp | 기온 | 도C |
| wind_dir | 풍향 | 도 |
| wind_speed | 풍속 | m/s |
| rain_day | 일강수량 | mm |
| rain_1h | 1시간 강수량 | mm |
| humidity | 상대습도 | % |
| air_pres_stn | 현지기압 | hPa |
| air_pres_sea | 해면기압 | hPa |

## 실행 방법

    # 특정 날짜 전체 지점 수집
    bash collect_kma_aws.sh 20260619

    # 날짜 범위 수집
    bash collect_kma_aws.sh 20260601 20260619

    # 특정 지점만 수집
    /home/collect/appl/miniconda3/envs/dataenv/bin/python libs/kma_aws_collect.py \
        --date 20260619 --stn-ids 42,43,44

    # 테스트 (지점 5개 제한)
    /home/collect/appl/miniconda3/envs/dataenv/bin/python libs/kma_aws_collect.py \
        --date 20260619 --limit 5 --show-sample

## cron 등록 예시 (매일 01:30, 전날 자료)

    30 1 * * * flock -n /home/collect/collector/run/kma_aws.lock \
      /home/collect/collector/bin/runjob kma_aws /home/collect/collector/collect/obs/kma \
      /bin/bash /home/collect/collector/collect/obs/kma/collect_kma_aws.sh

## 지점 메타 갱신

aws_station_info_KMA.csv 는 stn_inf.php API 로 생성됨.
갱신 필요 시 usage_aws.md 내 메타 갱신 예시를 참고해 별도 실행.
