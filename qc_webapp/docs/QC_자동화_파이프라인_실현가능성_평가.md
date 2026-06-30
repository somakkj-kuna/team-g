# 관측자료 자동 QC 파이프라인 — 실현가능성 및 설계 검토

> **작성일** 2026-06-30 · **목적** 공유용 타당성·설계 문서
> **검토 대상** "데이터 수집 경로를 주기적으로 스캔 → 신규 파일 자동 QC → 저장 / QC 실패 시 기록·재시도(주간·월간) / 실패가 다운로드 누락이면 재다운로드"하는 자동 파이프라인을 **현실적으로 구축 가능한가**
> **근거** 현 서버(`/home/data1/geosr/mwcho/claude_agent`)의 QC 로직(`qc_webapp/qc.py`)·다운로드 스크립트·자동화 인프라를 코드 수준으로 분석. 본 문서는 코드를 직접 보지 않아도 이해되도록 자기완결적으로 작성.

---

## 0. 한 장 요약 (Executive Summary)

**결론: 요청한 자동 QC 파이프라인은 구현 가능하다.** 핵심 자산(QC 엔진·다운로더·스케줄 인프라)이 이미 갖춰져 있고, 신규로 만들 부분(상태 원장 + 스캔/재시도 스크립트 + 스킬 명세)은 표준 배치 패턴이라 난이도가 낮다. 자동 QC의 대상은 **시계열 관측변수**다 — 현재 데이터가 흐르는 것은 수온이지만, **조위·염분·기온·파고·풍속 등 다른 관측변수도 같은 KHOA 바다누리 OpenAPI로 다운로드 가능하며 동일하게 시계열 QC 대상**이 된다(변수별 다운로더만 추가하면 됨). 공간·격자 데이터(연안침수·NOSC)는 다운로드는 되지만 시계열 QC(`run_qc`) 범위 밖이다. 또한 "새 파일이 계속 들어온다"는 전제를 세우려면 **관측 다운로더를 정기 스케줄에 등록**하는 선행 작업이 필요하다.

권장 구조는 **2-플레인 하이브리드** — 기계적 작업(스캔·QC·재시도·재다운로드)은 토큰 비용 0의 결정론적 cron+Python이 맡고, 지능형 작업(이상 패턴 해석·보고서 생성)은 저빈도 Claude 스케줄 에이전트가 맡는다.

| # | 요구사항 | 판정 | 근거 / 핵심 제약 |
|---|---|---|---|
| ① | QC 방법을 `skill.md`로 저장 | ✅ 가능 | `run_qc()` 입출력·플래그가 안정적 → 명세화 용이. 기존 SKILL.md 포맷 재사용 |
| ② | 수집 경로 주기 스캔 + 신규 감지 | ✅ 가능 | 내용 해시(sha256) 게이트 + 처리 원장 대조. cron/watchdog 패턴 보유 |
| ③ | 신규 파일 QC → 저장 | ✅ 가능 | 수온 JSON의 `series`가 `run_qc()` 입력과 **1:1 일치(ETL 불필요)** |
| ④ | 실패 기록 + 주간/월간 재시도 | ✅ 가능 | 상태 원장 + `next_retry_at` 사유별 차등 백오프 |
| ⑤ | 다운로드 누락 시 재다운로드 | ✅ 가능 | 수온은 `download_khoa_water_temp.py --force` 즉시. 조위·염분·기온 등 다른 변수도 **같은 KHOA 바다누리 OpenAPI로 다운로드 가능**(수온 스크립트를 변수별로 복제) |

---

## 1. 검토 요청 정의

원하는 자동 동작:
1. 데이터가 수집되는 경로들을 **계속 스캔**한다.
2. **새 파일이 들어오면** QC를 수행해 **저장**한다.
3. **QC가 안 되면 기록을 남기고**, 향후(주간 또는 월간) **다시 QC**한다.
4. QC가 안 된 이유가 **파일 다운로드 누락**이면 **재다운로드**도 수행한다.

부가 요건: QC 방법 자체를 `skill.md`로 외부화해 두어, 작업 주체(스크립트 또는 Claude 에이전트)가 일관된 방법으로 QC를 적용한다.

---

## 2. 현황 분석 (코드 탐색 결과)

### 2.1 QC 엔진 — `qc_webapp/qc.py :: run_qc()`

```python
run_qc(series, params=None, base=None) -> dict
#  입력  series : [[date, mean, min, max, count], ...]   ← 시계열 한 점이 한 행
#  출력  {"values":[{date,value,flag,reason}...], "flags":{ok,range,spike,missing 개수},
#         "n":전체수, "n_flagged":이상치수, "params":실제적용파라미터}
```

- **순수 표준 라이브러리 함수**. 파일 I/O·UI·외부 의존성 없음 → 배치/자동화에 이상적.
- 알고리즘 3단계: ① 물리범위·결측 1차 플래그 → ② 이동중앙값(Moving Median) 기반 **MAD 스파이크 검출** → ③ 플래그 집계.
- 기본 파라미터(수온 기준): 물리범위 −2 ~ 35 ℃, 윈도 7점, MAD 임계 3.5.
- 예외를 던지지 않고 **항상 dict를 반환**(빈 입력·결측 수용) → "QC 실패"는 예외가 아니라 결과 해석으로 판정(예: `n==0` 또는 `flags.ok==0`).

> ⚠️ **`qc.py`는 "교체 예정" 모듈**이다(파일 상단 주석에 명시). 현재는 간단한 이상치 제거만 하고, 향후 정식 QC 명세로 내부 구현이 바뀐다. 따라서 파이프라인은 `run_qc()`를 **느슨하게 결합**(`importlib` 동적 import + 출력 `.get()` 정규화)하고, 파라미터는 `base=` 인자로 외부 설정에서 주입하며, 적용된 QC 버전을 `method_version`으로 기록해 두어 엔진 교체에 대비해야 한다.

### 2.2 데이터 소스 정합성 (가장 중요한 발견)

| 수집 데이터 | 저장 경로 | 포맷 | run_qc 시계열 QC 대상? |
|---|---|---|---|
| **KHOA 조위관측소 수온** | `downloads/khoa_water_temp/{obsCode}.json` | JSON | ✅ **그대로 가능** |
| 연안침수 정보 | `downloads/coastal_flood/sgg/*.geojson` | GeoJSON(공간) | ❌ 범위 밖 |
| NOSC SST / 모자반 | `downloads/nosc/**/*.nc` | NetCDF(격자) | ❌ 범위 밖 |

KHOA 수온 JSON의 구조:
```json
{"obsCode":"DT_0001","name":"인천","lat":37.45,"lon":126.59,"unit":"degC",
 "interval_min":60,"count":122,
 "series":[["2025-06-04",18.13,17.8,18.6,24], ...]}   ← series = run_qc 입력과 1:1
```
즉 **수온 JSON의 `series` 필드를 `run_qc()`에 그대로 넘기면 된다 — 변환(ETL) 0**. 현재 31개 관측소 파일이 존재.

반면 연안침수(GeoJSON 폴리곤)·NOSC(NetCDF 격자)는 **공간/격자 데이터**라 시계열 이상치 QC(`run_qc`)의 대상이 아니다. 본 파이프라인의 자동 QC 범위에서 **명시적으로 제외**한다(별도의 공간 품질검사가 필요하면 다른 설계가 요구됨).

#### 다운로드 가능 범위는 수온보다 넓다 (중요)

KHOA 바다누리 OpenAPI는 **단일 제공자(data.go.kr `1192136`) 아래 여러 서비스 엔드포인트**로 구성된다 — 수온은 `…/1192136/surveyWaterTemp/…`, 연안침수는 `…/1192136/waterlogged/…` 처럼 **형제 서비스**다. 따라서 수온뿐 아니라 **조위·염분·유속·파고·기온·기압·풍향풍속** 등 다른 관측변수도 각자의 서비스 엔드포인트로 같은 방식으로 받을 수 있고, KMA·NIFS 부이 자료까지 더하면 `variables.py`에 정의된 **약 20종 관측변수**가 다운로드 대상이 된다.

기존 `download_khoa_water_temp.py`는 인증(서비스 키)·페이지네이션·증분 SKIP·재시도·일일 호출한도(코드22) 처리를 모두 갖춘 **재사용 가능한 템플릿**이라, 새 변수는 **엔드포인트 URL과 응답 파싱만 바꿔 복제**하면 된다. 이미 연안침수·NOSC 다운로더가 별도로 존재한다는 점도 다중 소스 다운로드 능력이 검증됐음을 보여준다.

요약하면 **"다운로드 가능 범위"(넓음)와 "시계열 QC 대상 범위"를 구분**해야 한다:

| 데이터 | 다운로드 가능? | run_qc 시계열 QC 대상? |
|---|---|---|
| 수온(현재 준비됨) | ✅ 스크립트 보유 | ✅ |
| 조위·염분·기온·파고·풍속 등 관측변수(약 20종) | ✅ 동일 API로 가능(변수별 스크립트 추가) | ✅ 시계열이라 가능 |
| 연안침수(GeoJSON) | ✅ 스크립트 보유 | ❌ 공간 데이터 |
| NOSC SST·모자반(NetCDF) | ✅ 스크립트 보유 | ❌ 격자 데이터 |

즉, **데이터를 받는 것은 수온에 국한되지 않는다.** 자동 QC 파이프라인은 우선 수온으로 가동하되, 다른 관측변수의 다운로더를 추가하는 만큼 그대로 확장된다(파이프라인 본체는 스캔 경로와 변수별 QC 파라미터만 늘리면 됨).

### 2.3 보유 자동화 인프라

- **시스템 crontab**: 9개 일일 잡 가동(08·15·18·19시대). 04시대는 비어 있어 신규 잡 배치 가능.
- **watchdog 패턴**: `qc_webapp/watchdog.sh` 등 "15초 폴링 health check → 죽으면 재기동" while 루프. "주기 감시 후 작업 실행"의 검증된 셸 패턴.
- **증분 추적 패턴**: `~/.claude/tasks/{uuid}/.highwatermark`(처리 오프셋) + `.lock`(동시성 락).
- **SKILL.md 포맷**: frontmatter(`name`/`description`/`user-invocable`/`allowed-tools`) + 마크다운 본문(디스패치 로직·상태 스키마·구현 노트). 예시: `~/.claude/plugins/.../skills/.../SKILL.md`, 그리고 자체 `geosr-hwpx/SKILL.md`.
- **무인 실행 권한**: settings.json `bypassPermissions`(권한 프롬프트 없음) → 자동 실행 가능(대신 안전장치 필요, §6).
- **Claude 스케줄 기능**: routine(`create_trigger`, cron으로 fresh 세션 발화)·`send_later`·loop 스킬.

### 2.4 ⚠️ 반드시 알아야 할 함정 3가지

1. **수온 다운로더는 현재 스케줄되어 있지 않다.** crontab 15:00의 `download_khoa_data.py`는 **다른 스크립트**(KHOA SST NetCDF 격자 수집, → `/home/data1/geosr/SST/`)다. QC 대상 수온 JSON을 만드는 것은 `download_khoa_water_temp.py`이며 **현재 cron에 없고 수동 실행**이다. 그래서 현 데이터는 2026-06-05에 멈춰 있다. "새 파일이 계속 들어온다"는 전제를 성립시키려면 **이 다운로더를 정기(주간) cron에 등록**하는 것이 설계의 일부가 되어야 한다.

2. **다운로더는 파일을 통째로 교체한다(증분 append 아님).** `--force`로 다시 받으면 내용이 같아도 파일이 새로 써져 **mtime이 항상 바뀐다**. 따라서 "신규/변경" 판정을 mtime만으로 하면 매번 재처리하게 된다 → **내용 해시(sha256) 비교**로 진짜 변경만 골라내야 한다.

3. **재다운로드 시 `--start-date`에 고정 시작일을 줘야 한다.** 다운로더는 지정 기간 전체를 새로 만들기 때문에, 최근 N일만 지정하면 **과거 시계열이 잘려 사라진다**. 재다운로드 호출에는 항상 **프로젝트 고정 시작일**(예: `2025-06-01`)을 전달한다.

---

## 3. 요구사항 ↔ 가능성 매핑 (상세)

| 요구 | 판정 | 어떻게 / 근거 | 제약 |
|---|---|---|---|
| ① skill.md 외부화 | 가능 | `run_qc` 안정 인터페이스를 산문+파라미터 표로 명세. 기존 SKILL.md 포맷 그대로 | qc.py 교체 시 `method_version` 동기화 |
| ② 경로 스캔·신규 감지 | 가능 | `(size,mtime)` 1차 필터 → 다르면 sha256 해시 게이트 → 원장과 비교 | half-write 회피 위한 settle-time 필요 |
| ③ 신규 QC·저장 | 가능 | 수온 JSON `series` → `run_qc(base=변수별파라미터)` → 결과 JSON/CSV 원자적 저장 | 저장 스키마 신규 정의 |
| ④ 실패 기록·재시도 | 가능 | 상태 원장에 `{status, reason, attempts, next_retry_at}` → due 항목만 재처리 | 무한루프 방지 위한 시도 상한 필요 |
| ⑤ 재다운로드 | 가능 | 수온은 `download_khoa_water_temp.py --obs-codes X --force --start-date 고정` 즉시. 다른 변수도 같은 KHOA 바다누리 OpenAPI로 다운로드 가능 | 변수별 다운로더는 수온 스크립트를 복제(엔드포인트·파싱 교체) |

---

## 4. 권장 아키텍처 — 2-플레인 하이브리드

```
┌─ 데이터 플레인 ── 결정론 · 무토큰 · 로컬 daemon 무관 ──────────────┐
│                                                                  │
│  cron(주1회)  download_khoa_water_temp.py  ── 신규 수온 데이터 유입 │
│       │                                                          │
│  cron(매일)   qc_scan.py                                          │
│       │  파일 감지(size/mtime → sha256) → run_qc() →             │
│       │  qc_results/{obsCode}.qc.json + flags.csv                │
│       │  실패 분류 → ledger.db 기록                              │
│       │  사유=다운로드누락 → download_*.py --force 트리거         │
│       │                                                          │
│  cron(매일)   qc_retry.py  : next_retry_at 도래분만 재처리         │
│                                                                  │
│                    ▼  ledger.db  ◀── 두 플레인의 유일 인터페이스   │
└──────────────────── ▲ ───────────────────────────────────────────┘
                      │
┌─ 지능 플레인 ── Claude routine · 주1회 fresh 세션 · 저빈도 ────────┐
│  create_trigger(주1회) → /qc-observation status → review → report │
│    이상 패턴 해석(계측오류 vs 실제현상) · HWPX 보고서 · 주간 요약   │
└──────────────────────────────────────────────────────────────────┘
```

**설계 원칙: 결정 가능한 모든 것은 Python(0토큰·재현가능), 판단·서술·자연어는 Claude(저빈도).**

| 작업 | 담당 | 이유 |
|---|---|---|
| 파일 감지 / `run_qc` 호출 / 결과 저장 | 결정론 Python | 매일 실행 → 토큰 0, 100% 재현 |
| 실패 분류 / 원장 기록 / 재다운로드 트리거 | 결정론 Python | 규칙 기반, LLM 불필요 |
| 재시도 만기 선택 | 결정론 Python | due 쿼리 |
| 이상 패턴 해석 · 비정형 실패 판단 | Claude (주1회) | 자연어 추론 영역 |
| HWPX 보고서 · 주간 품질 요약 | Claude (주1회) | `report.py` 재사용 |

두 플레인 모두 **로컬 Claude daemon에 의존하지 않는다**(데이터 플레인=시스템 cron, 지능 플레인=관리형 routine). 신뢰성과 비용이 동시에 확보된다.

---

## 5. 컴포넌트 상세 설계

### 5.1 디렉터리 레이아웃 (기존 코드 무수정, 신규 디렉터리 추가)

```
claude_agent/
├── download_khoa_water_temp.py     (기존 — 재다운로드 호출 대상)
├── qc_webapp/qc.py                 (기존 — run_qc import 대상)
├── downloads/khoa_water_temp/*.json (입력, 읽기 전용)
├── qc_pipeline/                    (신규)
│   ├── qc_pipeline.toml            # 경로·변수별 파라미터·재시도 간격·상한
│   ├── config.py / ledger.py / qc_runner.py / qc_scan.py / qc_retry.py
│   ├── state/  (ledger.db · pipeline.lock · khoa.key[600])
│   └── logs/   (qc_scan.log · qc_retry.log · download_water_temp.log)
└── qc_results/khoa_water_temp/{obsCode}/
    ├── {obsCode}_qc.json           # run_qc 결과 + provenance
    └── {obsCode}_flags.csv         # date,value,flag,reason
```

### 5.2 신규 파일 감지 — 내용 해시 게이트

1. **1차(저비용)**: 원장의 `(size, mtime)`과 동일하면 → **SKIP**(해시 계산도 생략).
2. **2차**: 다르면 `sha256` 계산 → 원장 `content_hash`와 비교 → 다르면 **신규/변경 → QC 실행**, 같으면(touch·동일내용 재기록) 메타만 갱신.
3. **Settle-time**: `now - mtime < 60s`인 파일은 쓰는 중일 수 있으니 이번 회차 건너뜀(다음 회차 처리).
4. glob 시 `stations.json`(인덱스) 제외, `DT_*.json`만.

### 5.3 QC 실행 래퍼 (`qc_runner.py`)

`load_khoa(path)` → `run_qc(series, base=toml_params[var])`(try/except) → `write_outputs()`(임시파일 후 `os.replace`로 원자적 저장, 저장 전 디스크 여유 가드). 출력 JSON에 **provenance**(소스 해시·qc_version·적용 파라미터·series 시작/끝) 포함. 파라미터는 `qc_pipeline.toml`의 변수별 섹션에서 주입해 `qc.py` 내부 기본값에 의존하지 않게 함(교체 대비).

### 5.4 상태 원장 (SQLite, WAL 모드 — JSON보다 권장)

권장 이유: 스캔/재시도 동시 접근의 트랜잭션 원자성, `next_retry_at` 인덱스로 due 조회 O(log n), 확장 시 전체 재작성 비용 없음, stdlib `sqlite3`로 의존성 0.

```sql
files(source, station PK, path, content_hash, src_mtime, src_size,
      series_end, n_points,
      status,         -- done | failed | pending_redownload | failed_permanent
      reason_class, reason_msg, attempts,
      first_seen, last_attempt, next_retry_at, result_path)
INDEX idx_due(status, next_retry_at)
```
시간은 **UTC ISO로 저장**(로그 출력만 KST 변환).

### 5.5 실패 분류 & 재시도/재다운로드

| reason_class | 판정 조건 | 후속 조치 | 재시도 주기 |
|---|---|---|---|
| `not_downloaded` | 파일 없음 / 0바이트 | **재다운로드** 후 재QC | 주간(+7d) |
| `parse_error` | JSON 깨짐 | 재다운로드 후 재QC | 주간(+7d) |
| `empty_series` | `series==[]` / `count==0` | 재다운로드 후 재QC | 주간(+7d) |
| `insufficient_data` | 점 수 < 최소(예 5) | 재QC만(데이터 누적 대기) | 월간(+30d) |
| `qc_exception` | run_qc 예외 | traceback 요약 기록·재QC | 주간(+7d) |
| `transient` | half-write 등 일시 | 단기 재시도 | ~1시간 |
| (정상) | 그 외 | `status=done` | — |

- **재다운로드 명령**(기존 CLI 재사용):
  ```bash
  python3 download_khoa_water_temp.py --obs-codes <station> --force \
    --start-date <고정시작일> --end-date <어제> \
    --output-dir downloads/khoa_water_temp        # 키는 $KHOA_SERVICE_KEY
  ```
  종료코드 매핑: `0/1`→파일 재검사, `2`(일일 호출한도 코드22)→**attempt 비소모 익일 재시도**.
- **차등 백오프**는 `next_retry_at`에 인코딩 → **단일 일간 재시도 cron**이 주간/월간을 자동 처리(별도 cron 불필요).
- **무한루프 가드**: reason별 `attempts_cap`(예 5~6) 초과 시 `failed_permanent` 전이 + 경보(수동 리셋 전까지 자동 재시도 중단).

### 5.6 스케줄링 (cron + Claude routine)

```cron
# (A) 수온 시계열 주간 갱신 — 월 04:10  (기존 잡과 무충돌)
10 4 * * 1  KHOA_SERVICE_KEY=… python3 …/download_khoa_water_temp.py --force --start-date 2025-06-01 … >> logs/download_water_temp.log 2>&1
# (B) QC 스캔 — 매일 15:40  (15:00 다운로드 클러스터 종료 후)
40 15 * * * flock -n state/pipeline.lock python3 …/qc_scan.py  >> logs/qc_scan.log 2>&1
# (C) 재시도 — 매일 04:30  (due 기반 = 주간/월간 자동 반영)
30 4 * * *  flock -n state/pipeline.lock python3 …/qc_retry.py >> logs/qc_retry.log 2>&1
```
**지능 플레인**: `create_trigger`(cron 주1회, `create_new_session_on_fire:true`) → fresh 세션에서 `/qc-observation status → review → report`. fresh 세션이라 컨텍스트 드리프트 없고, 토큰은 주1회로 한정. 이벤트성 후속(재다운로드 직후 1시간 뒤 재QC 등)은 `send_later`/ScheduleWakeup.

### 5.7 `skill.md` 설계 — `qc-observation`(가칭)

- **저장/배포**: 원천은 `qc_webapp/skills/qc-observation/SKILL.md`(git 추적), 배포는 `~/.claude/skills/qc-observation/`로 심볼릭 링크(어느 세션에서나 `/qc-observation` 발견).
- **frontmatter**: `name`/`description`/`user-invocable:true` + **`allowed-tools`를 특정 스크립트 경로 글롭으로만 제한**(bypassPermissions 안전성, §6).
- **본문**: ① QC 방법 명세(run_qc 3단계 + 변수별 파라미터 표) ② 입출력 계약 ③ 스캔 대상 경로(비대상 명시) ④ 원장 스키마 ⑤ 재시도/재다운로드 규칙 ⑥ 디스패치 인자(`scan`/`retry`/`status`/`review`/`report`) ⑦ "기계 작업은 스크립트에 위임, `run_qc`를 재구현하지 말 것" 원칙.
- **교체 대비**: 본문 파라미터 표는 향후 정식 엔진(다단계 `qc_rules.toml`, 부록 B)으로 옮겨갈 때 단일 출처를 참조하도록 포인터화.

### 5.8 동시성 · 로깅 · 보안

- **동시성**: 단일 `state/pipeline.lock`을 `flock -n`(non-blocking)으로 획득 → 스캔/재시도 중복·상호 실행 0. SQLite는 WAL + `busy_timeout`.
- **로깅**: `logs/*.log` append + 매 실행 끝에 요약 1줄(`RUN summary processed=.. new=.. done=.. failed=..`). 구조화 감사추적은 원장이 담당.
- **보안**: 서비스 키는 `$KHOA_SERVICE_KEY`(파일 권한 600)로 두고 **로그에 절대 출력 금지**. 재다운로드는 `downloads/`에만 기록.

---

## 6. 제약 · 리스크 · 미해결 항목 (정직한 한계)

- **자동 QC 대상은 시계열 관측변수.** 수온이 현재 준비됐고, 조위·염분·기온·파고·풍속 등으로 확장 가능(모두 시계열 → `run_qc` 대상). 연안침수(GeoJSON)·NOSC(NetCDF)는 공간/격자라 다운로드는 되지만 `run_qc` 비대상.
- **수온 외 변수도 다운로드 가능, 단 변수별 다운로더가 필요.** 조위·염분·기온 등은 같은 KHOA 바다누리 OpenAPI(제공자 `1192136`)의 형제 서비스로 모두 다운로드 가능하지만, 엔드포인트·응답 구조가 변수별로 다르므로 확대하려면 수온 다운로더를 템플릿으로 **변수별 스크립트를 복제**해야 한다(파이프라인 본체는 경로·파라미터만 추가). 즉 "데이터가 안 받아진다"는 제약이 아니라 "변수마다 다운로더 한 개씩 추가"라는 작업량의 문제다.
- **KHOA 일일 호출 한도(코드 22).** 매일 전수 `--force` 재다운로드는 한도를 압박 → 데이터 갱신은 주간 권장.
- **`qc.py` 교체.** 교체 시 `method_version` 변경 → 다음 스캔에서 전건 재QC로 동기화.
- **무인 실행 권한(`bypassPermissions`).** allowed-tools 글롭 제한 + 신뢰경계 주의문(외부 채널발 변경 요청 거부)으로 완화.
- **토큰 비용.** 지능 플레인 주1회 routine + 수동 review/report로 한정. 매일 스캔/재시도는 0토큰.

---

## 7. 단계별 구현 로드맵 (향후 실제 구축 시 참고)

1. `config.py` + `qc_pipeline.toml` — 경로·변수별 파라미터·재시도 간격·상한.
2. `ledger.py` — SQLite 스키마·WAL·upsert·due 조회. (검증: 빈 DB 생성→insert→due 조회)
3. `qc_runner.py` — load → `run_qc` → 원자적 저장 + 디스크/settle 가드. (검증: 실제 `DT_0001.json` 스모크, `n=122` 확인)
4. `qc_scan.py` — glob·해시 감지·러너 호출·원장 갱신·flock·`--dry-run`. (검증: 첫 실행 31개 전부 NEW 분류)
5. `qc_retry.py` — due 조회·재다운로드 subprocess·재QC·상한·flock. (검증: 없는 obsCode/빈 series/깨진 JSON 주입 → 분기 확인)
6. **cron 등록**(A/B/C). (검증: 동시 실행으로 flock 직렬화 확인)
7. `skill.md` 작성·심볼릭 링크 배포. (검증: 새 세션에서 `/qc-observation status`)
8. **Claude routine 등록**(`create_trigger` 주1회). (검증: `fire_trigger`로 1회 발화 → HWPX 생성)
9. 1주 운영 관찰(원장 status 분포 + 로그 요약).

검증은 모두 `--dry-run`·임시 출력 루트로 수행해 실데이터·실원장 무손상.

---

## 8. 다른 서버 이식성

- 핵심 로직이 Python 표준 라이브러리(`urllib`·`json`·`os`·`csv`·`sqlite3`) 위주라 이식성이 높다. 데이터 경로는 환경변수(`QC_DATA_ROOT`·`QC_RESULTS_ROOT`)로 분리한다.
- 의존: cron(또는 systemd timer) + Python 환경(anaconda/venv) + API 네트워크 도달성 + KHOA 서비스 키.
- 백그라운드 실행은 일반 서버면 cron/nohup으로 충분하다(현 서버 특유의 셸 제약은 대상 서버에선 보통 없어 더 단순해진다).

---

## 부록 A. 재사용하는 기존 자산

| 자산 | 용도 |
|---|---|
| `qc_webapp/qc.py :: run_qc(series, params, base)` | QC 엔진(느슨 결합 import) |
| `download_khoa_water_temp.py` | 재다운로드 CLI(`--obs-codes/--force/--start-date/--end-date/--output-dir`, `$KHOA_SERVICE_KEY`, 종료코드 0/1/2) |
| `qc_webapp/variables.py :: get()` | var_id 레지스트리(파라미터 외부화 키) |
| `qc_webapp/report.py :: build_prompt / run_claude / build_report` | 지능 플레인 HWPX 보고서 |
| `~/.claude/tasks/{uuid}/.lock` + watchdog flock 패턴 | 동시성 락 철학 |
| 기존 SKILL.md(`geosr-hwpx` 등) | frontmatter·디스패치 포맷 |

## 부록 B. 실제 QC 시스템 참고 (`sample_data`)

향후 `qc.py`가 교체될 정식 QC 시스템의 형태(현재 `qc_webapp/sample_data/`에 미니 샘플로 존재, server131(10.27.1.131) 실데이터 기반):

- 대상: 3기관(KHOA tidal · KMA buoy · NIFS buoy) 대표 관측소 × 2025년.
- 파이프라인: `00_sort → 01_aqc1(zero·range·stuck·edge·spike·roc …) → 02_aqc2(rolling stat) → 03_mqc(이벤트) → 04_export(flag/final) → 05_plot`.
- 규칙은 코드 수정 없이 **TOML 캐스케이드**로 제어: `qc_rules.toml` < 기관 TOML < 관측소 TOML.
- 결과: `result/flag/`(전체 flag) · `result/final/`(good+suspect만).

→ 본 파이프라인의 `skill.md` 파라미터 표는 장차 이 `qc_rules.toml`을 단일 출처로 참조하도록 확장하면 정식 엔진과 자연스럽게 합류한다.

## 부록 C. 용어

- **원장(ledger)**: 파일별 QC 처리 상태·실패 사유·다음 재시도일을 기록하는 상태 저장소(SQLite).
- **해시 게이트**: 파일 내용 sha256으로 진짜 변경만 골라 재처리하는 감지 방식.
- **2-플레인**: 결정론 데이터 플레인(cron+Python)과 지능 플레인(Claude routine)의 분리 구조.
- **차등 백오프**: 실패 사유에 따라 재시도 간격을 다르게(주간/월간) 두는 정책.
