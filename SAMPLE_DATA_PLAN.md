# 샘플 데이터 추출 플랜 — sample_data/ (G팀)

> 플랫폼(QC 대시보드·미니재현)을 팀에 공유하기 위해 server131 실데이터에서 추출한 샘플 세트의 **구성·추출·전달 계획**. (PLAN.md와 별개 문서)

## 1. 목적
- server131(`collect@fileserver`, 10.27.1.131)의 실데이터·실코드에서 **작은 샘플 세트**를 추출.
- 대시보드 팀이 바로 시각화·미니재현할 수 있도록 **입력 raw + QC 결과 + 코드/설정**을 한 묶음으로.
- 전체는 너무 큼(raw khoa/tidal 28GB, result 19GB) → 차원을 좁혀 추출.

## 2. 결정 사항
- **구성**: 결과 + 입력(미니재현) — flag/final 결과 + 필터된 raw + 코드/설정
- **범위**: 3기관 각 대표 1소 × **2025년**
- **구조**: `sample_data/` 폴더 아래에 server131 절대경로 트리를 **100% 미러**(선행 `/`만 제거)

| 기관 | 데이터셋 | 대표 관측소 | 비고 |
|------|----------|-------------|------|
| KHOA | tidal | `DT_0001` (인천) | 1분 간격 |
| KMA  | buoy  | `22003` | 시간 간격 |
| NIFS | buoy  | `bbbi5` | 시간 간격 |

## 3. 산출물 구조 (sample_data/ = 가상 루트)
```
sample_data/
├── README.md
├── data/DATA/OBS/raw/{khoa/tidal,kma/buoy,nifs/buoy}/2025/*.csv   # 입력 raw (대표소 필터)
└── home/collect/QC/
    ├── src/run_qc.sh, src/config/qc_rules.toml, src/libs/**       # QC 코드·설정
    ├── meta/agencies/*.toml, meta/stations/{KHOA,NIFS}/*.toml     # 메타
    └── result/{flag,final}/{기관}/{관측소}/2025/*.csv             # QC 결과
```
> 경로 매핑: 서버 `/X` → 로컬 `sample_data/X` (선행 슬래시만 제거, 그 외 동일).

## 4. 추출 방법 (서버 read-only — 서버엔 파일 안 만듦)
1. 대표소 raw·결과 존재 확인.
2. 로컬 트리 생성(`mkdir -p`).
3. **raw 필터**: 각 기관 대표소 × 2025 각 월 →
   `ssh server131 "awk -F, 'NR==1 || \$2==\"<station>\"' <raw월파일>" > <로컬 대상>`
   (2번째 컬럼 정확 매칭 → 헤더 보존, `-999` 쓰레기 행 자연 제외)
4. **result flag/final · config · libs · meta**: `rsync -a`로 해당 경로만 미러(`--exclude=__pycache__`).
5. 서버 `.bak` 백업파일 제거(노이즈).
6. `sample_data/README.md` 작성(출처·관측소·기간·컬럼·플래그·재현법).
7. `sample_data.zip` 생성(`python3 -m zipfile -c`, `zip` 미설치 대응).

## 5. 공개/보안 처리 (team-g는 PUBLIC)
- 관측 원본을 PUBLIC 저장소에 commit 금지 → 루트 `.gitignore`에 **`sample_data/`·`sample_data.zip`** 등록.
- 전달은 **`sample_data.zip` 사내 채널 공유**, 또는 팀원 server131 접근 시 추출 재현. (CLAUDE.md 규칙 6)

## 6. 실행 결과 (완료)
- 총 **92MB / 74파일**, 전달용 **`sample_data.zip` 9.1MB**.
- 용량 내역: khoa 68.3MB(raw 56.4+flag 6.7+final 5.1) / kma 11.9MB / nifs 3.9MB / config·libs·meta 0.4MB.
- 검증 통과: raw는 각 기관 단일 station, flag 분포 정상(khoa good 85,023·suspect 291·bad 26·missing 9,447).
- 기록: `submit/PROCESS_LOG.md` [#5] · `evidence/timestamps.txt` 갱신.

## 7. 전달 방법 (팀원 수령)
- **① zip 직접 공유(권장)**: `sample_data.zip`(9.1MB)을 사내 메신저·메일·공유드라이브로 전달 → 팀원이 압축 해제, `sample_data/`를 루트로 사용.
- **② server131 접근 가능 시**: 추출 스크립트를 저장소에 commit해 각자 재현(`extract_sample.sh`).
- **③ 비공개 저장소**: team-g를 private 전환 또는 별도 private repo에 데이터 push.

## 8. 데이터 형식 메모
- raw(wide): `time, station_id, station_name_k, lat, lon, temp, sal, tide_real, tide_pre, wave_h, air_temp, air_pres, wind_dir, wind_speed, wind_u, wind_v, station_type, area_name` / sentinel `-999`
- flag(long): `…, value, flag_final, flag_aqc1, reason_aqc1, flag_aqc2, reason_aqc2, flag_mqc, reason_mqc`
- final(long): `time, agency, station_id, lat, lon, var_id, value` (good+suspect만)
- 플래그(server131 config): 1 GOOD / 2 SUSPECT / 3 BAD / **4 INTERPOLATED** / 9 MISSING, `flag_final = max(…)`
