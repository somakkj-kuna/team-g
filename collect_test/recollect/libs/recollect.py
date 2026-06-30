#!/usr/bin/env python3
"""OBS 미수집 기록 + 지연 재수집 (collect_test 샌드박스).

서브명령:
  detect   : lookback 윈도의 (provider,dataset,station,date) 미수집을 대장(ledger)에 pending 기록
  backfill : 대장 pending(retention 이내)을 (dataset,date) 단위로 수집기 재호출 -> 재탐지 -> resolved / attempts++
  sweep    : first_seen 기준 retention 경과 미해결 -> unobserved 이관 후 대장 제거
  pass     : detect -> backfill -> sweep (일일 1패스, 기본)

미수집 = 해당 (정점,날짜)의 '행 자체'가 기대 슬롯 대비 부족한 경우(제공 지연). -999 값은 행 존재로 간주.
"""
import argparse
import csv
import subprocess
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path
import tomllib

BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config" / "recollect.toml"
FIELDS = ["provider", "dataset", "station", "date", "expected_n", "got_n",
          "missing_slots", "first_seen", "last_check", "attempts", "status", "reason"]


def load_cfg():
    with CONFIG.open("rb") as f:
        return tomllib.load(f)


def state_dir(cfg):
    p = Path(cfg["settings"]["state_dir"])
    p.mkdir(parents=True, exist_ok=True)
    return p


def ledger_path(cfg):
    return state_dir(cfg) / "ledger.csv"


def unobserved_path(cfg):
    return state_dir(cfg) / "unobserved.csv"


def read_ledger(cfg):
    p = ledger_path(cfg)
    if not p.exists():
        return []
    with p.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_ledger(cfg, rows):
    with ledger_path(cfg).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def append_unobserved(cfg, rows):
    p = unobserved_path(cfg)
    first = not p.exists()
    cols = FIELDS + ["dropped_at"]
    with p.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if first:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def k_of(r):
    return (r["provider"], r["dataset"], r["station"], r["date"])


def now_s():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def window_dates(end, lookback):
    return [(end - timedelta(days=i)).strftime("%Y%m%d") for i in range(lookback)]


def month_files(out_root, ds, dates):
    out = []
    for ym in sorted({d[:6] for d in dates}):
        fp = Path(out_root) / ds["subdir"] / ym[:4] / ds["file_tmpl"].format(yyyymm=ym)
        if fp.exists():
            out.append(fp)
    return out


def scan(paths):
    counts = defaultdict(lambda: defaultdict(int))
    stations = set()
    for fp in paths:
        with fp.open("r", newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                t = row.get("time", "")
                sid = row.get("station_id", "")
                if len(t) < 10 or not sid:
                    continue
                counts[t[:10].replace("-", "")][sid] += 1
                stations.add(sid)
    return counts, stations


def detect(cfg, datasets, end, lookback):
    out_root = cfg["settings"]["test_output_root"]
    thr = float(cfg["settings"].get("completeness_threshold", 0.9))
    dates = window_dates(end, lookback)
    findings = []
    for ds in datasets.values():
        exp = 1440 // int(ds["cadence_min"])
        counts, stations = scan(month_files(out_root, ds, dates))
        for d in dates:
            day = counts.get(d, {})
            for sid in sorted(stations):
                got = day.get(sid, 0)
                if got >= exp * thr:
                    continue
                findings.append({"provider": ds["provider"], "dataset": ds["dataset"],
                                 "station": sid, "date": d, "expected_n": exp,
                                 "got_n": got, "missing_slots": max(exp - got, 0)})
    return findings


def cmd_detect(cfg, datasets, end, lookback, dry):
    findings = detect(cfg, datasets, end, lookback)
    ledger = read_ledger(cfg)
    idx = {k_of(r): r for r in ledger}
    now = now_s()
    new = upd = 0
    for fn in findings:
        k = k_of(fn)
        if k in idx:
            r = idx[k]
            r["got_n"] = str(fn["got_n"])
            r["missing_slots"] = str(fn["missing_slots"])
            r["last_check"] = now
            if r["status"] == "resolved":
                r["status"] = "pending"
            upd += 1
        else:
            row = {kk: str(vv) for kk, vv in fn.items()}
            row.update({"first_seen": now, "last_check": now, "attempts": "0",
                        "status": "pending", "reason": "provider_delay"})
            ledger.append(row)
            idx[k] = row
            new += 1
    if not dry:
        write_ledger(cfg, ledger)
    win = window_dates(end, lookback)
    print(f"[detect] {win[-1]}..{win[0]} findings={len(findings)} new={new} updated={upd}" +
          (" (dry)" if dry else ""))
    return findings


def run_collector(cfg, ds, ymd, limit, dry):
    root = cfg["settings"]["collector_root"]
    cmd = ["/bin/bash", str(Path(root) / ds["script"]), *list(ds.get("script_args", [])), ymd, ymd]
    if limit:
        cmd += ["--limit", str(limit)]
    print("  $ " + " ".join(cmd))
    if dry:
        return 0
    return subprocess.run(cmd).returncode


def within_retention(r, ret):
    fs = datetime.strptime(r["first_seen"][:10], "%Y-%m-%d").date()
    return (date.today() - fs).days < ret


def cmd_backfill(cfg, datasets, end, lookback, limit, dry, force=None):
    by_pd = {(d["provider"], d["dataset"]): name for name, d in datasets.items()}
    ledger = read_ledger(cfg)
    ret = int(cfg["settings"]["retention_days"])
    if force:
        prov, dsn, ymd = force
        if (prov, dsn) not in by_pd:
            raise SystemExit(f"unknown provider/dataset: {prov}/{dsn}")
        todo = {(by_pd[(prov, dsn)], ymd)}
    else:
        todo = set()
        for r in ledger:
            if r["status"] == "pending" and within_retention(r, ret):
                todo.add((by_pd[(r["provider"], r["dataset"])], r["date"]))
    if not todo:
        print("[backfill] nothing pending")
        return
    print(f"[backfill] {len(todo)} (dataset,date) to recollect")
    for name, ymd in sorted(todo):
        rc = run_collector(cfg, datasets[name], ymd, limit, dry)
        print(f"  -> {name} {ymd} rc={rc}")
    if dry:
        print("[backfill] dry-run, ledger unchanged")
        return
    findings = detect(cfg, datasets, end, max(lookback, ret))
    miss = {k_of(f) for f in findings}
    now = now_s()
    resolved = 0
    for r in ledger:
        if r["status"] != "pending":
            continue
        name = by_pd[(r["provider"], r["dataset"])]
        if (name, r["date"]) not in todo:
            continue
        r["last_check"] = now
        r["attempts"] = str(int(r.get("attempts", "0") or 0) + 1)
        if k_of(r) not in miss:
            r["status"] = "resolved"
            r["got_n"] = str(r["expected_n"])
            r["missing_slots"] = "0"
            resolved += 1
    write_ledger(cfg, ledger)
    print(f"[backfill] resolved={resolved}")


def cmd_sweep(cfg, dry):
    ledger = read_ledger(cfg)
    ret = int(cfg["settings"]["retention_days"])
    today = date.today()
    keep = []
    drop = []
    for r in ledger:
        fs = datetime.strptime(r["first_seen"][:10], "%Y-%m-%d").date()
        age = (today - fs).days
        if r["status"] == "resolved":
            if age < ret:
                keep.append(r)
        elif age >= ret:
            r["dropped_at"] = today.isoformat()
            drop.append(r)
        else:
            keep.append(r)
    if drop and not dry:
        append_unobserved(cfg, drop)
    if not dry:
        write_ledger(cfg, keep)
    print(f"[sweep] kept={len(keep)} ->unobserved={len(drop)}" + (" (dry)" if dry else ""))


def parse_date(s):
    return datetime.strptime(s, "%Y%m%d").date()


def main():
    ap = argparse.ArgumentParser(description="OBS 미수집 기록 + 지연 재수집")
    ap.add_argument("mode", choices=["detect", "backfill", "sweep", "pass"], nargs="?", default="pass")
    ap.add_argument("--date", help="기준일 YYYYMMDD (기본=어제)")
    ap.add_argument("--lookback", type=int, default=None, help="탐지 일수 (기본=retention)")
    ap.add_argument("--limit", type=int, default=None, help="수집기 정점 수 제한(테스트)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--provider")
    ap.add_argument("--dataset")
    ap.add_argument("--force", action="store_true", help="수동 강제 재수집(--provider --dataset --date 필요)")
    a = ap.parse_args()
    cfg = load_cfg()
    datasets = cfg["datasets"]
    ret = int(cfg["settings"]["retention_days"])
    end = parse_date(a.date) if a.date else (date.today() - timedelta(days=1))
    lookback = a.lookback if a.lookback is not None else ret

    if a.mode == "detect":
        cmd_detect(cfg, datasets, end, lookback, a.dry_run)
    elif a.mode == "sweep":
        cmd_sweep(cfg, a.dry_run)
    elif a.mode == "backfill":
        force = None
        if a.force:
            if not (a.provider and a.dataset and a.date):
                ap.error("--force requires --provider --dataset --date")
            force = (a.provider, a.dataset, a.date)
        cmd_backfill(cfg, datasets, end, lookback, a.limit, a.dry_run, force)
    else:
        cmd_detect(cfg, datasets, end, lookback, a.dry_run)
        cmd_backfill(cfg, datasets, end, lookback, a.limit, a.dry_run)
        cmd_sweep(cfg, a.dry_run)


if __name__ == "__main__":
    main()
