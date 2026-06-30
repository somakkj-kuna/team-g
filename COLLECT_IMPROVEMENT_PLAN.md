# 수집·재수집 개선 계획 — collect_test 샌드박스

## 대상
KHOA tidal · KHOA buoy · KMA buoy · NIFS buoy (3 buoy + 1 tidal).
입력은 각 제공처 **외부 API 직접 호출**(로컬 입력경로 없음).

## 핵심 정책 (확정)
- **보관: 미수집 대장은 최근 7일만 추적.**
- **재수집 주기: 수집이 1일 1회 → 빠진 날은 다음날 수집 사이클에서 재수집(하루 1회, 매일 누적).**
- 한 항목은 최초 탐지 후 **최대 7일(최대 7회) 재시도**, 7일째도 실패하면 **대장에서 제거하고 미관측(unobserved)으로 확정**.

## 0. 경로 격리 (가장 먼저 — 운영자료 보호)
복사본 config의 `output_root`가 아직 **운영 경로**를 가리킴 → 테스트 전 반드시 테스트 경로로 변경.
수집기가 같은 달 월별 CSV를 읽어 누적하는 구조라, 격리 없이 돌리면 운영자료를 덮어쓴다.

| 데이터셋 | config 파일 | 현재(운영) | 변경(테스트) |
|---|---|---|---|
| KHOA tidal | obs/khoa/config/khoa_config.toml | /data/DATA/OBS/raw/khoa/tidal | /home/collect/collect_test/out/raw/khoa/tidal |
| KHOA buoy  | obs/khoa/config/khoa_config.toml | /data/DATA/OBS/raw/khoa/buoy  | /home/collect/collect_test/out/raw/khoa/buoy  |
| KMA buoy   | obs/kma/config/kma_config.toml   | /data/DATA/OBS/raw/kma/buoy   | /home/collect/collect_test/out/raw/kma/buoy   |
| NIFS buoy  | obs/nifs/config/nifs_config.toml | /data/DATA/OBS/raw/nifs/buoy  | /home/collect/collect_test/out/raw/nifs/buoy  |

- 입력: 외부 API 직접 호출이라 입력경로 변경 불필요. 읽기전용 meta 경로(예: nifs.yaml)는 그대로 둠.
- 재수집 대장/상태: `/home/collect/collect_test/recollect/state/` (운영과 완전 분리).
- 검증 후 운영 반영 시 `output_root`만 원복.

## 1. 미수집 탐지 (날짜 + 시간 슬롯)
파일 존재만이 아니라 **하루 안의 시간 슬롯 결손**까지 본다(제공 지연은 부분 수신이 흔함).
- 데이터셋별 기대 관측주기(config·실데이터로 확정)로 하루 기대 타임스탬프 집합 생성.
- 수집 CSV의 (station, time) 대비 **누락 슬롯** 계산 → expected_n / got_n / missing_slots.
- 운영 `monitor/data_check/missing_check/detect_abnormal_values.py` 로직 재사용 + 시간 슬롯 단위 확장.

## 2. 미수집 대장 (recollect/state/ledger.csv) — 최근 7일만 유지
키 = (provider, dataset, station, date).
컬럼: provider, dataset, station, date, expected_n, got_n, missing_slots, first_seen, last_check, attempts, status, reason
- status: pending → resolved(채워짐) → 7일 미해결 시 제거 + 미관측 기록.
- reason: provider_delay
- upsert(멱등): 같은 키 갱신, 신규 append. 부분 수신은 got_n / missing_slots 갱신.
- 미관측 확정분은 recollect/state/unobserved.csv 로 이관 후 대장에서 삭제.

## 3. 재수집 드라이버 (다음날 수집 시 1패스: detect → backfill → sweep)
매일 수집 직후 1회 실행, 아래 3단계 순서:
1. detect : 대상일(어제) 미수집을 대장에 pending 기록.
2. backfill: 대장의 pending(7일 이내)을 각 1회씩 해당 날짜로 수집기 재호출 →
   - KHOA tidal: obs/khoa/collect_khoa_obs.sh tidal {ymd} {ymd}
   - KHOA buoy : obs/khoa/collect_khoa_obs.sh buoy {ymd} {ymd}
   - KMA buoy  : obs/kma/collect_kma_obs.sh {ymd} {ymd}
   - NIFS buoy : obs/nifs/collect_nifs_obs.sh {ymd} {ymd}
   실행 후 재탐지 → 채워지면 resolved, 아니면 attempts++ / last_check 갱신.
3. sweep   : first_seen 기준 7일 경과·미해결 → unobserved로 이관 후 대장에서 제거.
- 순차 실행(제공처 API rate limit 보호), 수집기 내장 retry/sleep 재사용.

## 4. 실행 방식 (자동 + 수동 강제)
- 자동: 기존 일일 수집 직후 recollect 1패스(detect→backfill→sweep). crontab은 검증 후 등록.
- 수동: run_recollect.sh --run --provider khoa --dataset tidal --date 20260628 --force

## 5. 디렉터리 (신규)
```
collect_test/
  obs/{khoa,kma,nifs}/        # 수집기 (여기서 수정)
  recollect/
    run_recollect.sh          # detect→backfill→sweep 1패스 / 수동 옵션
    libs/{detect_missing.py, ledger.py, backfill.py}
    config/recollect.toml     # 데이터셋별 기대주기·매핑·retention=7d·max_attempts=7
    state/{ledger.csv, unobserved.csv}
  out/                        # 격리 테스트 출력 (raw/{khoa,kma,nifs}/...)
```

## 6. 테스트 절차 (10일치)
- 날짜는 START END 인자로 지정(= 10일 범위). --limit N = **정점(관측소) 개수 제한**(날짜 아님), 생략 시 전 정점.
  --show-sample = 수집행 5개 미리보기 출력.
- 1단계(가벼운 점검, 정점 3개 × 10일):
  collect_khoa_obs.sh tidal 20260620 20260629 --limit 3 --show-sample
- 2단계(본 테스트, 전 정점 × 10일):
  collect_khoa_obs.sh tidal 20260620 20260629
  collect_khoa_obs.sh buoy  20260620 20260629
  collect_kma_obs.sh        20260620 20260629
  collect_nifs_obs.sh       20260620 20260629
- 모든 산출물이 out/ 경로에만 생성되는지 확인(운영 경로 무변경).

## 7. 검증 (end-to-end, 격리)
1. config output_root를 out/ 으로 변경.
2. 과거 결손일로 detect → 대장 pending 생성(시간 슬롯 포함).
3. backfill --force → out/raw/.../{yyyymm}.csv 채움 + 대장 resolved.
4. 7일 경과 시나리오 → sweep로 unobserved 이관·대장 제거 확인.
5. 멱등성(재탐지 중복 없음)·운영 무간섭(별도 경로/lock) 확인.

## 8. 결정 필요
- 데이터셋별 기대 관측주기(정시/10분) 확정 — 시간 슬롯 탐지용.
- 테스트 날짜 구간 확정(기본 제안: 20260620~20260629).
- 미관측 확정분 통지/보존 방식(unobserved.csv + 로그; MAILTO 빈 환경).
