# -*- coding: utf-8 -*-
"""collect_test raw(wide, 2026) → 플랫폼 flag(long) CSV + 관측소 meta(toml) 변환.

수집된 raw 값을 그대로 표출하기 위한 변환:
  - wide(컬럼=변수) → long(행=var_id) 전개
  - 값이 -999/빈값 → flag_final=9(결측, value 빈칸), 그 외 → flag_final=1(수집됨=양호)
  - NIFS sur/mid/bot_temp 는 각 *_depth_m 를 depth_m 으로
  - time '2026-06-20 00:00:00' → '2026-06-20T00:00:00Z'
주의: 실제 QC 알고리즘(의심/불량 판정)은 미적용 — '수집 상태'(양호/결측) 표출용.
기존 sample_data 트리에 2026 연도로 '추가'(비파괴).
"""
import csv, os

CT = "/home/data1/geosr/mwcho/claude_agent/qc_webapp/collect_test/collect_test/out/raw"
SD = "/home/data1/geosr/mwcho/claude_agent/qc_webapp/sample_data/sample_data/home/collect/QC"
FLAG = os.path.join(SD, "result", "flag")
META = os.path.join(SD, "meta", "stations")
YEAR = "2026"

# (상대경로, agency)
DATASETS = [
    ("khoa/tidal/2026/tidal_202606.csv", "khoa"),
    ("khoa/buoy/2026/buoy_202606.csv",  "khoa"),
    ("kma/buoy/2026/buoy_202606.csv",   "kma"),
    ("nifs/buoy/2026/buoy_202606.csv",  "nifs"),
]
META_COLS = {"time", "station_id", "station_name_k", "lat", "lon", "station_type", "area_name"}
# NIFS 깊이 컬럼 → 대응 온도 var
NIFS_DEPTH = {"sur_temp": "sur_depth_m", "mid_temp": "mid_depth_m", "bot_temp": "bot_depth_m"}
HEADER = ["time", "agency", "station_id", "lat", "lon", "var_id", "value", "depth_m",
          "flag_final", "flag_aqc1", "reason_aqc1", "flag_aqc2", "reason_aqc2", "flag_mqc", "reason_mqc"]


def is_missing(s):
    s = (s or "").strip()
    if s == "":
        return True
    try:
        return float(s) == -999.0
    except ValueError:
        return True


def iso(t):
    return (t or "").strip().replace(" ", "T") + ("Z" if t and "Z" not in t else "")


names = {}   # (agency, station) -> name_k
total_files = total_rows = 0

for rel, agency in DATASETS:
    fp = os.path.join(CT, rel)
    if not os.path.isfile(fp):
        print("  [skip] 없음:", rel); continue
    with open(fp, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        cols = r.fieldnames
        # 값 변수 컬럼(메타·깊이 제외; 깊이는 따로 처리)
        depthcols = set(NIFS_DEPTH.values())
        valcols = [c for c in cols if c not in META_COLS and c not in depthcols]
        per_station = {}     # station -> list[output row]
        meta = {}            # station -> (name, lat, lon)
        for row in r:
            sid = (row.get("station_id") or "").strip()
            if not sid:
                continue
            t = iso(row.get("time"))
            lat = (row.get("lat") or "").strip()
            lon = (row.get("lon") or "").strip()
            if sid not in meta:
                meta[sid] = (row.get("station_name_k", "").strip(), lat, lon)
            out = per_station.setdefault(sid, [])
            for v in valcols:
                cell = row.get(v)
                miss = is_missing(cell)
                depth = ""
                if v in NIFS_DEPTH:
                    dv = row.get(NIFS_DEPTH[v])
                    depth = "" if is_missing(dv) else dv.strip()
                ff = 9 if miss else 1
                out.append([
                    t, agency, sid, lat, lon, v,
                    "" if miss else cell.strip(), depth,
                    ff, ff, ("missing" if miss else ""), 1, "", 0, "",
                ])
    # 관측소별 flag CSV + meta 기록
    for sid, rows in per_station.items():
        d = os.path.join(FLAG, agency, sid, YEAR)
        os.makedirs(d, exist_ok=True)
        outp = os.path.join(d, "%s_%s_%s_qc_flag.csv" % (agency, sid, YEAR))
        with open(outp, "w", encoding="utf-8-sig", newline="") as wf:
            w = csv.writer(wf)
            w.writerow(HEADER)
            w.writerows(rows)
        total_files += 1
        total_rows += len(rows)
        names[(agency, sid)] = meta[sid][0]
        # meta toml
        md = os.path.join(META, agency.upper())
        os.makedirs(md, exist_ok=True)
        nm = meta[sid][0] or sid
        with open(os.path.join(md, sid + ".toml"), "w", encoding="utf-8") as mf:
            mf.write('name_k = "%s"\n' % nm.replace('"', "'"))
    print("  [ok] %-12s 관측소 %3d개" % (rel.split("/2026")[0], len(per_station)))

print("== 완료: flag CSV %d개, long 행 %d, meta toml %d개 ==" % (total_files, total_rows, len(names)))
