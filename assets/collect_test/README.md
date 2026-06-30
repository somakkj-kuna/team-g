# collect_test — 해커톤 수집 개선 샌드박스

- 목적: 해커톤에서 **수정한 것**과 운영(`collector/collect/obs`)의 **기존 상태**를 분리.
- 원본: `/home/collect/collector/collect/obs/{khoa,kma,nifs}`
- 복사일: 2026-06-30
- 복사 시 제외: `gshhg`(HF 해안선 541M), `__pycache__`, `*.pyc`, `*.bak*`
- 대상 데이터셋: KHOA tidal · KHOA buoy · KMA buoy · NIFS buoy (3 buoy + 1 tidal)
- output 경로: 테스트 격리를 위해 각 config `output_root`를 `collect_test/out/raw/...`(샌드박스)로 변경함. 운영 반영 시 `/data/DATA/OBS/raw/...`로 원복.

## Git 업로드 제외 (보안)
**서비스키 보안 때문에** 아래는 공개 저장소(PUBLIC)에 올리지 않고 `.gitignore`로 제외함:
- `obs/khoa/config/khoa_config.toml`, `obs/kma/config/kma_config.toml`, `obs/kma/config/aws_config.toml`
  — **API 서비스 키 포함**이라 git 업로드 제외.
- `out/` — 32M **미공개 관측데이터**(공개 repo 부적합).

→ 클론 후 수집기를 실제로 돌리려면 위 config 3개를 **본인 API 서비스 키로** 다시 채워야 함
  (키 외 나머지 설정·정점목록·매핑은 동일 구조).
