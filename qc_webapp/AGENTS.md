# QC 웹앱 — 관측자료 품질관리(QC) 플랫폼

3개 기관(**KHOA·KMA·NIFS**) 관측소 **다변수 사전 QC 결과(`flag_final`) 표출** + AI 분석 + 한글(HWPX) 보고서.
Flask 백엔드 + 빌드리스 vanilla JS(`static/`, 로컬 Plotly) SPA. 포트 **8002**(외부 relay 8501).
웹앱은 QC를 직접 수행하지 않고 **이미 계산된 `flag_final`을 그대로 표출**한다.

> 이 문서는 Claude Code(`CLAUDE.md`)·Codex(`AGENTS.md`)·Cursor(`.cursorrules`)가 자동 로드한다.
> 세 파일은 **동일 내용의 실파일**이므로, 수정 시 셋을 함께 갱신할 것(또는 한 곳을 고치고 나머지에 복사).

---

## 1. 실행 / 재기동 (중요)
- `app.py`는 자동 리로드가 없다 → **파이썬 코드(`app.py`/`report.py`/`data.py`/`variables.py`/`sources.py`) 수정 후 반드시 재기동**.
- 재기동(이 환경 전용 우회):
  ```bash
  cd /home/data1/geosr/mwcho/claude_agent/qc_webapp
  fuser -k 8002/tcp; setsid python3 app.py >server.log 2>&1 </dev/null &
  ```
  - ⚠️ `pkill -f ...`(자기 명령문 매치로 셸 종료), 백그라운드 `&` 직접 실행, 포그라운드 `sleep`은 이 환경에서 차단/exit 144 → **반드시 `fuser -k 8002/tcp` + `setsid`** 사용.
- 정적 자산(html/js/css)은 `after_request` no-cache로 즉시 반영. 단 **브라우저 캐시 무력화를 위해 `index.html`의 `?v=N`을 수정마다 올릴 것**(현재 **v=24**).
- 검증: JS `node --check static/app.js`, PY `python3 -c "import ast; ast.parse(open('app.py').read())"`, 그리고 `curl http://127.0.0.1:8002/...` 또는 `app.test_client()`.

## 2. 데이터
- 출처: `sample_data/sample_data/` (server131 미러). **⚠️ 공개 repo 커밋 금지**(`.gitignore` 등록, zip 전달). 경로 env: `QC_SAMPLE_ROOT`.
- flag CSV: `home/collect/QC/result/flag/{agency}/{station}/{yyyy}/{agency}_{station}_{yyyy}_qc_flag.csv`
  (long: `time,agency,station_id,lat,lon,var_id,value,depth_m,flag_final,...`)
- `flag_final`: **1=good 2=suspect 3=bad 4=interp 9=missing** → 보존=1·2(·4), 제거=3·9.
- 3기관: `khoa`(국립해양조사원/tidal, DT_0001 인천 등 11변수) · `kma`(기상청/buoy, 22003 등 10변수) · `nifs`(국립수산과학원/buoy, bbbi5 부안 변산: 표/중/저층수온). **2025년 고정·시간별**. period(1m/1y/all)는 today가 아니라 **데이터 최신시점 기준**.

## 3. 파일 구조
- `app.py` — Flask API + LLM 호출(claude CLI 헤드리스, haiku/low).
- `data.py` — sample_data 로더(flag CSV·mtime 캐시), `valid_targets`/`export_rows`/`station_region`/`list_all_stations`.
- `variables.py` — `var_id` 레지스트리(한글명·단위).
- `sources.py` — 수집현황 카드(Observation=3기관 실데이터, Numerical·Satellite=준비중).
- `report.py` — 통계 + LLM 프롬프트 + HWPX. `build_report`(단일변수) / **`build_report_multi`(여러 변수 → 통합 1파일)**. HWPX는 `geosr-hwpx`의 `YeoboBuilder` 재사용(차트 라벨은 영문).
- `qc.py` — 미사용(사전 flag 표출). 보존만.
- `static/` — `index.html` / `app.js` / `styles.css` + 로컬 `plotly-2.35.2.min.js`(빌드 없음).
- `reports/` — 생성된 HWPX(+`figs/` 차트 PNG).

## 4. API
- `GET /api/sources` · `/api/stations?agency=` · `/api/variables?agency=&station=` · `/api/qc?agency=&station=&var=&period=`(series:[{time,value,flag}])
- `GET /api/catalog`(전기관 관측소+해역+변수) · `GET /api/download?targets=agency:station,..&vars=all|csv&start=&end=&maxflag=&minflag=`(BOM CSV, `X-Row-Count`)
- `POST /api/chat`(LLM 분석) · `POST /api/report` — 단일 `var`(+`analysis`) **또는** 다중 `vars`(list/csv, +`analyses{key:text}`) 수용. **다중이면 통합 1파일** 생성, 응답에 `n_vars`.

## 5. 작업 규약 / 주의
- **다운로드 보안**: `/api/download`의 `targets`는 반드시 `data.valid_targets()` 화이트리스트로만 허용(경로/와일드카드 `*:*`·절대경로·`..` 주입 차단). 사용자 입력은 `esc()`(따옴표 포함) 이스케이프.
- 시계열 견고화: 뷰 전환/placeholder 전 `Plotly.purge`(resize 리스너 누수·stale 줌 방지), `drawSeq` fetch 경쟁 가드, 에러/무관측소 시 통계·범례·결측노트 초기화.
- 보고서 생성: `reportBusy` 가드(중복요청 차단) + 시작 시점 컨텍스트 스냅샷(생성 중 기관/관측소/기간 변경 무영향).
- ⚠️ `report.py`의 단일 `build_report`/`station_stats`는 아직 구 KHOA 수온 구조(조위관측소·`data.go.kr`·물리범위/MAD params 가정)라 **단일 보고서 텍스트가 부정확**(동작은 함). `build_report_multi`는 출처를 3기관 일반표현으로 둠. → 3기관 일반화는 후속 과제.

---

## 6. 오늘(2026-06-30) 작업 내역

### 데이터 모델 대전환
- KHOA 수온 단일(JSON + 자체 `run_qc`) → **sample_data 3기관 사전 QC flag CSV 표출**로 교체. webapp은 QC 미수행, `flag_final` 그대로 표출.

### UI/기능 (정적 v=8 → **v=24**)
1. **시계열 줌·이동** — 차트 상단 ＋확대/－축소/⤢전체 버튼(`zoomChart`/`axZoom`, Plotly r2l·l2r) + **휠=확대·축소(`scrollZoom`)·좌드래그=이동(`dragmode:"pan"`)**, modebar 트림.
2. **전역 타이핑 검색**(`#global-q`/`#global-results`) — 3기관 관측소+수집변수 인덱싱(`buildSearchIndex`, `indexReady` 가드), 입력 즉시 필터, ↑↓/Enter/클릭으로 해당 시계열 점프.
3. **헤더 문구 전문화**·불필요 '2025' 제거.
4. **분석 결과 인라인 HWPX 저장**(`addAnalysisActions`) — askAI 분석 완료 시 그 아래 `📄 한글(HWPX)로 저장` 버튼(분석·ctx 클로저 고정 → `/api/report`에 analysis 전달=LLM 재실행 없이 생성).
5. **QC 자료 다운로드 모달**(`#open-download`→`#dl-modal`) — 신규 `GET /api/catalog`·`GET /api/download`. 관측소 범위·변수·기간(start~end)·**QC등급(`flag_final≤maxflag`, "몇 이하만")**, `<a download>` CSV(BOM). **보안: `valid_targets()` 화이트리스트**(경로/와일드카드 주입 차단).
6. **예시 질문(대표 질문 칩)** 새 내용으로 교체.
7. **우측 패널 탭 분리** — `🤖 LLM 분석` / `📄 품질 결과 보고서`(`switchPanelTab`, `#pane-llm`/`#pane-report`). 보고서 탭 = 기관+관측소+변수+기간 선택 → 생성.
8. **다운로드 모달: 해역 탭 → 기관별 탭**(`dlAgency`/`renderDlAgencies`/`dlScopeStations`).
9. **결측 수집상태 표시**(`renderCollectNote`, `#series-collect`) — 결측을 **최신 7일 내 = `자료 수집 진행중` / 그 외 = `자료 수집 안 함`**으로 시계열 하단에 표기.
10. **변수 다중선택 드롭다운(공용)** — `renderCkPanel`/`bindCkDropdown`/`updateCkTrigger`(클래스 `.ck-dd/.ck-trigger/.ck-panel/.ck-item/.ck-all`): **클릭하면 펼침·스크롤**, 전체 토글, 체크상태 보존, 바깥클릭 닫힘. **다운로드 모달 변수(`#dl-vars`) + 보고서 변수(`#report-vars`) 공유**.
11. **"자료 품질 평가" 예시칩 → 선택 카드**(`startQualityEval`/`setContextTo`) — 즉시 분석 대신 봇이 "어떤 관측소와 변수를 분석할까요?"로 기관·관측소·변수 선택 카드를 띄우고, 선택 후 분석.
12. **보고서 탭에서 다운로드 UI 제거**(주의이상 CSV 버튼·`downloadAttention` 삭제) — 다운로드는 상단 모달에서만.
13. **다중 변수 → 하나의 통합 HWPX**(`report.build_report_multi`, `/api/report` `vars`+`analyses`) — 개요 + 변수별 QC 통계 요약표 + 변수별 상세(통계표·이상치표·LLM분석 ㅇ/- 들여쓰기·차트). 선택 일치 분석만 재사용.
14. **보고서 생성 중 회전 표시**(`.ai-spinner` 상태줄 + `.btn.report.is-busy::before` 버튼 스피너, 라벨 "보고서 생성 중…").

### 적대적 멀티에이전트 리뷰로 발견·수정한 결함
- **`/api/download` 경로/와일드카드 주입**(`*:*`·절대경로·`..` 임의파일 읽기) → `valid_targets()` 화이트리스트(보안 핵심).
- `station_region` 동해 오분류 → `lon≥128.5`.
- 줌/리셋 stale Plotly 노드 + resize 리스너 누수 → `purgeSeriesChart`.
- 검색 인덱스 준비 전 "결과 없음" → `indexReady`; fetch 경쟁 → `drawSeq`.
- `esc()` 따옴표 미이스케이프 → 보강.
- 시계열 에러/무관측소 시 이전 관측소 결측노트 잔존 → 초기화. 다운로드 빈 문구 '해역' 잔재 → '관측소'.
- 보고서 생성 중 컨텍스트 변경/중복요청 → `reportBusy` 가드 + 컨텍스트 스냅샷.
- 다운로드 모달 Esc 종료 시 변수 드롭다운 펼침 잔존 → 열 때 초기화.
- 관측소 탭 전환 시 보고서 변수 목록(VARSTATUS) stale → 탭 전환 시 재로딩.

## 7. 미완 / 후속
- `report.py` 단일 보고서를 sample_data(3기관·`flag_final`)에 맞게 정교화(현재 "조위관측소"·더미 params 텍스트 부정확).
- 전 KHOA 변수 다운로드(`KHOA_SERVICE_KEY` 필요).
- 외부포트: 8501=QC(relay→8002), 8000=NOSC 수온, 8001=연안침수. 검증은 `app.test_client()` 또는 curl.
