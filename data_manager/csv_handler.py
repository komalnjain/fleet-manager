import csv
import json
import os
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from config.settings import CSV_FILES, BACKUP_DIR
from config.constants import CSV_HEADERS
from utils.logger import setup_logger


class CSVHandler:
    def __init__(self):
        self.logger = setup_logger('csv_handler')
        # Ensure 'racks' CSV headers match required schema
        try:
            CSV_HEADERS['racks'] = ['rack_id', 'map_name', 'zone_name', 'stop_id', 'rack_distance_mm']
        except Exception:
            # Non-fatal if constants cannot be modified
            pass

    def initialize_csv_files(self):
        """Initialize all CSV files with headers if they don't exist"""
        for file_type, file_path in CSV_FILES.items():
            if not file_path.exists():
                self.create_csv_with_headers(file_type, file_path)
                self.logger.info(f"Created CSV file: {file_path}")
            else:
                # Verify headers exist
                self.verify_csv_headers(file_type, file_path)

    def verify_csv_headers(self, file_type: str, file_path: Path):
        """Verify CSV file has correct headers"""
        try:
            if file_path.stat().st_size == 0:
                self.create_csv_with_headers(file_type, file_path)
                return

            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                first_row = next(reader, None)
                expected_headers = CSV_HEADERS.get(file_type, [])

                if not first_row or first_row != expected_headers:
                    self.logger.warning(f"Headers mismatch in {file_path}, recreating...")
                    # Backup existing data
                    existing_data = self.read_csv(file_type)
                    migrated_data = existing_data

                    # Perform migration for racks.csv to new schema
                    if file_type == 'racks' and expected_headers == ['rack_id', 'map_name', 'zone_name', 'stop_id', 'rack_distance_mm']:
                        try:
                            zones_lookup = {}
                            try:
                                zones = self.read_csv('zones')
                                for z in zones:
                                    zid = str(z.get('id', '')).strip()
                                    zones_lookup[zid] = f"{z.get('from_zone', '')} -> {z.get('to_zone', '')}"
                            except Exception:
                                pass

                            maps_lookup = {}
                            try:
                                maps = self.read_csv('maps')
                                for m in maps:
                                    mid = str(m.get('id', '')).strip()
                                    maps_lookup[mid] = m.get('name', '')
                            except Exception:
                                pass

                            migrated = []
                            for row in existing_data:
                                rack_id = (row.get('rack_id') or row.get('id') or '').strip()
                                map_name = (row.get('map_name') or maps_lookup.get(str(row.get('map_id', '')).strip(), '')).strip()
                                zone_name = (row.get('zone_name') or zones_lookup.get(str(row.get('zone_connection_id', '')).strip(), '')).strip()
                                stop_id = (row.get('stop_id') or '').strip()
                                distance = row.get('rack_distance_mm') or row.get('distance_mm') or ''
                                try:
                                    # Normalize to integer-like string
                                    distance_str = str(int(float(distance))) if str(distance).strip() != '' else ''
                                except Exception:
                                    distance_str = str(distance)
                                migrated.append({
                                    'rack_id': rack_id,
                                    'map_name': map_name,
                                    'zone_name': zone_name,
                                    'stop_id': stop_id,
                                    'rack_distance_mm': distance_str,
                                })
                            migrated_data = migrated
                        except Exception as me:
                            self.logger.warning(f"Could not migrate racks.csv to new schema: {me}. Using empty migrated data.")
                            migrated_data = []

                    # Perform migration for stops.csv to new schema (e.g. adding stop_function)
                    if file_type == 'stops' and 'stop_function' in expected_headers:
                        try:
                            migrated = []
                            for row in existing_data:
                                # Preserve existing fields; default stop_function to 'pickup' for backward compatibility
                                new_row = dict(row)
                                sf = str(new_row.get('stop_function') or '').strip().lower()
                                if not sf:
                                    sf = 'pickup'
                                new_row['stop_function'] = sf
                                migrated.append(new_row)
                            migrated_data = migrated
                        except Exception as me:
                            self.logger.warning(f"Could not migrate stops.csv to new schema: {me}. Using existing data.")
                            migrated_data = existing_data

                    # Recreate with proper headers
                    self.create_csv_with_headers(file_type, file_path)
                    # Restore data if any
                    if migrated_data:
                        self.write_csv(file_type, migrated_data)
        except Exception as e:
            self.logger.error(f"Error verifying headers for {file_type}: {e}")

    def create_csv_with_headers(self, file_type: str, file_path: Path):
        """Create a CSV file with appropriate headers"""
        headers = CSV_HEADERS.get(file_type, [])
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
            self.logger.info(f"Created CSV file with headers: {file_path}")
        except Exception as e:
            self.logger.error(f"Error creating CSV file {file_path}: {e}")

    def read_csv(self, file_type: str) -> List[Dict]:
        """Read CSV file and return list of dictionaries"""
        file_path = CSV_FILES.get(file_type)
        if not file_type or not file_path:
            self.logger.warning(f"Invalid file type: {file_type}")
            return []
            
        if not os.path.exists(file_path):
            self.logger.warning(f"CSV file not found: {file_path}")
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                data = []
                for row in reader:
                    # Clean up row data - remove empty string values for numeric fields
                    cleaned_row = {}
                    for key, value in row.items():
                        if value is None:
                            cleaned_row[key] = ''
                        elif isinstance(value, str):
                            cleaned_row[key] = value.strip()
                        else:
                            cleaned_row[key] = value
                    data.append(cleaned_row)
                return data
        except Exception as e:
            self.logger.error(f"Error reading {file_type} CSV: {e}")
            return []

    def write_csv(self, file_type: str, data: List[Dict]) -> bool:
        """Write data to CSV file"""
        file_path = CSV_FILES.get(file_type)
        if not file_path:
            self.logger.error(f"No file path configured for {file_type}")
            return False

        try:
            # Backup disabled - uncomment below line to re-enable automatic backups
            # if file_path.exists():
            #     self.backup_csv(file_type)

            headers = CSV_HEADERS.get(file_type, [])

            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                if headers:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    for row in data:
                        # Only write fields that exist in headers
                        filtered_row = {}
                        for header in headers:
                            value = row.get(header, '')
                            # Convert None to empty string
                            if value is None:
                                value = ''
                            filtered_row[header] = str(value)
                        writer.writerow(filtered_row)
                else:
                    # Fallback if no headers defined
                    if data:
                        fieldnames = list(data[0].keys())
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(data)

            self.logger.info(f"Successfully wrote {len(data)} rows to {file_type} CSV")
            return True

        except Exception as e:
            self.logger.error(f"Error writing {file_type} CSV: {e}")
            return False

    def append_to_csv(self, file_type: str, data: Dict) -> bool:
        """Append a single row to CSV file"""
        file_path = CSV_FILES.get(file_type)
        if not file_path:
            self.logger.error(f"No file path configured for {file_type}")
            return False

        try:
            headers = CSV_HEADERS.get(file_type, [])

            # Ensure file exists with headers
            if not file_path.exists():
                self.create_csv_with_headers(file_type, file_path)
            else:
                # Verify headers before appending to avoid mismatches
                self.verify_csv_headers(file_type, file_path)

            # Auto-generate ID if not provided
            if 'id' not in data or not data['id']:
                data['id'] = self.get_next_id(file_type)

            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'a', newline='', encoding='utf-8') as f:
                if headers:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    # Only write fields that exist in headers
                    filtered_row = {}
                    for header in headers:
                        value = data.get(header, '')
                        # Convert None to empty string
                        if value is None:
                            value = ''
                        filtered_row[header] = str(value)
                    writer.writerow(filtered_row)
                else:
                    # Fallback if no headers defined
                    fieldnames = list(data.keys())
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writerow(data)

            self.logger.info(f"Successfully appended row to {file_type} CSV with ID: {data.get('id')}")
            return True

        except Exception as e:
            self.logger.error(f"Error appending to {file_type} CSV: {e}")
            return False

    def update_csv_row(self, file_type: str, row_id: str, updated_data: Dict) -> bool:
        """Update a specific row in CSV file"""
        try:
            data = self.read_csv(file_type)
            updated = False

            for i, row in enumerate(data):
                if str(row.get('id')) == str(row_id):
                    # Update the row with new data
                    data[i].update(updated_data)
                    updated = True
                    break

            if updated:
                success = self.write_csv(file_type, data)
                if success:
                    self.logger.info(f"Successfully updated row {row_id} in {file_type} CSV")
                return success
            else:
                self.logger.warning(f"Row with ID {row_id} not found in {file_type} CSV")
                return False

        except Exception as e:
            self.logger.error(f"Error updating row in {file_type} CSV: {e}")
            return False

    def delete_csv_row(self, file_type: str, row_id: str) -> bool:
        """Delete a specific row from CSV file"""
        try:
            data = self.read_csv(file_type)
            original_length = len(data)

            # Filter out the row to delete
            data = [row for row in data if str(row.get('id')) != str(row_id)]

            if len(data) < original_length:
                success = self.write_csv(file_type, data)
                if success:
                    self.logger.info(f"Successfully deleted row {row_id} from {file_type} CSV")
                return success
            else:
                self.logger.warning(f"Row with ID {row_id} not found in {file_type} CSV")
                return False

        except Exception as e:
            self.logger.error(f"Error deleting row from {file_type} CSV: {e}")
            return False

    def backup_csv(self, file_type: str):
        """Create a timestamped backup of CSV file"""
        file_path = CSV_FILES.get(file_type)
        if not file_path or not file_path.exists():
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{file_type}_{timestamp}.csv"
        backup_path = BACKUP_DIR / backup_name

        try:
            # Ensure backup directory exists
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)

            import shutil
            shutil.copy2(file_path, backup_path)
            self.logger.info(f"Created backup: {backup_path}")
        except Exception as e:
            self.logger.error(f"Error backing up {file_type}: {e}")

    def get_next_id(self, file_type: str) -> int:
        """Get the next available ID for a CSV file"""
        try:
            data = self.read_csv(file_type)
            if not data:
                return 1

            max_id = 0
            for row in data:
                try:
                    # Handle both string and int IDs
                    row_id_str = str(row.get('id', '0')).strip()
                    if row_id_str and row_id_str.isdigit():
                        row_id = int(row_id_str)
                        max_id = max(max_id, row_id)
                except (ValueError, TypeError):
                    continue

            next_id = max_id + 1
            self.logger.debug(f"Next ID for {file_type}: {next_id}")
            return next_id

        except Exception as e:
            self.logger.error(f"Error getting next ID for {file_type}: {e}")
            return 1

    def search_csv(self, file_type: str, search_term: str, columns: List[str] = None) -> List[Dict]:
        """Search for rows containing the search term"""
        data = self.read_csv(file_type)
        if not data or not search_term:
            return data

        search_term = search_term.lower()
        results = []

        for row in data:
            if columns:
                # Search only in specified columns
                search_fields = [str(row.get(col, '')).lower() for col in columns if col in row]
            else:
                # Search in all columns
                search_fields = [str(value).lower() for value in row.values()]

            if any(search_term in field for field in search_fields):
                results.append(row)

        return results

    def get_csv_stats(self, file_type: str) -> Dict:
        """Get statistics about a CSV file"""
        data = self.read_csv(file_type)
        file_path = CSV_FILES.get(file_type)

        stats = {
            'total_rows': len(data),
            'file_size': file_path.stat().st_size if file_path and file_path.exists() else 0,
            'last_modified': datetime.fromtimestamp(
                file_path.stat().st_mtime) if file_path and file_path.exists() else None,
            'headers': CSV_HEADERS.get(file_type, [])
        }

        return stats

    def validate_csv_data(self, file_type: str, data: Dict) -> Dict:
        """Validate data before writing to CSV"""
        errors = []
        warnings = []

        # Check required fields based on file type
        required_fields = {
            'devices': ['device_id', 'device_name'],
            'tasks': ['task_name', 'task_type'],
            'users': ['username', 'email'],
            'maps': ['name'],
            'products': ['product_id', 'product_name', 'sku_location_id'],
        }

        if file_type in required_fields:
            for field in required_fields[file_type]:
                if not data.get(field):
                    errors.append(f"Missing required field: {field}")

        # Add timestamps if missing
        current_time = datetime.now().isoformat()
        if 'created_at' not in data:
            data['created_at'] = current_time
            warnings.append("Added created_at timestamp")

        if 'updated_at' not in data:
            data['updated_at'] = current_time
            warnings.append("Added updated_at timestamp")

        return {
            'data': data,
            'errors': errors,
            'warnings': warnings,
            'valid': len(errors) == 0
        }

    def repair_csv_file(self, file_type: str) -> bool:
        """Repair a corrupted CSV file"""
        try:
            file_path = CSV_FILES.get(file_type)
            if not file_path or not file_path.exists():
                return False

            # Try to read existing data
            data = []
            headers = CSV_HEADERS.get(file_type, [])

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():
                    # Empty file, just add headers
                    self.create_csv_with_headers(file_type, file_path)
                    return True

            # Backup corrupted file
            self.backup_csv(file_type)

            # Try to salvage data
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if any(row.values()):  # Skip completely empty rows
                            data.append(row)
            except Exception as e:
                self.logger.warning(f"Could not salvage data from {file_type}: {e}")

            # Recreate file with proper structure
            self.create_csv_with_headers(file_type, file_path)

            if data:
                self.write_csv(file_type, data)

            self.logger.info(f"Repaired CSV file for {file_type}")
            return True

        except Exception as e:
            self.logger.error(f"Error repairing CSV file for {file_type}: {e}")
            return False