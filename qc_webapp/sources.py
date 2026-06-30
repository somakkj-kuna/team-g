# -*- coding: utf-8 -*-
"""데이터 수집 현황 — 소스 카탈로그(메인 대시보드).

- Observation(현장관측): sample_data 3기관(KHOA/KMA/NIFS) 실데이터 카드.
- Numerical(수치모델)·Satellite(위성): 아직 데이터 미준비 → 회색 placeholder(박스 없음).
"""
from __future__ import annotations

from typing import Any, Dict, List

import data as D

BAR_LEN = 24
CATEGORIES = ["Numerical", "Observation", "Satellite"]
CAT_LABEL = {"Numerical": "수치모델", "Observation": "현장관측", "Satellite": "위성"}
CAT_DESC = {
    "Numerical": "재분석·예측장 — 데이터 준비중",
    "Observation": "관측소 실측 — KHOA·KMA·NIFS",
    "Satellite": "위성 L2/L3/L4 — 데이터 준비중",
}
CAT_EN = {"Numerical": "Numerical", "Observation": "Observation", "Satellite": "Satellite"}
CAT_EN_DESC = {
    "Numerical": "Reanalysis & forecast fields — not ready yet.",
    "Observation": "In-situ stations — KHOA tide, KMA/NIFS buoy.",
    "Satellite": "Satellite L2/L3/L4 — not ready yet.",
}


def _stat_bar(retained: int, total: int) -> List[str]:
    """보존율 기반 간이 24칸 상태바(ok=보존, warn=제거)."""
    if not total:
        return ["none"] * BAR_LEN
    nok = int(round(BAR_LEN * retained / total))
    nok = max(0, min(BAR_LEN, nok))
    return ["ok"] * nok + ["warn"] * (BAR_LEN - nok)


def _agency_card(agency: str) -> Dict[str, Any]:
    """한 기관 = Observation 소스 카드(드릴다운 → 관측소·변수별 현황).
    집계는 summary.json(사전계산) 우선 — 없으면 전 관측소 행 스캔(소규모 폴백)."""
    summ = D.agency_summary(agency)
    if summ is not None:
        n_stations = summ.get("n_stations", 0)
        n_vars = summ.get("n_vars", 0)
        total = summ.get("total", 0)
        retained = summ.get("retained", 0)
        flagged = summ.get("flagged", 0)
    else:
        stations = D.list_stations(agency)
        n_stations = len(stations)
        total = retained = flagged = 0
        n_vars = 0
        for st in stations:
            vs = D.variable_status(agency, st)
            n_vars = max(n_vars, len([v for v in vs if v["collected"]]))
            for v in vs:
                total += v["n"]; retained += v["retained"]; flagged += v["flagged"]
    return {
        "category": "Observation",
        "agency": agency,
        "source": agency.upper(),
        "dataset": "%s · %s" % (D.agency_name(agency), D.agency_dataset(agency)),
        "real": True,
        "drilldown": True,
        "var": None,
        "healthy": total > 0,
        "ratio": "%d개소" % n_stations,
        "n_stations": n_stations,
        "n_vars": n_vars,
        "total_points": total,
        "retained": retained,
        "flagged": flagged,
        "elapsed": "2025–2026",
        "bar": _stat_bar(retained, total),
        "warn": None,
    }


def collection_status() -> Dict[str, Any]:
    """전체 수집 현황 — 카테고리별 소스 + 요약."""
    obs_cards = [_agency_card(a) for a in D.list_agencies()]
    cats = []
    for cat in CATEGORIES:
        if cat == "Observation":
            sources = obs_cards
            pending = False
        else:
            sources = []          # 박스 제거
            pending = True         # 회색 처리(데이터 준비중)
        on_time = sum(1 for s in sources if s["healthy"])
        cats.append({
            "key": cat,
            "label": CAT_LABEL[cat],
            "desc": CAT_DESC[cat],
            "en": CAT_EN[cat],
            "en_desc": CAT_EN_DESC[cat],
            "n": len(sources),
            "on_time": on_time,
            "critical": len(sources) - on_time,
            "pending": pending,
            "sources": sources,
        })
    total = len(obs_cards)
    healthy = sum(1 for s in obs_cards if s["healthy"])
    return {
        "summary": {"tracked": total, "healthy": healthy, "errors": total - healthy},
        "categories": cats,
    }
