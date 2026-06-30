#!/home/collect/appl/miniconda3/envs/dataenv/bin/python
from __future__ import annotations

import argparse
import csv
import glob
import io
import re
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


DATAENV_PYTHON = Path("/home/collect/appl/miniconda3/envs/dataenv/bin/python")
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.toml"
PATH_KEYS = {
    "station_info",
    "station_reference",
    "post_data_dir",
    "post_all_dir",
    "merge_output_dir",
    "line_point_info_org_csv",
    "line_point_info_csv",
}
GLOB_KEYS = {"raw_data_glob", "source_glob"}
MISSING_TOKENS = {"", "-", "-999", "<NA>", "NaN", "nan", "None", "NULL", "null"}
REQUIRED_COLUMNS = {"line", "point", "record_time"}
CANONICAL_COLUMN_ORDER = [
    "record_time",
    "line",
    "point",
    "obs_lat",
    "obs_lon",
    "depth",
    "temp",
    "sal",
    "DO",
    "PO4",
    "NO2",
    "NO3",
    "SIL",
    "pH",
    "Transp",
    "air_pres",
    "sea_name",
]
SOURCE_HEADER_ALIASES = {
    "\ufeff해역": "해역",
    "수온(°C)": "수온(℃)",
}
LEGACY_OUTPUT_ALIASES = {
    "time": "record_time",
    "transect": "line",
    "station": "point",
    "lat": "obs_lat",
    "lon": "obs_lon",
    "M": "Transp",
}
SEA_NAME_MAP = {
    "동해": "EAST",
    "서해": "WEST",
    "남해": "SOUTH",
    "동중국해": "EAST_CHINA_SEA",
    "동해COAST": "EAST_COAST",
    "east": "EAST",
    "west": "WEST",
    "south": "SOUTH",
    "EAST": "EAST",
    "WEST": "WEST",
    "SOUTH": "SOUTH",
    "EAST_CHINA_SEA": "EAST_CHINA_SEA",
    "EAST_COAST": "EAST_COAST",
}
SOURCE_HEADER_PREFIX = "해역,정선,정점"

pd = None


def ensure_runtime_deps() -> None:
    global pd
    if pd is not None:
        return
    import pandas as pandas_module

    pd = pandas_module


def strip_wrapping_quotes(value: str) -> str:
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def parse_toml_scalar(raw: str):
    value = raw.strip()
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return strip_wrapping_quotes(value)


def load_config_fallback(path: Path) -> dict:
    cfg: dict = {}
    section_stack: list[str] = []
    current_list_key = None
    current_list_values = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue

        if current_list_key is not None:
            if line == "]":
                target = cfg
                for key in section_stack:
                    target = target.setdefault(key, {})
                target[current_list_key] = current_list_values
                current_list_key = None
                current_list_values = None
                continue

            match = re.match(r'["\'](.*?)["\']\s*,?\s*$', line)
            if match:
                current_list_values.append(match.group(1))
            continue

        if line.startswith("[") and line.endswith("]"):
            section_stack = [part.strip() for part in line[1:-1].split(".")]
            target = cfg
            for key in section_stack:
                target = target.setdefault(key, {})
            continue

        if "=" not in line:
            continue

        key, value = [part.strip() for part in line.split("=", 1)]
        key = strip_wrapping_quotes(key)

        target = cfg
        for section in section_stack:
            target = target.setdefault(section, {})

        if value == "[" or value.endswith("["):
            current_list_key = key
            current_list_values = []
        else:
            target[key] = parse_toml_scalar(value)

    return cfg


def resolve_path(path_value: str | Path, base_dir: Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def resolve_glob(pattern: str, base_dir: Path) -> str:
    path = Path(pattern).expanduser()
    if path.is_absolute():
        return str(path)
    return str(base_dir / path)


def load_config(config_path: str | Path | None = None) -> dict:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if tomllib is not None:
        with path.open("rb") as file_obj:
            config = tomllib.load(file_obj)
    else:
        config = load_config_fallback(path)

    paths_cfg = config.setdefault("paths", {})
    root_dir_raw = paths_cfg.get("root_dir")
    if root_dir_raw:
        root_dir = resolve_path(root_dir_raw, path.parent)
    else:
        root_dir = path.resolve().parents[1]
    paths_cfg["root_dir"] = str(root_dir)

    for key in PATH_KEYS:
        if key in paths_cfg:
            paths_cfg[key] = str(resolve_path(paths_cfg[key], root_dir))

    for key in GLOB_KEYS:
        if key in paths_cfg:
            paths_cfg[key] = resolve_glob(paths_cfg[key], root_dir)

    return config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge yearly NIFS CTD CSV files into per-transect CSV files."
    )
    parser.add_argument(
        "--year",
        help="Target year in YYYY. Uses paths.source_glob template from config.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config.toml",
    )
    parser.add_argument(
        "--source-glob",
        help="Override paths.source_glob from config.",
    )
    parser.add_argument(
        "--output-dir",
        help="Override paths.merge_output_dir from config.",
    )
    return parser.parse_args()


def build_year_source_glob(source_template: str, year: str) -> str:
    if "{yyyy}" in source_template:
        return source_template.replace("{yyyy}", year)
    resolved = source_template.replace("*", year, 1)
    return resolved.replace("*", year, 1)


def normalize_object_value(value):
    if isinstance(value, str):
        stripped = value.strip()
        return pd.NA if stripped in MISSING_TOKENS else stripped
    return value


def normalize_source_column_name(value):
    if not isinstance(value, str):
        return value
    normalized = value.replace("\ufeff", "").strip()
    return SOURCE_HEADER_ALIASES.get(normalized, normalized)


def normalize_code(value, pad: int | None = None):
    if value is None:
        return pd.NA
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in MISSING_TOKENS:
            return pd.NA
    else:
        stripped = str(value).strip()

    match = re.fullmatch(r"([+-]?\d+)(?:\.0+)?", stripped)
    if match:
        numeric_value = int(match.group(1))
        if pad is not None and numeric_value >= 0:
            return f"{numeric_value:0{pad}d}"
        return str(numeric_value)
    return stripped


def normalize_sea_name(value):
    if value is None:
        return pd.NA
    normalized = str(value).strip()
    if normalized in MISSING_TOKENS:
        return pd.NA
    return SEA_NAME_MAP.get(normalized, SEA_NAME_MAP.get(normalized.lower(), normalized))


def normalize_dataframe(df):
    normalized = df.copy()
    object_columns = normalized.select_dtypes(include=["object", "string"]).columns
    for column in object_columns:
        normalized[column] = normalized[column].map(normalize_object_value)
    return normalized


def build_column_map(var_mapping: dict) -> tuple[dict[str, str], list[str]]:
    output_columns: list[str] = []
    column_map: dict[str, str] = {}
    for source_name, target_name in var_mapping.items():
        if isinstance(target_name, list):
            output_columns.extend(target_name)
            continue
        output_columns.append(target_name)
        column_map[source_name] = target_name
    ordered_columns = [column for column in CANONICAL_COLUMN_ORDER if column in output_columns]
    extra_columns = [column for column in output_columns if column not in ordered_columns]
    return column_map, ordered_columns + extra_columns


def find_source_header_line(decoded_text: str) -> int:
    for index, raw_line in enumerate(decoded_text.splitlines()):
        normalized_line = raw_line.replace("\ufeff", "").strip()
        if normalized_line.startswith(SOURCE_HEADER_PREFIX):
            return index
    return 0


def read_csv_with_fallback(file_path: Path):
    raw_bytes = file_path.read_bytes()
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            decoded_text = raw_bytes.decode(encoding)
            header_line_index = find_source_header_line(decoded_text)
            lines = decoded_text.splitlines()
            payload = "\n".join(lines[header_line_index:])
            rows = list(csv.reader(io.StringIO(payload)))
            if not rows:
                return pd.DataFrame()

            header = [normalize_source_column_name(value) for value in rows[0]]
            data_rows = rows[1:]
            max_fields = max((len(row) for row in data_rows), default=len(header))
            if max_fields == len(header) + 1 and "투명도(m)" in header and "연직변화차트" not in header:
                insert_index = header.index("투명도(m)")
                header = header[:insert_index] + ["__unused_before_transp"] + header[insert_index:]
            elif max_fields > len(header):
                for extra_index in range(max_fields - len(header)):
                    header.append(f"__extra_{extra_index + 1}")

            normalized_rows = []
            for row in data_rows:
                if len(row) < len(header):
                    row = row + [""] * (len(header) - len(row))
                elif len(row) > len(header):
                    row = row[: len(header)]
                normalized_rows.append(row)

            return pd.DataFrame(normalized_rows, columns=header)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise last_error if last_error else UnicodeDecodeError("utf-8", b"", 0, 1, "decode failed")


def normalize_line_and_point(df):
    normalized = df.copy()

    if "정선-정점" in normalized.columns:
        split_columns = (
            normalized["정선-정점"]
            .astype("string")
            .str.strip()
            .str.split("-", n=1, expand=True)
        )
        if 0 in split_columns.columns:
            normalized["line"] = split_columns[0].where(split_columns[0].notna(), normalized.get("line"))
        if 1 in split_columns.columns:
            normalized["point"] = split_columns[1].where(split_columns[1].notna(), normalized.get("point"))

    if "line" in normalized.columns:
        normalized["line"] = normalized["line"].map(normalize_code)
    if "point" in normalized.columns:
        normalized["point"] = normalized["point"].map(lambda value: normalize_code(value, pad=2))
    return normalized


def prepare_dataframe(file_path: Path, column_map: dict[str, str], output_columns: list[str]):
    df = read_csv_with_fallback(file_path)
    df.rename(columns=column_map, inplace=True)
    df = normalize_line_and_point(df)

    available_columns = [column for column in output_columns if column in df.columns]
    df = df[available_columns].copy()
    df = normalize_dataframe(df)

    missing_required = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing_required:
        raise KeyError(f"Required columns not found in {file_path}: {missing_required}")

    df["record_time"] = pd.to_datetime(df["record_time"], errors="coerce")
    for column in ("line", "point"):
        if column in df.columns:
            df[column] = df[column].astype("string").str.strip()
    if "sea_name" in df.columns:
        df["sea_name"] = df["sea_name"].map(normalize_sea_name).astype("string").str.strip()

    df = df.dropna(subset=["line", "point", "record_time"])
    return df.reindex(columns=[column for column in output_columns if column in df.columns])


def load_existing_dataframe(output_file: Path, output_columns: list[str]):
    if not output_file.exists() or output_file.stat().st_size == 0:
        return pd.DataFrame(columns=output_columns)

    existing_df = pd.read_csv(
        output_file,
        encoding="utf-8-sig",
        na_values=sorted(MISSING_TOKENS),
        keep_default_na=True,
    )
    existing_df.rename(columns=LEGACY_OUTPUT_ALIASES, inplace=True)
    existing_df = normalize_line_and_point(existing_df)
    existing_df = existing_df.reindex(columns=output_columns)
    existing_df = normalize_dataframe(existing_df)
    if "record_time" in existing_df.columns:
        existing_df["record_time"] = pd.to_datetime(existing_df["record_time"], errors="coerce")
    if "sea_name" in existing_df.columns:
        existing_df["sea_name"] = existing_df["sea_name"].map(normalize_sea_name)
    return existing_df


def sort_and_deduplicate(df, dedupe_keys: list[str], sort_keys: list[str]):
    working_df = df.copy()
    available_dedupe_keys = [key for key in dedupe_keys if key in working_df.columns]
    if available_dedupe_keys:
        working_df = working_df.drop_duplicates(subset=available_dedupe_keys, keep="last")

    available_sort_keys = [key for key in sort_keys if key in working_df.columns]
    helper_columns: list[str] = []
    for sort_key in available_sort_keys:
        helper_column = f"__sort_{sort_key}"
        if sort_key == "record_time":
            working_df[helper_column] = pd.to_datetime(working_df[sort_key], errors="coerce")
            helper_columns.append(helper_column)
            continue
        if sort_key in {"line", "point", "depth"}:
            working_df[helper_column] = pd.to_numeric(working_df[sort_key], errors="coerce")
            helper_columns.extend([helper_column, sort_key])
            continue
        working_df[helper_column] = working_df[sort_key].astype("string")
        helper_columns.append(helper_column)

    if helper_columns:
        working_df = working_df.sort_values(by=helper_columns, na_position="last", kind="stable")

    cleaned_columns = [column for column in working_df.columns if not column.startswith("__sort_")]
    return working_df[cleaned_columns].reset_index(drop=True)


def finalize_for_csv(df, missing_value: str):
    finalized = df.copy()
    if "record_time" in finalized.columns:
        finalized["record_time"] = pd.to_datetime(finalized["record_time"], errors="coerce").dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    return finalized.fillna(missing_value)


def build_source_glob(paths_cfg: dict, year: str | None, source_glob_override: str | None) -> str:
    source_glob = paths_cfg["source_glob"]
    if "{yyyy}" in source_glob and not year and not source_glob_override:
        source_glob = source_glob.replace("{yyyy}", "*")
    if year:
        if not re.fullmatch(r"\d{4}", year):
            raise ValueError(f"Invalid year: {year}")
        source_glob = build_year_source_glob(source_glob, year)
    if source_glob_override:
        source_glob = source_glob_override
    return source_glob


def sort_line_codes(line_codes: list[str]) -> list[str]:
    def sort_key(value: str):
        numeric = pd.to_numeric([value], errors="coerce")[0]
        return (pd.isna(numeric), numeric, value)

    return sorted(line_codes, key=sort_key)
def main() -> None:
    ensure_runtime_deps()
    args = parse_args()
    config = load_config(args.config)
    paths_cfg = config["paths"]
    merge_cfg = config["merge"]
    var_mapping = merge_cfg["var_name"]
    missing_value = str(merge_cfg.get("missing_value", "-999"))
    dedupe_keys = list(merge_cfg.get("dedupe_keys", ["line", "point", "record_time", "depth"]))
    sort_keys = list(merge_cfg.get("sort_keys", ["record_time", "line", "point", "depth"]))

    if not args.year:
        raise ValueError("--year is required. Example: --year 2025")

    year = args.year

    source_glob = build_source_glob(paths_cfg, year, args.source_glob)

    base_output_dir = Path(args.output_dir or paths_cfg["merge_output_dir"])
    output_dir = base_output_dir / year
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"merge_ctd_{year}.csv"

    current_dir = Path(paths_cfg["root_dir"])
    print(f"   ∴ current work directory :: {current_dir}")
    print(f"   ∴ source glob            :: {source_glob}")
    print(f"   ∴ output directory       :: {output_dir}")
    print(f"   ∴ output file            :: {output_file}")

    column_map, output_columns = build_column_map(var_mapping)
    source_file_list = sorted(Path(file_name) for file_name in glob.glob(source_glob))

    if not source_file_list:
        print(f"[WARN] No source files found for pattern: {source_glob}")
        return

    processed_file_count = 0
    all_df_list = []

    for file_name in source_file_list:
        print(f"  ├── Processing : {file_name}")
        df = prepare_dataframe(file_name, column_map, output_columns)
        all_df_list.append(df)
        processed_file_count += 1

    if all_df_list:
        new_df = pd.concat(all_df_list, ignore_index=True)
    else:
        new_df = pd.DataFrame(columns=output_columns)

    print("==============================================================================")
    print(f"   ∴ Starting Creation of ::: merge_ctd_{year}.csv :::")
    print(f"   ∴    Save directory    ::: {output_dir} :::")
    print("==============================================================================")

    existing_df = load_existing_dataframe(output_file, output_columns)
    combined_df = pd.concat([existing_df, new_df], ignore_index=True)

    combined_df = sort_and_deduplicate(combined_df, dedupe_keys, sort_keys)
    combined_df = finalize_for_csv(combined_df, missing_value)

    combined_df.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig",
        na_rep=missing_value,
    )

    print(
        f"[INFO] Processed {processed_file_count} source files and saved yearly CTD CSV file: {output_file}"
    )

def run_processor() -> None:
    parent_dir = Path(__file__).resolve().parents[1]
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

    if find_spec("pandas") is None:
        raise SystemExit(subprocess.call([str(DATAENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]]))

    main()


if __name__ == "__main__":
    run_processor()
