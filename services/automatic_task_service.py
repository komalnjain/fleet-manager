import os
import csv
import json
import glob
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from PyQt5.QtCore import QTimer

from data_manager.csv_handler import CSVHandler
from data_manager.device_data_handler import DeviceDataHandler
from ui.tasks.distance_calculator import DistanceCalculator
from services.path_planner_service import plan_and_write_path
from utils.logger import setup_logger

class AutomaticTaskService:
    def __init__(self, csv_handler: CSVHandler, device_data_handler: DeviceDataHandler):
        self.csv_handler = csv_handler
        self.device_data_handler = device_data_handler
        self.distance_calculator = DistanceCalculator(csv_handler)
        self.logger = setup_logger('automatic_task_service')
        self.data_dir = Path('data')

    def monitor_and_process(self):
        """Scan for create_pickup_task CSV files and dispatcher acknowledgments."""
        # 1. Handle creation of new tasks from create_pickup_task files
        pattern = str(self.data_dir / "*_create_pickup_task.csv")
        files = glob.glob(pattern)
        for file_path in files:
            try:
                self._process_csv(file_path)
            except Exception as e:
                self.logger.error(f"Error processing {file_path}: {e}")
        
        # 2. Monitor dispatcher CSV files for "Tyre Ready" acknowledgments
        self._monitor_dispatcher_acknowledgments()
        
        # 3. Sync statuses for active tasks (handles both auto and manual tasks feedback)
        self.sync_task_statuses()

    def sync_task_statuses(self):
        """Synchronize task statuses from device logs to tasks.csv."""
        try:
            tasks = self.csv_handler.read_csv('tasks')
            active_tasks = [t for t in tasks if str(t.get('status')).lower() in ['pending', 'running', 'processing']]
            
            if not active_tasks:
                return

            for task in active_tasks:
                task_id = task.get('task_id')
                # Primary device for monitoring. 
                # For multi-device tasks, we typically use assigned_device_id as primary reporter.
                device_ref = task.get('assigned_device_id')
                if not device_ref or not task_id:
                    continue

                curr_status = str(task.get('status')).lower()
                
                # Check device log for feedback
                latest_feedback = self.device_data_handler.get_latest_task_status_for_task(device_ref, task_id)
                if not latest_feedback:
                    continue
                
                latest_feedback = str(latest_feedback).lower()
                
                # Update status based on device feedback
                if curr_status == 'pending' and latest_feedback == 'executing_task':
                    self.logger.info(f"Sync: Task {task_id} on {device_ref} is now EXECUTING")
                    task['status'] = 'running'
                    task['started_at'] = datetime.now().isoformat()
                    self.csv_handler.update_csv_row('tasks', task.get('id'), task)
                
                elif curr_status in ['running', 'processing'] and latest_feedback == 'task_completed':
                    self.logger.info(f"Sync: Task {task_id} on {device_ref} is COMPLETED")
                    task['status'] = 'completed'
                    task['completed_at'] = datetime.now().isoformat()
                    
                    # Calculate duration
                    try:
                        started = datetime.fromisoformat(task.get('started_at', '').replace('Z', ''))
                        now = datetime.now()
                        task['actual_duration'] = int((now - started).total_seconds())
                    except Exception:
                        task['actual_duration'] = 0
                        
                    self.csv_handler.update_csv_row('tasks', task.get('id'), task)
        except Exception as e:
            self.logger.error(f"Error in sync_task_statuses: {e}")

    def _process_csv(self, file_path: str):
        file_path_obj = Path(file_path)
        filename = file_path_obj.name
        # Extract map_id from filename (e.g., 15_create_pickup_task.csv)
        try:
            map_id = filename.split('_')[0]
        except Exception:
            self.logger.warning(f"Could not extract map_id from filename: {filename}")
            return

        rows = []
        reserved_this_cycle = set()
        updated = False
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row.get('action') == 'create_task':
                    success = self._handle_create_task(map_id, row, reserved_this_cycle)
                    if success:
                        row['action'] = 'task_created'
                        updated = True
                rows.append(row)

        if updated:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            self.logger.info(f"Updated {filename} with task_created status.")

    def _handle_create_task(self, map_id: str, row: Dict, reserved_this_cycle: set) -> bool:
        stop_id = row.get('stop_id')
        drop_zone = row.get('drop_zone')

        if not stop_id or not drop_zone:
            self.logger.warning(f"Incomplete data in CSV: stop_id={stop_id}, drop_zone={drop_zone}")
            return False

        # 1. Find eligible devices (battery > 20, not running/pending task, not reserved this cycle)
        eligible_devices = self._get_eligible_devices(map_id, excluded_device_ids=reserved_this_cycle)
        if not eligible_devices:
            self.logger.info(f"No eligible devices found for move {stop_id} -> {drop_zone} on map {map_id}")
            return False

        # 2. Select nearest device
        selected_device = self._select_nearest_device(map_id, eligible_devices, stop_id)
        if not selected_device:
            self.logger.warning(f"Could not calculate proximity or select device.")
            return False

        # 3. Create task
        task_data = self._build_task_data(map_id, selected_device, stop_id, drop_zone)
        if self.csv_handler.append_to_csv('tasks', task_data):
            self.logger.info(f"Automatically created task {task_data['task_id']} for device {selected_device['device_id']}")
            
            # Add to reservation for this cycle
            reserved_this_cycle.add(str(selected_device['id']))
            
            # 4. Generate Path Planning
            try:
                plan_and_write_picking_path(
                    device_id=selected_device['device_id'],
                    map_id=map_id,
                    pickup_stops=[stop_id],
                    drop_zone=drop_zone
                )
                self.logger.info(f"Generated path planning for device {selected_device['device_id']}")
                
                # Update device task status to pending in its local CSV
                self.device_data_handler.update_device_task_pending_by_task(selected_device['id'], task_data['task_id'])
                
                # New logic: Auto trigger picking tasks after 7 seconds
                if task_data.get('task_type') == 'picking':
                    self.logger.info(f"Scheduling auto-run for task {task_data['task_id']} in 7 seconds")
                    # Capture current values in lambda
                    device_ref = selected_device['id']
                    tid = task_data['task_id']
                    QTimer.singleShot(7000, lambda: self._trigger_automatic_execution(device_ref, tid))
                
                return True
            except Exception as e:
                self.logger.error(f"Failed to generate path planning: {e}")
                # We still return True because the task was created, 
                # but maybe we should revert? User said "make sure automatically the path planning will be generated".
                return True 
        
        return False

    def _get_eligible_devices(self, map_id: str, excluded_device_ids: set = None) -> List[Dict]:
        all_devices = self.csv_handler.read_csv('devices')
        tasks = self.csv_handler.read_csv('tasks')
        
        if excluded_device_ids is None:
            excluded_device_ids = set()

        unavailable_device_ids = set(excluded_device_ids)
        for t in tasks:
            status = t.get('status', '').lower()
            if status in ['running', 'pending']:
                did = t.get('assigned_device_id')
                if did: unavailable_device_ids.add(str(did))
                dids = t.get('assigned_device_ids', '')
                if dids:
                    for d in str(dids).split(','):
                        if d.strip(): unavailable_device_ids.add(d.strip())

        eligible = []
        for d in all_devices:
            # battery_level > 20
            try:
                battery = float(d.get('battery_level', 0))
            except ValueError:
                battery = 0
            
            # Should be in the right map
            if str(d.get('current_map')) != str(map_id):
                continue
                
            if battery > 20 and str(d.get('id')) not in unavailable_device_ids:
                eligible.append(d)
        
        return eligible

    def _select_nearest_device(self, map_id: str, devices: List[Dict], target_stop_id: str) -> Optional[Dict]:
        if not devices:
            return None
        
        # Get target stop zone
        stops = self.csv_handler.read_csv('stops')
        target_stop = next((s for s in stops if str(s.get('stop_id')) == str(target_stop_id) and str(s.get('map_id')) == str(map_id)), None)
        if not target_stop:
            self.logger.warning(f"Stop {target_stop_id} not found in map {map_id}")
            return None
        
        # We need a zone info for distance calculator
        zones = self.csv_handler.read_csv('zones')
        conn_id = target_stop.get('zone_connection_id')
        target_zone_row = next((z for z in zones if str(z.get('id')) == str(conn_id)), None)
        if not target_zone_row:
            return None
        
        target_zone = target_zone_row.get('from_zone') # Heuristic

        best_device = None
        min_dist = float('inf')

        for d in devices:
            curr_loc = d.get('current_location')
            if not curr_loc:
                dist = 999999.0 # Penalty
            else:
                # Use distance calculator to find path distance
                dist = self.distance_calculator.calculate_path_distance(
                    map_id, str(curr_loc), str(target_zone), include_all_stops=False
                )
                if dist == 0 and str(curr_loc) != str(target_zone):
                    dist = 999999.0 # unreachable
            
            if dist < min_dist:
                min_dist = dist
                best_device = d
        
        return best_device

    def _build_task_data(self, map_id: str, device: Dict, stop_id: str, drop_zone: str) -> Dict:
        task_id = f"TASK{self.csv_handler.get_next_id('tasks'):04d}"
        current_time = datetime.now().isoformat()
        
        details = {
            'pickup_map_id': str(map_id),
            'pickup_stops': [stop_id],
            'drop_zone': str(drop_zone),
            'automatic': True
        }

        return {
            'id': '',
            'task_id': task_id,
            'task_name': f"Auto Pickup - {stop_id}",
            'task_type': 'picking',
            'status': 'pending',
            'assigned_device_id': str(device['id']),
            'assigned_device_ids': str(device['id']),
            'assigned_user_id': '',
            'description': f"Automatically created from CSV for stop {stop_id}",
            'estimated_duration': '',
            'actual_duration': '',
            'created_at': current_time,
            'started_at': '',
            'completed_at': '',
            'map_id': str(map_id),
            'zone_ids': '',
            'stop_ids': str(stop_id),
            'task_details': json.dumps(details)
        }

    def _trigger_automatic_execution(self, device_ref: str, task_id: str):
        """Automatically trigger task execution in the device task CSV."""
        try:
            success = self.device_data_handler.set_task_status_for_task(device_ref, task_id, 'run_task')
            if success:
                self.logger.info(f"Automatically triggered execution (run_task) for task {task_id} on device {device_ref}")
            else:
                self.logger.warning(f"Failed to automatically trigger execution for task {task_id}")
        except Exception as e:
            self.logger.error(f"Error in automatic task trigger: {e}")
    
    def _monitor_dispatcher_acknowledgments(self):
        """Monitor dispatcher CSV files for 'Tyre Ready{pickup stop id}' acknowledgments."""
        try:
            # Get all device IDs to check their dispatcher CSV files
            devices = self.csv_handler.read_csv('devices')
            device_logs_dir = self.data_dir / 'device_logs'
            
            for device in devices:
                device_id = device.get('device_id')
                if not device_id:
                    continue
                
                # Check dispatcher CSV file (assuming format: {device_id}.csv in device_logs)
                dispatcher_file = device_logs_dir / f"{device_id}.csv"
                if not dispatcher_file.exists():
                    continue
                
                try:
                    # Read the CSV file and check for acknowledgments
                    with open(dispatcher_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        rows = list(reader)
                        
                        # Check the last few rows for "Tyre Ready" acknowledgment
                        for row in rows[-10:]:  # Check last 10 rows
                            # Look for acknowledgment in various possible columns
                            ack_text = None
                            for col in ['acknowledgment', 'acknowledgement', 'message', 'status', 'command']:
                                val = row.get(col, '')
                                if val and 'tyre ready' in str(val).lower():
                                    ack_text = str(val).strip()
                                    break
                            
                            if ack_text and 'tyre ready' in ack_text.lower():
                                # Extract pickup stop ID from acknowledgment
                                # Format: "Tyre Ready{stop_id}" or "Tyre Ready {stop_id}" or similar
                                match = re.search(r'tyre\s+ready[{\s]*([^}\s]+)', ack_text, re.IGNORECASE)
                                if match:
                                    pickup_stop_id = match.group(1).strip()
                                    self.logger.info(f"Found Tyre Ready acknowledgment for stop {pickup_stop_id} from dispatcher {device_id}")
                                    
                                    # Create task automatically
                                    self._create_task_from_acknowledgment(device, pickup_stop_id)
                                    break  # Process only one acknowledgment per cycle
                except Exception as e:
                    self.logger.error(f"Error reading dispatcher file {dispatcher_file}: {e}")
        except Exception as e:
            self.logger.error(f"Error monitoring dispatcher acknowledgments: {e}")
    
    def _create_task_from_acknowledgment(self, device: Dict, pickup_stop_id: str):
        """Create a complete picking task from Tyre Ready acknowledgment."""
        try:
            map_id = str(device.get('current_map', ''))
            if not map_id:
                self.logger.warning(f"Device {device.get('device_id')} has no current_map")
                return
            
            # Find all required stops for this map
            stops = self.csv_handler.read_csv('stops')
            map_stops = [s for s in stops if str(s.get('map_id')) == str(map_id)]
            
            # Find pickup stop
            pickup_stop = next((s for s in map_stops if str(s.get('stop_id')).strip() == str(pickup_stop_id).strip()), None)
            if not pickup_stop:
                self.logger.warning(f"Pickup stop {pickup_stop_id} not found in map {map_id}")
                return
            
            # Find check stop (first check stop in map)
            check_stops = [s for s in map_stops if str(s.get('stop_function', '')).strip().lower() == 'check']
            check_stop_id = check_stops[0].get('stop_id') if check_stops else None
            
            # Find drop stop (first drop stop in map)
            drop_stops = [s for s in map_stops if str(s.get('stop_function', '')).strip().lower() == 'drop']
            drop_stop_id = drop_stops[0].get('stop_id') if drop_stops else None
            
            # Find end stop (first end stop in map)
            end_stops = [s for s in map_stops if str(s.get('stop_function', '')).strip().lower() == 'end']
            end_stop_id = end_stops[0].get('stop_id') if end_stops else None
            
            # Find charging stop (first charging stop in map)
            charging_stops_list = [s for s in map_stops if str(s.get('stop_function', '')).strip().lower() == 'charging']
            charging_stop_id = charging_stops_list[0].get('stop_id') if charging_stops_list else None
            
            # Get drop zone from drop stop or end stop
            drop_zone = None
            if drop_stop_id:
                drop_stop = next((s for s in map_stops if str(s.get('stop_id')) == str(drop_stop_id)), None)
                if drop_stop:
                    zones = self.csv_handler.read_csv('zones')
                    conn_id = drop_stop.get('zone_connection_id')
                    zone_row = next((z for z in zones if str(z.get('id')) == str(conn_id)), None)
                    if zone_row:
                        drop_zone = zone_row.get('to_zone')
            
            if not drop_zone and end_stop_id:
                end_stop = next((s for s in map_stops if str(s.get('stop_id')) == str(end_stop_id)), None)
                if end_stop:
                    zones = self.csv_handler.read_csv('zones')
                    conn_id = end_stop.get('zone_connection_id')
                    zone_row = next((z for z in zones if str(z.get('id')) == str(conn_id)), None)
                    if zone_row:
                        drop_zone = zone_row.get('to_zone')
            
            if not drop_zone:
                self.logger.warning(f"Could not determine drop_zone for map {map_id}")
                return
            
            # Check if device is eligible
            eligible_devices = self._get_eligible_devices(map_id, excluded_device_ids=set())
            device_id_str = str(device.get('id'))
            selected_device = next((d for d in eligible_devices if str(d.get('id')) == device_id_str), None)
            
            if not selected_device:
                self.logger.info(f"Device {device.get('device_id')} is not eligible for task assignment")
                return
            
            # Build complete task data
            task_data = self._build_complete_task_data(
                map_id=map_id,
                device=selected_device,
                pickup_stop_id=pickup_stop_id,
                check_stop_id=check_stop_id,
                drop_stop_id=drop_stop_id,
                end_stop_id=end_stop_id,
                charging_stop_id=charging_stop_id,
                drop_zone=drop_zone
            )
            
            # Create task
            if self.csv_handler.append_to_csv('tasks', task_data):
                self.logger.info(f"Automatically created task {task_data['task_id']} from Tyre Ready acknowledgment")
                
                # Generate path planning with all stops
                try:
                    from services.path_planner_service import plan_and_write_path
                    from robot_navigation.zone_navigator import get_zone_navigation_manager
                    
                    # Get current zone and direction
                    device_id = selected_device.get('device_id')
                    nav = get_zone_navigation_manager()
                    nav_info = nav.get_navigation_info(device_id)
                    current_zone = nav_info.get('current_zone') or '1'
                    initial_direction = nav_info.get('locked_direction') or 'north'
                    
                    # Build zone sequence (simplified - will be improved)
                    zones = self.csv_handler.read_csv('zones')
                    zone_sequence = self._build_zone_sequence_for_stops(
                        map_id, current_zone, pickup_stop_id, check_stop_id, 
                        drop_stop_id, end_stop_id, charging_stop_id, zones, stops
                    )
                    
                    plan_and_write_path(
                        device_id=device_id,
                        map_id=map_id,
                        zone_sequence=zone_sequence,
                        initial_direction=str(initial_direction).lower(),
                        task_type='picking',
                        pickup_stops=[pickup_stop_id] if pickup_stop_id else None,
                        check_stops=[check_stop_id] if check_stop_id else None,
                        drop_stops=[drop_stop_id] if drop_stop_id else None,
                        end_stop_id=end_stop_id,
                        charging_stops=[charging_stop_id] if charging_stop_id else None,
                    )
                    
                    self.logger.info(f"Generated path planning for device {device_id}")
                    
                    # Update device task status
                    self.device_data_handler.update_device_task_pending_by_task(
                        selected_device['id'], task_data['task_id']
                    )
                    
                    # Auto trigger after 7 seconds
                    QTimer.singleShot(7000, lambda: self._trigger_automatic_execution(
                        selected_device['id'], task_data['task_id']
                    ))
                except Exception as e:
                    self.logger.error(f"Failed to generate path planning: {e}")
        except Exception as e:
            self.logger.error(f"Error creating task from acknowledgment: {e}")
    
    def _build_complete_task_data(self, map_id: str, device: Dict, pickup_stop_id: str,
                                   check_stop_id: Optional[str], drop_stop_id: Optional[str],
                                   end_stop_id: Optional[str], charging_stop_id: Optional[str],
                                   drop_zone: str) -> Dict:
        """Build complete task data with all stops."""
        task_id = f"TASK{self.csv_handler.get_next_id('tasks'):04d}"
        current_time = datetime.now().isoformat()
        
        details = {
            'pickup_map_id': str(map_id),
            'pickup_map_name': '',  # Can be filled from maps.csv if needed
            'pickup_stops': [pickup_stop_id] if pickup_stop_id else [],
            'pickup_stop_names': [pickup_stop_id] if pickup_stop_id else [],
            'check_stops': [check_stop_id] if check_stop_id else [],
            'check_stop_names': [check_stop_id] if check_stop_id else [],
            'drop_stops': [drop_stop_id] if drop_stop_id else [],
            'drop_stop_names': [drop_stop_id] if drop_stop_id else [],
            'end_stop_id': end_stop_id or '',
            'end_stop_name': end_stop_id or '',
            'charging_stops': [charging_stop_id] if charging_stop_id else [],
            'charging_stop_names': [charging_stop_id] if charging_stop_id else [],
            'drop_zone': str(drop_zone),
            'drop_zone_name': str(drop_zone),
            'automatic': True
        }
        
        # Combine all stop IDs
        all_stop_ids = []
        if pickup_stop_id:
            all_stop_ids.append(pickup_stop_id)
        if check_stop_id:
            all_stop_ids.append(check_stop_id)
        if drop_stop_id:
            all_stop_ids.append(drop_stop_id)
        if end_stop_id:
            all_stop_ids.append(end_stop_id)
        if charging_stop_id:
            all_stop_ids.append(charging_stop_id)
        
        return {
            'id': '',
            'task_id': task_id,
            'task_name': f"Auto Task - {pickup_stop_id}",
            'task_type': 'picking',
            'status': 'pending',
            'assigned_device_id': str(device['id']),
            'assigned_device_ids': str(device['id']),
            'assigned_user_id': '',
            'description': f"Automatically created from Tyre Ready acknowledgment for stop {pickup_stop_id}",
            'estimated_duration': '',
            'actual_duration': '',
            'created_at': current_time,
            'started_at': '',
            'completed_at': '',
            'map_id': str(map_id),
            'zone_ids': '',
            'stop_ids': ','.join(all_stop_ids),
            'task_details': json.dumps(details)
        }
    
    def _build_zone_sequence_for_stops(self, map_id: str, current_zone: str,
                                       pickup_stop_id: Optional[str], check_stop_id: Optional[str],
                                       drop_stop_id: Optional[str], end_stop_id: Optional[str],
                                       charging_stop_id: Optional[str], zones: List[Dict],
                                       stops: List[Dict]) -> List[Tuple[str, str]]:
        """Build zone sequence visiting all stops in order."""
        zone_sequence = []
        last_zone = current_zone
        
        # Helper to get zone for a stop
        def get_zone_for_stop(stop_id: Optional[str]) -> Optional[Tuple[str, str]]:
            if not stop_id:
                return None
            stop = next((s for s in stops if str(s.get('stop_id')) == str(stop_id) and 
                        str(s.get('map_id')) == str(map_id)), None)
            if not stop:
                return None
            conn_id = stop.get('zone_connection_id')
            zone_row = next((z for z in zones if str(z.get('id')) == str(conn_id) and
                            str(z.get('map_id')) == str(map_id)), None)
            if zone_row:
                return (zone_row.get('from_zone'), zone_row.get('to_zone'))
            return None
        
        # Visit stops in order: pickup -> check -> drop -> end -> (charging if battery low)
        stops_order = [
            (pickup_stop_id, 'pickup'),
            (check_stop_id, 'check'),
            (drop_stop_id, 'drop'),
            (end_stop_id, 'end'),
        ]
        
        for stop_id, _ in stops_order:
            if not stop_id:
                continue
            zone_pair = get_zone_for_stop(stop_id)
            if zone_pair:
                from_z, to_z = zone_pair
                if last_zone != from_z:
                    # Add path to from_zone if needed
                    zone_sequence.append((last_zone, from_z))
                zone_sequence.append((from_z, to_z))
                last_zone = to_z
        
        # Charging stop is conditionally added at END, so don't add it here
        # It will be handled by END logic checking battery
        
        return zone_sequence if zone_sequence else [(current_zone, current_zone)]
