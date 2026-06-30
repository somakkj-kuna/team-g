# recollect 사용법 — OBS 미수집 기록 + 지연 재수집

대상: KHOA tidal · KHOA buoy · KMA buoy · NIFS buoy
정책: 미수집(행 부재=제공 지연) 기록 → 다음날 수집 때 재수집(하루 1회) → 7일 미해결 시 미관측 확정.
**모든 기관·데이터셋이 하나의 대장으로 종합**됨(provider/dataset 컬럼으로 구분).

## 진입점
```
/home/collect/collect_test/recollect/run_recollect.sh
```

## 1. 매일 1패스 (핵심 — detect→backfill→sweep)
```bash
run_recollect.sh
```
- detect : 어제까지 빠진 (정점·날짜)를 대장에 pending 기록
- backfill: 대장 pending(7일 이내)을 해당 날짜로 재수집 → 채워지면 resolved
- sweep  : 7일 경과·미해결 → unobserved.csv 이관 + 대장에서 제거(미관측 확정)
→ crontab에 매일 수집 직후 1줄 등록하면 자동화.

## 2. 단계별 수동
```bash
run_recollect.sh detect --date 20260628 --lookback 7   # 탐지만
run_recollect.sh detect --lookback 7 --dry-run         # 미리보기(대장 무변경)
run_recollect.sh backfill                              # pending 재수집
run_recollect.sh backfill --limit 3                    # 정점 3개만(가벼운 테스트)
run_recollect.sh sweep                                 # 7일 경과분 정리
```

## 3. 강제 재수집 (운영자 on-demand)
```bash
run_recollect.sh backfill --force --provider khoa --dataset tidal --date 20260627
```
- provider: khoa | kma | nifs
- dataset : tidal | buoy

## 4. 대장 확인 (전 기관 종합)
```bash
column -s, -t /home/collect/collect_test/recollect/state/ledger.csv      # 진행중/해결
column -s, -t /home/collect/collect_test/recollect/state/unobserved.csv  # 미관측 확정
```
컬럼: provider, dataset, station, date, expected_n, got_n, missing_slots,
      first_seen, last_check, attempts, status(pending|resolved), reason
기관별 보기 예:  grep ',khoa,' ... / awk -F, '$1=="kma"' ...

## 5. 수집기 직접 백필(재수집 드라이버 없이)
```bash
obs/khoa/collect_khoa_obs.sh tidal 20260620 20260629
obs/khoa/collect_khoa_obs.sh buoy  20260620 20260629
obs/kma/collect_kma_obs.sh         20260620 20260629
obs/nifs/collect_nifs_obs.sh       20260620 20260629
```
- 날짜는 START END (범위). --limit N = 정점 수 제한(테스트), 생략 시 전 정점.

## 설정 (config/recollect.toml)
- retention_days=7, max_attempts=7, completeness_threshold=0.9
- 데이터셋별 cadence_min(khoa 10분=144/일, kma·nifs 30분=48/일), 수집기 매핑.

## 운영 반영 시
1. 검증 후 config output_root를 운영 경로로 원복(또는 운영 collector/에 recollect/ 이식)
2. crontab에 run_recollect.sh 1줄 등록(매일 수집 직후)

## 격리 주의
현재 수집 출력은 샌드박스(/home/collect/collect_test/out/)로 격리됨 → 운영자료 무영향.
