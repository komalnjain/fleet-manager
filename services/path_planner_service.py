#!/usr/bin/env python3
"""
Path Planner Service

High-level API to generate path-planning commands (A* + stop handling)
for a device and write them to data/device_logs/path_{device_id}.csv

Usage example:

from services.path_planner_service import plan_and_write_path

plan_and_write_path(
    device_id="DEV001",
    map_id="13",
    zone_sequence=[("1","2"),("2","4"),("4","2"),("2","3"),("3","2"),("2","1")],
    initial_direction="north",   # robot's current facing direction
)

Notes:
- Initial forward offset is taken from latest device log row's right_drive (in mm),
  converted to meters. If missing, defaults to 0.
- Stops are gathered from `data/stops.csv` filtered by the `map_id` and
  matched by zone_connection_id to the edges in `data/zones.csv`.
- The output CSV headers: [command,value,unit]

"""
from __future__ import annotations

import csv
import json
import os
from typing import List, Tuple, Dict, Any, Optional

from robot_navigation.astar_planner import (
    build_graph_from_zones,
    load_stops,
    generate_path_commands,
    serialize_commands_to_csv_rows,
    write_commands_csv,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
ZONES_CSV = os.path.join(DATA_DIR, "zones.csv")
STOPS_CSV = os.path.join(DATA_DIR, "stops.csv")
DEVICE_LOGS_DIR = os.path.join(DATA_DIR, "device_logs")
DEVICES_CSV = os.path.join(DATA_DIR, "devices.csv")
ZONE_ALIGNMENT_CSV = os.path.join(DATA_DIR, "zone_alignment.csv")
MAPS_CSV = os.path.join(DATA_DIR, "maps.csv")
RACKS_CSV = os.path.join(DATA_DIR, "racks.csv")


def _read_csv(path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def _read_latest_device_state(device_id: str) -> Dict[str, Any]:
    """Read the last row from data/device_logs/{device_id}.csv.
    Returns fields including right_drive,left_drive,right_motor,left_motor,current_location.
    """
    path = os.path.join(DEVICE_LOGS_DIR, f"{device_id}.csv")
    if not os.path.exists(path):
        return {}
    last: Optional[Dict[str, str]] = None
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            last = r
    return last or {}


def _initial_offset_from_logs(device_id: str) -> float:
    """Meters offset along the current zone from its starting point, based on right_drive (mm)."""
    row = _read_latest_device_state(device_id)
    try:
        rd_mm = float(row.get("right_drive", 0) or 0)
        return rd_mm / 1000.0
    except Exception:
        return 0.0


def _read_device_speeds(device_id: str) -> tuple[int, int]:
    """Read forward_speed and turning_speed from data/devices.csv for the device.
    Returns a tuple (forward_speed, turning_speed) as integers. Defaults to (0,0) if not found.
    """
    fs, ts = 0, 0
    try:
        if not os.path.exists(DEVICES_CSV):
            return fs, ts
        with open(DEVICES_CSV, "r", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if str(r.get("device_id", "")).strip() == str(device_id).strip():
                    try:
                        fs = int(float(r.get("forward_speed", 0) or 0))
                    except Exception:
                        fs = 0
                    try:
                        ts = int(float(r.get("turning_speed", 0) or 0))
                    except Exception:
                        ts = 0
                    break
    except Exception:
        pass
    return fs, ts


def _read_device_vertical_speed(device_id: str) -> int:
    vs = 0
    try:
        if not os.path.exists(DEVICES_CSV):
            return vs
        with open(DEVICES_CSV, "r", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if str(r.get("device_id", "")).strip() == str(device_id).strip():
                    try:
                        vs = int(float(r.get("vertical_speed", 0) or 0))
                    except Exception:
                        vs = 0
                    break
    except Exception:
        pass
    return vs


def _load_zone_alignment(map_id: str) -> Dict[str, str]:
    """Load per-zone alignment settings for a given map.

    Returns a mapping {zone: alignment_value} where alignment_value is the raw
    CSV value (e.g. 'Yes' or 'No'). Missing zones imply alignment "No".
    """
    settings: Dict[str, str] = {}
    try:
        rows = _read_csv(ZONE_ALIGNMENT_CSV)
        for r in rows:
            if str(r.get("map_id")) != str(map_id):
                continue
            zone = str(r.get("zone") or "").strip()
            if not zone:
                continue
            alignment = str(r.get("alignment") or "").strip()
            settings[zone] = alignment
    except Exception:
        # Non-fatal; treat as all zones having default alignment "No"
        pass
    return settings


def generate_leg_commands(
    device_id: str,
    map_id: str,
    zone_sequence: List[Tuple[str, str]],
    initial_direction: str,
    task_type: Optional[str] = None,
    selected_stop_ids: Optional[List[str]] = None,
    selected_rack_ids: Optional[List[str]] = None,
    drop_zone: Optional[str] = None,
    forward_speed: Optional[int] = None,
    turning_speed: Optional[int] = None,
    stop_operations: Optional[Dict[str, str]] = None,
) -> Tuple[List[Tuple], str]:
    """
    Generate path commands for a single leg without writing to file.
    Returns (commands_list, last_direction) for chaining multiple legs.
    """
    zones_rows = _read_csv(ZONES_CSV)
    stops_rows = _read_csv(STOPS_CSV)

    # Filter stops by selection if provided
    if selected_stop_ids or selected_rack_ids:
        allowed_stops: set = set()
        if selected_stop_ids:
            allowed_stops.update(str(s) for s in selected_stop_ids)
        if selected_rack_ids:
            racks_rows = _read_csv(RACKS_CSV)
            for r in racks_rows:
                if str(r.get('rack_id') or '').strip() in (str(rid) for rid in selected_rack_ids):
                    sid = str(r.get('stop_id') or '').strip()
                    if sid:
                        allowed_stops.add(sid)
        stops_rows = [r for r in stops_rows if str(r.get('stop_id') or '').strip() in allowed_stops]

    graph = build_graph_from_zones(zones_rows, map_id)
    stops_by_conn = load_stops(stops_rows, map_id)
    zone_alignment = _load_zone_alignment(map_id)

    # Get device speeds
    fs, ts = forward_speed, turning_speed
    if fs is None or ts is None:
        fs_csv, ts_csv = _read_device_speeds(device_id)
        fs = fs or fs_csv
        ts = ts or ts_csv

    cmds = generate_path_commands(
        graph=graph,
        zones_rows=zones_rows,
        stops_by_conn=stops_by_conn,
        zone_sequence=zone_sequence,
        initial_direction=initial_direction,
        initial_offset_m=0.0,  # Not using offset for mid-journey legs
        forward_speed=fs,
        turning_speed=ts,
        vertical_speed=None,
        task_type=task_type,
        zone_alignment=zone_alignment,
        selected_racks_by_stop=None,
        drop_zone=drop_zone,
        stop_operations=stop_operations,
    )

    # Determine final direction from last edge if possible
    last_dir = initial_direction
    for fz, tz in reversed(zone_sequence):
        for zr in zones_rows:
            if (str(zr.get('from_zone')) == str(fz) and 
                str(zr.get('to_zone')) == str(tz) and
                str(zr.get('map_id')) == str(map_id)):
                last_dir = str(zr.get('direction') or initial_direction).lower()
                break
        else:
            continue
        break

    return cmds, last_dir


def plan_and_write_path(
    device_id: str,
    map_id: str,
    zone_sequence: List[Tuple[str, str]],
    initial_direction: str,
    task_type: Optional[str] = None,
    output_dir: Optional[str] = None,
    selected_stop_ids: Optional[List[str]] = None,
    selected_rack_ids: Optional[List[str]] = None,
    drop_zone: Optional[str] = None,
    end_zone: Optional[str] = None,
    pickup_stops: Optional[List[str]] = None,
    check_stops: Optional[List[str]] = None,
    drop_stops: Optional[List[str]] = None,
) -> str:
    """
    Generate path commands and write to data/device_logs/path_{device_id}.csv.

    - device_id: unique device identifier (used for input log and output file name)
    - map_id: which map to use from zones/stops
    - zone_sequence: ordered list of (from_zone,to_zone) pairs to traverse
    - initial_direction: robot's current facing direction ('north','south','east','west')
    - output_dir: optional override of output directory (defaults to data/device_logs)

    Returns the path to the written file.
    """
    zones_rows = _read_csv(ZONES_CSV)
    stops_rows = _read_csv(STOPS_CSV)

    selected_racks_by_stop: Dict[str, List[Tuple[str, float]]] = {}
    rack_id_to_stop: Dict[str, str] = {}
    rack_by_stop: Dict[str, List[Dict[str, str]]] = {}

    try:
        maps_rows = _read_csv(MAPS_CSV)
        map_name_lookup: Dict[str, str] = {}
        for m in maps_rows:
            mid = str(m.get("id", "")).strip()
            if not mid:
                continue
            map_name_lookup[mid] = (m.get("name") or "").strip()

        current_map_name = map_name_lookup.get(str(map_id), "")

        if current_map_name:
            racks_rows = _read_csv(RACKS_CSV)
            for r in racks_rows:
                r_map = (r.get("map_name") or "").strip()
                if r_map != current_map_name:
                    continue
                sid = (r.get("stop_id") or "").strip()
                if not sid:
                    continue
                rid = (r.get("rack_id") or "").strip()
                rack_by_stop.setdefault(sid, []).append(r)
                if rid:
                    rack_id_to_stop[rid] = sid

            if rack_by_stop:
                for s in stops_rows:
                    if str(s.get("map_id")) != str(map_id):
                        continue
                    sid = str(s.get("stop_id") or "").strip()
                    if not sid:
                        continue
                    r_list = rack_by_stop.get(sid) or []
                    if not r_list:
                        continue
                    r0 = r_list[0]
                    s["rack_id"] = (r0.get("rack_id") or "").strip()
                    s["rack_distance_mm"] = (r0.get("rack_distance_mm") or "").strip()
    except Exception:
        pass

    # If a subset of stops is provided (e.g. Picking "Pick Up Stops"),
    # filter stops to only those stop_id values. This ensures the path
    # planner visits exactly the requested logical stops while other
    # task types (Auditing/Storing) continue to use all stops.
    # For picking tasks with pickup/check/drop stops, include all of them
    allowed_stops: Dict[str, bool] = {}
    if selected_stop_ids:
        for s in selected_stop_ids:
            if str(s).strip():
                allowed_stops[str(s).strip()] = True
    if selected_rack_ids and rack_id_to_stop:
        for rid in selected_rack_ids:
            rid_str = str(rid).strip()
            if not rid_str:
                continue
            sid = rack_id_to_stop.get(rid_str)
            if sid:
                allowed_stops[sid] = True
    # Include pickup, check, and drop stops for picking tasks
    if pickup_stops:
        for s in pickup_stops:
            if str(s).strip():
                allowed_stops[str(s).strip()] = True
    if check_stops:
        for s in check_stops:
            if str(s).strip():
                allowed_stops[str(s).strip()] = True
    if drop_stops:
        for s in drop_stops:
            if str(s).strip():
                allowed_stops[str(s).strip()] = True
    if allowed_stops:
        stops_rows = [
            r for r in stops_rows
            if str(r.get("stop_id", "")).strip() in allowed_stops
        ]

    if selected_rack_ids and rack_id_to_stop:
        for rid in selected_rack_ids:
            rid_str = str(rid).strip()
            if not rid_str:
                continue
            sid = rack_id_to_stop.get(rid_str)
            if not sid:
                continue
            rows = rack_by_stop.get(sid) or []
            row = None
            for r in rows:
                rv = (r.get("rack_id") or "").strip()
                if rv == rid_str:
                    row = r
                    break
            if not row:
                continue
            val = row.get("rack_distance_mm") or ""
            try:
                dist = float(val)
            except Exception:
                try:
                    dist = float(str(val).strip()) if str(val).strip() else 0.0
                except Exception:
                    dist = 0.0
            selected_racks_by_stop.setdefault(sid, []).append((rid_str, dist))

    # If charging task, ignore all intermediate stops/racks
    if task_type and str(task_type).lower() == 'charging':
        stops_rows = []

    graph = build_graph_from_zones(zones_rows, map_id)
    stops_by_conn = load_stops(stops_rows, map_id)

    zone_alignment = _load_zone_alignment(map_id)

    initial_offset_m = _initial_offset_from_logs(device_id)

    fs, ts = _read_device_speeds(device_id)
    vs = _read_device_vertical_speed(device_id)

    # Build stop_operations mapping: stop_id -> operation ('pickup', 'check', 'drop')
    stop_operations: Dict[str, str] = {}
    if pickup_stops:
        for stop_id in pickup_stops:
            stop_operations[str(stop_id)] = 'pickup'
    if check_stops:
        for stop_id in check_stops:
            stop_operations[str(stop_id)] = 'check'
    if drop_stops:
        for stop_id in drop_stops:
            stop_operations[str(stop_id)] = 'drop'
    
    # Use end_zone if provided, otherwise fallback to drop_zone for backward compatibility
    target_end_zone = end_zone if end_zone else drop_zone

    cmds = generate_path_commands(
        graph=graph,
        zones_rows=zones_rows,
        stops_by_conn=stops_by_conn,
        zone_sequence=zone_sequence,
        initial_direction=initial_direction,
        initial_offset_m=initial_offset_m,
        forward_speed=fs,
        turning_speed=ts,
        vertical_speed=vs,
        task_type=task_type,
        zone_alignment=zone_alignment,
        selected_racks_by_stop=selected_racks_by_stop,
        drop_zone=drop_zone,  # Keep for backward compatibility
        end_zone=target_end_zone,
        stop_operations=stop_operations if stop_operations else None,
    )

    if task_type and str(task_type).lower() == 'charging':
        cmds.append(('CALL', 'CHARGING'))

    rows = serialize_commands_to_csv_rows(cmds, device_id, task_type=task_type)

    out_dir = output_dir or DEVICE_LOGS_DIR
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"path_{device_id}.csv")

    # Overwrite fully, per-user requirement
    write_commands_csv(out_path, rows)

    return out_path


def plan_and_write_picking_path(
    device_id: str,
    map_id: str,
    pickup_stops: List[str] = None,
    pickup_racks: List[str] = None,
    drop_zone: str = None,
    initial_direction: str = 'north',
    current_zone: Optional[str] = None
) -> str:
    """
    Generate and write path commands for a picking task (round-trip per stop).
    """
    if not pickup_stops:
        pickup_stops = []
    
    # Resolve racks to stops if provided
    if pickup_racks:
        racks_rows = _read_csv(RACKS_CSV)
        id_to_stop = {}
        for r in racks_rows:
            rid = str(r.get('rack_id') or '').strip()
            sid = str(r.get('stop_id') or '').strip()
            if rid and sid:
                id_to_stop[rid] = sid
        for rid in pickup_racks:
            sid = id_to_stop.get(str(rid))
            if sid and sid not in pickup_stops:
                pickup_stops.append(sid)

    if not pickup_stops:
        raise ValueError("No valid pickup stops or racks provided.")

    zones_rows = _read_csv(ZONES_CSV)
    stops_rows = _read_csv(STOPS_CSV)
    zone_by_id = {str(z.get('id')): z for z in zones_rows if str(z.get('map_id')) == str(map_id)}

    last_zone = str(current_zone) if current_zone else None
    if not last_zone:
        # Try to derive current zone from logs
        state = _read_latest_device_state(device_id)
        last_zone = state.get('current_location')
    
    if not last_zone:
        # Fallback: smallest zone id in map
        zone_ids = set()
        for z in zones_rows:
            if str(z.get('map_id')) == str(map_id):
                zone_ids.add(str(z.get('from_zone')))
                zone_ids.add(str(z.get('to_zone')))
        zone_ids = {z for z in zone_ids if z}
        
        def zone_key(z: str):
            s = str(z)
            return (0, int(s)) if s.isdigit() else (1, s)
        
        last_zone = sorted(zone_ids, key=zone_key)[0] if zone_ids else None

    all_cmds = []
    cur_direction = str(initial_direction).lower()

    for sid in pickup_stops:
        # Get edge for this stop
        s_row = next((r for r in stops_rows if str(r.get('stop_id')) == str(sid) and str(r.get('map_id')) == str(map_id)), None)
        if not s_row:
            continue
        conn_id = str(s_row.get('zone_connection_id') or '').strip()
        if not conn_id:
            continue
        z_row = zone_by_id.get(conn_id)
        if not z_row:
            continue
        fz = str(z_row.get('from_zone'))
        tz = str(z_row.get('to_zone'))

        # Build zone_sequence for this leg: current -> fz -> tz -> drop_zone
        leg_sequence = []
        if last_zone and last_zone != fz:
            leg_sequence.append((str(last_zone), fz))
        leg_sequence.append((fz, tz))
        if tz != str(drop_zone):
            leg_sequence.append((tz, str(drop_zone)))
        
        if leg_sequence:
            leg_cmds, cur_direction = generate_leg_commands(
                device_id=device_id,
                map_id=str(map_id),
                zone_sequence=leg_sequence,
                initial_direction=cur_direction,
                task_type='picking',
                selected_stop_ids=[sid],
                drop_zone=str(drop_zone),
            )
            # Deduplicate ALIGN commands
            if all_cmds and leg_cmds:
                last_cmd = all_cmds[-1]
                first_cmd = leg_cmds[0]
                if (len(last_cmd) >= 2 and len(first_cmd) >= 2 and
                    str(last_cmd[0]).upper() == 'ALIGN' and
                    str(first_cmd[0]).upper() == 'ALIGN' and
                    str(last_cmd[1]) == str(first_cmd[1])):
                    leg_cmds = leg_cmds[1:]
            all_cmds.extend(leg_cmds)
            last_zone = str(drop_zone)

    if not all_cmds:
        raise ValueError("Could not generate any path commands for picking task.")

    rows = serialize_commands_to_csv_rows(all_cmds, device_id)
    out_path = os.path.join(DEVICE_LOGS_DIR, f"path_{device_id}.csv")
    write_commands_csv(out_path, rows)
    return out_path


if __name__ == "__main__":
    # Simple manual smoke test using the example described by the user (map_id 13)
    device = "DEV001"
    path = plan_and_write_path(
        device_id=device,
        map_id="13",
        zone_sequence=[("1","2"),("2","4"),("4","2"),("2","3"),("3","2"),("2","1")],
        initial_direction="north",
    )

