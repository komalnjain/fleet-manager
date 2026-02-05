from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton,
                             QLabel, QFrame, QMessageBox, QScrollArea)
from PyQt5.QtCore import Qt
from ui.common.base_dialog import BaseDialog
from PyQt5.QtGui import QFont
from pathlib import Path
import csv
from config.constants import DEVICE_STATUS
from datetime import datetime
from utils.device_movement_tracker import DeviceMovementTracker
from utils.zone_navigation_manager import get_zone_navigation_manager
from ui.common.input_validators import apply_no_special_chars_validator

class AddDeviceDialog(BaseDialog):
    def __init__(self, parent=None, device_data=None):
        super().__init__(parent)
        self.device_data = device_data
        self.is_edit_mode = device_data is not None

        self.setup_ui()
        self.setup_validation()

        if self.is_edit_mode:
            self.populate_fields()

    def populate_maps_dropdown(self):
        """Populate maps dropdown with all available maps from maps.csv"""
        try:
            # Get the CSV handler from parent (DeviceManagementWidget)
            csv_handler = None
            if hasattr(self.parent(), 'csv_handler'):
                csv_handler = self.parent().csv_handler
            elif hasattr(self, 'parent_widget') and hasattr(self.parent_widget, 'csv_handler'):
                csv_handler = self.parent_widget.csv_handler
            
            if not csv_handler:
                return

            maps = csv_handler.read_csv('maps')
            
            self.current_map_combo.clear()
            self.current_map_combo.addItem("Select Map", "")
            
            for m in maps:
                name = m.get('name', '')
                map_id = m.get('id', '')
                if name and map_id:
                    self.current_map_combo.addItem(name, map_id)
                    
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error populating maps dropdown: {e}")
            elif hasattr(self.parent(), 'logger'):
                self.parent().logger.error(f"Error populating maps dropdown: {e}")

    def on_map_changed(self, index):
        """Handle map selection change to filter locations"""
        map_id = self.current_map_combo.currentData()
        if map_id:
            self.current_location_combo.setEnabled(True)
            self.populate_location_dropdown(map_id)
        else:
            self.current_location_combo.clear()
            self.current_location_combo.addItem("Select Location", "")
            self.current_location_combo.setEnabled(False)

    def populate_location_dropdown(self, map_id=None):
        """Populate location dropdown with unique zones filtered by map_id"""
        try:
            self.current_location_combo.clear()
            self.current_location_combo.addItem("Select Location", "")
            
            if not map_id:
                return

            # Get CSV handler
            csv_handler = None
            if hasattr(self.parent(), 'csv_handler'):
                csv_handler = self.parent().csv_handler
            elif hasattr(self, 'parent_widget') and hasattr(self.parent_widget, 'csv_handler'):
                csv_handler = self.parent_widget.csv_handler
            
            if not csv_handler:
                return

            zones = csv_handler.read_csv('zones')
            
            # Filter zones by map_id
            unique_zones = set()
            for zone in zones:
                if str(zone.get('map_id')) == str(map_id):
                    from_zone = zone.get('from_zone', '')
                    to_zone = zone.get('to_zone', '')
                    if from_zone:
                        unique_zones.add(from_zone)
                    if to_zone:
                        unique_zones.add(to_zone)
            
            # Add sorted unique zones for this map
            for zone in sorted(unique_zones):
                self.current_location_combo.addItem(zone, zone)
                
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"Error populating location dropdown: {e}")
            elif hasattr(self.parent(), 'logger'):
                self.parent().logger.error(f"Error populating location dropdown: {e}")

    def setup_ui(self):
        """Setup dialog UI"""
        self.setWindowTitle("Edit Device" if self.is_edit_mode else "Add New Device")
        self.setModal(True)
        self.setFixedSize(900, 900)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 8px;
                border-radius: 4px;
                color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #ff6b35;
                background-color: #454545;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 15px;
            }
            QComboBox::down-arrow {
                width: 12px;
                height: 12px;
            }
            QPushButton {
                background-color: #555555;
                border: 1px solid #666666;
                padding: 10px 20px;
                border-radius: 4px;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #666666;
            }
            QPushButton:pressed {
                background-color: #444444;
            }
            QFormLayout {
                spacing: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(30)  # Further increased spacing between sections
        layout.setContentsMargins(40, 40, 40, 40)  # Further increased margins

        # Title
        title = QLabel("Edit Device Details" if self.is_edit_mode else "Add New Device")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #ff6b35; margin-bottom: 10px;")
        layout.addWidget(title)

        # Form (wrapped in a scroll area)
        form_frame = QFrame()
        form_frame.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 25px;
            }
        """)
        form_layout = QFormLayout(form_frame)
        form_layout.setSpacing(15)

        # Device Model (Add mode only)
        if not self.is_edit_mode:
            model_label = QLabel("Device Model:")
            model_label.setStyleSheet("""
                QLabel {
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 120px;
                }
            """)
            self.device_model_combo = QComboBox()
            self.device_model_combo.addItems(["V1", "V2"]) 
            form_layout.addRow(model_label, self.device_model_combo)

        # Device ID
        id_label = QLabel("Device ID *:")
        id_label.setStyleSheet("""
            QLabel {
                color: #ff6b35;
                font-weight: bold;
                font-size: 14px;
                min-width: 120px;
            }
        """)
        self.device_id_input = QLineEdit()
        self.device_id_input.setPlaceholderText("e.g., DEV001, ROBOT_01")
        form_layout.addRow(id_label, self.device_id_input)

        # Device Name
        name_label = QLabel("Device Name *:")
        name_label.setStyleSheet("""
            QLabel {
                color: #ff6b35;
                font-weight: bold;
                font-size: 14px;
                min-width: 120px;
            }
        """)
        self.device_name_input = QLineEdit()
        self.device_name_input.setPlaceholderText("e.g., Main Picker Robot")
        form_layout.addRow(name_label, self.device_name_input)

        # Forward Speed
        fwd_label = QLabel("Forward Speed (m/s):")
        fwd_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                min-width: 120px;
            }
        """)
        self.forward_speed_spinbox = QDoubleSpinBox()
        self.forward_speed_spinbox.setRange(0, 10.0)
        self.forward_speed_spinbox.setDecimals(2)
        self.forward_speed_spinbox.setSingleStep(0.1)
        self.forward_speed_spinbox.setValue(0.0)
        form_layout.addRow(fwd_label, self.forward_speed_spinbox)

        # Turning Speed
        turn_label = QLabel("Turning Speed (m/s):")
        turn_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                min-width: 120px;
            }
        """)
        self.turning_speed_spinbox = QDoubleSpinBox()
        self.turning_speed_spinbox.setRange(0, 10.0)
        self.turning_speed_spinbox.setDecimals(2)
        self.turning_speed_spinbox.setSingleStep(0.1)
        self.turning_speed_spinbox.setValue(0.0)
        form_layout.addRow(turn_label, self.turning_speed_spinbox)

        # Vertical Speed
        vertical_label = QLabel("Vertical Speed (m/s):")
        vertical_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                min-width: 120px;
            }
        """)
        self.vertical_speed_spinbox = QDoubleSpinBox()
        self.vertical_speed_spinbox.setRange(0, 10.0)
        self.vertical_speed_spinbox.setDecimals(2)
        self.vertical_speed_spinbox.setSingleStep(0.1)
        self.vertical_speed_spinbox.setValue(0.0)
        form_layout.addRow(vertical_label, self.vertical_speed_spinbox)

        # Horizontal Speed
        horizontal_label = QLabel("Horizontal Speed (m/s):")
        horizontal_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                min-width: 120px;
            }
        """)
        self.horizontal_speed_spinbox = QDoubleSpinBox()
        self.horizontal_speed_spinbox.setRange(0, 10.0)
        self.horizontal_speed_spinbox.setDecimals(2)
        self.horizontal_speed_spinbox.setSingleStep(0.1)
        self.horizontal_speed_spinbox.setValue(0.0)
        form_layout.addRow(horizontal_label, self.horizontal_speed_spinbox)

        # Status
        status_label = QLabel("Status:")
        status_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                min-width: 120px;
            }
        """)
        self.status_combo = QComboBox()
        for key, value in DEVICE_STATUS.items():
            self.status_combo.addItem(value, key)
        self.status_combo.setCurrentText("Working")
        form_layout.addRow(status_label, self.status_combo)

        # Battery Level
        battery_label = QLabel("Battery Level:")
        battery_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                min-width: 120px;
            }
        """)
        self.battery_spinbox = QSpinBox()
        self.battery_spinbox.setRange(0, 100)
        self.battery_spinbox.setValue(100)
        self.battery_spinbox.setSuffix("%")
        form_layout.addRow(battery_label, self.battery_spinbox)

        # Current Map and Location (Add mode only)
        if not self.is_edit_mode:
            # Current Map
            current_map_label = QLabel("Current Map *:")
            current_map_label.setStyleSheet("""
                QLabel {
                    color: #ff6b35;
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 120px;
                }
            """)
            self.current_map_combo = QComboBox()
            self.current_map_combo.setPlaceholderText("Select Map")
            self.current_map_combo.currentIndexChanged.connect(self.on_map_changed)
            form_layout.addRow(current_map_label, self.current_map_combo)

            # Current Location
            current_location_label = QLabel("Current Location *:")
            current_location_label.setStyleSheet("""
                QLabel {
                    color: #ff6b35;
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 120px;
                }
            """)
            self.current_location_combo = QComboBox()
            self.current_location_combo.setPlaceholderText("Select Map First")
            self.current_location_combo.setEnabled(False)
            form_layout.addRow(current_location_label, self.current_location_combo)

            # Populate Map Dropdown
            self.populate_maps_dropdown()

        # Additional sections (Add mode only)
        if not self.is_edit_mode:
            # Driving-Parameters section header
            driving_header = QLabel("Driving-Parameters")
            driving_header.setStyleSheet("color: #ff6b35; font-weight: bold; font-size: 14px; margin-top: 10px;")
            form_layout.addRow(driving_header)

            # Wheel Diameter
            wheel_label = QLabel("Wheel Diameter (mm):")
            wheel_label.setStyleSheet("""
                QLabel {
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 120px;
                }
            """)
            self.wheel_diameter_spinbox = QDoubleSpinBox()
            self.wheel_diameter_spinbox.setRange(0, 100000)
            self.wheel_diameter_spinbox.setDecimals(2)
            self.wheel_diameter_spinbox.setSingleStep(0.1)
            self.wheel_diameter_spinbox.setValue(0.0)
            form_layout.addRow(wheel_label, self.wheel_diameter_spinbox)

            # Distance Between Wheels
            dbw_label = QLabel("Distance Between Wheels (m):")
            dbw_label.setStyleSheet("""
                QLabel {
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 120px;
                }
            """)
            self.distance_between_wheels_spinbox = QDoubleSpinBox()
            self.distance_between_wheels_spinbox.setRange(0, 100000)
            self.distance_between_wheels_spinbox.setDecimals(2)
            self.distance_between_wheels_spinbox.setSingleStep(0.1)
            self.distance_between_wheels_spinbox.setValue(0.0)
            form_layout.addRow(dbw_label, self.distance_between_wheels_spinbox)

            # Physical Dimensions section header
            physical_header = QLabel("Physical Dimensions")
            physical_header.setStyleSheet("color: #ff6b35; font-weight: bold; font-size: 14px; margin-top: 10px;")
            form_layout.addRow(physical_header)

            # Length
            length_label = QLabel("Length (m):")
            length_label.setStyleSheet("""
                QLabel {
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 120px;
                }
            """)
            self.length_spinbox = QDoubleSpinBox()
            self.length_spinbox.setRange(0, 100000)
            self.length_spinbox.setDecimals(2)
            self.length_spinbox.setSingleStep(0.1)
            self.length_spinbox.setValue(0.0)
            form_layout.addRow(length_label, self.length_spinbox)

            # Width
            width_label = QLabel("Width (m):")
            width_label.setStyleSheet("""
                QLabel {
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 120px;
                }
            """)
            self.width_spinbox = QDoubleSpinBox()
            self.width_spinbox.setRange(0, 100000)
            self.width_spinbox.setDecimals(2)
            self.width_spinbox.setSingleStep(0.1)
            self.width_spinbox.setValue(0.0)
            form_layout.addRow(width_label, self.width_spinbox)

            # Height
            height_label = QLabel("Height (m):")
            height_label.setStyleSheet("""
                QLabel {
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 120px;
                }
            """)
            self.height_spinbox = QDoubleSpinBox()
            self.height_spinbox.setRange(0, 100000)
            self.height_spinbox.setDecimals(2)
            self.height_spinbox.setSingleStep(0.1)
            self.height_spinbox.setValue(0.0)
            form_layout.addRow(height_label, self.height_spinbox)

            # Lifting Height
            lifting_label = QLabel("Lifting Height (m):")
            lifting_label.setStyleSheet("""
                QLabel {
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 120px;
                }
            """)
            self.lifting_height_spinbox = QDoubleSpinBox()
            self.lifting_height_spinbox.setRange(0, 100000)
            self.lifting_height_spinbox.setDecimals(2)
            self.lifting_height_spinbox.setSingleStep(0.1)
            self.lifting_height_spinbox.setValue(0.0)
            form_layout.addRow(lifting_label, self.lifting_height_spinbox)

        # Place form in a scroll area to make it scrollable
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { background-color: transparent; }")
        scroll_area.setWidget(form_frame)
        layout.addWidget(scroll_area)

        # Validation info
        validation_label = QLabel("* Required fields")
        validation_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        layout.addWidget(validation_label)

        # Buttons
        self.create_buttons(layout)

    def create_buttons(self, parent_layout):
        """Create dialog buttons"""
        button_layout = QHBoxLayout()

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        # Save button
        save_btn = QPushButton("Update Device" if self.is_edit_mode else "Add Device")
        save_btn.setAutoDefault(False)
        save_btn.clicked.connect(self.save_device)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6b35;
                color: white;
            }
            QPushButton:hover {
                background-color: #e55a2b;
            }
        """)
        button_layout.addWidget(save_btn)

        parent_layout.addLayout(button_layout)

    def setup_validation(self):
        """Setup input validation"""
        # Restrict special characters in key text fields
        apply_no_special_chars_validator(self.device_id_input)
        apply_no_special_chars_validator(self.device_name_input)

        # Connect validation to input changes
        self.device_id_input.textChanged.connect(self.validate_inputs)
        self.device_name_input.textChanged.connect(self.validate_inputs)

    def validate_inputs(self):
        """Validate required inputs"""
        device_id = self.device_id_input.text().strip()
        device_name = self.device_name_input.text().strip()

        # Change border color based on validation
        inputs_validation = [
            (self.device_id_input, bool(device_id)),
            (self.device_name_input, bool(device_name))
        ]
        
        if not self.is_edit_mode:
            current_map = self.current_map_combo.currentData()
            current_location = self.current_location_combo.currentData()
            inputs_validation.extend([
                (self.current_map_combo, bool(current_map)),
                (self.current_location_combo, bool(current_location))
            ])

        for widget, is_valid in inputs_validation:
            if is_valid:
                widget.setStyleSheet(widget.styleSheet().replace("border: 2px solid #ff0000;", ""))
            else:
                if "border: 2px solid #ff0000;" not in widget.styleSheet():
                    current_style = widget.styleSheet()
                    widget.setStyleSheet(current_style + "border: 2px solid #ff0000;")

    def populate_fields(self):
        """Populate fields with existing device data"""
        if not self.device_data:
            return

        self.device_id_input.setText(self.device_data.get('device_id', ''))
        self.device_name_input.setText(self.device_data.get('device_name', ''))

        # Device type handling removed

        # Set status
        status = self.device_data.get('status', 'working')
        for i in range(self.status_combo.count()):
            if self.status_combo.itemData(i) == status:
                self.status_combo.setCurrentIndex(i)
                break

        self.battery_spinbox.setValue(int(self.device_data.get('battery_level', 100)))

        # Set speeds if available (convert from mm/s to m/s)
        try:
            fs = self.device_data.get('forward_speed', '')
            if fs is not None and str(fs) != '':
                self.forward_speed_spinbox.setValue(float(fs) / 1000.0)
        except Exception:
            pass
        try:
            ts = self.device_data.get('turning_speed', '')
            if ts is not None and str(ts) != '':
                self.turning_speed_spinbox.setValue(float(ts) / 1000.0)
        except Exception:
            pass
        try:
            vs = self.device_data.get('vertical_speed', '')
            if vs is not None and str(vs) != '':
                self.vertical_speed_spinbox.setValue(float(vs) / 1000.0)
        except Exception:
            pass
        try:
            hs = self.device_data.get('horizontal_speed', '')
            if hs is not None and str(hs) != '':
                self.horizontal_speed_spinbox.setValue(float(hs) / 1000.0)
        except Exception:
            pass

        # No map/location population in edit mode as per latest request
        pass

    def save_device(self):
        """Save device data"""
        # Validate required fields
        device_id = self.device_id_input.text().strip()
        device_name = self.device_name_input.text().strip()

        if not device_id:
            QMessageBox.warning(self, "Validation Error", "Device ID is required")
            self.device_id_input.setFocus()
            return

        if not device_name:
            QMessageBox.warning(self, "Validation Error", "Device Name is required")
            self.device_name_input.setFocus()
            return

        if not self.is_edit_mode:
            current_map = self.current_map_combo.currentData()
            current_location = self.current_location_combo.currentData()
            
            if not current_map:
                QMessageBox.warning(self, "Validation Error", "Current Map is required")
                self.current_map_combo.setFocus()
                return
                
            if not current_location:
                QMessageBox.warning(self, "Validation Error", "Current Location is required")
                self.current_location_combo.setFocus()
                return

        # Check for duplicate device ID (only for new devices)
        if not self.is_edit_mode:
            # Create device log file
            if not self.create_device_log_file(device_id):
                QMessageBox.warning(self, "Error", "Failed to create device log file")
                return

            # Create device command file for robot control
            if not self.create_device_command_file(device_id):
                QMessageBox.warning(self, "Error", "Failed to create device command file")
                return

            # Create battery status file
            if not self.create_battery_status_file(device_id):
                QMessageBox.warning(self, "Error", "Failed to create battery status file")
                return

            # Create charging status file
            if not self.create_charging_status_file(device_id):
                QMessageBox.warning(self, "Error", "Failed to create charging status file")
                return

            # Create alarm status file
            if not self.create_alarm_status_file(device_id):
                QMessageBox.warning(self, "Error", "Failed to create alarm status file")
                return

            # Create obstacle file
            if not self.create_obstacle_file(device_id):
                QMessageBox.warning(self, "Error", "Failed to create obstacle file")
                return

            # Create emergency status file
            if not self.create_emergency_status_file(device_id):
                QMessageBox.warning(self, "Error", "Failed to create emergency status file")
                return

            # Create DROP logic file
            if not self.create_drop_logic_file(device_id):
                QMessageBox.warning(self, "Error", "Failed to create DROP logic file")
                return

            # Create CHECK logic file
            if not self.create_check_logic_file(device_id):
                QMessageBox.warning(self, "Error", "Failed to create PICKUP logic file")
                return

            # Create PICKUP logic file
            if not self.create_pickup_logic_file(device_id):
                QMessageBox.warning(self, "Error", "Failed to create PICKUP logic file")
                return

            # Create END logic file
            if not self.create_end_logic_file(device_id):
                QMessageBox.warning(self, "Error", "Failed to create END logic file")
                return

            # Add initial log entry
            if not self.add_device_log_entry(
                device_id,
                self.status_combo.currentData(),
                self.battery_spinbox.value(),
                "Device initialized"
            ):
                QMessageBox.warning(self, "Error", "Failed to add initial device log entry")
                return

        self.accept()

    def create_device_log_file(self, device_id: str) -> bool:
        """Create a new device log file with headers"""
        try:
            device_file_path = Path('data/device_logs') / f"{device_id}.csv"
            device_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Define headers for device-specific CSV
            headers = [
                'timestamp',
                'right_drive',
                'left_drive',
                'right_motor',
                'left_motor',
                'current_location'
            ]

            # Create new file with headers
            with open(device_file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

            return True
        except Exception as e:
            print(f"Error creating device log file: {e}")
            return False

    def create_device_command_file(self, device_id: str) -> bool:
        """Create a device command file for robot control"""
        try:
            command_file_path = Path('data/device_logs') / f"{device_id}_command.csv"
            command_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Define headers matching commands.csv format
            headers = ['command', 'params', 'timestamp']

            # Create new file with headers
            with open(command_file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

            print(f"Created device command file: {command_file_path}")
            return True
        except Exception as e:
            print(f"Error creating device command file: {e}")
            return False

    def create_battery_status_file(self, device_id: str) -> bool:
        """Create {device_id}_Battery_status.csv for battery monitoring"""
        try:
            file_path = Path('data/device_logs') / f"{device_id}_Battery_status.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            headers = ['battery_percentage', 'timestamp']

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

            print(f"Created battery status file: {file_path}")
            return True
        except Exception as e:
            print(f"Error creating battery status file: {e}")
            return False

    def create_charging_status_file(self, device_id: str) -> bool:
        """Create {device_id}_Charging_Status.csv for charging monitoring"""
        try:
            file_path = Path('data/device_logs') / f"{device_id}_Charging_Status.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            headers = ['Charging_type', 'timestamp']

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

            print(f"Created charging status file: {file_path}")
            return True
        except Exception as e:
            print(f"Error creating charging status file: {e}")
            return False

    def create_alarm_status_file(self, device_id: str) -> bool:
        """Create {device_id}_Alarm_status.csv for alarm monitoring"""
        try:
            file_path = Path('data/device_logs') / f"{device_id}_Alarm_status.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            headers = ['alarmRM', 'alarmLM', 'timestamp']

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

            print(f"Created alarm status file: {file_path}")
            return True
        except Exception as e:
            print(f"Error creating alarm status file: {e}")
            return False

    def create_obstacle_file(self, device_id: str) -> bool:
        """Create {device_id}_obstacle.csv for obstacle detection"""
        try:
            file_path = Path('data/device_logs') / f"{device_id}_obstacle.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            headers = ['obstacle', 'timestamp']

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

            print(f"Created obstacle file: {file_path}")
            return True
        except Exception as e:
            print(f"Error creating obstacle file: {e}")
            return False

    def create_emergency_status_file(self, device_id: str) -> bool:
        """Create {device_id}_emergency_status.csv for emergency stop detection"""
        try:
            file_path = Path('data/device_logs') / f"{device_id}_emergency_status.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            headers = ['switch_status', 'timestamp']

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

            print(f"Created emergency status file: {file_path}")
            return True
        except Exception as e:
            print(f"Error creating emergency status file: {e}")
            return False


    def create_drop_logic_file(self, device_id: str) -> bool:
        """Create {device_id}_DROP_Logic.csv for drop zone logic commands"""
        try:
            file_path = Path('data/device_logs') / f"{device_id}_DROP_Logic.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Create empty file (no headers, user will add content directly)
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                pass  # Create empty file

            print(f"Created DROP logic file: {file_path}")
            return True
        except Exception as e:
            print(f"Error creating DROP logic file: {e}")
            return False

    def create_check_logic_file(self, device_id: str) -> bool:
        """Create {device_id}_CHECK_Logic.csv for check zone logic commands"""
        try:
            file_path = Path('data/device_logs') / f"{device_id}_CHECK_Logic.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Create empty file (no headers, user will add content directly)
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                pass  # Create empty file

            print(f"Created CHECK logic file: {file_path}")
            return True
        except Exception as e:
            print(f"Error creating CHECK logic file: {e}")
            return False

    def create_pickup_logic_file(self, device_id: str) -> bool:
        """Create {device_id}_PICKUP_Logic.csv for pickup logic commands"""
        try:
            file_path = Path('data/device_logs') / f"{device_id}_PICKUP_Logic.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Create empty file (no headers, user will add content directly)
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                pass  # Create empty file

            print(f"Created PICKUP logic file: {file_path}")
            return True
        except Exception as e:
            print(f"Error creating PICKUP logic file: {e}")
            return False

    def create_end_logic_file(self, device_id: str) -> bool:
        """Create {device_id}_END_Logic.csv for end zone logic commands"""
        try:
            file_path = Path('data/device_logs') / f"{device_id}_END_Logic.csv"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Create empty file (no headers, user will add content directly)
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                pass  # Create empty file

            print(f"Created END logic file: {file_path}")
            return True
        except Exception as e:
            print(f"Error creating END logic file: {e}")
            return False

    def add_device_log_entry(self, device_id: str, status: str, battery_level: int, notes: str = '') -> bool:
        """Add a new entry to device log file"""
        try:
            current_location = self.current_location_combo.currentData() or ''
            
            # Use DeviceMovementTracker to log initial position (no movement)
            success, error = DeviceMovementTracker.log_device_movement(
                device_id=device_id,
                right_drive=0,  # No initial movement
                left_drive=0,   # No initial movement
                right_motor=0,  # Motors off
                left_motor=0,   # Motors off
                current_location=current_location
            )
            
            if not success:
                raise Exception(error)

            # Set initial facing direction to 'north' for the new device so UI shows Facing immediately
            try:
                nav = get_zone_navigation_manager()
                nav.set_initial_direction(device_id, str(current_location) if current_location else '', 'north')
            except Exception as _e:
                print(f"Warning: failed to set initial facing direction: {_e}")
            return True
        except Exception as e:
            print(f"Error adding device log entry: {e}")
            return False

    def get_device_data(self):
        """Get device data from form"""
        current_time = datetime.now().isoformat()

        data = {
            'device_id': self.device_id_input.text().strip(),
            'device_name': self.device_name_input.text().strip(),
            'forward_speed': int(self.forward_speed_spinbox.value() * 1000),
            'turning_speed': int(self.turning_speed_spinbox.value() * 1000),
            'vertical_speed': int(self.vertical_speed_spinbox.value() * 1000),
            'horizontal_speed': int(self.horizontal_speed_spinbox.value() * 1000),
            'status': self.status_combo.currentData(),
            'battery_level': self.battery_spinbox.value()
        }

        if not self.is_edit_mode:
            data['current_map'] = self.current_map_combo.currentData() or ''
            data['current_location'] = self.current_location_combo.currentData() or ''
        else:
            # Preserve existing map and location in edit mode
            data['current_map'] = self.device_data.get('current_map', '')
            data['current_location'] = self.device_data.get('current_location', '')

        # Include additional fields only if present (i.e., in Add mode)
        if hasattr(self, 'device_model_combo'):
            data['device_model'] = self.device_model_combo.currentText()
        if hasattr(self, 'wheel_diameter_spinbox'):
            data['wheel_diameter'] = f"{float(self.wheel_diameter_spinbox.value()):.2f}"
        if hasattr(self, 'distance_between_wheels_spinbox'):
            data['distance_between_wheels'] = f"{float(self.distance_between_wheels_spinbox.value()):.2f}"
        if hasattr(self, 'length_spinbox'):
            data['length'] = f"{float(self.length_spinbox.value()):.2f}"
        if hasattr(self, 'width_spinbox'):
            data['width'] = f"{float(self.width_spinbox.value()):.2f}"
        if hasattr(self, 'height_spinbox'):
            data['height'] = f"{float(self.height_spinbox.value()):.2f}"
        if hasattr(self, 'lifting_height_spinbox'):
            data['lifting_height'] = f"{float(self.lifting_height_spinbox.value()):.2f}"
        # Try to derive current_location and distance from the latest device log entry
        try:
            device_id = data.get('device_id')
            if device_id:
                device_file_path = Path('data/device_logs') / f"{device_id}.csv"
                if device_file_path.exists():
                    with open(device_file_path, 'r', newline='', encoding='utf-8') as f:
                        rows = list(csv.DictReader(f))
                        if rows:
                            last = rows[-1]
                            # Update current_location from log if available
                            log_location = last.get('current_location')
                            if log_location is not None and str(log_location) != '':
                                data['current_location'] = str(log_location)
                            # Set distance from right_drive
                            rd = last.get('right_drive')
                            if rd is not None and str(rd) != '':
                                try:
                                    data['distance'] = f"{float(rd):.2f}"
                                except ValueError:
                                    data['distance'] = "0.00"
                            else:
                                data['distance'] = "0.00"
        except Exception:
            # Non-fatal: if any error occurs, distance may be omitted and handled by sync later
            pass

        if not self.is_edit_mode:
            data['created_at'] = current_time

        data['updated_at'] = current_time

        return data