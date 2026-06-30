"""명령행에서 NIFS buoy 관측 검색/다운로드를 실행하는 CLI."""

from __future__ import annotations

import argparse
import logging

try:
    from .client import (
        crawl_all_buoy_observations,
        download_buoy_observation_excel,
        download_buoy_observation_text,
        search_buoy_observation,
    )
except ImportError:  # python cli.py 직접 실행 호환
    from client import (  # type: ignore
        crawl_all_buoy_observations,
        download_buoy_observation_excel,
        download_buoy_observation_text,
        search_buoy_observation,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NIFS buoy 관측정보 수집기")
    parser.add_argument("--log-level", default="INFO", help="DEBUG/INFO/WARNING/ERROR")

    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("search", "text", "excel"):
        p = sub.add_parser(name)
        p.add_argument("--area", required=True, choices=["남해", "동해", "서해"])
        p.add_argument("--station", default=None, help="예: 강진 마량(fgmk6)")
        p.add_argument("--start-date", required=True, help="YYYY-MM-DD")
        p.add_argument("--end-date", required=True, help="YYYY-MM-DD")
        p.add_argument("--start-time", default="00:00", help="HH:MM")
        p.add_argument("--end-time", default="23:30", help="HH:MM")
        p.add_argument("--sort-field", default="station", choices=["station", "datetime"])
        p.add_argument("--sort-order", default="asc", choices=["asc", "desc"])
        p.add_argument("--page", type=int, default=1, help="조회 페이지(1부터 시작)")
        p.add_argument("--page-size", type=int, default=50, help="페이지당 조회 건수")
        p.add_argument("--no-browser-fallback", action="store_true")
        if name == "search":
            p.add_argument("--preview-rows", type=int, default=50, help="화면 출력 행 수")
        if name in ("text", "excel"):
            p.add_argument("--output", required=False, help="출력 파일 경로")

    p_all = sub.add_parser("crawl-all")
    p_all.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    p_all.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    p_all.add_argument("--start-time", default="00:00", help="HH:MM")
    p_all.add_argument("--end-time", default="23:30", help="HH:MM")
    p_all.add_argument("--sort-field", default="station", choices=["station", "datetime"])
    p_all.add_argument("--sort-order", default="asc", choices=["asc", "desc"])
    p_all.add_argument("--page-size", type=int, default=200, help="페이지당 조회 건수")
    p_all.add_argument("--request-interval-sec", type=float, default=0.3, help="관측소 간 요청 간격(초)")
    p_all.add_argument("--output", required=False, default=None, help="출력 파일 경로(.csv/.parquet/.xlsx)")
    p_all.add_argument("--preview-rows", type=int, default=20, help="화면 출력 행 수")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    use_browser_fallback = not args.no_browser_fallback

    common_kwargs = {
        "area": args.area,
        "station_name": args.station,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "start_time": args.start_time,
        "end_time": args.end_time,
        "sort_field": args.sort_field,
        "sort_order": args.sort_order,
        "use_browser_fallback": use_browser_fallback,
        "page": args.page,
        "page_size": args.page_size,
    }

    if args.command == "search":
        df = search_buoy_observation(**common_kwargs)
        print(f"rows={len(df)}")
        print(df.head(args.preview_rows).to_string(index=False))
        return

    if args.command == "text":
        path = download_buoy_observation_text(output=args.output, **common_kwargs)
        print(f"saved: {path}")
        return

    if args.command == "excel":
        path = download_buoy_observation_excel(output=args.output, **common_kwargs)
        print(f"saved: {path}")
        return

    if args.command == "crawl-all":
        df = crawl_all_buoy_observations(
            start_date=args.start_date,
            end_date=args.end_date,
            start_time=args.start_time,
            end_time=args.end_time,
            sort_field=args.sort_field,
            sort_order=args.sort_order,
            page_size=args.page_size,
            request_interval_sec=args.request_interval_sec,
        )
        print(f"rows={len(df)}")
        print(df.head(args.preview_rows).to_string(index=False))

        if args.output:
            output = str(args.output)
            if output.endswith(".parquet"):
                df.to_parquet(output, index=False)
            elif output.endswith(".xlsx"):
                df.to_excel(output, index=False)
            else:
                df.to_csv(output, index=False)
            print(f"saved: {output}")
        return

    raise ValueError(f"알 수 없는 command: {args.command}")


if __name__ == "__main__":
    main()
