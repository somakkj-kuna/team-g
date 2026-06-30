"""KHOA HF radar daily CSV -> annual NetCDF converter.

Dimensions : time (UNLIMITED, hourly), y (common grid rows), x (common grid cols)
Variables  : lat(y,x), lon(y,x), land_mask(y,x),
             current_speed/direct/u_current/v_current(time,y,x)
Grid       : fixed common Korean-coastal grid (0.01°, from config)
Strategy   : one-day-at-a-time write to keep peak memory under ~64 MB
Fill       : NaN (_FillValue=NaN) — ncview/xarray 등에서 자동 마스킹
UV formula : u = speed * sin(rad(direct)), v = speed * cos(rad(direct))
             (direct = to-direction, oceanographic convention)
"""
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

import netCDF4 as nc_lib
from global_land_mask import globe

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


MISSING_CSV = -999.0
NAN32 = np.float32("nan")


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)["hf_nc"]


def load_station_name(station_info_path: Path, obs_code: str) -> str:
    df = pd.read_csv(station_info_path, encoding="utf-8-sig")
    row = df[df["obs_post_id"] == obs_code]
    if row.empty:
        return obs_code
    return str(row.iloc[0]["name_e"])


def build_common_grid(cfg: dict) -> tuple:
    """Build fixed Korean-coastal common grid and land mask."""
    cg = cfg["common_grid"]
    res = float(cg["resolution"])

    grid_lats = np.round(
        np.arange(float(cg["lat_min"]), float(cg["lat_max"]) + res * 0.5, res), 6
    ).astype(np.float32)
    grid_lons = np.round(
        np.arange(float(cg["lon_min"]), float(cg["lon_max"]) + res * 0.5, res), 6
    ).astype(np.float32)

    lon_2d, lat_2d = np.meshgrid(grid_lons, grid_lats)
    lat_2d = lat_2d.astype(np.float32)
    lon_2d = lon_2d.astype(np.float32)

    print(f"[INFO] Common grid: y={len(grid_lats)} x={len(grid_lons)} "
          f"lat={grid_lats[0]:.2f}~{grid_lats[-1]:.2f} "
          f"lon={grid_lons[0]:.2f}~{grid_lons[-1]:.2f}")

    print("[INFO] Building land mask...")
    is_ocean = globe.is_ocean(lat_2d.ravel(), lon_2d.ravel())
    land_mask = (~is_ocean).reshape(lat_2d.shape).astype(np.uint8)
    print(f"[INFO] Land mask: ocean={int(is_ocean.sum()):,}  land={int(land_mask.sum()):,}")

    return grid_lats, grid_lons, lat_2d, lon_2d, land_mask


def build_station_pt_map(
    daily_files: list,
    obs_code: str,
    grid_lats: np.ndarray,
    grid_lons: np.ndarray,
) -> dict:
    """Pass 1: map each unique raw (lat, lon) to nearest common grid (y_idx, x_idx)."""
    res = float(round(float(grid_lats[1]) - float(grid_lats[0]), 6))
    lat_min, lat_max = float(grid_lats[0]), float(grid_lats[-1])
    lon_min, lon_max = float(grid_lons[0]), float(grid_lons[-1])
    n_y, n_x = len(grid_lats), len(grid_lons)

    raw_points: set = set()
    for fpath in daily_files:
        df = pd.read_csv(fpath, encoding="utf-8-sig",
                         usecols=["obs_post_id", "obs_lat", "obs_lon"])
        df = df[df["obs_post_id"] == obs_code]
        lats = pd.to_numeric(df["obs_lat"], errors="coerce").round(5)
        lons = pd.to_numeric(df["obs_lon"], errors="coerce").round(5)
        valid = lats.notna() & lons.notna()
        for lat, lon in zip(lats[valid].values, lons[valid].values):
            raw_points.add((float(lat), float(lon)))

    pt_map: dict[tuple, tuple] = {}
    for lat, lon in raw_points:
        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            continue
        yi = int(round((lat - lat_min) / res))
        xi = int(round((lon - lon_min) / res))
        pt_map[(lat, lon)] = (max(0, min(yi, n_y - 1)), max(0, min(xi, n_x - 1)))

    return pt_map


def compute_uv(speed_arr: np.ndarray, direct_arr: np.ndarray) -> tuple:
    """NaN-aware UV decomposition."""
    u = np.full_like(speed_arr, np.nan)
    v = np.full_like(speed_arr, np.nan)
    valid = ~np.isnan(speed_arr) & ~np.isnan(direct_arr)
    rad = np.deg2rad(direct_arr[valid])
    u[valid] = speed_arr[valid] * np.sin(rad)
    v[valid] = speed_arr[valid] * np.cos(rad)
    return u, v


def create_nc(
    out_path: Path,
    obs_code: str,
    station_name: str,
    n_y: int,
    n_x: int,
    lat_2d: np.ndarray,
    lon_2d: np.ndarray,
    land_mask: np.ndarray,
    global_attrs: dict,
) -> nc_lib.Dataset:
    """Create NetCDF file, write static variables, return open Dataset for appending."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    chunks = (24, n_y, n_x)

    ds = nc_lib.Dataset(str(out_path), "w", format="NETCDF4")
    ds.createDimension("time", None)
    ds.createDimension("y", n_y)
    ds.createDimension("x", n_x)

    t_var = ds.createVariable("time", "f8", ("time",))
    t_var.units = "seconds since 1970-01-01 00:00:00"
    t_var.calendar = "gregorian"
    t_var.long_name = "time"
    t_var.standard_name = "time"

    lat_var = ds.createVariable("lat", "f4", ("y", "x"))
    lat_var.units = "degrees_north"
    lat_var.long_name = "latitude"
    lat_var.standard_name = "latitude"
    lat_var[:] = lat_2d

    lon_var = ds.createVariable("lon", "f4", ("y", "x"))
    lon_var.units = "degrees_east"
    lon_var.long_name = "longitude"
    lon_var.standard_name = "longitude"
    lon_var[:] = lon_2d

    lm_var = ds.createVariable("land_mask", "u1", ("y", "x"), zlib=True, complevel=4)
    lm_var.long_name = "land mask"
    lm_var.flag_values = np.array([0, 1], dtype=np.uint8)
    lm_var.flag_meanings = "ocean land"
    lm_var[:] = land_mask

    for vname, lname, stdname in [
        ("current_speed",  "surface current speed",                               None),
        ("current_direct", "surface current direction (to direction, oceanographic)", None),
        ("u_current",      "eastward surface current velocity",  "eastward_sea_water_velocity"),
        ("v_current",      "northward surface current velocity", "northward_sea_water_velocity"),
    ]:
        v = ds.createVariable(
            vname, "f4", ("time", "y", "x"),
            fill_value=NAN32, zlib=True, complevel=4,
            chunksizes=chunks,
        )
        v.units = "cm s-1" if vname != "current_direct" else "degree"
        v.long_name = lname
        v.coordinates = "lat lon"
        if stdname:
            v.standard_name = stdname

    ds.station_id = obs_code
    ds.station_name = station_name
    for key, val in global_attrs.items():
        setattr(ds, key, val)
    ds.history = f"Created {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"

    return ds


def process_station(
    cfg: dict,
    year: int,
    obs_code: str,
    grid_lats: np.ndarray,
    grid_lons: np.ndarray,
    lat_2d: np.ndarray,
    lon_2d: np.ndarray,
    land_mask: np.ndarray,
) -> None:
    raw_root = Path(cfg["raw_root"]) / str(year)
    prc_root = Path(cfg["prc_root"]) / str(year)
    n_y, n_x = lat_2d.shape

    daily_files = sorted(raw_root.glob(f"hf_{year}*.csv"))
    if not daily_files:
        print(f"[WARN] No files found in {raw_root}")
        return

    print(f"[INFO] {obs_code} {year}: {len(daily_files)} daily files")
    station_name = load_station_name(Path(cfg["station_info"]), obs_code)

    print("[INFO] Pass 1: mapping station points to common grid...")
    pt_map = build_station_pt_map(daily_files, obs_code, grid_lats, grid_lons)
    if not pt_map:
        print(f"[WARN] No data found for {obs_code} in {year}")
        return
    print(f"[INFO] Active grid cells: {len(pt_map)}")

    st_code_clean = obs_code.replace("_", "")
    out_path = prc_root / f"hf_{st_code_clean}_{year}.nc"

    ds = create_nc(
        out_path, obs_code, station_name, n_y, n_x,
        lat_2d, lon_2d, land_mask,
        cfg.get("global_attrs", {}),
    )

    epoch = pd.Timestamp("1970-01-01")
    t_cursor = 0
    valid_total = 0

    print("[INFO] Pass 2: writing daily chunks...")
    for fpath in daily_files:
        df = pd.read_csv(
            fpath, encoding="utf-8-sig",
            usecols=["obs_post_id", "record_time", "obs_lat", "obs_lon",
                     "current_speed", "current_direct"],
        )
        df = df[df["obs_post_id"] == obs_code].copy()
        if df.empty:
            continue

        df["record_time"] = pd.to_datetime(df["record_time"], errors="coerce")
        df["obs_lat"] = pd.to_numeric(df["obs_lat"], errors="coerce").round(5)
        df["obs_lon"] = pd.to_numeric(df["obs_lon"], errors="coerce").round(5)
        df["current_speed"] = pd.to_numeric(df["current_speed"], errors="coerce")
        df["current_direct"] = pd.to_numeric(df["current_direct"], errors="coerce")
        df.replace(MISSING_CSV, np.nan, inplace=True)
        df.dropna(subset=["record_time", "obs_lat", "obs_lon"], inplace=True)
        if df.empty:
            continue

        day = df["record_time"].dt.normalize().iloc[0]
        hour_index = pd.date_range(day, periods=24, freq="h")
        hour_idx_map = {t: i for i, t in enumerate(hour_index)}
        n_hours = 24

        spd_chunk = np.full((n_hours, n_y, n_x), np.nan, dtype=np.float32)
        dir_chunk = np.full((n_hours, n_y, n_x), np.nan, dtype=np.float32)

        t_idx = df["record_time"].map(hour_idx_map).fillna(-1).astype(np.int64).values
        yx = np.array(
            [pt_map.get((lat, lon), (-1, -1))
             for lat, lon in zip(df["obs_lat"].values, df["obs_lon"].values)],
            dtype=np.int64,
        )
        y_idx, x_idx = yx[:, 0], yx[:, 1]

        valid = (t_idx >= 0) & (y_idx >= 0) & (x_idx >= 0)
        ti, yi, xi = t_idx[valid], y_idx[valid], x_idx[valid]
        spd  = df["current_speed"].values[valid]
        dir_ = df["current_direct"].values[valid]

        spd_ok = ~np.isnan(spd)
        spd_chunk[ti[spd_ok], yi[spd_ok], xi[spd_ok]] = spd[spd_ok].astype(np.float32)
        dir_ok = ~np.isnan(dir_)
        dir_chunk[ti[dir_ok], yi[dir_ok], xi[dir_ok]] = dir_[dir_ok].astype(np.float32)

        u_chunk, v_chunk = compute_uv(spd_chunk, dir_chunk)

        time_vals = ((hour_index - epoch).total_seconds()).values.astype(np.float64)
        sl = slice(t_cursor, t_cursor + n_hours)
        ds["time"][sl]           = time_vals
        ds["current_speed"][sl]  = spd_chunk
        ds["current_direct"][sl] = dir_chunk
        ds["u_current"][sl]      = u_chunk
        ds["v_current"][sl]      = v_chunk

        valid_total += int(spd_ok.sum())
        t_cursor += n_hours

    ds.close()
    print(f"[INFO] Written: {out_path}  ({out_path.stat().st_size / 1e6:.1f} MB)")
    print(f"[INFO] Valid obs written: {valid_total:,}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert KHOA HF daily CSV to annual NetCDF (CF-1.8, common Korean grid)."
    )
    parser.add_argument("--year", type=int, required=True, help="Target year (YYYY)")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parents[1] / "config" / "khoa_hf_nc_config.toml"),
    )
    parser.add_argument("--obs-codes")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))

    if args.obs_codes:
        obs_codes = [c.strip() for c in args.obs_codes.split(",") if c.strip()]
    else:
        main_cfg_path = Path(args.config).parent / "khoa_config.toml"
        with main_cfg_path.open("rb") as f:
            obs_codes = list(tomllib.load(f)["hf"]["stations"]["obs_codes"])

    grid_lats, grid_lons, lat_2d, lon_2d, land_mask = build_common_grid(cfg)

    for obs_code in obs_codes:
        print(f"\n[INFO] ===== {obs_code} / {args.year} =====")
        try:
            process_station(
                cfg, args.year, obs_code,
                grid_lats, grid_lons, lat_2d, lon_2d, land_mask,
            )
        except Exception as exc:
            import traceback
            print(f"[ERROR] {obs_code}: {exc}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
