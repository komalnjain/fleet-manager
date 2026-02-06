#!/usr/bin/env python3
"""
A* Path Planner and Command Generator for zone-based maps.

- Builds a directed graph from `zones.csv` for a given `map_id`.
- Optionally runs A* to compute a shortest path between zones.
- Generates motor commands for moving along each edge and handling stops.
- Serializes commands to a list of CSV rows [command, value, unit].

Assumptions and conventions:
- Distance/magnitude in `zones.csv` are in meters. We convert to millimeters for F,SR,SL commands.
- Turn commands: PVTR (right), PVTL (left), 90/180 DEG.
- Forward command: F,<mm>,MM
- Side commands: SR/SL,<mm>,MM then return SL/SR with same distance.
- Stops are described in `stops.csv` using `zone_connection_id` that maps to an edge (from_zone->to_zone).
- Side selection heuristic:
    1) If left_bins_count>0 and right_bins_count==0 => left
    2) If right_bins_count>0 and left_bins_count==0 => right
    3) Else parse stop_id/name for 'LEFT'/'RIGHT' tokens (case-insensitive)
    4) Else default to right

Orientation logic (critical and consistent with existing `ZoneNavigationManager`):
- north + right => east
- north + left  => west
- south + right => west
- south + left  => east
- east + right  => south
- east + left   => north
- west + right  => north
- west + left   => south

Author: Cascade A* module
"""
from __future__ import annotations

import csv
import heapq
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any

# Import for reading CSV files
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
STOPS_CSV = os.path.join(DATA_DIR, "stops.csv")
ZONES_CSV = os.path.join(DATA_DIR, "zones.csv")

# Types
ZoneId = str
Direction = str  # 'north'|'south'|'east'|'west'


@dataclass
class Edge:
    from_zone: ZoneId
    to_zone: ZoneId
    distance_m: float
    direction: Direction
    connection_id: Optional[int] = None


class ZoneGraph:
    def __init__(self):
        self.adj: Dict[ZoneId, List[Edge]] = {}

    def add_edge(self, edge: Edge):
        self.adj.setdefault(edge.from_zone, []).append(edge)

    def neighbors(self, zone: ZoneId) -> List[Edge]:
        return self.adj.get(zone, [])


# Directions and turning logic
TURN_MAP = {
    'north': {'left': 'west', 'right': 'east'},
    'south': {'left': 'east', 'right': 'west'},
    'east':  {'left': 'north', 'right': 'south'},
    'west':  {'left': 'south', 'right': 'north'},
}

# Determine required turn from current_direction to target_direction
# Returns tuple (turn_cmd: Optional[str], degrees: Optional[int])
# turn_cmd in {'PVTR','PVTL'}; degrees in {90,180} or None when no turn

def compute_turn(current_direction: Direction, target_direction: Direction) -> Tuple[Optional[str], Optional[int]]:
    cur = current_direction.lower()
    tgt = target_direction.lower()
    if cur == tgt:
        return None, None
    # 180 U-turn if opposite
    opposite = {
        'north': 'south', 'south': 'north', 'east': 'west', 'west': 'east'
    }
    if opposite.get(cur) == tgt:
        # Use right 180 as in user examples
        return 'PVTR', 180
    # figure left/right 90
    for turn, ndir in TURN_MAP[cur].items():
        if ndir == tgt:
            return ('PVTL', 90) if turn == 'left' else ('PVTR', 90)
    # Fallback
    return 'PVTR', 90


# A* (zones weighted by distance)

def heuristic(a: ZoneId, b: ZoneId) -> float:
    # Simple admissible heuristic: 0 (Dijkstra). Extend later if we have coordinates.
    return 0.0


def astar_path(graph: ZoneGraph, start: ZoneId, goal: ZoneId) -> List[ZoneId]:
    frontier: List[Tuple[float, ZoneId]] = []
    heapq.heappush(frontier, (0.0, start))
    came_from: Dict[ZoneId, Optional[ZoneId]] = {start: None}
    cost_so_far: Dict[ZoneId, float] = {start: 0.0}

    while frontier:
        _, current = heapq.heappop(frontier)
        if current == goal:
            break
        for edge in graph.neighbors(current):
            new_cost = cost_so_far[current] + edge.distance_m
            if edge.to_zone not in cost_so_far or new_cost < cost_so_far[edge.to_zone]:
                cost_so_far[edge.to_zone] = new_cost
                priority = new_cost + heuristic(edge.to_zone, goal)
                heapq.heappush(frontier, (priority, edge.to_zone))
                came_from[edge.to_zone] = current

    # Reconstruct
    if goal not in came_from:
        return []
    path: List[ZoneId] = []
    cur: Optional[ZoneId] = goal
    while cur is not None:
        path.append(cur)
        cur = came_from[cur]
    path.reverse()
    return path


# Stops handling
@dataclass
@dataclass
class Stop:
    connection_id: int
    name: str
    stop_id: str
    distance_from_start_m: float
    side: str  # 'left'|'right'
    side_distance_m: float
    stop_type: str  # 'left'|'right'|'center'|'' (positional type)
    rack_id: str = ''
    rack_distance_mm: float = 0.0
    stop_function: str = ''  # 'pickup'|'check'|'drop'|'charging'|'end' (operational type)


def infer_side(stop_row: Dict[str, Any]) -> str:
    left_count = int(float(stop_row.get('left_bins_count', 0) or 0))
    right_count = int(float(stop_row.get('right_bins_count', 0) or 0))
    stop_id = (stop_row.get('stop_id') or '').lower()
    name = (stop_row.get('name') or '').lower()
    if left_count > 0 and right_count == 0:
        return 'left'
    if right_count > 0 and left_count == 0:
        return 'right'
    if 'left' in stop_id or 'left' in name:
        return 'left'
    if 'right' in stop_id or 'right' in name:
        return 'right'
    # default
    return 'right'


def build_graph_from_zones(zones_rows: List[Dict[str, str]], map_id: str) -> ZoneGraph:
    g = ZoneGraph()
    for r in zones_rows:
        if str(r.get('map_id')) != str(map_id):
            continue
        try:
            edge = Edge(
                from_zone=str(r['from_zone']).strip(),
                to_zone=str(r['to_zone']).strip(),
                distance_m=float(r['magnitude']),
                direction=str(r['direction']).lower().strip(),
                connection_id=int(r['id']) if r.get('id') else None,
            )
            g.add_edge(edge)
        except Exception:
            continue
    return g


def load_stops(stops_rows: List[Dict[str, str]], map_id: str) -> Dict[int, List[Stop]]:
    by_conn: Dict[int, List[Stop]] = {}
    for r in stops_rows:
        if str(r.get('map_id')) != str(map_id):
            continue
        try:
            conn_id = int(r['zone_connection_id'])
            dist_m = float(r['distance_from_start'])
            # Stop type from CSV (may be missing in legacy rows)
            stype = str(r.get('stop_type', '') or '').strip().lower()
            # Prefer explicit stop_type for side; otherwise infer
            if stype in ('left', 'right'):
                side = stype
            else:
                side = infer_side(r)
            # Robust parse for distances; treat N/A or blanks as 0
            def _to_float(val: Any) -> float:
                try:
                    return float(val)
                except Exception:
                    return 0.0
            left_d = _to_float(r.get('left_bins_distance'))
            right_d = _to_float(r.get('right_bins_distance'))
            # For center, no lateral movement
            side_dist_m = 0.0 if stype == 'center' else (left_d if side == 'left' else right_d)
            rack_id = str(r.get('rack_id') or '').strip()
            rack_distance_mm = _to_float(r.get('rack_distance_mm'))
            stop_id = str(r.get('stop_id') or '').strip()
            # Use stop_function for operation type (pickup, check, drop, charging, end)
            stop_function = str(r.get('stop_function', '') or '').strip().lower()
            by_conn.setdefault(conn_id, []).append(
                Stop(
                    connection_id=conn_id,
                    name=r.get('name') or '',
                    stop_id=stop_id,
                    distance_from_start_m=dist_m,
                    side=side,
                    side_distance_m=side_dist_m,
                    stop_type=stype,  # This is positional (center/left/right)
                    rack_id=rack_id,
                    rack_distance_mm=rack_distance_mm,
                    stop_function=stop_function,  # This is operational (pickup/check/drop/charging/end)
                )
            )
        except Exception:
            continue
    # sort by distance, then by operation priority (pickup → check → drop → charging → end)
    operation_priority = {
        'pickup': 1,
        'check': 2,
        'drop': 3,
        'charging': 4,
        'end': 5,
    }
    for k in by_conn:
        # Sort by distance first, then by stop function (operation) priority
        by_conn[k].sort(key=lambda s: (
            s.distance_from_start_m,
            operation_priority.get(s.stop_function, 999)
        ))
    return by_conn


def mm(meters: float) -> int:
    return int(round(meters * 1000))


def generate_edge_commands(
    edge: Edge,
    current_direction: Direction,
    current_offset_m: float,
    stops_on_edge: List[Stop],
    task_type: Optional[str] = None,
    vertical_speed: Optional[int] = None,
    selected_racks_by_stop: Optional[Dict[str, List[Tuple[str, float]]]] = None,
    stop_operations: Optional[Dict[str, str]] = None,  # Maps stop_id to operation: 'pickup', 'check', 'drop'
) -> Tuple[List[Tuple[Any, ...]], Direction]:
    """
    Generate commands to traverse a single edge from current offset to end, visiting stops.
    Returns (commands, new_direction)
    """
    commands: List[Tuple[Any, ...]] = []

    # Turn if needed before entering edge direction.
    # Do not add ALIGN here: the caller already adds ALIGN at the previous segment's to_zone
    # (which equals this edge's from_zone), so adding ALIGN(from_zone) again would duplicate.
    turn_cmd, deg = compute_turn(current_direction, edge.direction)
    if turn_cmd and deg:
        commands.append((turn_cmd, deg, 'DEG'))
        current_direction = edge.direction  # orientation after the turn

    # Travel along the edge, accounting for current offset
    traveled_m = max(0.0, float(current_offset_m))
    total_m = float(edge.distance_m)

    def forward_to(target_m: float):
        nonlocal traveled_m
        delta = max(0.0, target_m - traveled_m)
        if delta > 0:
            commands.append(('F', mm(delta), 'MM'))
            traveled_m += delta

    # Visit each stop in order
    for stop in stops_on_edge:
        # Go forward to stop longitudinal position
        forward_to(stop.distance_from_start_m)
        # If center stop or side distance is 0/N/A, do nothing (no WAITIN)
        stype = (stop.stop_type or '').lower()
        if not (stype == 'center' or (stop.side_distance_m is None or stop.side_distance_m <= 0.0)):
            # Side approach and return
            if stop.side == 'left':
                commands.append(('SL', mm(stop.side_distance_m), 'MM'))
                commands.append(('SR', mm(stop.side_distance_m), 'MM'))
            else:
                commands.append(('SR', mm(stop.side_distance_m), 'MM'))
                commands.append(('SL', mm(stop.side_distance_m), 'MM'))

        # Logical task callback at the stop - use stop_operations if provided, otherwise fallback to task_type
        stop_key = getattr(stop, 'stop_id', '') or ''
        operation = None
        if stop_operations and stop_key:
            operation = stop_operations.get(str(stop_key))
        
        if operation:
            # Use specific operation for this stop
            if operation == 'pickup':
                per_stop_racks: List[Tuple[str, float]] = []
                try:
                    if selected_racks_by_stop and stop_key:
                        per_stop_racks = selected_racks_by_stop.get(str(stop_key), []) or []
                except Exception:
                    per_stop_racks = []

                if per_stop_racks and vertical_speed:
                    try:
                        vs_val = int(vertical_speed)
                    except Exception:
                        vs_val = 0
                    if vs_val <= 0:
                        commands.append(('CALL', 'PICKUP'))
                    else:
                        for _, rack_mm in per_stop_racks:
                            try:
                                mm_val = int(round(float(rack_mm)))
                            except Exception:
                                try:
                                    mm_val = int(rack_mm)  # type: ignore[arg-type]
                                except Exception:
                                    mm_val = 0
                            if mm_val > 0:
                                commands.append(('VMOV', mm_val, vs_val))
                                commands.append(('CALL', 'PICKUP'))
                                commands.append(('VMOV', mm_val, vs_val))
                            else:
                                commands.append(('CALL', 'PICKUP'))
                else:
                    commands.append(('CALL', 'PICKUP'))
            elif operation == 'check':
                commands.append(('CALL', 'CHECK'))
            elif operation == 'drop':
                commands.append(('CALL', 'DROP'))
            elif operation == 'charging':
                commands.append(('CALL', 'CHARGING'))
            elif operation == 'end':
                commands.append(('CALL', 'END'))
                # CRITICAL: Stop processing after END - no more commands should be generated
                # Don't finish remaining forward distance - END is the final stop
                return commands, current_direction
        elif task_type:
            # Fallback to task_type-based logic
            tt = str(task_type).lower()
            if tt == 'picking':
                per_stop_racks: List[Tuple[str, float]] = []
                try:
                    if selected_racks_by_stop and stop_key:
                        per_stop_racks = selected_racks_by_stop.get(str(stop_key), []) or []
                except Exception:
                    per_stop_racks = []

                if per_stop_racks and vertical_speed:
                    try:
                        vs_val = int(vertical_speed)
                    except Exception:
                        vs_val = 0
                    if vs_val <= 0:
                        commands.append(('CALL', 'PICKUP'))
                    else:
                        for _, rack_mm in per_stop_racks:
                            try:
                                mm_val = int(round(float(rack_mm)))
                            except Exception:
                                try:
                                    mm_val = int(rack_mm)  # type: ignore[arg-type]
                                except Exception:
                                    mm_val = 0
                            if mm_val > 0:
                                commands.append(('VMOV', mm_val, vs_val))
                                commands.append(('CALL', 'PICKUP'))
                                commands.append(('VMOV', mm_val, vs_val))
                            else:
                                commands.append(('CALL', 'PICKUP'))
                else:
                    commands.append(('CALL', 'PICKUP'))
            elif tt in ('storing', 'store'):
                commands.append(('CALL', 'STORE'))
            elif tt in ('auditing', 'audit'):
                commands.append(('CALL', 'AUDIT'))

    # Finish remaining forward distance to end of edge
    # BUT: If we already called END, we should have returned earlier
    # This ensures we don't add unnecessary movement after END
    forward_to(total_m)

    return commands, current_direction


def generate_path_commands(
    graph: ZoneGraph,
    zones_rows: List[Dict[str, str]],
    stops_by_conn: Dict[int, List[Stop]],
    zone_sequence: List[Tuple[ZoneId, ZoneId]],
    initial_direction: Direction,
    initial_offset_m: float,
    forward_speed: Optional[int] = None,
    turning_speed: Optional[int] = None,
    vertical_speed: Optional[int] = None,
    task_type: Optional[str] = None,
    zone_alignment: Optional[Dict[str, str]] = None,
    selected_racks_by_stop: Optional[Dict[str, List[Tuple[str, float]]]] = None,
    drop_zone: Optional[str] = None,
    end_zone: Optional[str] = None,  # Renamed from drop_zone, but keeping drop_zone for backward compatibility
    end_stop_id: Optional[str] = None,  # Stop ID to use for CALL,{end_stop_id} instead of CALL,END
    stop_operations: Optional[Dict[str, str]] = None,  # Maps stop_id to operation: 'pickup', 'check', 'drop'
    map_id: Optional[str] = None,  # Map ID to filter zone rows
) -> List[Tuple[Any, ...]]:
    # Helper to choose ALIGN variant based on per-zone alignment settings.
    def _align_cmd(zone: ZoneId) -> Tuple[str, str, str, str]:
        align_val = None
        try:
            if zone_alignment:
                align_val = zone_alignment.get(str(zone))
        except Exception:
            align_val = None
        # Treat anything starting with 'y'/'Y' as Yes => last arg '1', else '0'
        last_param = '1' if align_val and str(align_val).strip().lower().startswith('y') else '0'
        return ('ALIGN', str(zone), '0', last_param)
    # map connection by (from,to) to edge
    conn_lookup: Dict[Tuple[str, str], Edge] = {}
    for r in zones_rows:
        # Filter by map_id if provided to avoid conflicts between maps
        if map_id and str(r.get('map_id', '')) != str(map_id):
            continue
        try:
            edge = Edge(
                from_zone=str(r['from_zone']).strip(),
                to_zone=str(r['to_zone']).strip(),
                distance_m=float(r['magnitude']),
                direction=str(r['direction']).lower().strip(),
                connection_id=int(r['id']) if r.get('id') else None,
            )
            conn_lookup[(edge.from_zone, edge.to_zone)] = edge
        except Exception:
            continue

    cmds: List[Tuple[Any, ...]] = []
    cur_dir = initial_direction
    offset_m_for_first_edge = initial_offset_m

    last_arrival_zone: Optional[str] = None
    end_reached = False  # Flag to track if END has been called
    for i, (fz, tz) in enumerate(zone_sequence):
        # Stop processing if END has been reached
        if end_reached:
            break
            
        if i == 0 and initial_offset_m <= 0.0:
            try:
                cmds.append(_align_cmd(fz))
            except Exception:
                pass
        edge = conn_lookup.get((str(fz), str(tz)))
        if not edge:
            # try to compute A* between zones and expand
            path = astar_path(graph, str(fz), str(tz))
            if not path or len(path) < 2:
                # cannot move, skip
                continue
            # turn path into pair edges
            sub_pairs = list(zip(path[:-1], path[1:]))
            for j, (sf, st) in enumerate(sub_pairs):
                # Stop if END reached
                if end_reached:
                    break
                sub_edge = conn_lookup.get((sf, st))
                if not sub_edge:
                    continue
                stops = stops_by_conn.get(sub_edge.connection_id or -1, [])
                seg_cmds, cur_dir = generate_edge_commands(
                    sub_edge,
                    cur_dir,
                    offset_m_for_first_edge if (i == 0 and j == 0) else 0.0,
                    stops,
                    task_type=task_type,
                    vertical_speed=vertical_speed,
                    selected_racks_by_stop=selected_racks_by_stop,
                    stop_operations=stop_operations,
                )
                cmds.extend(seg_cmds)
                # Check if END was called in this segment
                if any(isinstance(cmd, (tuple, list)) and len(cmd) >= 2 and 
                       str(cmd[0]).upper() == 'CALL' and str(cmd[1]).upper() == 'END' 
                       for cmd in seg_cmds):
                    end_reached = True
                    break
                last_arrival_zone = sub_edge.to_zone
                try:
                    is_last_overall_leg = (i == len(zone_sequence) - 1) and (j == len(sub_pairs) - 1)
                    if not is_last_overall_leg:
                        cmds.append(_align_cmd(sub_edge.to_zone))
                except Exception:
                    pass
            offset_m_for_first_edge = 0.0
        else:
            stops = stops_by_conn.get(edge.connection_id or -1, [])
            seg_cmds, cur_dir = generate_edge_commands(
                edge,
                cur_dir,
                offset_m_for_first_edge if i == 0 else 0.0,
                stops,
                task_type=task_type,
                vertical_speed=vertical_speed,
                selected_racks_by_stop=selected_racks_by_stop,
                stop_operations=stop_operations,
            )
            cmds.extend(seg_cmds)
            # Check if END was called in this segment
            if any(isinstance(cmd, (tuple, list)) and len(cmd) >= 2 and 
                   str(cmd[0]).upper() == 'CALL' and str(cmd[1]).upper() == 'END' 
                   for cmd in seg_cmds):
                end_reached = True
                break  # Stop processing further edges
            offset_m_for_first_edge = 0.0
            last_arrival_zone = edge.to_zone
            try:
                if i < len(zone_sequence) - 1:
                    cmds.append(_align_cmd(edge.to_zone))
                # Handle end_zone (preferred) or drop_zone (backward compatibility)
                # End zone is just a final destination - no operations here
                # DROP operations happen at drop_stops (handled in generate_edge_commands via stop_operations)
                target_end_zone = end_zone if end_zone else drop_zone
                if target_end_zone:
                    if str(edge.to_zone) == str(target_end_zone) and i >= len(zone_sequence) - 1:
                        # Last edge reaching end zone - add ALIGN and END marker
                        # END is just a marker for final destination, no operations
                        cmds.append(_align_cmd(edge.to_zone))
                        # Note: CALL,END should already be generated at the end_stop via stop_operations
                        # Skip adding CALL,END here to avoid duplication when end_stop_id is provided
                        # Only emit CALL,END if no end_stop_id is specified
                        if not end_stop_id:
                            cmds.append(('CALL', 'END'))
                            end_reached = True
            except Exception:
                pass

    # If END was reached, don't add any more commands
    if end_reached:
        return cmds
    
    # Append final ALIGN at the last arrival zone, if available
    # Skip for tasks with end_zone - ALIGN was already added before END
    if last_arrival_zone is not None:
        try:
            target_end_zone = end_zone if end_zone else drop_zone
            # For tasks with end_zone, skip final ALIGN (already added before END)
            if target_end_zone and str(last_arrival_zone) == str(target_end_zone):
                pass  # ALIGN already added with END
            else:
                cmds.append(_align_cmd(last_arrival_zone))
        except Exception:
            pass

    # For non-picking tasks, return to initial facing direction at the end.
    # For picking tasks, skip this final reorientation and just stop at drop zone.
    try:
        if not (task_type and str(task_type).lower() == 'picking'):
            turn_cmd, deg = compute_turn(cur_dir, initial_direction)
            if turn_cmd and deg:
                cmds.append((turn_cmd, deg, 'DEG'))
    except Exception:
        pass
    # Canonicalize and de-duplicate ALIGN commands.
    # For any consecutive ALIGNs targeting the same zone, keep only one, and
    # force its last parameter to reflect the current zone_alignment setting.
    cleaned_cmds: List[Tuple[Any, ...]] = []
    for c in cmds:
        try:
            if not isinstance(c, (tuple, list)) or len(c) == 0:
                cleaned_cmds.append(c)
                continue

            op = str(c[0]).upper()
            if op != 'ALIGN':
                cleaned_cmds.append(c)
                continue

            # Determine zone id from the ALIGN command (second field if present)
            zone_val = c[1] if len(c) > 1 else ''
            canonical = _align_cmd(zone_val)

            # If the previous cleaned command is also ALIGN for the same zone,
            # replace it with the canonical one instead of appending a second.
            if cleaned_cmds:
                last = cleaned_cmds[-1]
                try:
                    if (
                        isinstance(last, (tuple, list)) and len(last) > 1
                        and str(last[0]).upper() == 'ALIGN'
                        and str(last[1]) == str(zone_val)
                    ):
                        cleaned_cmds[-1] = canonical
                        continue
                except Exception:
                    # If anything goes wrong, just fall back to appending.
                    pass

            cleaned_cmds.append(canonical)
        except Exception:
            # On any unexpected issue, keep the original command.
            cleaned_cmds.append(c)
    cmds = cleaned_cmds
    # Augment commands with speeds where requested
    aug_cmds: List[Tuple[Any, ...]] = []
    for c in cmds:
        try:
            if not isinstance(c, (tuple, list)) or len(c) < 3:
                aug_cmds.append(c)
                continue
            op = str(c[0]).upper()
            if op == 'F' and forward_speed is not None:
                aug_cmds.append((c[0], c[1], c[2], int(forward_speed)))
            elif op in ('PVTR', 'PVTL') and turning_speed is not None:
                aug_cmds.append((c[0], c[1], c[2], int(turning_speed)))
            elif op in ('SR', 'SL') and turning_speed is not None:
                aug_cmds.append((c[0], c[1], c[2], int(turning_speed)))
            else:
                aug_cmds.append(c)
        except Exception:
            aug_cmds.append(c)
    return aug_cmds


def serialize_commands_to_csv_rows(
    cmds: List[Tuple[Any, ...]], 
    device_id: Optional[str] = None, 
    task_type: Optional[str] = None, 
    charging_stops: Optional[List[str]] = None,
    end_stop_id: Optional[str] = None,
    map_id: Optional[str] = None,
    end_zone: Optional[str] = None
) -> List[List[str]]:
    rows: List[List[str]] = [["command", "value", "unit"]]
    # Ensure first command row is HOMING,ALL as requested
    rows.append(["HOMING", "ALL"])
    for item in cmds:
        try:
            if isinstance(item, (list, tuple)):
                rows.append([str(x) for x in item])
            else:
                rows.append([str(item)])
        except Exception:
            rows.append([str(item)])
    
    # Add blank line and LABEL sections at the end
    # Note: CALL,END is already added in generate_path_commands when reaching end_zone
    # Do not add it again here to avoid duplication
    rows.append([])  # Blank line

    tt = str(task_type).lower() if task_type else ""
    has_charging_call = False
    try:
        for c in cmds:
            if isinstance(c, (list, tuple)) and len(c) >= 2 and str(c[0]).upper() == 'CALL' and str(c[1]).upper() == 'CHARGING':
                has_charging_call = True
                break
    except Exception:
        has_charging_call = False

    rows.append(["LABEL", "PICKUP"])

    if device_id:
        pickup_logic_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "device_logs", f"{device_id}_PICKUP_Logic.csv"
        )
        if os.path.exists(pickup_logic_path):
            try:
                with open(pickup_logic_path, 'r', newline='', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            rows.append(line.split(','))
            except Exception:
                pass

    rows.append(["RETURN"])
    rows.append([])  # Blank line
    rows.append(["LABEL", "CHECK"])

    if device_id:
        check_logic_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "device_logs", f"{device_id}_CHECK_Logic.csv"
        )
        if os.path.exists(check_logic_path):
            try:
                with open(check_logic_path, 'r', newline='', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            rows.append(line.split(','))
            except Exception:
                pass

    rows.append(["RETURN"])
    rows.append([])  # Blank line
    rows.append(["LABEL", "DROP"])

    if device_id:
        drop_logic_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "device_logs", f"{device_id}_DROP_Logic.csv"
        )
        if os.path.exists(drop_logic_path):
            try:
                with open(drop_logic_path, 'r', newline='', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            rows.append(line.split(','))
            except Exception:
                pass

    rows.append(["RETURN"])
    rows.append([])  # Blank line
    rows.append(["LABEL", "END"])

    if device_id:
        end_logic_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "device_logs", f"{device_id}_END_Logic.csv"
        )
        if os.path.exists(end_logic_path):
            try:
                with open(end_logic_path, 'r', newline='', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            rows.append(line.split(','))
            except Exception:
                pass
        else:
            # Default END logic: check battery and conditionally go to charging
            # If battery < 20%, CALL CHARGING, else UPDATE_STATUS to IDLE and RETURN
            rows.append(["CHECK_BATTERY", "20"])
            rows.append(["IF_LESS_THAN", "CALL", "CHARGING"])
            rows.append(["ELSE", "UPDATE_STATUS", "IDLE"])
            rows.append(["RETURN"])
    else:
        # If no END_Logic.csv file exists, add default logic
        rows.append(["CHECK_BATTERY", "20"])
        rows.append(["IF_LESS_THAN", "CALL", "CHARGING"])
        rows.append(["ELSE", "UPDATE_STATUS", "IDLE"])
        rows.append(["RETURN"])

    # Don't add extra RETURN here - it's already in the logic file or default logic

    # Always add CHARGING label section for picking tasks (will be called conditionally from END logic)
    # Also add if charging task_type or CALL,CHARGING exists in cmds or charging_stops are provided
    should_add_charging = (tt == 'picking' or tt == 'charging' or has_charging_call or 
                          (charging_stops and len(charging_stops) > 0))
    if should_add_charging:
        rows.append([])  # Blank line
        rows.append(["LABEL", "CHARGING"])
        
        # Always generate navigation path from END stop to charging stop FIRST
        # This ensures robot moves to charging location before executing CHARGING logic
        charging_nav_commands = _generate_charging_navigation(
            end_stop_id, charging_stops, map_id, end_zone
        )
        if charging_nav_commands:
            rows.extend(charging_nav_commands)
        
        if device_id:
            charging_logic_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "device_logs", f"{device_id}_CHARGING_Logic.csv"
            )
            if os.path.exists(charging_logic_path):
                try:
                    with open(charging_logic_path, 'r', newline='', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                rows.append(line.split(','))
                except Exception:
                    pass
            else:
                # Default CHARGING logic: wait until 100% charged
                rows.append(["UPDATE_STATUS", "CHARGING"])
                rows.append(["WAIT_BATTERY", "100"])
                rows.append(["UPDATE_STATUS", "IDLE"])
                rows.append(["RETURN"])
        else:
            # Default CHARGING logic if no device_id
            rows.append(["UPDATE_STATUS", "CHARGING"])
            rows.append(["WAIT_BATTERY", "100"])
            rows.append(["UPDATE_STATUS", "IDLE"])
            rows.append(["RETURN"])
        # Don't add extra RETURN here - it's already in the logic file or default logic

    return rows


def _read_csv(path: str) -> List[Dict[str, str]]:
    """Helper function to read CSV files."""
    rows: List[Dict[str, str]] = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def _generate_charging_navigation(
    end_stop_id: Optional[str],
    charging_stops: Optional[List[str]],
    map_id: Optional[str],
    end_zone: Optional[str]
) -> List[List[str]]:
    """
    Generate navigation commands to move from END stop to charging stop.
    Returns list of command rows [command, value, unit] for navigation.
    Uses generate_path_commands to create actual movement commands.
    """
    nav_commands = []
    
    if not charging_stops or not map_id:
        return nav_commands
    
    try:
        # Get first charging stop
        charging_stop_id = charging_stops[0] if charging_stops else None
        if not charging_stop_id:
            return nav_commands
        
        # Read stops and zones
        stops_rows = _read_csv(STOPS_CSV)
        zones_rows = _read_csv(ZONES_CSV)
        
        # Find end stop zone (where robot currently is after CALL,END)
        end_stop_zone = None
        end_stop_conn_id = None
        if end_stop_id:
            for stop in stops_rows:
                if (str(stop.get('stop_id')) == str(end_stop_id) and 
                    str(stop.get('map_id')) == str(map_id)):
                    end_stop_conn_id = stop.get('zone_connection_id')
                    for zone in zones_rows:
                        if (str(zone.get('id')) == str(end_stop_conn_id) and
                            str(zone.get('map_id')) == str(map_id)):
                            end_stop_zone = zone.get('to_zone')
                            break
                    break
        
        # Fallback to end_zone if end_stop_id not found
        if not end_stop_zone and end_zone:
            end_stop_zone = end_zone
        
        # Find charging stop zone and connection (where robot needs to go)
        charging_stop_zone = None
        charging_conn_id = None
        charging_from_zone = None
        for stop in stops_rows:
            if (str(stop.get('stop_id')) == str(charging_stop_id) and 
                str(stop.get('map_id')) == str(map_id)):
                charging_conn_id = stop.get('zone_connection_id')
                for zone in zones_rows:
                    if (str(zone.get('id')) == str(charging_conn_id) and
                        str(zone.get('map_id')) == str(map_id)):
                        charging_from_zone = zone.get('from_zone')
                        charging_stop_zone = zone.get('to_zone')
                        break
                break
        
        # If we have both zones and they're different, generate navigation path
        if end_stop_zone and charging_stop_zone and end_stop_zone != charging_stop_zone:
            # Build graph for A* pathfinding
            graph = build_graph_from_zones(zones_rows, str(map_id))
            
            # Find path using A*
            path_zones = astar_path(graph, str(end_stop_zone), str(charging_stop_zone))
            
            if path_zones and len(path_zones) >= 2:
                # Create zone_sequence from path
                zone_sequence = list(zip(path_zones[:-1], path_zones[1:]))
                
                # Generate actual navigation commands using generate_path_commands
                # We need to get stops_by_conn for the charging stop
                stops_by_conn = load_stops(stops_rows, str(map_id))
                
                # Generate commands for the path to charging stop
                charging_cmds = generate_path_commands(
                    graph=graph,
                    zones_rows=zones_rows,
                    stops_by_conn=stops_by_conn,
                    zone_sequence=zone_sequence,
                    initial_direction='north',  # Default, could be improved
                    initial_offset_m=0.0,
                    task_type=None,
                    zone_alignment=None,
                    selected_racks_by_stop=None,
                    drop_zone=None,
                    end_zone=charging_stop_zone,
                    end_stop_id=None,  # Don't add CALL,END here
                    stop_operations={str(charging_stop_id): 'charging'},  # Mark charging stop
                    map_id=str(map_id),
                )
                
                # Convert commands to CSV rows (skip HOMING if present)
                for cmd in charging_cmds:
                    if isinstance(cmd, (tuple, list)):
                        cmd_str = [str(x) for x in cmd]
                        # Skip CALL,CHARGING if present (we'll add it after navigation)
                        if len(cmd_str) >= 2 and cmd_str[0].upper() == 'CALL' and cmd_str[1].upper() == 'CHARGING':
                            continue
                        nav_commands.append(cmd_str)
                    else:
                        nav_commands.append([str(cmd)])
        
        # If charging stop is on the same zone connection as end stop (same edge)
        if end_stop_conn_id and charging_conn_id and str(end_stop_conn_id) == str(charging_conn_id):
            # Same edge - need to move along the edge to reach charging stop
            # Find distance difference between stops
            end_stop_dist = None
            charging_stop_dist = None
            for stop in stops_rows:
                if (str(stop.get('stop_id')) == str(end_stop_id) and 
                    str(stop.get('map_id')) == str(map_id)):
                    try:
                        end_stop_dist = float(stop.get('distance_from_start', 0) or 0)
                    except:
                        pass
                if (str(stop.get('stop_id')) == str(charging_stop_id) and 
                    str(stop.get('map_id')) == str(map_id)):
                    try:
                        charging_stop_dist = float(stop.get('distance_from_start', 0) or 0)
                    except:
                        pass
            
            if end_stop_dist is not None and charging_stop_dist is not None:
                dist_diff = charging_stop_dist - end_stop_dist  # Can be positive or negative
                if abs(dist_diff) > 0.001:  # If there's a meaningful distance difference
                    # Get zone connection info for alignment
                    for zone in zones_rows:
                        if (str(zone.get('id')) == str(charging_conn_id) and
                            str(zone.get('map_id')) == str(map_id)):
                            # Add alignment to the zone connection
                            # ALIGN should use zone ids, not connection ids
                            align_zone = charging_from_zone or charging_stop_zone
                            if align_zone is not None:
                                nav_commands.append(["ALIGN", str(align_zone), "0", "0"])
                            # Add forward command (convert meters to mm)
                            nav_commands.append(["F", str(int(abs(dist_diff) * 1000)), "MM"])
                            break
        elif end_stop_zone == charging_stop_zone:
            # Different edges but same zone - might need alignment to charging connection
            if charging_stop_zone is not None:
                # ALIGN should use zone ids, not connection ids
                nav_commands.append(["ALIGN", str(charging_stop_zone), "0", "0"])
    
    except Exception as e:
        # If navigation generation fails, add a comment (but don't break the path)
        import traceback
        nav_commands.append(["#", "ERROR", "Could", "not", "generate", "charging", "navigation:", str(e)])
        nav_commands.append(["#", "Traceback:", traceback.format_exc()])
    
    return nav_commands


def write_commands_csv(path: str, rows: List[List[str]]):
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
