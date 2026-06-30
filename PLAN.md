# 해양 현장관측 수집현황·QC·로컬 대시보드 — 프로젝트 플랜 (G팀)

> 이 문서는 팀 공유용 계획서입니다. `git pull`로 최신본을 받으세요. 각자 작업은 **본인 이름 파일/모듈**에서만 진행해 충돌을 방지합니다.

## 1. 배경 / 목표
제공처별 해양 현장관측 자료에 **센서이상 점검 등으로 인한 수집 지연**과 **결측·이상치**가 발생한다.
- ① **수집 현황 파악** — 제공처·정점별 지연/결측 집계
- ② **문헌 기반 QC** — 이상치 식별·플래깅 (공식 표준 근거)
- ③ **로컬 HTTP 대시보드** — 현황을 한눈에 확인

## 2. QC 문헌 근거 (확정)
- **주 표준 — QARTOD** (U.S. IOOS/NOAA): 실시간 in-situ QC 테스트 + 플래그 체계
  - 플래그: **1 Good / 2 Not evaluated / 3 Suspect / 4 Fail / 9 Missing**
  - 변수별 매뉴얼(수온·염분 / 유속 / 파고 / 조위) 존재
- **보조** — Copernicus Marine In Situ TAC RTQC(Ifremer/Coriolis), 국내 **KHOA·NIFS** 통합 QC, 이어도 ORS 이상치검출 논문(e-opr.org)
- **구현 재사용** — `ioos_qc`(IOOS 공식 파이썬 패키지, QARTOD 테스트 구현) 또는 동등 구현

### 참고 링크
- QARTOD 프로젝트: https://ioos.noaa.gov/project/qartod/
- 수온·염분 RTQC 매뉴얼: https://cdn.ioos.noaa.gov/media/2020/03/QARTOD_TS_Manual_Update2_200324_final.pdf
- QC 플래그 매뉴얼: https://repository.library.noaa.gov/view/noaa/24982
- Copernicus In Situ TAC QC 절차: https://archimer.ifremer.fr/doc/00950/106219/119273.pdf
- 이어도 ORS 국제 QC 평가 논문: https://e-opr.org/articles/xml/zqB1/

## 3. 현황 (팀원 선행 작업 반영)
- 저장소에 이미 **`qc_webapp/`** 가 올라와 있음: 자체 **웹앱**(`app.py` + `static/`의 HTML·JS·Plotly), 조위관측소 QC 대상.
  - 구성: `app.py · data.py · qc.py · report.py · variables.py · run.sh · static/*`
- → **M5(대시보드)는 Streamlit 신규 제작 대신 이 `qc_webapp/` 확장 우선 검토** (중복 방지). M2 QC 로직도 `qc_webapp/qc.py`와 통합/정렬.
- 점검 필요: `qc_webapp/qc.py`가 QARTOD 테스트·플래그 체계를 따르는지 → 부족하면 보강.

## 4. 마일스톤
| MS | 목표 | 산출물 | 문헌 근거 |
|----|------|--------|-----------|
| **M0** 스키마·샘플 | 변수/정점/제공처/기대주기 정의, 합성 샘플 생성 | 스키마, 샘플셋 | — |
| **M1** 수집현황 | 정점·제공처·변수별 **최신수신시각·지연·결측률·가용률** 집계 | 수집현황표 | QARTOD Timing/Gap |
| **M2** QC 엔진(핵심) | **Gross Range·Spike·Rate-of-Change·Flat Line·Climatology·Location** 테스트 + 플래그 부여, 임계값은 출처 명시 | QC 모듈·리포트 | QARTOD 매뉴얼 |
| **M3** 처리정책 | 플래그 기준 결측·이상치 처리(원칙 *플래깅*; 보간/제외는 명시정책) | 정책문서·적용 | QARTOD |
| **M4** 집계·저장 | 현황·QC 지표를 재현가능 산출물로 저장 | 집계 데이터셋 | — |
| **M5** 로컬 대시보드 | ①수집현황 ②QC결과(시계열+플래그 하이라이트) ③요약(가용률·지연랭킹) | 실행되는 대시보드 | — |
| **M6** 검증·문서·효과 | end-to-end 재현, README, Before/After 효과 | 데모·문서 | — |

## 5. 역할 분담
| 팀원 | 담당 |
|------|------|
| **김광진(KimKwangjin)** | M0 스키마 · M2 QC 엔진(문헌 근거) · 총괄 |
| **moonuns** | M1 수집현황 집계 · M4 집계·저장 (+ `qc_webapp/` 선행) |
| **heartmii** | M5 로컬 대시보드 |

> 각자 **본인 이름 파일/모듈만** 작업. 개인 작업기록은 `submit/G_<이름>_PROCESS_LOG.md`(로컬, zip 제출).

## 6. 기술 스택
Python 3 · pandas/numpy · QARTOD 근거(`ioos_qc` 참조/동등 구현) · Plotly · 로컬 http 서버
(대시보드: **ⓐ `qc_webapp` 확장 우선** vs ⓑ Streamlit 신규)

## 7. 미해결/확인 포인트
- 대상 변수 확정(기본 **수온·염분**) · 자료 형태(기본 **CSV/Excel**) · 실데이터 확보 시점 · "보정" 범위(보간 허용 여부) · 대시보드 방향(ⓐ/ⓑ)

## 8. 검증 (end-to-end)
1. 의존성 설치
2. 합성 샘플 생성(결측·지연·스파이크·flat-line 주입)
3. 수집현황 집계 → 지연/결측 확인
4. QC 실행 → 플래그(1/2/3/4/9) 부여, 주입한 이상치가 3/4로 잡히는지 확인
5. 로컬 대시보드 실행 → 현황·QC 시각화 확인
