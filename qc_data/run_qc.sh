#!/usr/bin/env bash
# run_qc.sh — QC 파이프라인 실행 진입점
#
# 사용법:
#   bash src/run_qc.sh                                     # 인자 없음 → 전날 일별 자동 실행
#   bash src/run_qc.sh <agency> <dataset> <날짜> [끝날짜] [옵션]
#
# agency  : khoa | kma | nifs | all
# dataset : tidal | buoy | all
# 날짜    : 20260618             (일별 — YYYYMMDD)
#           20250101 20250331    (일자범위 — 시작YYYYMMDD 끝YYYYMMDD, 일단위 트리밍)
#           202501               (단월 — YYYYMM)
#           2025                 (연간 — 1~12월 전체)
#           2023 2025            (연범위 — 2023~2025년 전체)
#
# 옵션:
#   --station <ID>   단일 관측소만 처리
#   --step <00~05>   특정 단계만 실행 (일별 모드 제외)
#   --plotmerge      연범위 실행 후 다년도 병합 플롯 생성
#   --err            합성 에러 테스트데이터(test/raw)로 실행 → 결과는 err_result/ 에 생성
#                    (test/raw에 해당 월이 있으면 재사용, 없으면 실데이터에 에러 주입해 생성)
#
# 예시:
#   bash src/run_qc.sh                                     # cron 전날 일별 자동
#   bash src/run_qc.sh khoa tidal 20260618                 # 일별
#   bash src/run_qc.sh khoa tidal 20250101 20250331        # 일자범위(일단위)
#   bash src/run_qc.sh khoa tidal 20250101 20250331 --err  # 에러주입 테스트 → err_result/
#   bash src/run_qc.sh khoa tidal 202501                   # 단월
#   bash src/run_qc.sh khoa tidal 2025                     # 2025 연간
#   bash src/run_qc.sh khoa tidal 2023 2025                # 2023~2025 연범위
#   bash src/run_qc.sh all  all   2023 2025 --plotmerge    # 전체 연범위 + 병합 플롯

set -euo pipefail

# ── 기관별 데이터셋 정의 ──────────────────────────────────────────────
declare -A AGENCY_DATASETS
AGENCY_DATASETS[khoa]="tidal buoy"
AGENCY_DATASETS[kma]="buoy"
AGENCY_DATASETS[nifs]="buoy"
ALL_AGENCIES="khoa kma nifs"

# ── 인자 파싱 ────────────────────────────────────────────────────────
# 인자 없으면: 전날 날짜로 all all YYYYMMDD 자동 실행
if [[ $# -eq 0 ]]; then
    AGENCY_ARG="all"
    DATASET_ARG="all"
    DATE_ARG="$(date -d 'yesterday' +%Y%m%d)"
    echo "[auto] 인자 없음 → 전날 일별 모드: all / all / ${DATE_ARG}"
elif [[ $# -eq 1 ]]; then
    echo "사용법: bash src/run_qc.sh [agency dataset [날짜]] [옵션]"; exit 1
elif [[ $# -eq 2 || ( $# -ge 3 && "$3" == --* ) ]]; then
    # 날짜 생략 또는 3번째 인자가 옵션(--) → 전날 자동
    AGENCY_ARG="$1"
    DATASET_ARG="$2"
    DATE_ARG="$(date -d 'yesterday' +%Y%m%d)"
    shift 2 || true
    echo "[auto] 날짜 미지정 → 전날 일별 모드: ${AGENCY_ARG} / ${DATASET_ARG} / ${DATE_ARG}"
else
    AGENCY_ARG="$1"
    DATASET_ARG="$2"
    DATE_ARG="$3"
    shift 3 || true
fi

STATION_ARG=""
STEP=""
FROM_STEP=""

# 4번째 인자: 4자리=끝연도(연범위), 8자리=끝일자(일자범위), 아니면 옵션
END_YEAR_ARG=""
END_DATE_ARG=""
if [[ $# -gt 0 && "$1" =~ ^[0-9]{8}$ ]]; then
    END_DATE_ARG="$1"
    shift
elif [[ $# -gt 0 && "$1" =~ ^[0-9]{4}$ ]]; then
    END_YEAR_ARG="$1"
    shift
fi

PLOTMERGE=0
ERR_MODE=0
ERR_THRESHOLD="0.005"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --station)   STATION_ARG="--station $2"; shift 2 ;;
        --step)      STEP="$2";                  shift 2 ;;
        --from-step) FROM_STEP="$2";             shift 2 ;;
        --plotmerge) PLOTMERGE=1;                shift   ;;
        --err)       ERR_MODE=1;                 shift   ;;
        --err-threshold) ERR_THRESHOLD="$2";     shift 2 ;;
        *) echo "알 수 없는 인자: $1"; exit 1 ;;
    esac
done

# ── 연도 목록 확장 ───────────────────────────────────────────────────
YEARS=()
if [[ "${#DATE_ARG}" -eq 4 ]]; then
    START_YEAR="$DATE_ARG"
    if [[ -n "$END_YEAR_ARG" ]]; then
        for (( y=START_YEAR; y<=END_YEAR_ARG; y++ )); do
            YEARS+=("$y")
        done
    else
        YEARS=("$START_YEAR")
    fi
fi

# YYYYMM 시작~끝 월 목록 확장 헬퍼
expand_months() {  # $1=startYYYYMM $2=endYYYYMM
    local cy cm ey em
    cy=$((10#${1:0:4})); cm=$((10#${1:4:2}))
    ey=$((10#${2:0:4})); em=$((10#${2:4:2}))
    while (( cy < ey || (cy == ey && cm <= em) )); do
        printf '%04d%02d\n' "$cy" "$cm"
        cm=$((cm + 1)); if (( cm > 12 )); then cm=1; cy=$((cy + 1)); fi
    done
}

# ── 날짜 모드 판별 ───────────────────────────────────────────────────
# RANGE_MODE=1 : 8자리+8자리 — 일자범위(일단위 트리밍), 월별 파이프라인으로 처리
# DAILY_MODE=1 : 8자리 YYYYMMDD — 하루치 incremental QC
# YEAR_MODE=1  : 4자리 YYYY     — 연간/연범위 재처리
# YEAR_MODE=0  : 6자리 YYYYMM   — 단월 재처리
DAILY_MODE=0
YEAR_MODE=0
RANGE_MODE=0
YYYYMM_LIST=()

if [[ "${#DATE_ARG}" -eq 8 && -n "$END_DATE_ARG" ]]; then
    # 일자범위 모드 — 시작·끝 일자 사이를 일단위로 트리밍
    if [[ "$END_DATE_ARG" < "$DATE_ARG" ]]; then
        echo "날짜 범위 오류: 끝일자($END_DATE_ARG)가 시작일자($DATE_ARG)보다 빠릅니다."
        exit 1
    fi
    RANGE_MODE=1
    while IFS= read -r ym; do YYYYMM_LIST+=("$ym"); done \
        < <(expand_months "${DATE_ARG:0:6}" "${END_DATE_ARG:0:6}")
    export QC_RANGE_START="$DATE_ARG"
    export QC_RANGE_END="$END_DATE_ARG"
    echo "[range] 일자범위 모드: ${DATE_ARG} ~ ${END_DATE_ARG}  (월: ${YYYYMM_LIST[*]})"
elif [[ "${#DATE_ARG}" -eq 8 ]]; then
    DAILY_MODE=1
    YYYYMMDD_ARG="$DATE_ARG"
    YYYYMM_ARG="${DATE_ARG:0:6}"
    YYYY_ARG="${DATE_ARG:0:4}"
elif [[ "${#DATE_ARG}" -eq 4 ]]; then
    YEAR_MODE=1
    for yr in "${YEARS[@]}"; do
        for mm in 01 02 03 04 05 06 07 08 09 10 11 12; do
            YYYYMM_LIST+=("${yr}${mm}")
        done
    done
elif [[ "${#DATE_ARG}" -eq 6 ]]; then
    YYYYMM_LIST=("$DATE_ARG")
else
    echo "날짜 형식 오류: '$DATE_ARG' — YYYYMMDD(8자리), YYYYMM(6자리), YYYY(4자리)를 입력하세요."
    exit 1
fi

export YEAR_MODE DAILY_MODE

# ── 기관 목록 확장 ───────────────────────────────────────────────────
if [[ "$AGENCY_ARG" == "all" ]]; then
    AGENCIES=($ALL_AGENCIES)
else
    AGENCIES=("$AGENCY_ARG")
fi

# ── 경로·환경 ────────────────────────────────────────────────────────
QC_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="/home/collect/appl/miniconda3/envs/dataenv/bin/python"

# ── 실행 프로파일: --err 이면 입력 test/raw, 출력 err_result/ 로 분리 ──
if [[ "$ERR_MODE" == "1" ]]; then
    export QC_PROFILE="err"
    echo "[err] 에러검증 모드: 입력 test/raw, 출력 err_result/  (임계 ${ERR_THRESHOLD})"
fi

# 합성 에러 테스트데이터 보장 (test/raw에 있으면 재사용, 없으면 생성)
ensure_err_raw() {  # $1=agency $2=dataset $3=yyyymm
    $PYTHON "$QC_ROOT/src/libs/tools/make_err_data.py" \
        --agency "$1" --dataset "$2" --yyyymm "$3" || \
        echo "[WARN] 합성 에러 데이터 생성 실패: $1/$2/$3"
}

declare -A STEP_FILES
STEP_FILES[00]="00_sort.py"
STEP_FILES[01]="01_aqc1.py"
STEP_FILES[02]="02_aqc2.py"
STEP_FILES[03]="03_mqc.py"
STEP_FILES[04]="04_export.py"
STEP_FILES[05]="05_plot.py"

# ── 일별 파이프라인 ──────────────────────────────────────────────────
run_daily_pipeline() {
    local agency="$1" dataset="$2" yyyymmdd="$3"
    local yyyy="${yyyymmdd:0:4}"
    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "  DAILY  ${agency} / ${dataset} / ${yyyymmdd}"
    echo "════════════════════════════════════════════════════════"

    echo "── STEP 00  ${agency}/${dataset}/${yyyymmdd} ──"
    $PYTHON "$QC_ROOT/src/libs/pipeline/00_sort.py" \
        --agency "$agency" --dataset "$dataset" --yyyymmdd "$yyyymmdd"

    echo "── STEP 01  ${agency}/${dataset}/${yyyymmdd} ──"
    $PYTHON "$QC_ROOT/src/libs/pipeline/01_aqc1.py" \
        --agency "$agency" --dataset "$dataset" --yyyymmdd "$yyyymmdd" \
        $STATION_ARG

    echo "── STEP 02  ${agency}/${dataset}/${yyyymmdd} ──"
    $PYTHON "$QC_ROOT/src/libs/pipeline/02_aqc2.py" \
        --agency "$agency" --dataset "$dataset" --yyyymmdd "$yyyymmdd" \
        $STATION_ARG

    echo "── STEP 03  ${agency}/${dataset}/${yyyymmdd} ──"
    $PYTHON "$QC_ROOT/src/libs/pipeline/03_mqc.py" \
        --agency "$agency" --dataset "$dataset" --yyyymmdd "$yyyymmdd" \
        $STATION_ARG

    echo "── STEP 04  ${agency}/${dataset}/${yyyymmdd} ──"
    $PYTHON "$QC_ROOT/src/libs/pipeline/04_export.py" \
        --agency "$agency" --dataset "$dataset" --yyyymmdd "$yyyymmdd" \
        $STATION_ARG

    echo "  DONE   ${agency} / ${dataset} / ${yyyymmdd}"
}

# ── 단일 step 실행 ───────────────────────────────────────────────────
run_step() {
    local step="$1" agency="$2" dataset="$3" yyyymm="$4"
    local fname="${STEP_FILES[$step]:-}"
    [[ -z "$fname" ]] && { echo "알 수 없는 step: $step (00~05 중 선택)"; exit 1; }

    # 일자범위/err 모드는 sorted를 새로 써야 하므로 bash 레벨 skip 비활성
    if [[ "$step" == "00" && -n "$STATION_ARG" \
          && "$RANGE_MODE" != "1" && "$ERR_MODE" != "1" ]]; then
        local sorted_path="$QC_ROOT/src/tmp/sorted/$dataset/${agency}_${yyyymm}.csv"
        if [[ -f "$sorted_path" ]]; then
            echo ""
            echo "── STEP 00 건너뜀 (sorted 파일 존재, --station 지정됨)  ${agency}/${dataset}/${yyyymm} ──"
            return 0
        fi
    fi

    echo ""
    echo "── STEP ${step} (${fname})  ${agency}/${dataset}/${yyyymm} ──"
    if [[ "$step" == "00" ]]; then
        $PYTHON "$QC_ROOT/src/libs/pipeline/$fname" \
            --agency  "$agency"  \
            --dataset "$dataset" \
            --yyyymm  "$yyyymm"
    else
        $PYTHON "$QC_ROOT/src/libs/pipeline/$fname" \
            --agency  "$agency"  \
            --dataset "$dataset" \
            --yyyymm  "$yyyymm"  \
            $STATION_ARG
    fi
}

# ── 단일 월 파이프라인 실행 ──────────────────────────────────────────
run_pipeline() {
    local agency="$1" dataset="$2" yyyymm="$3"
    # err 모드: 입력 합성 데이터 보장 (있으면 재사용)
    if [[ "$ERR_MODE" == "1" ]]; then
        ensure_err_raw "$agency" "$dataset" "$yyyymm"
    fi
    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "  START  ${agency} / ${dataset} / ${yyyymm}"
    echo "════════════════════════════════════════════════════════"
    echo '            |\__/,|   (\ '
    echo '  QC CAT  _.|o o  |_   ) )'
    echo '---------(((---(((----------'
    echo ""

    if [[ -n "$STEP" ]]; then
        run_step "$STEP" "$agency" "$dataset" "$yyyymm"
    elif [[ -n "$FROM_STEP" ]]; then
        local started=0
        for st in 00 01 02 03 04 05; do
            [[ "$st" == "$FROM_STEP" ]] && started=1
            [[ "$started" == "1" ]] && run_step "$st" "$agency" "$dataset" "$yyyymm"
        done
    elif [[ "$YEAR_MODE" == "1" ]]; then
        run_step "00" "$agency" "$dataset" "$yyyymm"
        run_step "01" "$agency" "$dataset" "$yyyymm"
        run_step "02" "$agency" "$dataset" "$yyyymm"
        run_step "03" "$agency" "$dataset" "$yyyymm"
        run_step "04" "$agency" "$dataset" "$yyyymm"
    else
        run_step "00" "$agency" "$dataset" "$yyyymm"
        run_step "01" "$agency" "$dataset" "$yyyymm"
        run_step "02" "$agency" "$dataset" "$yyyymm"
        run_step "03" "$agency" "$dataset" "$yyyymm"
        run_step "04" "$agency" "$dataset" "$yyyymm"
        run_step "05" "$agency" "$dataset" "$yyyymm"
    fi
    echo "  DONE   ${agency} / ${dataset} / ${yyyymm}"
}

# ── 일별 모드 ───────────────────────────────────────────────────────
if [[ "$DAILY_MODE" == "1" ]]; then
    for agency in "${AGENCIES[@]}"; do
        if [[ "$DATASET_ARG" == "all" ]]; then
            IFS=" " read -ra datasets <<< "${AGENCY_DATASETS[$agency]:-}"
        else
            datasets=("$DATASET_ARG")
        fi
        for dataset in "${datasets[@]}"; do
            run_daily_pipeline "$agency" "$dataset" "$YYYYMMDD_ARG" || \
                echo "[WARN] ${agency}/${dataset}/${YYYYMMDD_ARG} 실패 — 계속 진행"
        done
    done

    # YTD 연간 플롯 덮어쓰기 (연초~어제까지 누적)
    echo ""
    echo "── YTD 연간 플롯 갱신  ${YYYY_ARG} ──"
    for agency in "${AGENCIES[@]}"; do
        $PYTHON "$QC_ROOT/src/libs/pipeline/05_plot.py" \
            --agency "$agency" --year "$YYYY_ARG" \
            $STATION_ARG || \
            echo "[WARN] YTD 플롯 실패: ${agency}/${YYYY_ARG}"
    done

    echo ""
    echo "══════════════════════════════════════════════════"
    echo "  일별 QC 완료  ${YYYYMMDD_ARG}"
    echo "══════════════════════════════════════════════════"
    exit 0
fi

# ── 특수: step=05 + 연도 → 연간 플롯만 ──────────────────────────────
if [[ "$STEP" == "05" && "$YEAR_MODE" == "1" ]]; then
    for agency in "${AGENCIES[@]}"; do
        if [[ "$DATASET_ARG" == "all" ]]; then
            IFS=" " read -ra datasets <<< "${AGENCY_DATASETS[$agency]:-}"
        else
            datasets=("$DATASET_ARG")
        fi
        for dataset in "${datasets[@]}"; do
            for yr in "${YEARS[@]}"; do
                echo ""
                echo "── STEP 05 (05_plot.py)  ANNUAL  ${agency}/${dataset}/${yr} ──"
                $PYTHON "$QC_ROOT/src/libs/pipeline/05_plot.py" \
                    --agency  "$agency"  \
                    --dataset "$dataset" \
                    --year    "$yr"      \
                    $STATION_ARG
            done
        done
    done
    echo ""
    echo "══════════════════════════════════════════════════"
    echo "  전체 완료"
    echo "══════════════════════════════════════════════════"
    exit 0
fi

# ── 메인 루프 ────────────────────────────────────────────────────────
for agency in "${AGENCIES[@]}"; do
    if [[ "$DATASET_ARG" == "all" ]]; then
        IFS=" " read -ra datasets <<< "${AGENCY_DATASETS[$agency]:-}"
        if [[ ${#datasets[@]} -eq 0 ]]; then
            echo "[skip] $agency: 정의된 데이터셋 없음"
            continue
        fi
    else
        datasets=("$DATASET_ARG")
    fi

    for dataset in "${datasets[@]}"; do
        if [[ "$YEAR_MODE" == "1" ]]; then
            # 연간/연범위 모드: 연도별로 12개월 처리 후 연간 합산·플롯
            for yr in "${YEARS[@]}"; do
                echo ""
                echo "████████████████████████████████████████████████████████"
                echo "  YEAR  ${agency} / ${dataset} / ${yr}"
                echo "████████████████████████████████████████████████████████"

                for mm in 01 02 03 04 05 06 07 08 09 10 11 12; do
                    run_pipeline "$agency" "$dataset" "${yr}${mm}" || \
                        echo "[WARN] ${agency}/${dataset}/${yr}${mm} 실패 — 계속 진행"
                done

                echo ""
                echo "── 연간 합산 CSV  ${agency}/${dataset}/${yr} ──"
                $PYTHON "$QC_ROOT/src/libs/pipeline/04_export.py" \
                    --agency "$agency" --dataset "$dataset" --year "$yr" $STATION_ARG || \
                    echo "[WARN] 연간 합산 실패: ${agency}/${dataset}/${yr}"

                echo ""
                echo "── 연간 플롯  ${agency}/${dataset}/${yr} ──"
                $PYTHON "$QC_ROOT/src/libs/pipeline/05_plot.py" \
                    --agency "$agency" --dataset "$dataset" --year "$yr" $STATION_ARG || \
                    echo "[WARN] 연간 플롯 실패: ${agency}/${dataset}/${yr}"

                echo ""
                echo "  YEAR DONE  ${agency} / ${dataset} / ${yr}"
            done
        else
            # 단월 모드
            for yyyymm in "${YYYYMM_LIST[@]}"; do
                run_pipeline "$agency" "$dataset" "$yyyymm" || \
                    echo "[WARN] ${agency}/${dataset}/${yyyymm} 실패 — 계속 진행"
            done
        fi
    done
done

# ── 이상치 부족 자동 점검 → 합성 테스트데이터 준비 (err 모드/일별 제외) ──
if [[ "$ERR_MODE" != "1" && "$DAILY_MODE" != "1" ]]; then
    declare -A _YRS=()
    if [[ "$YEAR_MODE" == "1" ]]; then
        for y in "${YEARS[@]}"; do _YRS[$y]=1; done
    else
        for ym in "${YYYYMM_LIST[@]}"; do _YRS[${ym:0:4}]=1; done
    fi
    GEN_ANY=0
    for agency in "${AGENCIES[@]}"; do
        if [[ "$DATASET_ARG" == "all" ]]; then
            IFS=" " read -ra _ds <<< "${AGENCY_DATASETS[$agency]:-}"
        else
            _ds=("$DATASET_ARG")
        fi
        for dataset in "${_ds[@]}"; do
            for yr in "${!_YRS[@]}"; do
                echo ""
                echo "── 이상치 점검  ${agency}/${dataset}/${yr} ──"
                VERDICT="$($PYTHON "$QC_ROOT/src/libs/tools/anomaly_summary.py" \
                    --agency "$agency" --dataset "$dataset" --year "$yr" \
                    --threshold "$ERR_THRESHOLD" | tee /dev/stderr \
                    | grep '^VERDICT:' | awk '{print $2}')" || VERDICT=""
                if [[ "$VERDICT" == "TOO_FEW" ]]; then
                    echo "[err] 이상치가 임계 미만 — 합성 테스트데이터 생성(test/raw)"
                    if [[ "$YEAR_MODE" == "1" ]]; then
                        for mm in 01 02 03 04 05 06 07 08 09 10 11 12; do
                            ensure_err_raw "$agency" "$dataset" "${yr}${mm}"
                        done
                    else
                        for ym in "${YYYYMM_LIST[@]}"; do
                            [[ "${ym:0:4}" == "$yr" ]] && ensure_err_raw "$agency" "$dataset" "$ym"
                        done
                    fi
                    GEN_ANY=1
                fi
            done
        done
    done
    if [[ "$GEN_ANY" == "1" ]]; then
        echo ""
        echo "[안내] 이상치가 적어 합성 에러 데이터를 test/raw에 준비했습니다."
        echo "       동일 명령에 --err 를 붙여 재실행하면 err_result/ 에 에러검증 결과가 생성됩니다."
        echo "       예: bash run_qc.sh ${AGENCY_ARG} ${DATASET_ARG} ${DATE_ARG} ${END_DATE_ARG:-} --err"
    fi
fi

# ── --plotmerge: 다년도 병합 플롯 ──────────────────────────────────────
if [[ "$PLOTMERGE" == "1" ]]; then
    if [[ "$YEAR_MODE" == "1" ]]; then
        START_YR="${YEARS[0]}"
        END_YR="${YEARS[-1]}"
    else
        # daily/monthly 모드: 데이터 존재 첫 연도 ~ 현재 연도
        START_YR="2023"
        END_YR="$(date +%Y)"
    fi
    for agency in "${AGENCIES[@]}"; do
        echo ""
        echo "── 다년도 병합 플롯  ${agency}  ${START_YR}~${END_YR} ──"
        $PYTHON "$QC_ROOT/src/libs/pipeline/07_plot_multiyr.py" \
            --agency     "$agency"     \
            --start_year "$START_YR"  \
            --end_year   "$END_YR"    \
            $STATION_ARG
    done
fi

echo ""
echo "══════════════════════════════════════════════════"
echo "  전체 완료"
echo "══════════════════════════════════════════════════"
