# 해양 현장관측 수집–QC–대시보드 파이프라인 — 프로젝트 플랜 (G팀)

> 팀 공유용 계획서. `git pull`로 최신본 받기.
> 3축: **① 수집(+재수집) · ② QC · ③ 라이브 대시보드**.
> (이 플랜은 팀원이 올린 `qcsrc/`·`QC.md`·`qc_webapp/` 실제 구현과 server131 수집 환경을 반영해 갱신됨)

## 1. 배경 / 목표
제공처별 해양 현장관측 자료에 **제공 지연으로 인한 미수집**과 **결측·이상치**가 발생한다. 세 축으로 해결한다.
- ① **수집·재수집** — server131 수집기로 제공처·정점별 수집, **미수집(날짜/시간) 기록 → 일정기간 후 자동 재수집**
- ② **자동 QC** — QC 플래그 생산 → **이상치(BAD)·의심(SUSPECT) 제외(플래깅)** 로 분석용 자료 생산
- ③ **로컬 대시보드** — 수집현황·QC결과를 한눈에(조문원 라이브 가동 중)

### 전체 흐름
```
server131 수집(+미수집 재수집) → 표준 prc CSV → QC 플래그 → BAD·SUSPECT 제외 → 산출물(flag/final) → 대시보드
```

## 2. 수집 · 재수집 (server131)
- 위치: `collect@server131:/home/collect/collector`. crontab이 제공처별 수집기를 매일 실행하고,
  `bin/runjob`이 `monitor/log/<연도>/<job>_<날짜>.log`에 `START/END rc=`까지 자동 로깅한다.
- 제공처(현장관측): **KHOA**(tidal·buoy·hf) · **KMA**(buoy) · **NIFS**(buoy).
  수집기는 **날짜 인자 백필 지원**(예: `collect_khoa_obs.sh tidal START END`, 기본=어제 / kma·nifs도 `START END` 동일).
- 저장: 원시 `/data/DATA/OBS/raw/{khoa,kma,nifs}/...` → 표준화 `/data/DATA/OBS/{khoa,kma,nifs}/...`(대시보드·QC 입력).

### 2-1. 미수집 기록 + 지연 재수집 자동화 (신설)
제공 지연 시 그날 수집이 비거나 일부만 들어온다 → **기록해 두고, 자료가 올라오면 일정기간 동안 다시 수집**한다.
- **탐지**: `monitor/data_check/missing_check`(`detect_abnormal_values.py`)로 (제공처, 날짜)별 행 누락 탐지(재사용).
- **미수집 대장(ledger)**: `(target, date/time, first_seen, attempts, status[pending|resolved|escalated], reason=provider_delay)` 영속 기록.
- **재수집 드라이버**: 대장의 `pending`을 **재시도 윈도 동안 주기적으로 수집기 백필 재호출** →
  채워지면 `resolved`, 한도 초과 시 `escalated`. crontab **자동 재시도** + 운영자 **수동 강제**(`--target --date --force`) 지원.
- 신규 위치(예정): `monitor/data_check/recollect/`(run 스크립트 · libs · config · `state/ledger` · usage).

## 3. QC
### 3-1. 문헌 근거 / 플래그 체계 (개선중)
- **주 표준 — QARTOD**(U.S. IOOS/NOAA). 보조 — Copernicus Marine In Situ TAC RTQC · 국내 KHOA·NIFS · 이어도 ORS.

| 코드 | 의미 | severity | 비고 |
|------|------|----------|------|
| `1` | GOOD | 4위(최저) | 정상 |
| `2` | SUSPECT | 3위 | 의심 |
| `3` | BAD | 2위 | 불량(QARTOD Fail(4) 통합) |
| `9` | MISSING | 1위(최고) | 결측(NaN) |
- 병합 원칙: `flag_final = max(severity)`.
- QC 알고리즘(qcsrc, 개선중) 9종: zero · range · stuck · roc · spike · stat · consistency · cross · edge.

### 3-2. 처리정책 — 제외(플래깅)
- QC 플래그로 **BAD(3)·SUSPECT(2)를 분석에서 제외**(플래깅)한다.
- 산출물: `flag` CSV(전체 플래그) + `final` CSV(제외 후 분석용 자료).
- > 보간(결측·이상치 값 채움)은 이번 범위에서 제외(시간 제약).

### 참고 링크
- QARTOD: https://ioos.noaa.gov/project/qartod/
- 수온·염분 RTQC 매뉴얼: https://cdn.ioos.noaa.gov/media/2020/03/QARTOD_TS_Manual_Update2_200324_final.pdf
- QC 플래그 매뉴얼: https://repository.library.noaa.gov/view/noaa/24982
- Copernicus In Situ TAC QC: https://archimer.ifremer.fr/doc/00950/106219/119273.pdf
- 이어도 ORS 국제 QC 평가: https://e-opr.org/articles/xml/zqB1/

## 4. 대시보드 (라이브 — 현재 내용 그대로)
- 조문원 `qc_webapp` 확장본, **라이브 가동 중**(http://27.112.246.50:8501). 커스텀 HTML/JS + Plotly(Streamlit 아님).
- 구성:
  - ① **수집현황** — 소스 매트릭스(KHOA·KMA·NIFS), 요약카드, 24칸 적시성 바
  - ② **QC결과** — 변수→관측소→시계열 드릴다운, 플래그(1/2/3/9) 하이라이트 + 범례
  - ③ **요약** — 보존(good+suspect)·제거율 등 stat 카드
  - ＋ **AI 분석 패널**(`/api/chat`, LLM) ＋ **HWPX 한글 보고서**(`/api/report`, `geosr-hwpx` 스킬 재사용)
- 최신본은 추후 repo 반영 예정.

## 5. 기술 스택
Python 3 · pandas/numpy · QARTOD 근거(자체 구현) · Plotly · 로컬 http 서버 · 설정 TOML · server131 crontab/runjob.
- 입력: **CSV**(전처리 prc CSV) · 출력: flag/final CSV
- 대시보드: **qc_webapp 확장**

## 6. 데이터
- **위치**: 외부 저장서버(`/data/DATA/OBS/...`). 저장소/로컬에는 원자료 없음.
- **입력 경로**: `/data/DATA/OBS/prc/{tidal,buoy}/{yyyy}/{yyyymmdd}.csv`
- **데이터셋**: tidal(조위) · buoy(부이) / agency(khoa·kma·nifs) · station_id
- **합성 데이터**: QC 성능평가(benchmark, precision/recall/F1)에 한해 이상치 주입 사용.

## 7. 마일스톤
| MS | 목표 | 상태 |
|----|------|------|
| **M0** 스키마·표준 | var_id·정점·제공처·결측 sentinel·시간형식 정의 | QC.md 8절 |
| **M1** 수집현황 | 제공처·정점별 수신시각·지연·결측률·가용률 집계 | 진행 |
| **M2** 미수집 재수집 | 미수집 대장 기록 + 지연 자동 재수집 파이프라인 | **신설(설계 완료)** |
| **M3** QC 엔진 | 플래그(1/2/3/9) 생산, 9종 검사 | qcsrc 구현·개선중 |
| **M4** 처리정책 | BAD·SUSPECT 제외(플래깅), final CSV 생산 | 진행 |
| **M5** 집계·저장 | 재현가능 산출물(flag/final) 저장 | 진행 |
| **M6** 대시보드 | 라이브 가동(수집현황·QC·요약·AI·HWPX) | 가동 중 |
| **M7** 검증·문서·효과 | end-to-end 재현, benchmark 효과측정, README | 진행 |

## 8. 미해결 / 확인 포인트
- 재수집 재시도 윈도/최대횟수(제공처별 지연 특성), escalated 알림 방식(`MAILTO` 빈 환경 → 로그/대장 표시).
- consistency·cross 등 다변수 검사의 변수별 활성 매트릭스(QC.md 7절).
- 대시보드에 미수집·재수집 현황(대장) 연동 여부.

## 9. 검증 (end-to-end)
1. 의존성 설치 + `pytest qcsrc/tests` 통과.
2. server131 수집 → 미수집 탐지 → 대장 기록 → 재수집 백필 → 채움 확인.
3. QC 실행 → 플래그(1/2/3/9) 부여 → **BAD·SUSPECT 제외** → final CSV 생산.
4. benchmark로 주입 이상치가 BAD(3)로 잡히는지(precision/recall/F1).
5. 라이브 대시보드에서 수집현황·QC 시계열·요약 확인.
