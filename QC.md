# 해양 관측 데이터 자동 품질 검사(QC) 시스템 기술 보고서

> 작성일: 2026-06-30  
> 대상 경로: `/home/collect/QC/`  
> 목적: 해커톤 참가 AGI가 시스템 전체를 즉시 이해할 수 있도록 구성

---

## 1. 시스템 개요

### 1.1 목적

한국 연근해 해양·기상 관측소에서 수집된 **시계열 관측 데이터**에 대해 자동 품질 검사(Automated Quality Control, AQC)를 수행하고, 각 데이터 포인트에 신뢰도 플래그를 부여한다.

### 1.2 데이터 출처

| 기관 | 코드 | 데이터셋 | 주요 변수 |
|------|------|---------|-----------|
| 국립해양조사원 | `khoa` | `tidal` | 조위, 수온, 염분 |
| 국립해양조사원 | `khoa` | `buoy` | 파고, 유속, 기상 |
| 기상청 | `kma` | `buoy` | 기온, 기압, 풍속, 습도 |
| 국립수산과학원 | `nifs` | `buoy` | 표층·중층·저층 수온 |

### 1.3 관측소 ID 패턴

| 기관 | 형식 | 예시 |
|------|------|------|
| khoa | `[A-Z]{2,3}_[0-9]{4,}` | `DT_0001`, `IE_0060` |
| kma | 숫자 | `22601` |
| nifs | 소문자 영숫자 4+ | `bgj8a`, `bbbi5` |

### 1.4 처리 단위

월별 처리(`--yyyymm YYYYMM`) 또는 일별 처리(`--yyyymmdd YYYYMMDD`)를 지원한다. 출력 결과는 **연간 단일 CSV**에 누적된다.

---

## 2. 데이터 경로 및 폴더 구조

### 2.1 전처리 입력 경로 (parquet)

QC 파이프라인의 실제 입력은 원시 CSV가 아닌 **전처리된 parquet** 파일이다.

```
/data/DATA/OBS/prc/
├── tidal/
│   └── {yyyy}/
│       └── {yyyymmdd}.parquet       # 전처리된 조위 (일별 parquet)
└── buoy/
    └── {yyyy}/
        └── {yyyymmdd}.parquet       # 전처리된 부이 (일별 parquet)
```

> 원시 수집 CSV(`/data/DATA/OBS/raw/`)는 수집기가 생성하는 중간 파일이며, QC 파이프라인은 전처리된 prc parquet을 입력으로 사용한다.

### 2.2 프로젝트 전체 폴더 트리

```
/home/collect/QC/
│
├── src/                               # 소스 코드 루트
│   ├── config/
│   │   └── qc_rules.toml             # 마스터 QC 설정 (변수별 파라미터)
│   │
│   ├── libs/
│   │   ├── checks/                   # QC 검사 모듈 (9종)
│   │   │   ├── zero_check.py         # Zero 검사
│   │   │   ├── range_check.py        # 물리 범위 검사
│   │   │   ├── stuck_check.py        # 고착값 검사
│   │   │   ├── roc_check.py          # 변화율 검사
│   │   │   ├── spike_check.py        # 급등락 검사
│   │   │   ├── stat_check.py         # Rolling 통계 검사
│   │   │   ├── edge_check.py         # 데이터 갭 복귀 검사
│   │   │   ├── consistency_check.py  # 연동 변수 일관성 검사
│   │   │   └── cross_check.py        # 교차·수직·벡터 검사
│   │   │
│   │   ├── pipeline/                 # 처리 파이프라인 (단계별)
│   │   │   ├── 00_sort.py            # 정렬·표준화
│   │   │   ├── 01_aqc1.py            # 1차 자동 QC
│   │   │   ├── 02_aqc2.py            # 2차 자동 QC (rolling)
│   │   │   ├── 03_mqc.py             # 수동 QC (이벤트 기반)
│   │   │   ├── 04_export.py          # 최종 CSV 저장
│   │   │   ├── 05_plot.py            # 월별/연간 시각화
│   │   │   └── 07_plot_multiyr.py    # 다년도 시각화
│   │   │
│   │   └── utils/
│   │       ├── flag_io.py            # 플래그 상수 정의, 읽기/쓰기
│   │       ├── loader.py             # CSV 로더·표준화
│   │       └── config_loader.py      # TOML 설정 로더 (3단계 병합)
│   │
│   └── tmp/                          # 임시 작업 파일 (파이프라인 중간 결과)
│       ├── sorted/                   # 00_sort 출력 (parquet)
│       │   └── {dataset}/
│       │       └── {agency}_{key}.parquet
│       └── flags/                    # 01~03 임시 flag CSV
│           └── {agency}/{station_id}/
│               └── {key}_flag.csv
│
├── meta/                             # 메타데이터
│   ├── agencies/
│   │   ├── khoa.toml                 # 기관별 파라미터 오버라이드
│   │   ├── kma.toml
│   │   └── nifs.toml
│   ├── stations/
│   │   ├── KHOA/{station_id}.toml   # 관측소별 파라미터 오버라이드 + y축 범위
│   │   ├── KMA/{station_id}.toml
│   │   └── NIFS/{station_id}.toml
│   └── mqc_events.toml              # 수동 QC 이벤트 목록 (태풍, 장비 교체 등)
│
└── result/                           # 최종 출력
    ├── flag/                         # 전체 플래그 포함 연간 CSV
    │   └── {agency}/{station_id}/{yyyy}/
    │       └── {agency}_{station_id}_{yyyy}_qc_flag.csv
    ├── final/                        # good+suspect 데이터만 추출한 연간 CSV
    │   └── {agency}/{station_id}/{yyyy}/
    │       └── {agency}_{station_id}_{yyyy}_qc_final.csv
    └── plots/                        # 시각화 이미지
        ├── {agency}/{station_id}/{yyyy}/
        │   ├── {YYYYMM}.png          # 월별 플롯
        │   └── {yyyy}_annual.png     # 연간 플롯
        └── all_year/{agency}/
            └── {station_id}_all_year.png   # 다년도 플롯
```

---

## 3. 파이프라인 전체 흐름

### 3.1 실행 스크립트 (`run_qc.sh`)

진입점은 `run_qc.sh`이며, 내부적으로 각 파이프라인 단계를 순차 호출한다.

```bash
# 예시 실행
bash run_qc.sh khoa tidal 2025 2025          # 전체 연도 처리
bash run_qc.sh khoa tidal 202501 202501      # 특정 월만
bash run_qc.sh khoa tidal 2025 2025 --from-step 01   # AQC1부터 재처리
```

### 3.2 데이터 흐름 다이어그램

```
전처리 parquet (/data/DATA/OBS/prc/{tidal,buoy}/{yyyy}/{yyyymmdd}.parquet)
        │
        ▼
  [00_sort.py]
  정렬·표준화·중복 제거
  → src/tmp/sorted/{dataset}/{agency}_{key}.parquet
        │
        ▼
  [01_aqc1.py]  — 1차 자동 QC (물리 검사)
  zero / range / stuck / consistency / edge /
  spike(최대 10회 수렴) / roc / reference / vertical / vector_range
  → src/tmp/flags/{agency}/{station_id}/{YYYYMM}_flag.csv
    (컬럼: flag_aqc1, reason_aqc1)
        │
        ▼
  [02_aqc2.py]  — 2차 자동 QC (통계 검사)
  rolling 90d σ 클리핑 이상치 탐지
  → flag 파일에 flag_aqc2, reason_aqc2 추가
        │
        ▼
  [03_mqc.py]   — 수동 QC (이벤트 기반)
  mqc_events.toml에 정의된 기간·관측소·변수에 flag 부여
  → flag 파일에 flag_mqc, reason_mqc 추가
        │
        ▼
  [04_export.py]  — 최종 저장
  flag_final = max(flag_aqc1, flag_aqc2, flag_mqc) (severity 기준)
  → result/flag/{agency}/{station_id}/{yyyy}/*_qc_flag.csv
  → result/final/{agency}/{station_id}/{yyyy}/*_qc_final.csv
  (tmp/flags 삭제)
        │
        ▼
  [05_plot.py]       — 월별/연간 시각화
  [07_plot_multiyr.py] — 다년도 시각화
  → result/plots/.../
```

### 3.3 각 파이프라인 단계 상세

#### Step 00: `00_sort.py` — 정렬·표준화

| 항목 | 내용 |
|------|------|
| 입력 | 전처리 parquet (`/data/DATA/OBS/prc/{tidal,buoy}/{yyyy}/{yyyymmdd}.parquet`) |
| 출력 | `src/tmp/sorted/{dataset}/{agency}_{key}.parquet` |
| 처리 | 변수명 표준화(`var_aliases`), 결측 sentinel 제거(-999 등), UV 성분 도출, 중복 제거, station_id 패턴 검증 |
| 스킵 조건 | 해당 기간 데이터 이미 존재 시 건너뜀 |

Long format 컬럼: `time, agency, station_id, lat, lon, var_id, value, depth_m`

**NIFS 부이 수온 깊이 매핑** (`loader.py::apply_depth_mapping_nifs()`):

NIFS 부이는 동일 변수명 `temp`로 3개 수심의 수온을 전송한다. 로드 단계에서 `loader.py`의 `apply_depth_mapping_nifs()` 함수가 `depth_m` rank를 기준으로 표준 var_id를 부여한다:

| depth_m rank | 표준 var_id | 의미 |
|:---:|---|---|
| 가장 얕은 수심 (rank 1) | `sur_temp` | 표층수온 |
| 중간 수심 (rank 2) | `mid_temp` | 중층수온 |
| 가장 깊은 수심 (rank 3) | `bot_temp` | 저층수온 |

이 매핑 없이는 NIFS 수온 3개가 모두 `temp`로 중복 적재되어 수직 일관성 검사(`check_vertical`)가 동작하지 않는다.

#### Step 01: `01_aqc1.py` — 1차 자동 QC

**처리 순서** (변수 단위, 하나의 관측소 내 모든 변수를 순차 처리):

1. `zero` — Zero 검사
2. `range` — 물리 범위 검사 (계절별 포함)
3. `stuck` — 고착값 검사
4. `consistency` — 연동 변수 일관성 (reference 변수 먼저 처리 후)
5. `edge` — 갭 복귀 검사 (인접 월 buffer 포함)
6. `spike` — 급등락 검사 (수렴할 때까지 최대 10회 반복)
7. `roc` — 변화율 검사
8. `reference` — 기준 변수 비교 (tide_real vs tide_pre 등)
9. `vertical` — 수직층 일관성 (sur/mid/bot_temp)
10. `vector_range` — U-V 합성 크기 범위

**플래그 병합 원칙**: severity 높은 쪽이 이긴다

```
SEVERITY: MISSING(9) > BAD(3) > SUSPECT(2) > GOOD(1)
(주의: 코드 숫자 크기 ≠ severity 순서. 9가 최고 severity이나 이는 약속된 코드일 뿐이다)
```

#### Step 02: `02_aqc2.py` — 2차 자동 QC (rolling 통계)

- AQC1에서 BAD/MISSING으로 표시된 값은 NaN으로 마스킹 후 rolling 계산
- 인접 2개월 buffer 포함하여 경계 효과 방지
- 결과를 `flag_aqc2`, `reason_aqc2`로 저장

#### Step 03: `03_mqc.py` — 수동 QC

`meta/mqc_events.toml`에 정의된 이벤트(태풍, 장비 교체 등) 기간에 수동 flag 부여.

```toml
[[events]]
label       = "태풍 KHANUN"
start       = "2023-08-10T00:00:00"
end         = "2023-08-12T23:59:59"
agency      = "khoa"
station_ids = ["DT_0001"]
var_ids     = []          # 빈 리스트 = 전체 변수
flag        = 2           # suspect
reason      = "typhoon_KHANUN"
```

#### Step 04: `04_export.py` — 최종 저장

- `flag_final = max(flag_aqc1, flag_aqc2, flag_mqc)` (severity 기준)
- 연간 파일에 월 단위로 누적 (재실행 시 해당 기간만 교체)
- flag CSV(전체 컬럼) + final CSV(good+suspect만, 최소 컬럼)

#### Step 05: `05_plot.py` — 시각화

- 월별 PNG 또는 연간 PNG 생성
- 변수별 subplot, flag 색상 산포도 (good=녹, suspect=노랑, bad=빨강, missing=회색)
- 관측소별 TOML에서 y축 범위 오버라이드 가능

#### Step 07: `07_plot_multiyr.py` — 다년도 시각화

- 복수 연도의 flag CSV를 합산하여 단일 PNG
- 연도 경계 세로선 표시

---

## 4. Flag 체계

### 4.1 플래그 코드 및 Severity 순위 (통합 표)

> **주의**: 코드 숫자 크기 ≠ severity 순서. 9(MISSING)이 수치상 가장 크지만, 이는 약속된 코드이며 severity 순서는 아래 표의 "severity 순위" 열을 따른다.

| 코드 | 이름 | severity 순위 | 의미 |
|:----:|------|:---:|------|
| `9` | MISSING | 1위 (최고) | 결측값 (NaN). 어떤 검사도 덮어쓰지 않는다 |
| `3` | BAD | 2위 | 불량 데이터 (분석에서 제외) |
| `2` | SUSPECT | 3위 | 의심스러운 데이터 (사용 가능하나 주의) |
| `4` | INTERPOLATED | 4위 | 보간 데이터 (현재 미사용) |
| `1` | GOOD | 5위 | 정상 데이터 |
| `0` | UNSET | 6위 (최저) | 초기값 (처리 후 GOOD으로 전환) |

병합 기준: `flag_final = max(flag_aqc1, flag_aqc2, flag_mqc)` — severity가 더 높은 flag가 우선한다.

```
severity: MISSING(9) > BAD(3) > SUSPECT(2) > INTERPOLATED(4) > GOOD(1) > UNSET(0)
```

### 4.2 flag 컬럼 구조 (flag CSV)

```
time, agency, station_id, lat, lon, var_id, value, depth_m,
flag_final,
flag_aqc1, reason_aqc1,
flag_aqc2, reason_aqc2,
flag_mqc,  reason_mqc
```

---

## 5. QC 알고리즘 상세

### 5.1 Zero 검사 (`zero_check.py`)

**목적**: 센서 미수신 sentinel(0값)을 이상치로 처리

**알고리즘**:
```
정수형 데이터:
  value == 0 → BAD ("zero_fail(int)")

실수형 + single_fail=true (염분 등):
  value == 0 → BAD ("zero_fail(single)")

실수형 기본:
  연속 2개 이상 0 → BAD ("zero_fail(consec)")
```

**적용 변수**: `temp`, `sur_temp`, `mid_temp`, `bot_temp`, `sal`(single_fail=true)

---

### 5.2 물리 범위 검사 (`range_check.py`)

**목적**: 물리적으로 불가능한 값 제거

**알고리즘**:
```
value < min → BAD ("below_range(min)")
value > max → BAD ("above_range(max)")

계절별 narrowing (선택):
  해당 월이 계절 범위에 속하면:
    value < s_min → BAD ("below_seasonal_{label}(s_min)")
    value > s_max → BAD ("above_seasonal_{label}(s_max)")
```

**연중 고정 범위 (주요 변수)**:

| 변수 | min | max |
|------|-----|-----|
| `temp` / `sur_temp` | -2.0°C | 40.0°C |
| `mid_temp` | 0.0°C | 35.0°C |
| `bot_temp` | 0.0°C | 33.0°C |
| `sal` | 0.0 psu | 40.0 psu |
| `tide_real` | -200 cm | 1300 cm |
| `air_temp` | -20.0°C | 40.0°C |
| `air_pres` | 900.0 hPa | 1050.0 hPa |
| `air_humi` | 0.0% | 100.0% |
| `wind_speed` | 0.0 m/s | 75.0 m/s |
| `wave_h` | 0.0 m | 20.0 m |
| `current_speed` | 0.0 cm/s | 300.0 cm/s |

**염분 계절별 narrowing**:

| 계절 | 월 | min | max |
|------|---|-----|-----|
| 겨울 | 1, 2, 3 | 25.0 | 35.0 |
| 봄 | 4, 5, 6 | 24.0 | 35.0 |
| 여름 | 7, 8, 9 | 5.0 | 35.0 |
| 가을 | 10, 11, 12 | 20.0 | 35.0 |

---

### 5.3 고착값 검사 (`stuck_check.py`)

**목적**: 센서 동결·전송 오류로 동일 값이 반복되는 구간 탐지

**알고리즘**:
```
epsilon = 0.0 (기본; 완전히 동일한 값만 고착으로 간주)

연속 run 계산:
  이전 값이 BAD → run 리셋 (bad가 구간을 분리)
  |vals[i] - vals[i-1]| <= epsilon → run_len[i] = run_len[i-1] + 1
  else → run_len[i] = 1

  각 run의 전체 길이를 역방향 전파(max_run_len)

판정:
  max_run_len >= fail_count    → BAD     ("stuck_fail(run=N)")
  max_run_len >= suspect_count → SUSPECT ("stuck_suspect(run=N)")

skip_below_col 설정 시:
  skip_col의 값 < skip_below_value 이면 해당 시점 run 리셋 (무풍 시 wind_dir 고착 제외)
  단, skip_col 자체가 BAD이면 skip 면제 무효화
```

**주요 파라미터**:

| 변수 | suspect_count | fail_count |
|------|:---:|:---:|
| `temp` / `sur_temp` / `bot_temp` | 12h | 48h |
| `sal` | 24h | 168h (1주일) |
| `tide_real` | 12h | 36h |
| `wind_dir` | 16h | 24h (skip: wind_speed<1m/s) |
| `wave_h` | 24h | 99999 (fail 없음) |
| `air_humi` | 12h | 24h |

---

### 5.4 변화율 검사 (`roc_check.py`)

**목적**: 시간당 변화율이 물리적으로 불가능한 값 탐지

**알고리즘**:
```
BAD/MISSING 값을 건너뛰고 마지막 정상 이전값 p 탐색
dt = (t[i] - t[p]) / 3600.0  # 시간

diff_per_hour = |vals[i] - vals[p]| / dt  (linear)
              = circular_diff(vals[i], vals[p]) / dt  (circular)

diff_per_hour >= fail_per_hour    → BAD     ("roc_fail(X.X/h)")
diff_per_hour >= suspect_per_hour → SUSPECT ("roc_suspect(X.X/h)")
```

**적용 변수** (현재 `roc: false`인 변수가 많음):

| 변수 | suspect/h | fail/h | 활성 |
|------|:---------:|:------:|:----:|
| `tide_real` | 150 cm | 300 cm | false |
| `temp` / `sur_temp` | 3.0°C | 5.0°C | false |
| `bot_temp` | 1.5°C | 3.0°C | false |
| `sal` | 1.5 psu | 3.0 psu | false |

> **현재 상태**: 대부분 변수에서 비활성(false). spike 검사가 더 신뢰성 있다고 판단.

---

### 5.5 급등락 검사 / Spike (`spike_check.py`)

**목적**: 주변값 대비 급격히 이탈한 개별 값(spike) 탐지

**알고리즘**:
```
neighbor_count = 3 (기본; 좌/우 각 최대 3개)
max_gap_hours  = 6.0 (기본; 이 시간 내 이웃만 포함)

각 포인트 i에 대해:
  left_vals  = 좌측에서 최대 neighbor_count개 GOOD 값
               (max_gap_hours 이내, BAD/MISSING 건너뜀, 시간 초과 시 중단)
  right_vals = 우측에서 최대 neighbor_count개 GOOD 값

  all_neighbors = left_vals + right_vals
  if len(all_neighbors) < 2: continue  # 최소 2개 필요

  ref = mean(all_neighbors)
  d   = |vals[i] - ref|

  d >= fail    → BAD     ("spike_fail(d)")
  d >= suspect → SUSPECT ("spike_suspect(d)")

  판정 직후 flags_arr[i] 즉시 갱신
  (후속 이웃 탐색 시 해당 값 제외됨)

수렴 반복 (01_aqc1.py):
  최대 10회 반복; 결과가 변하지 않으면 조기 종료
  hard_bad = zero/range/stuck fail 값 (반복 내내 이웃 창에서 제외)
  SUSPECT는 GOOD으로 초기화하여 이웃으로 포함
```

**주요 파라미터**:

| 변수 | suspect | fail |
|------|:-------:|:----:|
| `temp` / `sur_temp` / `bot_temp` | 3.0°C | 7.0°C |
| `mid_temp` | 2.5°C | 8.0°C |
| `sal` | 5.0 psu | 10.0 psu |
| `air_temp` | 5.0°C | 8.0°C |
| `air_pres` | 10.0 hPa | 20.0 hPa |
| `wind_speed` | 30.0 m/s | 45.0 m/s |
| `wave_h` | 3.0 m | 5.0 m |
| `current_speed` | 50 cm/s | 100 cm/s |

**알려진 한계 — Spike Cascade**:

연속된 이상 블록(예: 급격한 수온 하강 구간)에서 cascade 오탐이 발생할 수 있다.

```
메커니즘:
  정상값 A (21:00) ─ 이웃에 판정 전 냉수 블록(19.5, 17.5, 18.4)이 포함
  → ref = mean([정상, 냉수, 냉수]) → ref 낮아짐
  → |A - ref| >= fail → A가 오탐(BAD)

완화 방법 (미구현):
  bilateral check: 좌/우 ref를 독립 계산, 양쪽 모두 초과 시만 BAD
```

---

### 5.6 Rolling 통계 검사 (`stat_check.py`)

**목적**: 90일 이동 평균/표준편차 기반 장기 클라이마톨로지 이탈 탐지

**알고리즘**:
```
window    = "2160h" (90일)
center    = True    (가운데 정렬)
min_periods = 100

# AQC1 BAD/MISSING → NaN 마스킹 후 통계 계산
ts_masked = series (BAD/MISSING는 NaN)

roll = ts_masked.rolling(window, center=True, min_periods=100)
roll_mean = roll.mean()
roll_std  = roll.std().clip(lower=min_std)  # 최소 표준편차 하한 적용

dev = |ts_masked - roll_mean| / roll_std

sigma clipping (1회):
  dev > fail_sigma → NaN
  재계산

판정:
  dev >= fail_sigma    → BAD     ("rolling_fail(X.Xσ)")
  dev >= suspect_sigma → SUSPECT ("rolling_suspect(X.Xσ)")

인접 2개월 buffer 포함(02_aqc2.py):
  경계 효과 방지를 위해 이전 2개월 + 이후 2개월 포함 후 현재 월만 추출
```

**min_std (최소 표준편차 하한값)**:

신호가 안정적일 때 표준편차가 0에 가까워지면 정상값도 오탐되는 문제를 방지한다.

| 변수 | min_std | 의미 |
|------|:-------:|------|
| `temp` / `sur_temp` | 0.5°C | 표층수온 일변동 하한 |
| `sal` | 0.5 psu | 염분 변동 하한 |
| `bot_temp` / `mid_temp` | 0.2°C | 저층/중층 안정 환경 |
| `air_pres` | 3.0 hPa | 기압 변동 하한 |
| `air_temp` | 1.5°C | 기온 변동 하한 |

**적용 변수**: `temp`, `sur_temp`, `mid_temp`, `bot_temp`, `sal`, `tide_real`, `air_temp`, `air_pres`

---

### 5.7 갭 복귀 검사 / Edge (`edge_check.py`)

**목적**: 데이터 공백(gap) 이후 복귀 segment 시작값의 내부 일관성 검사. 장비 재설치·케이블 재연결 직후 센서 안정화 이전의 이상값을 탐지한다.

**알고리즘**:
```
gap_min  = "24h" (기본; 이 이상의 공백이어야 검사 발동)
fwd_scan = "48h" (기본; 전방 탐색 범위)
n_start  = 3     (기본; segment 시작부 검사 개수)

segment 시작 위치 탐지:
  이전 유효값과 시간 차 >= gap_min → segment 시작
  (데이터셋 첫 번째 유효값도 포함)

각 segment에서 첫 n_start개 유효값 = a[0..n-1]

각 a[k]에 대해:
  b, c = a[k] 이후 fwd_scan 이내의 다음 유효값 최대 2개
         (NaN/BAD/MISSING 건너뜀)

  b, c 모두 없으면 skip

  ref = mean(b, c)   # b만 있으면 b 단독 사용
  d   = |a[k] - ref|

  d >= abs_fail    → BAD     ("edge_start_fail(d.dd)")
  d >= abs_suspect → SUSPECT ("edge_start_suspect(d.dd)")

월 경계 처리 (01_aqc1.py):
  이전 월 끝 fwd_scan시간 + 현재 월 + 다음 월 앞 fwd_scan시간을 합산
  → 경계 값도 정확히 검사
```

**특징**:
- **bwd(이전 값) 참조 완전 제거**: 공백 이전 값은 신뢰 불가 (장비 고장 가능성)
- **fwd 내부 일관성만**: 복귀 직후 값끼리만 비교 → 오탐 대폭 감소

**주요 파라미터**:

| 변수 | abs_fail | abs_suspect | gap_min |
|------|:--------:|:-----------:|:-------:|
| `temp` / `sur_temp` / `mid_temp` / `bot_temp` | 2.0°C | 1.0°C | 24h |
| `sal` | 5.0 psu | 2.0 psu | 24h |
| `tide_real` | 30 cm | 15 cm | 12h |
| `wave_h` | 2.0 m | 1.0 m | 24h |
| `air_temp` | 3.0°C | 2.0°C | 24h |
| `air_pres` | 5.0 hPa | 3.0 hPa | 24h |
| `wind_speed` / `wind_gust` | 5.0 m/s | 3.0 m/s | 24h |
| `current_speed` | 30 cm/s | 15 cm/s | 24h |

---

### 5.8 일관성 검사 (`consistency_check.py`)

**목적**: 연동 변수 간 물리적 일관성 확인

**규칙 1: 전파 (propagate_bad)**
```
참조 변수가 BAD이면 대상 변수도 bad/suspect로 표시
예: wind_speed BAD → wind_dir BAD
    wind_speed BAD → wind_gust SUSPECT
```

**규칙 2: 정온 시 비정상 양수**
```
ref_zero_threshold = T_ref
target_nonzero_threshold = T_tgt

ref_val < T_ref 이고 target_val > T_tgt → SUSPECT
예: wind_speed < 0.5 m/s (정온) 인데 wind_gust > 2.0 m/s → SUSPECT
```

**적용**:
- `wind_dir` ← `wind_speed` (propagate_bad)
- `wind_gust` ← `wind_speed` (propagate_bad + 정온 검사)

---

### 5.9 교차 검사 (`cross_check.py`)

**세 가지 검사 모듈**:

#### 5.9.1 Reference 검사 (`check_reference`)

기준 변수(예측값)와 실측값의 차이 비교.

```
diff = |series - ref_series|
ref가 BAD인 시점은 건너뜀

diff >= fail_threshold    → BAD     ("ref_fail(diff=X.X,ref_col)")
diff >= suspect_threshold → SUSPECT ("ref_suspect(diff=X.X,ref_col)")
```

**적용**: `tide_real` vs `tide_pre` (suspect=50cm, fail=150cm)

#### 5.9.2 수직 일관성 검사 (`check_vertical`)

수직층 간 온도 차 범위 검사.

```
diff = series - other_series

diff < min_diff → BAD ("vertical_low(other, diff=min_diff)")
diff > max_diff → BAD ("vertical_high(other, diff=max_diff)")
```

**적용**:

| 대상 | 비교 | min_diff | max_diff |
|------|------|:--------:|:--------:|
| `mid_temp` - `sur_temp` | sur_temp | -2.0°C | 8.0°C |
| `mid_temp` - `bot_temp` | bot_temp | -2.0°C | 6.0°C |
| `bot_temp` - `mid_temp` | mid_temp | -2.0°C | 5.0°C |
| `bot_temp` - `sur_temp` | sur_temp | -3.0°C | 10.0°C |

#### 5.9.3 벡터 크기 범위 검사 (`check_vector_range`)

U-V 성분 쌍의 합성 크기 범위 검사.

```
magnitude = sqrt(u² + v²)
magnitude < min → BAD
magnitude > max → BAD
```

---

## 6. 설정 파일 계층 구조

### 6.1 3단계 병합

```
qc_rules.toml          (기본값, 모든 변수의 베이스라인)
    ↓ deep_merge
meta/agencies/{agency}.toml   (기관별 오버라이드)
    ↓ deep_merge
meta/stations/{AGENCY}/{station_id}.toml  (관측소별 오버라이드)
```

각 단계에서 `override.variables.{var_id}` 섹션만 병합된다. 딥 머지이므로 지정한 키만 덮어쓰고 나머지는 상위 값을 유지한다.

### 6.2 qc_rules.toml 구조

```toml
[paths.{agency}.{dataset}]
raw = "/data/DATA/OBS/raw/{agency}/{dataset}"

[flag]
good=1, suspect=2, bad=3, interpolated=4, missing=9

[standardization]
var_aliases = {...}      # 원시 컬럼명 → 표준 var_id 매핑
missing_sentinels = [-999.0, -9999.0, 999.0, 9999.0]

[variables.{var_id}]
enable = true/false

[variables.{var_id}.enabled_tests]
zero=true/false, range=true/false, stuck=true/false,
roc=true/false, spike=true/false, rolling=true/false,
reference=true/false, vertical=true/false, edge=true/false,
consistency=true/false, vector_range=true/false

[variables.{var_id}.range]
min = ..., max = ...
[[variables.{var_id}.range.seasonal]]
label=..., months=[...], min=..., max=...

[variables.{var_id}.stuck.hourly]
suspect_count=..., fail_count=...

[variables.{var_id}.spike]
suspect=..., fail=...

[variables.{var_id}.rolling]
window="2160h", suspect_sigma=3.0, fail_sigma=5.0,
min_periods=100, min_std=...

[variables.{var_id}.edge]
n_start=3, abs_fail=..., abs_suspect=..., gap_min="24h"

[variables.{var_id}.reference]
column="tide_pre", suspect_threshold=..., fail_threshold=...

[[variables.{var_id}.vertical.rules]]
other="sur_temp", min_diff=..., max_diff=...

[variables.{var_id}.consistency]
reference_col="wind_speed", propagate_bad=true,
ref_zero_threshold=..., target_nonzero_threshold=...
```

### 6.3 관측소별 TOML 구조

```toml
[info]
name_k = "부산항"       # 한글 이름 (플롯 제목용)

[plot.ylim]
sur_temp = [-2.0, 35.0]   # 이 관측소 전용 y축 범위

[override.variables.sur_temp.spike]
fail = 10.0               # 이 관측소 spike fail 임계값만 변경
```

---

## 7. 변수별 활성 테스트 매트릭스

| 변수 | zero | range | stuck | edge | spike | rolling | roc | ref | vertical | consistency |
|------|:----:|:-----:|:-----:|:----:|:-----:|:-------:|:---:|:---:|:--------:|:-----------:|
| `temp` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| `sur_temp` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| `mid_temp` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | — |
| `bot_temp` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | — |
| `sal` | ✓(1) | ✓ | — | ✓ | — | ✓ | — | — | — | — |
| `tide_real` | — | ✓ | ✓ | ✓ | — | ✓ | — | ✓ | — | — |
| `tide_pre` | — | — | — | — | — | — | — | — | — | — |
| `wave_h` | — | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — |
| `air_temp` | — | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| `air_pres` | — | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| `air_humi` | — | ✓ | ✓ | — | — | — | — | — | — | — |
| `wind_speed` | — | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — |
| `wind_gust` | — | ✓ | ✓ | ✓ | ✓ | — | — | — | — | ✓ |
| `wind_dir` | — | ✓ | ✓(2) | — | — | — | — | — | — | ✓ |
| `current_speed` | — | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — |
| `current_dir` | — | ✓ | ✓ | — | — | — | — | — | — | — |
| `current_u/v` | — | — | ✓ | ✓ | ✓ | — | — | — | — | — |
| `wind_u/v` | — | — | ✓ | ✓ | ✓ | — | — | — | — | — |

> (1) `sal`: zero.single_fail=true (단독 0값도 BAD)  
> (2) `wind_dir` stuck: wind_speed < 1 m/s 시 skip (정온 제외)  
> `current_u/v`, `wind_u/v`: enable=false (QC 자체 비활성)

---

## 8. 표준화 및 데이터 규격

### 8.1 표준 var_id 목록

| 표준 var_id | 한글명 | 단위 |
|------------|--------|------|
| `temp` | 수온 | °C |
| `sur_temp` | 표층수온 | °C |
| `mid_temp` | 중층수온 | °C |
| `bot_temp` | 저층수온 | °C |
| `sal` | 염분 | psu |
| `tide_real` | 조위(실측) | cm |
| `tide_pre` | 조위(예측) | cm |
| `wave_h` | 유의파고 | m |
| `air_temp` | 기온 | °C |
| `air_pres` | 기압 | hPa |
| `air_humi` | 상대습도 | % |
| `wind_speed` | 풍속 | m/s |
| `wind_gust` | 순간최대풍속 | m/s |
| `wind_dir` | 풍향 | ° |
| `wind_u` | 풍속 U성분 | m/s |
| `wind_v` | 풍속 V성분 | m/s |
| `current_speed` | 유속 | cm/s |
| `current_dir` | 유향 | ° |
| `current_u` | 유속 U성분 | cm/s |
| `current_v` | 유속 V성분 | cm/s |

### 8.2 결측 Sentinel 값

다음 값은 로딩 시 NaN으로 교체된다:
`-999.0`, `-9999.0`, `999.0`, `9999.0`

### 8.3 시간 형식

- 내부 처리: UTC tz-aware (`pd.Timestamp`, `DatetimeIndex`)
- 저장 형식: `"YYYY-MM-DDTHH:MM:SSZ"` (ISO 8601 UTC)

### 8.4 데이터 간격

`infer_interval()` 함수가 중앙값으로 자동 추정:
- 10분 간격 → `"ten_min"`
- 1시간 간격 → `"hourly"`
- 기타 → `"other"`

---

## 9. 알고리즘 선택 근거 및 설계 원칙

### 9.1 AQC1/AQC2 분리 이유

- **AQC1 (물리 검사)**: 장기 통계 없이도 판정 가능한 즉각적 이상값 제거
- **AQC2 (통계 검사)**: AQC1에서 불량 데이터를 제거한 후 클라이마톨로지 기반 판정  
  → AQC1 없이 rolling을 하면 이상값이 평균/표준편차를 오염시켜 정상값 오탐 발생

### 9.2 Spike 수렴 반복의 이유

단일 패스로는 cascade 문제(앞의 BAD 판정이 뒤 값의 이웃을 오염)가 완전히 해소되지 않는다. 최대 10회 반복으로 이상 블록이 전파하는 상황을 점진적으로 해소한다.

### 9.3 Edge에서 bwd 제거 이유

공백 이전 값은 장비 이상으로 신뢰 불가. 이전 session 실험 결과 bwd 참조 시 오탐률이 높았음.  
→ fwd 전방값 b, c만으로 내부 일관성 판단.

### 9.4 min_std 도입 이유

해저 케이블 관측소처럼 수온이 오랜 기간 거의 변동 없는 경우, rolling std → 0 으로 수렴하여 모든 작은 변동도 5σ 이상으로 판정되는 문제 발생. min_std로 하한을 둬서 방지.

### 9.5 severity 병합 원칙

서로 다른 검사가 같은 포인트에 다른 등급을 부여할 때, 더 심각한 쪽이 승리한다. 단, 이미 MISSING인 포인트는 어떤 검사도 덮어쓰지 않는다.

---

## 10. 실행 예시

```bash
# 특정 월 전체 처리 (sort → aqc1 → aqc2 → mqc → export → plot)
bash run_qc.sh khoa tidal 202501

# AQC1부터 재처리 (sorted 파일 있음, QC 파라미터 변경 후)
bash run_qc.sh khoa tidal 2024 2024 --from-step 01

# 특정 관측소만
python src/libs/pipeline/01_aqc1.py --agency khoa --dataset tidal \
  --yyyymm 202401 --station DT_0001

# 다년도 플롯
python src/libs/pipeline/07_plot_multiyr.py \
  --agency khoa --start_year 2023 --end_year 2026

# 단일 관측소 연간 플롯
python src/libs/pipeline/05_plot.py \
  --agency khoa --station DT_0001 --year 2024
```

---

## 11. 주요 파일 참조 목록

| 역할 | 경로 |
|------|------|
| QC 파라미터 마스터 | `src/config/qc_rules.toml` |
| Flag 상수 정의 | `src/libs/utils/flag_io.py` |
| 설정 로더 (3단계 병합) | `src/libs/utils/config_loader.py` |
| 데이터 로더·표준화 | `src/libs/utils/loader.py` |
| Zero 검사 | `src/libs/checks/zero_check.py` |
| 물리 범위 검사 | `src/libs/checks/range_check.py` |
| 고착값 검사 | `src/libs/checks/stuck_check.py` |
| 변화율 검사 | `src/libs/checks/roc_check.py` |
| Spike 검사 | `src/libs/checks/spike_check.py` |
| Rolling 통계 검사 | `src/libs/checks/stat_check.py` |
| 갭 복귀 검사 | `src/libs/checks/edge_check.py` |
| 일관성 검사 | `src/libs/checks/consistency_check.py` |
| 교차/수직/벡터 검사 | `src/libs/checks/cross_check.py` |
| 정렬·표준화 | `src/libs/pipeline/00_sort.py` |
| 1차 자동 QC | `src/libs/pipeline/01_aqc1.py` |
| 2차 자동 QC | `src/libs/pipeline/02_aqc2.py` |
| 수동 QC | `src/libs/pipeline/03_mqc.py` |
| 최종 저장 | `src/libs/pipeline/04_export.py` |
| 월별/연간 시각화 | `src/libs/pipeline/05_plot.py` |
| 다년도 시각화 | `src/libs/pipeline/07_plot_multiyr.py` |

---

## 12. 운영 환경

- **conda 환경**: `/home/collect/appl/miniconda3/envs/dataenv/bin/python`
- **crontab**: 매일 06:30, flock 락파일 사용
  ```
  30 6 * * * flock -n /home/collect/collector/run/QC_obs.lock \
    /home/collect/collector/bin/runjob QC_obs /home/collect/QC/src \
    /bin/bash /home/collect/QC/src/run_qc.sh
  ```
- **락파일**: `/home/collect/collector/run/QC_obs.lock` (동시 실행 방지)
- **한글 폰트**: `/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc` (Noto Sans CJK JP — JP이지만 한글 글리프 포함)
- **진입점**: `bash /home/collect/QC/src/run_qc.sh [agency] [dataset] [date]`
