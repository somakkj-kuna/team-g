# -*- coding: utf-8 -*-
"""전 관측소 카탈로그(catalog.json) 사전계산.

대규모(수백 관측소)에서 /api/catalog 가 매번 전체 행을 적재하지 않도록,
관측소별 (이름·위경도·해역·변수목록)만 추출해 catalog.json 으로 저장한다.
data.py(list_all_stations/station_meta/station_name)가 있으면 이를 우선 사용.
데이터가 바뀌면 다시 실행할 것.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import data as D
import variables as V

# 강제 재스캔: 기존 catalog.json/summary.json 제거 + 캐시 리셋
for p in (D.CATALOG_JSON, D.SUMMARY_JSON):
    if os.path.exists(p):
        os.remove(p)
D._catalog_cache = None
D._summary_cache = None

out = []
summary = {}     # agency -> {n_stations,n_vars,total,retained,flagged}
for agency in D.list_agencies():
    agg = {"n_stations": 0, "n_vars": 0, "total": 0, "retained": 0, "flagged": 0}
    for st in D.list_stations(agency):
        meta = D.station_meta(agency, st)               # catalog 없음 → 행 스캔
        vs = D.variable_status(agency, st)              # 변수별 카운트(같은 행 캐시 재사용)
        collected = [v for v in vs if v["collected"]]
        vlist = [{"key": v["key"], "name": v["name"], "unit": v["unit"]} for v in collected]
        out.append({
            "agency": agency, "agencyName": D.agency_name(agency),
            "station": st, "name": meta["name"],
            "lat": meta["lat"], "lon": meta["lon"],
            "region": D.station_region(meta["lat"], meta["lon"]),
            "vars": vlist,
        })
        agg["n_stations"] += 1
        agg["n_vars"] = max(agg["n_vars"], len(collected))
        for v in vs:
            agg["total"] += v["n"]; agg["retained"] += v["retained"]; agg["flagged"] += v["flagged"]
        D._rows_cache.clear()                            # 관측소별 행 캐시 해제(메모리 절약)
    summary[agency] = agg
    print("  %s: %d개소 (변수 %d, 관측 %d점)" % (agency, agg["n_stations"], agg["n_vars"], agg["total"]))

with open(D.CATALOG_JSON, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False)
with open(D.SUMMARY_JSON, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False)
print("== catalog.json(%d소) + summary.json 생성 ==" % len(out))
