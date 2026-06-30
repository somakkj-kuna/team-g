import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib


def load_config(path: Path) -> dict:
    with path.open("rb") as file_obj:
        return tomllib.load(file_obj)


def build_output_path(storage_cfg: dict, obs_code: str, target_date: datetime) -> Path:
    tokens = {
        "yyyy": target_date.strftime("%Y"),
        "yyyymmdd": target_date.strftime("%Y%m%d"),
        "obs_code": obs_code,
    }
    subdir = storage_cfg["dir_layout"].format_map(tokens)
    filename = storage_cfg["file_pattern"].format_map(tokens)
    return Path(storage_cfg["output_root"]) / subdir / filename


def request_with_retry(url: str, params: dict, timeout: int, max_retry: int, sleep_seconds: float):
    retry_wait_seconds = float(params.pop("__retry_wait_seconds__", 1800))
    while True:
        last_error = None
        for attempt in range(1, max_retry + 1):
            try:
                response = requests.get(url, params=params, timeout=timeout)
                if response.status_code == 200:
                    return response
                last_error = RuntimeError(f"HTTP {response.status_code}")
                print(f"[WARN] HTTP {response.status_code} (attempt {attempt}/{max_retry})")
            except requests.RequestException as exc:
                last_error = exc
                print(f"[WARN] Request error: {exc} (attempt {attempt}/{max_retry})")
            if attempt < max_retry:
                time.sleep(sleep_seconds)
        print(f"[ERROR] Request failed after {max_retry} attempts: {last_error}")
        print(f"[WARN] retrying in {retry_wait_seconds / 60:g} minutes...")
        time.sleep(retry_wait_seconds)


def dump_response(output_path: Path, response: requests.Response, show_sample: bool):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = response.json()
        with output_path.open("w", encoding="utf-8-sig") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False)
        if show_sample:
            result = payload.get("result") if isinstance(payload, dict) else None
            data = result.get("data") if isinstance(result, dict) else None
            meta = result.get("meta") if isinstance(result, dict) else None
            print(f"  - keys: {list(payload.keys()) if isinstance(payload, dict) else 'n/a'}")
            if isinstance(data, list):
                print(f"  - data_count: {len(data)}")
                if data:
                    print(f"  - data_sample: {data[0]}")
            if isinstance(meta, dict):
                print(f"  - meta: {meta}")
    except ValueError:
        # Non-JSON response; keep raw text for inspection
        with output_path.open("w", encoding="utf-8-sig") as file_obj:
            file_obj.write(response.text)
        if show_sample:
            print("  - non-json response saved as text")


def parse_args():
    parser = argparse.ArgumentParser(
        description="KHOA DT recent raw collector (date-based)"
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Target date in YYYYMMDD (or config req_date_format).",
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parents[1] / "config" / "khoa_config.toml"),
        help="Path to khoa_config.toml",
    )
    parser.add_argument(
        "--obs-codes",
        help="Comma-separated obs codes to fetch (default: config).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Fetch only the first N obs codes (for quick check).",
    )
    parser.add_argument(
        "--show-sample",
        action="store_true",
        help="Print a small sample from each response.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = load_config(Path(args.config))

    api_cfg = cfg["api"]
    req_cfg = cfg["request"]
    storage_cfg = cfg["storage"]["raw"]
    stations_cfg = cfg["stations"]

    date_fmt = req_cfg.get("req_date_format", "%Y%m%d")
    target_date = datetime.strptime(args.date, date_fmt)
    req_date = target_date.strftime(date_fmt)

    if args.obs_codes:
        obs_codes = [code.strip() for code in args.obs_codes.split(",") if code.strip()]
    else:
        obs_codes = list(stations_cfg["obs_codes"])

    if args.limit is not None:
        obs_codes = obs_codes[: args.limit]

    print(f"[INFO] Target date: {req_date} ({len(obs_codes)} stations)")

    for obs_code in obs_codes:
        params = {
            "obsCode": obs_code,
            "reqDate": req_date,
            "min": req_cfg.get("min", 1),
            "serviceKey": api_cfg["service_key"],
            "resultType": api_cfg.get("result_type", "json"),
        }
        print(f"[INFO] Requesting {obs_code}...")
        response = request_with_retry(
            api_cfg["base_url"],
            {**params, "__retry_wait_seconds__": float(api_cfg.get("retry_wait_seconds", 1800))},
            timeout=int(api_cfg.get("request_timeout", 120)),
            max_retry=int(api_cfg.get("max_retry", 5)),
            sleep_seconds=float(api_cfg.get("sleep_seconds", 0.2)),
        )
        if response is None:
            continue

        output_path = build_output_path(storage_cfg, obs_code, target_date)
        dump_response(output_path, response, args.show_sample)
        print(f"[INFO] Saved: {output_path}")


if __name__ == "__main__":
    main()
