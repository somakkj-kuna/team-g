# collect_test — 해커톤 수집 개선 샌드박스

- 목적: 해커톤에서 **수정한 것**과 운영(`collector/collect/obs`)의 **기존 상태**를 분리.
- 원본: `/home/collect/collector/collect/obs/{khoa,kma,nifs}`
- 복사일: 2026-06-30
- 제외: `gshhg`(HF 해안선 541M), `__pycache__`, `*.pyc`, `*.bak*`
- 대상 데이터셋: KHOA tidal · KHOA buoy · KMA buoy · NIFS buoy (3 buoy + 1 tidal)
- 주의: 각 config의 output 경로가 아직 **운영 경로(/data/DATA/OBS/raw/...)** 를 가리킴.
  테스트 실행 전 반드시 테스트 출력 경로로 변경할 것.
