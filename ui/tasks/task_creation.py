from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QComboBox, QTextEdit, QSpinBox, QPushButton,
                             QLabel, QFrame, QMessageBox, QScrollArea, QGroupBox,
                             QCheckBox, QDateTimeEdit, QProgressBar, QTabWidget,
                             QListWidget, QListWidgetItem, QSplitter, QFileDialog)
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime, QTimer
from PyQt5.QtGui import QFont, QPixmap, QIcon
from datetime import datetime, timedelta
import os
import csv
import json

from api.client import APIClient
from api.tasks import TasksAPI
from data_manager.csv_handler import CSVHandler
from config.constants import TASK_TYPES
from utils.logger import setup_logger
from data_manager.device_data_handler import DeviceDataHandler
from ui.common.input_validators import apply_no_special_chars_validator

# Import modular components
from .battery_mapper import BatteryMapper
from .distance_calculator import DistanceCalculator
from .device_filter import DeviceFilter
from .task_type_handlers import TaskTypeHandlerFactory
from .form_components import FormComponents


class TaskCreationWidget(QWidget):
    task_created = pyqtSignal(dict)

    def __init__(self, api_client: APIClient, csv_handler: CSVHandler):
        super().__init__()
        self.api_client = api_client
        self.csv_handler = csv_handler
        self.tasks_api = TasksAPI(api_client)
        self.logger = setup_logger('task_creation')
        self.device_data_handler = DeviceDataHandler()
        
        # Initialize modular components
        self.battery_mapper = BatteryMapper()
        self.distance_calculator = DistanceCalculator(csv_handler)
        self.device_filter = DeviceFilter(csv_handler, self.distance_calculator)
        self.task_handler = None  # Will be set based on task type
        
        # Initialize task-specific data
        self.current_map_distance = 0
        self.required_distance = 0
        
        self.setup_ui()
        self.load_data()
        # Initialize form completion check
        self.check_form_completion()

    
    def setup_ui(self):
        """Setup task creation UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Task statistics header
        #self.create_stats_header(layout)

        # Main content with tabs
        self.create_main_content(layout)

        # Action buttons
        self.create_action_buttons(layout)

    '''
    def create_stats_header(self, parent_layout):
        """Create task statistics header"""
        stats_frame = QFrame()
        stats_frame.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 15px;
            }
        """)
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setSpacing(20)

        # Active tasks label
        self.active_tasks_label = QLabel("Active Tasks: 0")
        self.active_tasks_label.setStyleSheet("""
            QLabel {
                color: #10B981;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        stats_layout.addWidget(self.active_tasks_label)

        # Pending tasks label
        self.pending_tasks_label = QLabel("Pending: 0")
        self.pending_tasks_label.setStyleSheet("""
            QLabel {
                color: #F59E0B;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        stats_layout.addWidget(self.pending_tasks_label)

        stats_layout.addStretch()
        parent_layout.addWidget(stats_frame)
        '''


    def create_main_content(self, parent_layout):
        """Create main content with tabs"""
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #404040;
                color: #ffffff;
                padding: 10px 20px;
                margin-right: 2px;
                border: 1px solid #555555;
                border-bottom: none;
                border-radius: 6px 6px 0 0;
            }
            QTabBar::tab:selected {
                background-color: #ff6b35;
                color: #ffffff;
            }
            QTabBar::tab:hover:!selected {
                background-color: #4a4a4a;
            }
        """)

        # Tab 1: Manual Task Creation
        self.manual_tab = self.create_manual_creation_tab()
        self.tab_widget.addTab(self.manual_tab, "✏️ Manual Creation")

        parent_layout.addWidget(self.tab_widget)

    def create_manual_creation_tab(self):
        """Create manual task creation tab"""
        tab_widget = QWidget()
        layout = QHBoxLayout(tab_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(25)

        # Left panel - Task form with scroll
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameStyle(QFrame.NoFrame)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        left_panel = self.create_task_form_panel()
        left_scroll.setWidget(left_panel)
        layout.addWidget(left_scroll, 2)

        # Right panel - Assignment and preview with scroll
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameStyle(QFrame.NoFrame)
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        right_panel = self.create_assignment_panel()
        right_scroll.setWidget(right_panel)
        layout.addWidget(right_scroll, 1)

        return tab_widget

    def create_task_form_panel(self):
        """Create task form panel"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 25px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setSpacing(25)

        # Basic Information Section
        basic_section = self.create_basic_info_section()
        layout.addWidget(basic_section)

        # Add some bottom spacing
        layout.addStretch()

        return panel

    def create_basic_info_section(self):
        """Create basic information section"""
        section = QGroupBox("Basic Information")
        section.setStyleSheet(self.get_groupbox_style())
        layout = QFormLayout(section)
        layout.setSpacing(15)
        layout.setVerticalSpacing(15)

        # Task Name
        self.task_name_input = QLineEdit()
        self.task_name_input.setPlaceholderText("Enter descriptive task name")
        self.task_name_input.setMinimumHeight(35)
        self.apply_input_style(self.task_name_input)
        apply_no_special_chars_validator(self.task_name_input)
        self.task_name_input.textChanged.connect(self.on_task_name_changed)
        self.task_name_input.textChanged.connect(self.check_form_completion)
        layout.addRow("Task Name *:", self.task_name_input)

        # Task Type
        self.task_type_combo = QComboBox()
        self.task_type_combo.setMinimumHeight(35)
        # Add default option
        self.task_type_combo.addItem("Select Task Type", "")
        # Add required task types
        self.task_type_combo.addItem("Picking", "picking")
        self.task_type_combo.addItem("Auditing", "auditing")
        self.task_type_combo.addItem("Storing", "storing")
        self.task_type_combo.addItem("Charging", "charging")
        self.task_type_combo.setEnabled(False)  # Disabled until Task Name is entered
        self.task_type_combo.currentTextChanged.connect(self.on_task_type_changed)
        self.task_type_combo.currentIndexChanged.connect(self.check_form_completion)
        self.apply_combo_style(self.task_type_combo)
        layout.addRow("Task Type *:", self.task_type_combo)

        # Picking-specific section (initially hidden)
        self.picking_section = self.create_picking_section()
        self.picking_section.setVisible(False)
        layout.addRow(self.picking_section)
        
        # Storing-specific section (initially hidden)
        self.storing_section = self.create_storing_section()
        self.storing_section.setVisible(False)
        layout.addRow(self.storing_section)
        
        # Auditing-specific section (initially hidden)
        self.auditing_section = self.create_auditing_section()
        self.auditing_section.setVisible(False)
        layout.addRow(self.auditing_section)

        # Charging-specific section (initially hidden)
        self.charging_section = self.create_charging_section()
        self.charging_section.setVisible(False)
        layout.addRow(self.charging_section)

        return section


    def create_picking_section(self):
        """Create picking-specific section with map, pickup stops, drop zone, file upload, and barcode fields"""
        section = QGroupBox("Picking Details")
        section.setStyleSheet(self.get_groupbox_style())
        layout = QFormLayout(section)
        layout.setSpacing(15)
        layout.setVerticalSpacing(15)

        # Pickup Map dropdown
        self.pickup_map_combo = QComboBox()
        self.pickup_map_combo.setMinimumHeight(35)
        self.pickup_map_combo.addItem("Select Pickup Map", "")
        self.pickup_map_combo.setEnabled(False)  # Disabled until Task Type is selected
        self.pickup_map_combo.currentIndexChanged.connect(self.check_form_completion)
        self.apply_combo_style(self.pickup_map_combo)
        layout.addRow("Pickup Map *:", self.pickup_map_combo)

        # Pick Up Stops list (multi-select of all stops in the pickup map)
        self.pickup_stop_list = QListWidget()
        self.pickup_stop_list.setMinimumHeight(100)
        self.pickup_stop_list.setSelectionMode(QListWidget.MultiSelection)
        self.pickup_stop_list.setEnabled(False)
        self.pickup_stop_list.setStyleSheet("""
            QListWidget {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 4px;
                color: #ffffff;
                font-size: 13px;
                min-height: 15px;
            }
            QListWidget:disabled {
                background-color: #2b2b2b;
                border: 1px solid #444444;
                color: #888888;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #ff6b35;
                color: white;
            }
        """)
        self.pickup_stop_list.itemSelectionChanged.connect(self.on_pickup_stop_selection_changed)
        layout.addRow("Pick Up Stops *:", self.pickup_stop_list)

        # Check Stops list (multi-select, only shows unselected stops)
        self.check_stop_list = QListWidget()
        self.check_stop_list.setMinimumHeight(100)
        self.check_stop_list.setSelectionMode(QListWidget.MultiSelection)
        self.check_stop_list.setEnabled(False)
        self.check_stop_list.setStyleSheet("""
            QListWidget {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 4px;
                color: #ffffff;
                font-size: 13px;
                min-height: 15px;
            }
            QListWidget:disabled {
                background-color: #2b2b2b;
                border: 1px solid #444444;
                color: #888888;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #ff6b35;
                color: white;
            }
        """)
        self.check_stop_list.itemSelectionChanged.connect(self.on_check_stop_selection_changed)
        layout.addRow("Check Stops:", self.check_stop_list)

        # Drop Stops list (multi-select, only shows unselected stops)
        self.drop_stop_list = QListWidget()
        self.drop_stop_list.setMinimumHeight(100)
        self.drop_stop_list.setSelectionMode(QListWidget.MultiSelection)
        self.drop_stop_list.setEnabled(False)
        self.drop_stop_list.setStyleSheet("""
            QListWidget {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 4px;
                color: #ffffff;
                font-size: 13px;
                min-height: 15px;
            }
            QListWidget:disabled {
                background-color: #2b2b2b;
                border: 1px solid #444444;
                color: #888888;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #ff6b35;
                color: white;
            }
        """)
        self.drop_stop_list.itemSelectionChanged.connect(self.on_drop_stop_selection_changed)
        layout.addRow("Drop Stops:", self.drop_stop_list)

        # End Stop list (single-select) - show only stops created with stop_function='end'
        self.end_stop_list = QListWidget()
        self.end_stop_list.setMinimumHeight(100)
        self.end_stop_list.setSelectionMode(QListWidget.SingleSelection)
        self.end_stop_list.setEnabled(False)
        self.end_stop_list.setStyleSheet("""
            QListWidget {
                background-color: #2d2d2d;
                color: white;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #0078D4;
                color: white;
            }
        """)
        self.end_stop_list.itemSelectionChanged.connect(self.check_form_completion)
        layout.addRow("End Stop *:", self.end_stop_list)

        # Charging Stops list (show all stops with stop_function='charging')
        self.charging_stops_list = QListWidget()
        self.charging_stops_list.setMinimumHeight(100)
        self.charging_stops_list.setSelectionMode(QListWidget.MultiSelection)
        self.charging_stops_list.setEnabled(False)
        self.charging_stops_list.setStyleSheet("""
            QListWidget {
                background-color: #2d2d2d;
                color: white;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #0078D4;
                color: white;
            }
        """)
        self.charging_stops_list.itemSelectionChanged.connect(self.check_form_completion)
        layout.addRow("Charging Stops:", self.charging_stops_list)

        # Keep a hidden end_zone_combo for backward compatibility (not shown)
        self.end_zone_combo = QComboBox()
        self.end_zone_combo.addItem("Select End Zone", "")
        self.end_zone_combo.setEnabled(False)
        self.end_zone_combo.setVisible(False)

        # Upload CSV file button
        upload_layout = QHBoxLayout()
        self.upload_csv_button = QPushButton("📁 Upload CSV File")
        self.upload_csv_button.clicked.connect(self.upload_csv_file)
        self.upload_csv_button.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: white;
                border: none;
                padding: 10px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        
        self.uploaded_file_label = QLabel("No file uploaded")
        self.uploaded_file_label.setStyleSheet("color: #cccccc; font-size: 11px; padding: 5px;")
        
        upload_layout.addWidget(self.upload_csv_button)
        upload_layout.addWidget(self.uploaded_file_label)
        layout.addRow("Upload File:", upload_layout)

        # Barcode input
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Enter barcode")
        self.barcode_input.setMinimumHeight(35)
        self.apply_input_style(self.barcode_input)
        layout.addRow("Barcode:", self.barcode_input)

        return section

    def create_auditing_section(self):
        """Create auditing-specific section with map, file upload, and barcode fields"""
        section = QGroupBox("Auditing Details")
        section.setStyleSheet(self.get_groupbox_style())
        layout = QFormLayout(section)
        layout.setSpacing(15)
        layout.setVerticalSpacing(15)

        # Auditing Map dropdown
        self.auditing_map_combo = QComboBox()
        self.auditing_map_combo.setMinimumHeight(35)
        self.auditing_map_combo.addItem("Select Auditing Map", "")
        self.auditing_map_combo.setEnabled(False)  # Disabled until Task Type is selected
        self.auditing_map_combo.currentIndexChanged.connect(self.check_form_completion)
        self.apply_combo_style(self.auditing_map_combo)
        layout.addRow("Auditing Map *:", self.auditing_map_combo)

        # Upload CSV file button
        upload_layout = QHBoxLayout()
        self.auditing_upload_csv_button = QPushButton("📁 Upload CSV File")
        self.auditing_upload_csv_button.clicked.connect(self.upload_csv_file)
        self.auditing_upload_csv_button.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: white;
                border: none;
                padding: 10px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        
        self.auditing_uploaded_file_label = QLabel("No file uploaded")
        self.auditing_uploaded_file_label.setStyleSheet("color: #cccccc; font-size: 11px; padding: 5px;")
        
        upload_layout.addWidget(self.auditing_upload_csv_button)
        upload_layout.addWidget(self.auditing_uploaded_file_label)
        layout.addRow("Upload File:", upload_layout)

        # Barcode input
        self.auditing_barcode_input = QLineEdit()
        self.auditing_barcode_input.setPlaceholderText("Enter barcode")
        self.auditing_barcode_input.setMinimumHeight(35)
        self.apply_input_style(self.auditing_barcode_input)
        layout.addRow("Barcode:", self.auditing_barcode_input)

        # End Zone dropdown for auditing
        self.auditing_end_zone_combo = QComboBox()
        self.auditing_end_zone_combo.setMinimumHeight(35)
        self.auditing_end_zone_combo.addItem("Select End Zone", "")
        self.auditing_end_zone_combo.setEnabled(False)
        self.auditing_end_zone_combo.currentIndexChanged.connect(self.check_form_completion)
        self.apply_combo_style(self.auditing_end_zone_combo)
        layout.addRow("End Zone *:", self.auditing_end_zone_combo)

        return section

    def create_storing_section(self):
        """Create storing-specific section with map, zone, file upload, and barcode fields"""
        section = QGroupBox("Storing Details")
        section.setStyleSheet(self.get_groupbox_style())
        layout = QFormLayout(section)
        layout.setSpacing(15)
        layout.setVerticalSpacing(15)

        # Storing Map dropdown
        self.storing_map_combo = QComboBox()
        self.storing_map_combo.setMinimumHeight(35)
        self.storing_map_combo.addItem("Select Storing Map", "")
        self.storing_map_combo.setEnabled(False)  # Disabled until Task Type is selected
        self.storing_map_combo.currentIndexChanged.connect(self.check_form_completion)
        self.apply_combo_style(self.storing_map_combo)
        layout.addRow("Storing Map *:", self.storing_map_combo)

        # From Zone dropdown for storing
        self.storing_from_zone_combo = QComboBox()
        self.storing_from_zone_combo.setMinimumHeight(35)
        self.storing_from_zone_combo.addItem("Select From Zone", "")
        self.storing_from_zone_combo.setEnabled(False)  # Disabled until Map is selected
        self.storing_from_zone_combo.currentIndexChanged.connect(self.check_form_completion)
        self.apply_combo_style(self.storing_from_zone_combo)
        layout.addRow("From Zone *:", self.storing_from_zone_combo)

        # To Zone dropdown for storing
        self.storing_to_zone_combo = QComboBox()
        self.storing_to_zone_combo.setMinimumHeight(35)
        self.storing_to_zone_combo.addItem("Select To Zone", "")
        self.storing_to_zone_combo.setEnabled(False)  # Disabled until From Zone is selected
        self.storing_to_zone_combo.currentIndexChanged.connect(self.check_form_completion)
        self.apply_combo_style(self.storing_to_zone_combo)
        layout.addRow("To Zone *:", self.storing_to_zone_combo)

        # Check Stops list for storing
        self.storing_check_stop_list = QListWidget()
        self.storing_check_stop_list.setMinimumHeight(100)
        self.storing_check_stop_list.setSelectionMode(QListWidget.MultiSelection)
        self.storing_check_stop_list.setEnabled(False)
        self.storing_check_stop_list.setStyleSheet("""
            QListWidget {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 4px;
                color: #ffffff;
                font-size: 13px;
                min-height: 15px;
            }
            QListWidget:disabled {
                background-color: #2b2b2b;
                border: 1px solid #444444;
                color: #888888;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #ff6b35;
                color: white;
            }
        """)
        self.storing_check_stop_list.itemSelectionChanged.connect(self.on_storing_check_stop_selection_changed)
        layout.addRow("Check Stops:", self.storing_check_stop_list)

        # Drop Stops list for storing
        self.storing_drop_stop_list = QListWidget()
        self.storing_drop_stop_list.setMinimumHeight(100)
        self.storing_drop_stop_list.setSelectionMode(QListWidget.MultiSelection)
        self.storing_drop_stop_list.setEnabled(False)
        self.storing_drop_stop_list.setStyleSheet("""
            QListWidget {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 4px;
                color: #ffffff;
                font-size: 13px;
                min-height: 15px;
            }
            QListWidget:disabled {
                background-color: #2b2b2b;
                border: 1px solid #444444;
                color: #888888;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #ff6b35;
                color: white;
            }
        """)
        self.storing_drop_stop_list.itemSelectionChanged.connect(self.on_storing_drop_stop_selection_changed)
        layout.addRow("Drop Stops:", self.storing_drop_stop_list)

        # End Zone dropdown for storing (renamed from drop zone)
        self.storing_end_zone_combo = QComboBox()
        self.storing_end_zone_combo.setMinimumHeight(35)
        self.storing_end_zone_combo.addItem("Select End Zone", "")
        self.storing_end_zone_combo.setEnabled(False)
        self.storing_end_zone_combo.currentIndexChanged.connect(self.check_form_completion)
        self.apply_combo_style(self.storing_end_zone_combo)
        layout.addRow("End Zone *:", self.storing_end_zone_combo)

        # Upload CSV file button
        upload_layout = QHBoxLayout()
        self.storing_upload_csv_button = QPushButton("📁 Upload CSV File")
        self.storing_upload_csv_button.clicked.connect(self.upload_csv_file)
        self.storing_upload_csv_button.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: white;
                border: none;
                padding: 10px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
        """)
        
        self.storing_uploaded_file_label = QLabel("No file uploaded")
        self.storing_uploaded_file_label.setStyleSheet("color: #cccccc; font-size: 11px; padding: 5px;")
        
        upload_layout.addWidget(self.storing_upload_csv_button)
        upload_layout.addWidget(self.storing_uploaded_file_label)
        layout.addRow("Upload File:", upload_layout)

        # Barcode input
        self.storing_barcode_input = QLineEdit()
        self.storing_barcode_input.setPlaceholderText("Enter barcode")
        self.storing_barcode_input.setMinimumHeight(35)
        self.apply_input_style(self.storing_barcode_input)
        layout.addRow("Barcode:", self.storing_barcode_input)

        return section



        return section

    def create_charging_section(self):
        """Create charging-specific section with map and charging station fields"""
        section = QGroupBox("Charging Details")
        section.setStyleSheet(self.get_groupbox_style())
        layout = QFormLayout(section)
        layout.setSpacing(15)
        layout.setVerticalSpacing(15)

        # Charging Map dropdown
        self.charging_map_combo = QComboBox()
        self.charging_map_combo.setMinimumHeight(35)
        self.charging_map_combo.addItem("Select Charging Map", "")
        self.charging_map_combo.setEnabled(False)  # Disabled until Task Type is selected
        self.charging_map_combo.currentIndexChanged.connect(self.on_charging_map_changed)
        self.charging_map_combo.currentIndexChanged.connect(self.check_form_completion)
        self.apply_combo_style(self.charging_map_combo)
        layout.addRow("Charging Map *:", self.charging_map_combo)

        # Charging Station dropdown
        self.charging_station_combo = QComboBox()
        self.charging_station_combo.setMinimumHeight(35)
        self.charging_station_combo.addItem("Select Charging Station", "")
        self.charging_station_combo.setEnabled(False)  # Disabled until Map is selected
        self.charging_station_combo.currentIndexChanged.connect(self.check_form_completion)
        self.apply_combo_style(self.charging_station_combo)
        layout.addRow("Charging Station *:", self.charging_station_combo)

        return section

    def populate_charging_maps(self):
        """Populate charging maps dropdown with existing maps"""
        self.charging_map_combo.clear()
        self.charging_map_combo.addItem("Select Charging Map", "")
        
        try:
            maps = self.csv_handler.read_csv('maps')
            for map_data in maps:
                map_id = map_data.get('id', '')
                map_name = map_data.get('name', map_id)
                if map_id:
                    self.charging_map_combo.addItem(map_name, map_id)
        except Exception as e:
            self.logger.error(f"Error loading maps: {e}")

    def on_charging_map_changed(self):
        """Handle charging map selection and populate stations"""
        map_id = self.charging_map_combo.currentData()
        self.charging_station_combo.clear()
        self.charging_station_combo.addItem("Select Charging Station", "")
        
        if not map_id:
            self.charging_station_combo.setEnabled(False)
            return

        self.charging_station_combo.setEnabled(True)
        try:
            stations = self.csv_handler.read_csv('charging_zones')
            devices = self.csv_handler.read_csv('devices')
            tasks = self.csv_handler.read_csv('tasks')
            
            # Identify occupied zones
            occupied_zones = set()
            
            # 1. Physical occupancy: Device in this zone AND status is 'charging'
            for d in devices:
                if str(d.get('status')).lower() == 'charging':
                    loc = str(d.get('current_location'))
                    if loc:
                        occupied_zones.add(loc)
            
            # 2. Logical reservation: 'Pending' or 'Running' charging tasks for this station
            for t in tasks:
                if str(t.get('status')).lower() in ['pending', 'running', 'processing'] and t.get('task_type') == 'charging':
                    try:
                        details_raw = t.get('task_details', '{}')
                        details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
                        if str(details.get('charging_map_id')) == str(map_id):
                            occupied_zones.add(str(details.get('charging_station')))
                    except Exception as je:
                        self.logger.warning(f"Error parsing task details for occupancy check: {je}")

            # Filter stations by map_id, static occupancy, and dynamic occupancy
            map_stations = [
                s for s in stations 
                if str(s.get('map_id')) == str(map_id) 
                and s.get('occupied', '').strip().lower() == 'no'
                and str(s.get('zone')) not in occupied_zones
            ]
            
            for s in map_stations:
                zone = s.get('zone', '')
                if zone:
                    self.charging_station_combo.addItem(zone, zone)
                    
        except Exception as e:
            self.logger.error(f"Error loading charging stations: {e}")

    def create_assignment_panel(self):
        """Create assignment panel"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 25px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setSpacing(20)

        # Assignment Section
        assignment_section = QGroupBox("Assignment")
        assignment_section.setStyleSheet(self.get_groupbox_style())
        assignment_layout = QFormLayout(assignment_section)
        assignment_layout.setSpacing(15)
        assignment_layout.setVerticalSpacing(15)

        # Device Assignment (Multi-select)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumHeight(35)
        self.device_combo.addItem("Auto-assign Available Device", "")  # kept for backward compatibility (hidden)
        self.device_combo.currentTextChanged.connect(self.on_device_changed)
        self.apply_combo_style(self.device_combo)
        # Multi-select device list
        self.device_list = QListWidget()
        self.device_list.setSelectionMode(QListWidget.MultiSelection)
        self.device_list.setMinimumHeight(140)
        self.device_list.setEnabled(False)  # Initially disabled until prerequisites are met
        self.device_list.setStyleSheet("""
            QListWidget {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 6px;
                border-radius: 4px;
                color: #ffffff;
                font-size: 13px;
            }
            QListWidget:disabled {
                background-color: #2b2b2b;
                border: 1px solid #444444;
                color: #888888;
            }
            QListWidget::item { padding: 4px; }
            QListWidget::item:selected { background-color: #ff6b35; color: white; }
            QListWidget::item:disabled { color: #666666; }
        """)
        try:
            self.device_list.itemSelectionChanged.disconnect()
        except Exception:
            pass
        self.device_list.itemSelectionChanged.connect(self.on_device_selection_changed)
        assignment_layout.addRow("Assign Devices *:", self.device_list)

        # Device Status Label
        self.device_status_label = QLabel("Complete task name, type, and details first")
        self.device_status_label.setStyleSheet("""
            QLabel {
                color: #F59E0B;
                font-size: 11px;
                padding: 5px;
                background-color: #404040;
                border: 1px solid #555555;
                border-radius: 4px;
            }
        """)
        self.device_status_label.setWordWrap(True)
        self.device_status_label.setMinimumHeight(60)
        assignment_layout.addRow("Device Status:", self.device_status_label)

        # User Assignment
        self.user_combo = QComboBox()
        self.user_combo.setMinimumHeight(35)
        self.user_combo.addItem("Auto-assign Available User", "")
        self.apply_combo_style(self.user_combo)
        assignment_layout.addRow("Assign User:", self.user_combo)

        layout.addWidget(assignment_section)

        layout.addStretch()

        return panel



    def create_action_buttons(self, parent_layout):
        """Create action buttons"""
        action_layout = QHBoxLayout()

        # Clear form button
        clear_btn = QPushButton("🗑️ Clear Form")
        clear_btn.clicked.connect(self.clear_form)
        self.apply_button_style(clear_btn)
        action_layout.addWidget(clear_btn)


        action_layout.addStretch()

        # Create task button
        self.create_btn = QPushButton("➕ Create Task")
        self.create_btn.clicked.connect(self.create_task)
        self.create_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6b35;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e55a2b;
            }
        """)
        action_layout.addWidget(self.create_btn)

        parent_layout.addLayout(action_layout)

    def get_groupbox_style(self):
        """Get groupbox styling"""
        return """
            QGroupBox {
                color: #ffffff;
                border: 1px solid #666666;
                border-radius: 6px;
                padding-top: 20px;
                margin: 15px 0;
                font-weight: bold;
                font-size: 14px;
            }
            QGroupBox::title {
                color: #ff6b35;
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                font-size: 14px;
            }
        """

    def apply_input_style(self, widget):
        """Apply input styling"""
        widget.setStyleSheet("""
            QLineEdit, QSpinBox, QDateTimeEdit, QDoubleSpinBox {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 10px;
                border-radius: 4px;
                color: #ffffff;
                font-size: 13px;
                min-height: 15px;
            }
            QLineEdit:focus, QSpinBox:focus, QDateTimeEdit:focus, QDoubleSpinBox:focus {
                border: 2px solid #ff6b35;
            }
        """)

    def apply_combo_style(self, combo):
        """Apply combobox styling"""
        combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 10px;
                padding-right: 35px;
                border-radius: 4px;
                color: #ffffff;
                min-width: 150px;
                font-size: 13px;
                min-height: 15px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border: none;
                border-left: 1px solid #555555;
                border-radius: 0 4px 4px 0;
                background: #ff6b35;
            }
            QComboBox::down-arrow {
                image: none;
                text: "˅";
                color: #ffffff;
                font-size: 20px;
                font-weight: bold;
                right: 8px;
                top: 1px;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #ff6b35;
                padding: 5px;
                border: 1px solid #555555;
                border-radius: 4px;
            }
        """)

    def apply_button_style(self, button):
        """Apply button styling"""
        button.setStyleSheet("""
            QPushButton {
                background-color: #555555;
                color: white;
                border: none;
                padding: 10px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666666;
            }
        """)

    def load_data(self):
        """Load devices and users for assignment"""
        # Don't load devices here - only load when device selection is enabled
        # self.load_devices()  # Moved to check_form_completion()
        self.load_users()
        self.update_task_stats()

    # Battery parsing and distance mapping moved to BatteryMapper module
    def parse_battery(self, val):
        """Centralized battery parsing helper - delegates to BatteryMapper"""
        return self.battery_mapper.parse_battery(val)

    def load_devices(self):
        """Load available devices - filtered, sorted by battery, with disabled items marked"""
        try:
            self.device_combo.clear()
            self.device_combo.addItem("Auto-assign Available Device", "")
        
            if hasattr(self, 'device_list') and self.device_list is not None:
                self.device_list.clear()

            # Get current task type and details
            task_type = self.task_type_combo.currentData() if hasattr(self, 'task_type_combo') else None
            
            if not task_type:
                return
            
            # Get task-specific parameters
            map_id = None
            from_zone = None
            to_zone = None
            
            if task_type == 'picking':
                # New picking semantics: distance is based on map and selected
                # pickup stops / drop zone, not from/to zones.
                map_id = self.pickup_map_combo.currentData() if hasattr(self, 'pickup_map_combo') else None
            elif task_type == 'storing':
                map_id = self.storing_map_combo.currentData() if hasattr(self, 'storing_map_combo') else None
                from_zone = self.storing_from_zone_combo.currentData() if hasattr(self, 'storing_from_zone_combo') else None
                to_zone = self.storing_to_zone_combo.currentData() if hasattr(self, 'storing_to_zone_combo') else None
            elif task_type == 'auditing':
                map_id = self.auditing_map_combo.currentData() if hasattr(self, 'auditing_map_combo') else None
            elif task_type == 'charging':
                map_id = self.charging_map_combo.currentData() if hasattr(self, 'charging_map_combo') else None
            
            # Create task handler and calculate required distance
            try:
                self.task_handler = TaskTypeHandlerFactory.create_handler(
                    task_type, self.csv_handler, self.distance_calculator
                )
                
                # Calculate required distance based on task type
                if task_type == 'auditing':
                    self.required_distance = self.task_handler.calculate_required_distance(map_id)
                elif task_type == 'storing':
                    if from_zone and to_zone:
                        self.required_distance = self.task_handler.calculate_required_distance(
                            map_id, from_zone, to_zone
                        )
                    else:
                        self.required_distance = 0
                elif task_type == 'picking':
                    # Get selected stops and end zone for picking
                    pickup_stops = self.get_selected_stops_from_list(self.pickup_stop_list) or []
                    check_stops = self.get_selected_stops_from_list(self.check_stop_list) or []
                    drop_stops = self.get_selected_stops_from_list(self.drop_stop_list) or []
                    all_stops = (pickup_stops or []) + (check_stops or []) + (drop_stops or [])
                    end_zone = self.end_zone_combo.currentData()
                    
                    # For picking, we approximate required distance using map distance with stops
                    # This ensures we don't under-estimate the robot's range needs
                    if map_id:
                        self.required_distance = self.distance_calculator.get_required_distance_for_task(
                            task_type, map_id, from_zone=None, to_zone=end_zone, selected_stops=all_stops
                        )
                    else:
                        self.required_distance = 0
                else:
                    self.required_distance = 0
                    
            except Exception as e:
                self.logger.error(f"Error creating task handler: {e}")
                self.required_distance = 0
            
            # Filter devices using DeviceFilter
            selected_stops = []
            if task_type == 'picking':
                pickup_stops = self.get_selected_stops_from_list(self.pickup_stop_list) or []
                check_stops = self.get_selected_stops_from_list(self.check_stop_list) or []
                drop_stops = self.get_selected_stops_from_list(self.drop_stop_list) or []
                selected_stops = (pickup_stops or []) + (check_stops or []) + (drop_stops or [])

            candidates = self.device_filter.filter_devices(
                task_type=task_type,
                map_id=map_id,
                from_zone=from_zone,
                to_zone=to_zone,
                required_distance=self.required_distance if self.required_distance > 0 else None,
                selected_stops=selected_stops
            )
            
            # Create list items from filtered candidates
            items = self.device_filter.create_device_list_items(candidates, task_type)
            
            # Populate device combo (legacy)
            for candidate in candidates:
                device = candidate['device']
                selectable = candidate['selectable']
                
                device_name = device.get('device_name', '')
                device_id = device.get('device_id', '')
                icon = "✅" if selectable else "❌"
                device_text = f"{icon} {device_name} ({device_id}) - {candidate['battery']}%"
                
                self.device_combo.addItem(device_text, device.get('id'))
            
            # Add items to device list
            if hasattr(self, 'device_list') and self.device_list is not None:
                for item in items:
                    self.device_list.addItem(item)
        
            self.logger.info(f"Loaded {len(candidates)} devices ({sum(1 for c in candidates if c['selectable'])} selectable)")

            # Show informative message if no devices available in the map
            if not candidates and map_id:
                self.device_status_label.setText("No devices available in the selected map")
                self.device_status_label.setStyleSheet("""
                    QLabel {
                        color: #EF4444;
                        font-size: 11px;
                        padding: 5px;
                        background-color: #404040;
                        border: 1px solid #555555;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                """)

        except Exception as e:
            self.logger.error(f"Error loading devices: {e}")
    def get_selected_stops_from_list(self, list_widget):
        """
        Get selected stop IDs from a QListWidget.
    
        Args:
            list_widget: QListWidget containing stops
        
        Returns:
            List of selected stop IDs, or None if none selected
        """
        if list_widget is None:
            return None
    
        selected_stops = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item and item.isSelected():
                stop_id = item.data(Qt.UserRole)
                if stop_id:
                    selected_stops.append(str(stop_id))
    
        return selected_stops if selected_stops else None


    def load_users(self):
        """Load available users"""
        try:
            users = self.csv_handler.read_csv('users')

            self.user_combo.clear()
            self.user_combo.addItem("Auto-assign Available User", "")

            for user in users:
                is_active = user.get('is_active', 'true').lower() == 'true'

                user_text = user.get('username', '')
                employee_id = user.get('employee_id', '')
                if employee_id:
                    user_text += f" ({employee_id})"

                if is_active:
                    self.user_combo.addItem(f"✅ {user_text.strip()}", user.get('id'))
                else:
                    self.user_combo.addItem(f"❌ {user_text.strip()} - Inactive", user.get('id'))

        except Exception as e:
            self.logger.error(f"Error loading users: {e}")
    

    def update_task_stats(self):
        """Update task statistics"""
        try:
            tasks = self.csv_handler.read_csv('tasks')

            active_count = len([t for t in tasks if t.get('status', '').lower() == 'running'])
            pending_count = len([t for t in tasks if t.get('status', '').lower() == 'pending'])

            # Safely update labels if they exist
            if hasattr(self, 'active_tasks_label') and self.active_tasks_label:
                self.active_tasks_label.setText(f"Active Tasks: {active_count}")
            if hasattr(self, 'pending_tasks_label') and self.pending_tasks_label:
                self.pending_tasks_label.setText(f"Pending: {pending_count}")

        except Exception as e:
            self.logger.error(f"Error updating stats: {e}")

    def on_task_name_changed(self, text):
        """Handle task name change - enable/disable task type combo"""
        task_name_filled = bool(text.strip())
        if hasattr(self, 'task_type_combo'):
            self.task_type_combo.setEnabled(task_name_filled)
            # If task name is cleared, reset task type and disable subsequent steps
            if not task_name_filled:
                self.task_type_combo.setCurrentIndex(0)
                # Disable all subsequent combos
                if hasattr(self, 'pickup_map_combo'):
                    self.pickup_map_combo.setEnabled(False)
                    self.pickup_map_combo.setCurrentIndex(0)
                if hasattr(self, 'storing_map_combo'):
                    self.storing_map_combo.setEnabled(False)
                    self.storing_map_combo.setCurrentIndex(0)
                if hasattr(self, 'auditing_map_combo'):
                    self.auditing_map_combo.setEnabled(False)
                    self.auditing_map_combo.setCurrentIndex(0)
                if hasattr(self, 'from_zone_combo'):
                    self.from_zone_combo.setEnabled(False)
                    self.from_zone_combo.setCurrentIndex(0)
                if hasattr(self, 'to_zone_combo'):
                    self.to_zone_combo.setEnabled(False)
                    self.to_zone_combo.setCurrentIndex(0)
                if hasattr(self, 'storing_from_zone_combo'):
                    self.storing_from_zone_combo.setEnabled(False)
                    self.storing_from_zone_combo.setCurrentIndex(0)
                if hasattr(self, 'storing_to_zone_combo'):
                    self.storing_to_zone_combo.setEnabled(False)
                    self.storing_to_zone_combo.setCurrentIndex(0)
                if hasattr(self, 'end_zone_combo'):
                    self.end_zone_combo.setEnabled(False)
                    self.end_zone_combo.setCurrentIndex(0)
                if hasattr(self, 'storing_end_zone_combo'):
                    self.storing_end_zone_combo.setEnabled(False)
                    self.storing_end_zone_combo.setCurrentIndex(0)
                if hasattr(self, 'auditing_end_zone_combo'):
                    self.auditing_end_zone_combo.setEnabled(False)
                    self.auditing_end_zone_combo.setCurrentIndex(0)
                if hasattr(self, 'device_list') and self.device_list is not None:
                    self.device_list.setEnabled(False)
                    self.device_list.clear()

    def on_task_type_changed(self):
        """Handle task type change"""
        # Update suggested locations based on task type
        task_type = self.task_type_combo.currentData()

        # Disable all map/zone combos first
        if hasattr(self, 'pickup_map_combo'):
            self.pickup_map_combo.setEnabled(False)
            self.pickup_map_combo.clear()
            self.pickup_map_combo.addItem("Select Pickup Map", "")
        if hasattr(self, 'storing_map_combo'):
            self.storing_map_combo.setEnabled(False)
            self.storing_map_combo.clear()
            self.storing_map_combo.addItem("Select Storing Map", "")
        if hasattr(self, 'auditing_map_combo'):
            self.auditing_map_combo.setEnabled(False)
            self.auditing_map_combo.clear()
            self.auditing_map_combo.addItem("Select Auditing Map", "")
        
        # Disable zone combos
        if hasattr(self, 'from_zone_combo'):
            self.from_zone_combo.setEnabled(False)
            self.from_zone_combo.clear()
            self.from_zone_combo.addItem("Select From Zone", "")
        if hasattr(self, 'to_zone_combo'):
            self.to_zone_combo.setEnabled(False)
            self.to_zone_combo.clear()
            self.to_zone_combo.addItem("Select To Zone", "")
        if hasattr(self, 'storing_from_zone_combo'):
            self.storing_from_zone_combo.setEnabled(False)
            self.storing_from_zone_combo.clear()
            self.storing_from_zone_combo.addItem("Select From Zone", "")
        if hasattr(self, 'storing_to_zone_combo'):
            self.storing_to_zone_combo.setEnabled(False)
            self.storing_to_zone_combo.clear()
            self.storing_to_zone_combo.addItem("Select To Zone", "")

        # Show/hide sections based on task type
        if hasattr(self, 'picking_section') and hasattr(self, 'storing_section') and hasattr(self, 'auditing_section') and hasattr(self, 'charging_section'):
            # Hide all sections first
            self.picking_section.setVisible(False)
            self.storing_section.setVisible(False)
            self.auditing_section.setVisible(False)
            self.charging_section.setVisible(False)
            
            # Show the appropriate section based on task type
            if task_type == 'picking':
                self.picking_section.setVisible(True)
                # Enable map combo and populate
                if hasattr(self, 'pickup_map_combo'):
                    self.pickup_map_combo.setEnabled(True)
                    self.populate_pickup_maps()
            elif task_type == 'storing':
                self.storing_section.setVisible(True)
                # Enable map combo and populate
                if hasattr(self, 'storing_map_combo'):
                    self.storing_map_combo.setEnabled(True)
                    self.populate_pickup_maps_for_storing()
            elif task_type == 'auditing':
                self.auditing_section.setVisible(True)
                # Enable map combo and populate
                if hasattr(self, 'auditing_map_combo'):
                    self.auditing_map_combo.setEnabled(True)
                    self.populate_pickup_maps_for_auditing()
            elif task_type == 'charging':
                self.charging_section.setVisible(True)
                if hasattr(self, 'charging_map_combo'):
                    self.charging_map_combo.setEnabled(True)
                    self.populate_charging_maps()
        
        # Disable device list until all prerequisites are met
        if hasattr(self, 'device_list') and self.device_list is not None:
            self.device_list.setEnabled(False)
            self.device_list.clear()
        
        # Check form completion after task type change
        self.check_form_completion()

    def on_device_changed(self):
        """Handle device selection change"""
        device_id = self.device_combo.currentData()
        if device_id:
            # Find device info
            devices = self.csv_handler.read_csv('devices')
            device = next((d for d in devices if str(d.get('id')) == str(device_id)), None)

            if device:
                status = device.get('status', 'unknown').title()
                battery = device.get('battery_level', 'N/A')
                location = device.get('current_location', 'Unknown')

                info_text = f"Status: {status}\nBattery: {battery}%\nLocation: {location}"
                self.device_status_label.setText(info_text)
            else:
                self.device_status_label.setText("Device information not available")
        else:
            self.device_status_label.setText("Please select a device")

    def on_device_selection_changed(self):
        """Handle multi-device selection change (update status summary)."""
        try:
            selected = self.get_selected_device_ids()
            if not selected:
                self.device_status_label.setText("Please select one or more devices")
                return
            # Summarize selected devices
            devices = self.csv_handler.read_csv('devices')
            names = []
            for did in selected:
                d = next((x for x in devices if str(x.get('id')) == str(did)), None)
                if d:
                    names.append(f"{d.get('device_name','')} ({d.get('device_id','')})")
                else:
                    names.append(str(did))
            if len(names) <= 3:
                text = "\n".join([f"• {n}" for n in names])
            else:
                head = "\n".join([f"• {n}" for n in names[:3]])
                text = f"{head}\n+{len(names)-3} more..."
            self.device_status_label.setText(text)
        except Exception:
            pass

    def get_selected_device_ids(self):
        """Return list of selected device 'id' values from the multi-select list.
        Only returns IDs for enabled/selectable items.
        """
        if hasattr(self, 'device_list') and self.device_list is not None:
            selected_ids = []
            for i in range(self.device_list.count()):
                item = self.device_list.item(i)
                if item and item.isSelected() and item.data(Qt.UserRole):
                    # Only include if item is enabled (selectable)
                    if item.flags() & Qt.ItemIsEnabled:
                        selected_ids.append(item.data(Qt.UserRole))
            return selected_ids
        return []

    def check_form_completion(self):
        """Check if form prerequisites are met to enable device selection"""
        # Step 1: Task name must be filled
        task_name_filled = bool(self.task_name_input.text().strip())
        
        # Step 2: Task type must be selected
        task_type_selected = bool(self.task_type_combo.currentData())
        
        # Step 3: Task type details must be filled based on task type
        task_details_filled = False
        task_type = self.task_type_combo.currentData()
        
        if task_type == 'picking':
            # For picking: map, at least one pickup stop, and end stop must be selected
            # Check stops optional; Drop stops required if map defines any drop stops
            has_map = hasattr(self, 'pickup_map_combo') and self.pickup_map_combo.currentIndex() > 0
            has_end_stop = False
            if hasattr(self, 'end_stop_list'):
                for i in range(self.end_stop_list.count()):
                    item = self.end_stop_list.item(i)
                    if item and item.isSelected():
                        has_end_stop = True
                        break
            has_pickup_stops = False
            if hasattr(self, 'pickup_stop_list'):
                for i in range(self.pickup_stop_list.count()):
                    item = self.pickup_stop_list.item(i)
                    if item and item.isSelected():
                        has_pickup_stops = True
                        break
            # Drop stops requirement if drop list has items
            has_drop_stops = True
            if hasattr(self, 'drop_stop_list') and self.drop_stop_list.count() > 0:
                has_drop_stops = False
                for i in range(self.drop_stop_list.count()):
                    item = self.drop_stop_list.item(i)
                    if item and item.isSelected():
                        has_drop_stops = True
                        break
            # End stop should be enabled if pickup stops are selected
            if has_pickup_stops and hasattr(self, 'end_stop_list'):
                self.end_stop_list.setEnabled(True)
            task_details_filled = has_map and has_pickup_stops and has_drop_stops and has_end_stop
        elif task_type == 'storing':
            # For storing: map, from zone, to zone, and end zone must be selected
            task_details_filled = (
                hasattr(self, 'storing_map_combo') and
                self.storing_map_combo.currentIndex() > 0 and
                hasattr(self, 'storing_from_zone_combo') and
                self.storing_from_zone_combo.currentIndex() > 0 and
                hasattr(self, 'storing_to_zone_combo') and
                self.storing_to_zone_combo.currentIndex() > 0 and
                hasattr(self, 'storing_end_zone_combo') and
                self.storing_end_zone_combo.currentIndex() > 0
            )
        elif task_type == 'auditing':
            # For auditing: map and end zone must be selected
            task_details_filled = (
                hasattr(self, 'auditing_map_combo') and
                self.auditing_map_combo.currentIndex() > 0 and
                hasattr(self, 'auditing_end_zone_combo') and
                self.auditing_end_zone_combo.currentIndex() > 0
            )
        elif task_type == 'charging':
            # For charging: map and station must be selected
            task_details_filled = (
                hasattr(self, 'charging_map_combo') and
                self.charging_map_combo.currentIndex() > 0 and
                hasattr(self, 'charging_station_combo') and
                self.charging_station_combo.currentIndex() > 0
            )
        
        # Enable device selection only if all prerequisites are met
        all_prerequisites_met = task_name_filled and task_type_selected and task_details_filled
        
        if hasattr(self, 'device_list') and self.device_list is not None:
            if all_prerequisites_met:
                # Load devices right before enabling selection
                self.load_devices()
                self.device_list.setEnabled(True)
                self.device_status_label.setText("Select one or more devices")
                self.device_status_label.setStyleSheet("""
                    QLabel {
                        color: #10B981;
                        font-size: 11px;
                        padding: 5px;
                        background-color: #404040;
                        border: 1px solid #555555;
                        border-radius: 4px;
                    }
                """)
            else:
                self.device_list.setEnabled(False)
                # Clear device list when prerequisites not met
                if self.device_list.count() > 0:
                    self.device_list.clear()
                
                missing_steps = []
                if not task_name_filled:
                    missing_steps.append("Task Name")
                if not task_type_selected:
                    missing_steps.append("Task Type")
                if not task_details_filled:
                    if task_type == 'auditing':
                        missing_steps.append("Auditing Map, End Zone")
                    elif task_type == 'picking':
                        missing_steps.append("Pickup Map, Pick Up Stops, End Stop")
                    elif task_type == 'charging':
                        missing_steps.append("Charging Map, Charging Station")
                    else:
                        missing_steps.append("Map, From Zone, To Zone, End Zone")
                
                self.device_status_label.setText(f"Complete: {', '.join(missing_steps)}")
                self.device_status_label.setStyleSheet("""
                    QLabel {
                        color: #F59E0B;
                        font-size: 11px;
                        padding: 5px;
                        background-color: #404040;
                        border: 1px solid #555555;
                        border-radius: 4px;
                    }
                """)

    def clear_form(self):
        """Clear all form fields"""
        self.task_name_input.clear()
        self.task_type_combo.setCurrentIndex(0)
        self.device_combo.setCurrentIndex(0)
        if hasattr(self, 'device_list') and self.device_list is not None:
            self.device_list.clearSelection()
        self.user_combo.setCurrentIndex(0)
        
        # Clear picking section fields
        if hasattr(self, 'pickup_stop_list'):
            self.pickup_stop_list.clear()
            self.pickup_stop_list.setEnabled(False)
        if hasattr(self, 'check_stop_list'):
            self.check_stop_list.clear()
            self.check_stop_list.setEnabled(False)
        if hasattr(self, 'drop_stop_list'):
            self.drop_stop_list.clear()
            self.drop_stop_list.setEnabled(False)
        if hasattr(self, 'end_zone_combo'):
            self.end_zone_combo.setCurrentIndex(0)
            self.end_zone_combo.setEnabled(False)
        
        # Clear storing section fields
        if hasattr(self, 'storing_check_stop_list'):
            self.storing_check_stop_list.clear()
            self.storing_check_stop_list.setEnabled(False)
        if hasattr(self, 'storing_drop_stop_list'):
            self.storing_drop_stop_list.clear()
            self.storing_drop_stop_list.setEnabled(False)
        if hasattr(self, 'storing_end_zone_combo'):
            self.storing_end_zone_combo.setCurrentIndex(0)
            self.storing_end_zone_combo.setEnabled(False)
        
        # Clear auditing section fields
        if hasattr(self, 'auditing_end_zone_combo'):
            self.auditing_end_zone_combo.setCurrentIndex(0)
            self.auditing_end_zone_combo.setEnabled(False)
        
        # Reset device list state
        self.check_form_completion()



    def create_task(self):
        """Create new task"""
        if not self.validate_form():
            return

        try:
            task_data = self.collect_task_data()
            self.save_task(task_data)
        except Exception as e:
            self.logger.error(f"Error creating task: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create task: {e}")


    def check_device_availability(self, device_id):
        """Check if device is available (not running another task)"""
        if not device_id:
            return True
        
        tasks = self.csv_handler.read_csv('tasks')
        device_tasks = [t for t in tasks if (
            t.get('assigned_device_id') == str(device_id) and
            t.get('status', '').lower() == 'running'
        )]
        
        return len(device_tasks) == 0

    def validate_form(self):
        """Validate form inputs"""
        if not self.task_name_input.text().strip():
            QMessageBox.warning(self, "Validation Error", "Task name is required")
            self.task_name_input.setFocus()
            return False

        if not self.task_type_combo.currentData():
            QMessageBox.warning(self, "Validation Error", "Task type is required")
            self.task_type_combo.setFocus()
            return False

        # Require at least one device selection
        selected_devices = self.get_selected_device_ids()
        if not selected_devices:
            QMessageBox.warning(self, "Validation Error", "At least one device must be selected")
            if hasattr(self, 'device_list') and self.device_list is not None:
                self.device_list.setFocus()
            return False
        # Check all selected devices are available
        if not self.check_devices_availability(selected_devices):
            QMessageBox.warning(
                self,
                "Device Busy",
                "One or more selected devices are currently running another task. "
                "Please adjust your selection."
            )
            if hasattr(self, 'device_list') and self.device_list is not None:
                self.device_list.setFocus()
            return False

        # Task type specific validations
        task_type = self.task_type_combo.currentData()
        if task_type == 'picking':
            if not self.pickup_map_combo.currentData():
                QMessageBox.warning(self, "Validation Error", "Pickup map is required")
                self.pickup_map_combo.setFocus()
                return False
            has_pickup_stops = False
            if hasattr(self, 'pickup_stop_list'):
                for i in range(self.pickup_stop_list.count()):
                    item = self.pickup_stop_list.item(i)
                    if item and item.isSelected():
                        has_pickup_stops = True
                        break
            if not has_pickup_stops:
                QMessageBox.warning(self, "Validation Error", "Select at least one Pick Up Stop")
                if hasattr(self, 'pickup_stop_list'):
                    self.pickup_stop_list.setFocus()
                return False
            # Require at least one drop stop if drop stops exist on map
            if hasattr(self, 'drop_stop_list') and self.drop_stop_list.count() > 0:
                has_drop = False
                for i in range(self.drop_stop_list.count()):
                    item = self.drop_stop_list.item(i)
                    if item and item.isSelected():
                        has_drop = True
                        break
                if not has_drop:
                    QMessageBox.warning(self, "Validation Error", "Select at least one Drop Stop")
                    self.drop_stop_list.setFocus()
                    return False
            # End stop instead of end zone - require a selected end stop
            has_end = False
            if hasattr(self, 'end_stop_list'):
                for i in range(self.end_stop_list.count()):
                    item = self.end_stop_list.item(i)
                    if item and item.isSelected():
                        has_end = True
                        break
            if not has_end:
                QMessageBox.warning(self, "Validation Error", "End Stop is required")
                if hasattr(self, 'end_stop_list'):
                    self.end_stop_list.setFocus()
                return False

        elif task_type == 'storing':
            if not self.storing_map_combo.currentData():
                QMessageBox.warning(self, "Validation Error", "Storing map is required")
                self.storing_map_combo.setFocus()
                return False
            if not self.storing_from_zone_combo.currentData():
                QMessageBox.warning(self, "Validation Error", "From zone is required")
                self.storing_from_zone_combo.setFocus()
                return False
            if not self.storing_to_zone_combo.currentData():
                QMessageBox.warning(self, "Validation Error", "To zone is required")
                self.storing_to_zone_combo.setFocus()
                return False
            if not self.storing_end_zone_combo.currentData():
                QMessageBox.warning(self, "Validation Error", "End Zone is required")
                self.storing_end_zone_combo.setFocus()
                return False

        elif task_type == 'auditing':
            if not self.auditing_map_combo.currentData():
                QMessageBox.warning(self, "Validation Error", "Auditing map is required")
                self.auditing_map_combo.setFocus()
                return False
            if not self.auditing_end_zone_combo.currentData():
                QMessageBox.warning(self, "Validation Error", "End Zone is required")
                self.auditing_end_zone_combo.setFocus()
                return False
        
        elif task_type == 'charging':
            if not self.charging_map_combo.currentData():
                QMessageBox.warning(self, "Validation Error", "Charging map is required")
                self.charging_map_combo.setFocus()
                return False
            if not self.charging_station_combo.currentData():
                QMessageBox.warning(self, "Validation Error", "Charging station is required")
                self.charging_station_combo.setFocus()
                return False

        return True

    def collect_task_data(self):
        """Collect task data from form"""
        current_time = datetime.now().isoformat()

        # Generate task ID automatically
        task_id = f"TASK{self.csv_handler.get_next_id('tasks'):04d}"

        task_data = {
            'id': '',  # Will be auto-generated by the CSV handler
            'task_id': task_id,
            'task_name': self.task_name_input.text().strip(),
            'task_type': self.task_type_combo.currentData(),
            'status': 'pending',
            # Backward-compat single device id = first selected
            'assigned_device_id': (self.get_selected_device_ids()[0] if self.get_selected_device_ids() else ''),
            # New multi-device field (comma-separated device ids)
            'assigned_device_ids': ','.join(str(x) for x in self.get_selected_device_ids()) if self.get_selected_device_ids() else '',
            'assigned_user_id': self.user_combo.currentData() or '',
            'description': self.description_input.text().strip() if hasattr(self, 'description_input') else '',
            'estimated_duration': '',  # We can calculate this based on zones/path later
            'actual_duration': '',
            'created_at': current_time,
            'started_at': '',
            'completed_at': '',
            'map_id': '',  # Will be set based on task type
            'zone_ids': '',  # Will be set based on task type
            'stop_ids': '',  # Will be set based on task type
            'task_details': {}  # Will be filled based on task type
        }

        # Add task-type specific data and consolidate map/zone/stop information
        task_type = self.task_type_combo.currentData()
        
        # Initialize common fields
        task_data['map_id'] = ''
        task_data['zone_ids'] = ''
        task_data['stop_ids'] = ''
        task_data['task_details'] = {}  # Dictionary to store type-specific details
        
        if task_type == 'auditing':
            # Add auditing-specific data
            if hasattr(self, 'auditing_map_combo'):
                map_id = self.auditing_map_combo.currentData() or ''
                task_data['map_id'] = map_id
                task_data['task_details']['auditing_map_id'] = map_id
                task_data['task_details']['auditing_map_name'] = self.auditing_map_combo.currentText() or ''
            if hasattr(self, 'auditing_barcode_input'):
                task_data['task_details']['barcode'] = self.auditing_barcode_input.text().strip()
            if hasattr(self, 'uploaded_csv_file'):
                task_data['task_details']['csv_file_path'] = self.uploaded_csv_file
            
            # Capture End Zone
            end_zone_id = self.auditing_end_zone_combo.currentData() if hasattr(self, 'auditing_end_zone_combo') else ''
            end_zone_name = self.auditing_end_zone_combo.currentText() if hasattr(self, 'auditing_end_zone_combo') else ''
            if end_zone_id:
                task_data['zone_ids'] = str(end_zone_id)
                task_data['task_details']['end_zone'] = str(end_zone_id)
            if end_zone_name:
                task_data['task_details']['end_zone_name'] = end_zone_name
                
        elif task_type == 'picking':
            # Add picking-specific data
            if hasattr(self, 'pickup_map_combo'):
                map_id = self.pickup_map_combo.currentData() or ''
                task_data['map_id'] = map_id
                task_data['task_details']['pickup_map_id'] = map_id
                task_data['task_details']['pickup_map_name'] = self.pickup_map_combo.currentText() or ''

            # Capture selected pickup stops
            pickup_stops = []
            pickup_stop_names = []
            if hasattr(self, 'pickup_stop_list'):
                for i in range(self.pickup_stop_list.count()):
                    item = self.pickup_stop_list.item(i)
                    if item and item.isSelected():
                        stop_id = item.data(Qt.UserRole)
                        if stop_id:
                            pickup_stops.append(str(stop_id))
                            pickup_stop_names.append(item.text())
            task_data['task_details']['pickup_stops'] = pickup_stops
            task_data['task_details']['pickup_stop_names'] = pickup_stop_names

            # Capture selected check stops
            check_stops = []
            check_stop_names = []
            if hasattr(self, 'check_stop_list'):
                for i in range(self.check_stop_list.count()):
                    item = self.check_stop_list.item(i)
                    if item and item.isSelected():
                        stop_id = item.data(Qt.UserRole)
                        if stop_id:
                            check_stops.append(str(stop_id))
                            check_stop_names.append(item.text())
            task_data['task_details']['check_stops'] = check_stops
            task_data['task_details']['check_stop_names'] = check_stop_names

            # Capture selected drop stops
            drop_stops = []
            drop_stop_names = []
            if hasattr(self, 'drop_stop_list'):
                for i in range(self.drop_stop_list.count()):
                    item = self.drop_stop_list.item(i)
                    if item and item.isSelected():
                        stop_id = item.data(Qt.UserRole)
                        if stop_id:
                            drop_stops.append(str(stop_id))
                            drop_stop_names.append(item.text())
            task_data['task_details']['drop_stops'] = drop_stops
            task_data['task_details']['drop_stop_names'] = drop_stop_names

            # Combine all stops for stop_ids field
            all_stops = pickup_stops + check_stops + drop_stops
            task_data['stop_ids'] = ','.join(all_stops) if all_stops else ''

            # Capture End Stop (renamed from Drop Zone) - this stop_id is used for CALL,END
            end_stop_ids = []
            end_stop_names = []
            if hasattr(self, 'end_stop_list'):
                for i in range(self.end_stop_list.count()):
                    item = self.end_stop_list.item(i)
                    if item and item.isSelected():
                        sid = item.data(Qt.UserRole)
                        if sid:
                            end_stop_ids.append(str(sid))
                            end_stop_names.append(item.text())
            # store first selected end stop (single-select expected)
            if end_stop_ids:
                task_data['task_details']['end_stop_id'] = end_stop_ids[0]
                task_data['task_details']['end_stop_name'] = end_stop_names[0]
            else:
                task_data['task_details']['end_stop_id'] = ''
                task_data['task_details']['end_stop_name'] = ''
            
            # Capture Charging Stops
            charging_stops = []
            charging_stop_names = []
            if hasattr(self, 'charging_stops_list'):
                for i in range(self.charging_stops_list.count()):
                    item = self.charging_stops_list.item(i)
                    if item and item.isSelected():
                        stop_id = item.data(Qt.UserRole)
                        if stop_id:
                            charging_stops.append(str(stop_id))
                            charging_stop_names.append(item.text())
            task_data['task_details']['charging_stops'] = charging_stops
            task_data['task_details']['charging_stop_names'] = charging_stop_names
        
        elif task_type == 'charging':
            # Add charging-specific data
            if hasattr(self, 'charging_map_combo'):
                map_id = self.charging_map_combo.currentData() or ''
                task_data['map_id'] = map_id
                task_data['task_details']['charging_map_id'] = map_id
                task_data['task_details']['charging_map_name'] = self.charging_map_combo.currentText() or ''
            if hasattr(self, 'charging_station_combo'):
                station_zone = self.charging_station_combo.currentData() or ''
                task_data['zone_ids'] = str(station_zone)
                task_data['task_details']['charging_station'] = station_zone
                
        elif task_type == 'storing':
            # Add storing-specific data
            if hasattr(self, 'storing_map_combo'):
                map_id = self.storing_map_combo.currentData() or ''
                task_data['map_id'] = map_id
                task_data['task_details']['storing_map_id'] = map_id
                task_data['task_details']['storing_map_name'] = self.storing_map_combo.currentText() or ''
            # Handle from and to zones for storing
            if hasattr(self, 'storing_from_zone_combo') and hasattr(self, 'storing_to_zone_combo'):
                from_zone = self.storing_from_zone_combo.currentData() or ''
                to_zone = self.storing_to_zone_combo.currentData() or ''
                
                # Find all zones in the path
                zones = self.csv_handler.read_csv('zones')
                selected_map_id = self.storing_map_combo.currentData()
                
                # Get the complete path and all zone IDs
                zone_path, zone_ids = self.find_path_between_zones(
                    selected_map_id, from_zone, to_zone, zones
                )
                
                if zone_ids:
                    task_data['task_details']['from_zone'] = from_zone
                    task_data['task_details']['to_zone'] = to_zone
                    task_data['task_details']['zone_path'] = zone_path
                    task_data['task_details']['pickup_zone_ids'] = zone_ids
                    task_data['task_details']['pickup_zone_name'] = ' → '.join(zone_path)
            
            # Capture selected check stops
            check_stops = []
            check_stop_names = []
            if hasattr(self, 'storing_check_stop_list'):
                for i in range(self.storing_check_stop_list.count()):
                    item = self.storing_check_stop_list.item(i)
                    if item and item.isSelected():
                        stop_id = item.data(Qt.UserRole)
                        if stop_id:
                            check_stops.append(str(stop_id))
                            check_stop_names.append(item.text())
            task_data['task_details']['check_stops'] = check_stops
            task_data['task_details']['check_stop_names'] = check_stop_names

            # Capture selected drop stops
            drop_stops = []
            drop_stop_names = []
            if hasattr(self, 'storing_drop_stop_list'):
                for i in range(self.storing_drop_stop_list.count()):
                    item = self.storing_drop_stop_list.item(i)
                    if item and item.isSelected():
                        stop_id = item.data(Qt.UserRole)
                        if stop_id:
                            drop_stops.append(str(stop_id))
                            drop_stop_names.append(item.text())
            task_data['task_details']['drop_stops'] = drop_stops
            task_data['task_details']['drop_stop_names'] = drop_stop_names

            # Combine all stops for stop_ids field
            all_stops = check_stops + drop_stops
            task_data['stop_ids'] = ','.join(all_stops) if all_stops else ''

            # Capture End Zone
            end_zone_id = self.storing_end_zone_combo.currentData() if hasattr(self, 'storing_end_zone_combo') else ''
            end_zone_name = self.storing_end_zone_combo.currentText() if hasattr(self, 'storing_end_zone_combo') else ''
            if end_zone_id:
                task_data['zone_ids'] = str(end_zone_id)
                task_data['task_details']['end_zone'] = str(end_zone_id)
            if end_zone_name:
                task_data['task_details']['end_zone_name'] = end_zone_name
        
        # Convert task_details to JSON string for storage
        import json
        task_data['task_details'] = json.dumps(task_data['task_details'])
        return task_data


    def save_task(self, task_data):
        """Save task to CSV or API"""
        if self.save_task_data(task_data):
            QMessageBox.information(
                self, "Success",
                f"Task '{task_data['task_name']}' created successfully!"
            )

            self.task_created.emit(task_data)
            self.clear_form()
            self.update_task_stats()

            # Switch to first tab after successful creation
            self.tab_widget.setCurrentIndex(0)

    def save_task_data(self, task_data):
        """Save task data (helper method)"""
        try:
            # Validate the data first
            validation_result = self.csv_handler.validate_csv_data('tasks', task_data)

            if not validation_result['valid']:
                error_msg = '\n'.join(validation_result['errors'])
                QMessageBox.critical(self, "Validation Error", f"Cannot create task:\n{error_msg}")
                return False

            # Use validated data
            task_data = validation_result['data']

            # Try API first
            if self.api_client.is_authenticated():
                response = self.tasks_api.create_task(task_data)
                if 'error' not in response:
                    # Update per-device task CSV on success (for all assigned devices)
                    try:
                        ids_str = task_data.get('assigned_device_ids') or ''
                        ids = [s for s in str(ids_str).split(',') if str(s).strip()]
                        if not ids:
                            # fallback to single field
                            single = task_data.get('assigned_device_id')
                            ids = [single] if single else []
                        for dev in ids:
                            self.device_data_handler.update_device_task_pending_by_task(dev, task_data.get('task_id'))
                    except Exception as e:
                        self.logger.warning(f"Could not update device task CSV after API create: {e}")
                    return True
                else:
                    self.logger.warning(f"API failed: {response['error']}, falling back to CSV")

            # Fallback to CSV
            if 'id' not in task_data or not task_data['id']:
                task_data['id'] = self.csv_handler.get_next_id('tasks')

            if self.csv_handler.append_to_csv('tasks', task_data):
                # Update per-device task CSV on CSV fallback success (for all assigned devices)
                try:
                    ids_str = task_data.get('assigned_device_ids') or ''
                    ids = [s for s in str(ids_str).split(',') if str(s).strip()]
                    if not ids:
                        single = task_data.get('assigned_device_id')
                        ids = [single] if single else []
                    for dev in ids:
                        self.device_data_handler.update_device_task_pending_by_task(dev, task_data.get('task_id'))
                except Exception as e:
                    self.logger.warning(f"Could not update device task CSV after local save: {e}")
                self.logger.info(f"Successfully created task: {task_data.get('task_id', task_data.get('id'))}")
                return True
            else:
                raise Exception("Failed to save to CSV")

        except Exception as e:
            self.logger.error(f"Error saving task: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save task: {e}")
            return False

    def refresh_data(self):
        """Refresh data"""
        self.load_data()

    def populate_pickup_maps(self):
        """Populate pickup maps dropdown with existing maps"""
        self.pickup_map_combo.clear()
        self.pickup_map_combo.addItem("Select Pickup Map", "")
        
        # Load maps using the CSV handler
        try:
            maps = self.csv_handler.read_csv('maps')
            for map_data in maps:
                map_id = map_data.get('id', '')
                map_name = map_data.get('name', map_id)
                if map_id:
                    self.pickup_map_combo.addItem(map_name, map_id)
            
            # Connect map selection to zone population if not already connected
            try:
                self.pickup_map_combo.currentIndexChanged.disconnect(self.on_map_selection_changed)
            except TypeError:
                # Signal was not connected, that's fine
                pass
            self.pickup_map_combo.currentIndexChanged.connect(self.on_map_selection_changed)
        except Exception as e:
            self.logger.error(f"Error loading maps: {e}")

    def check_devices_availability(self, device_ids):
        """Return True if none of the given device ids are running another task.
        Considers both single 'assigned_device_id' and multi 'assigned_device_ids' fields.
        """
        if not device_ids:
            return True
        tasks = self.csv_handler.read_csv('tasks')
        busy = set()
        dev_set = {str(d) for d in device_ids}
        for t in tasks:
            if str(t.get('status','')).lower() != 'running':
                continue
            sid = str(t.get('assigned_device_id') or '').strip()
            if sid and sid in dev_set:
                busy.add(sid)
                continue
            mids = [s.strip() for s in str(t.get('assigned_device_ids') or '').split(',') if s.strip()]
            for m in mids:
                if m in dev_set:
                    busy.add(m)
        return len(busy) == 0

    def on_map_selection_changed(self, index):
        """Handle pickup map selection change and populate Pick Up Stops, Check Stops, Drop Stops, End Stop, and Charging Stops."""
        # Clear existing stops and end stop
        self.pickup_stop_list.clear()
        self.check_stop_list.clear()
        self.drop_stop_list.clear()
        self.charging_stops_list.clear()
        if hasattr(self, 'end_stop_list'):
            self.end_stop_list.clear()
            self.end_stop_list.setEnabled(False)
        
        # Disable all stop lists initially
        self.pickup_stop_list.setEnabled(False)
        self.check_stop_list.setEnabled(False)
        self.drop_stop_list.setEnabled(False)
        self.charging_stops_list.setEnabled(False)

        # Reset distance calculations
        self.current_map_distance = 0
        self.required_distance = 0

        # Disable device list until prerequisites are complete
        if hasattr(self, 'device_list') and self.device_list is not None:
            self.device_list.setEnabled(False)
            self.device_list.clear()

        if index > 0:  # A valid map is selected
            selected_map_id = self.pickup_map_combo.currentData()

            try:
                # Enable all stop lists (they will be populated by stop_function)
                self.pickup_stop_list.setEnabled(True)
                self.check_stop_list.setEnabled(True)
                self.drop_stop_list.setEnabled(True)
                self.charging_stops_list.setEnabled(True)

                stops = self.csv_handler.read_csv('stops')
                racks = self.csv_handler.read_csv('racks')
                maps = self.csv_handler.read_csv('maps')
                map_name_lookup = {}
                for m in maps:
                    mid = str(m.get('id', '')).strip()
                    if not mid:
                        continue
                    map_name_lookup[mid] = (m.get('name') or '').strip()
                current_map_name = map_name_lookup.get(str(selected_map_id), '')

                racks_by_stop = {}
                if current_map_name:
                    for r in racks:
                        r_map = (r.get('map_name') or '').strip()
                        if r_map != current_map_name:
                            continue
                        sid = (r.get('stop_id') or '').strip()
                        if not sid:
                            continue
                        racks_by_stop.setdefault(sid, []).append(r)

                # Populate stops by stop_function and end stops
                added_pickup, added_check, added_drop, added_charging, added_end = set(), set(), set(), set(), set()
                for stop_data in stops:
                    if str(stop_data.get('map_id', '')) != str(selected_map_id):
                        continue
                    stop_id = str(stop_data.get('stop_id', '')).strip()
                    if not stop_id:
                        continue
                    stop_name = stop_data.get('name', stop_id)
                    sf = str(stop_data.get('stop_function') or 'pickup').strip().lower()
                    
                    # Create item for lists
                    display_text = f"{stop_name} ({stop_id})"
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.UserRole, stop_id)
                    
                    if sf == 'pickup':
                        if stop_id in added_pickup:
                            continue
                        self.pickup_stop_list.addItem(item)
                        added_pickup.add(stop_id)
                    elif sf == 'check':
                        if stop_id in added_check:
                            continue
                        item_copy = QListWidgetItem(display_text)
                        item_copy.setData(Qt.UserRole, stop_id)
                        self.check_stop_list.addItem(item_copy)
                        added_check.add(stop_id)
                    elif sf == 'drop':
                        if stop_id in added_drop:
                            continue
                        item_copy = QListWidgetItem(display_text)
                        item_copy.setData(Qt.UserRole, stop_id)
                        self.drop_stop_list.addItem(item_copy)
                        added_drop.add(stop_id)
                    elif sf == 'charging':
                        if stop_id in added_charging:
                            continue
                        item_copy = QListWidgetItem(display_text)
                        item_copy.setData(Qt.UserRole, stop_id)
                        self.charging_stops_list.addItem(item_copy)
                        added_charging.add(stop_id)
                    elif sf == 'end':
                        if stop_id in added_end:
                            continue
                        item_copy = QListWidgetItem(display_text)
                        item_copy.setData(Qt.UserRole, stop_id)
                        self.end_stop_list.addItem(item_copy)
                        added_end.add(stop_id)

                # If there are no check/drop/charging stops defined, keep those lists disabled
                if self.check_stop_list.count() == 0:
                    self.check_stop_list.setEnabled(False)
                if self.drop_stop_list.count() == 0:
                    self.drop_stop_list.setEnabled(False)
                if self.charging_stops_list.count() == 0:
                    self.charging_stops_list.setEnabled(False)

                # Enable end stop list only if it has entries
                if self.end_stop_list.count() > 0:
                    self.end_stop_list.setEnabled(True)
                
                # Ensure pickup stop selection handler is connected
                try:
                    self.pickup_stop_list.itemSelectionChanged.disconnect()
                except Exception:
                    pass
                self.pickup_stop_list.itemSelectionChanged.connect(self.on_pickup_stop_selection_changed)
            except Exception as e:
                self.logger.error(f"Error loading stops for pickup map: {e}")

        # Check form completion after map selection
        self.check_form_completion()
    
    def on_pickup_stop_selection_changed(self):
        """Handle pickup stop selection - enable End Zone and refresh devices."""
        selected_pickup_stops = self.get_selected_stops_from_list(self.pickup_stop_list) or []
        self.logger.info(f"Pickup stops selected: {selected_pickup_stops}")
        
        if selected_pickup_stops:
            # Enable end stop list if present
            if hasattr(self, 'end_stop_list') and self.end_stop_list.count() > 0:
                self.end_stop_list.setEnabled(True)
        else:
            # Disable end stop list if no pickup stops selected
            if hasattr(self, 'end_stop_list'):
                self.end_stop_list.setEnabled(False)
        
        
        self.check_form_completion()
    
    def on_check_stop_selection_changed(self):
        """Handle check stop selection change (no list filtering needed when stop_function is defined)."""
        self.check_form_completion()
    
    def on_drop_stop_selection_changed(self):
        """Handle drop stop selection - enable end zone"""
        selected_pickup_stops = self.get_selected_stops_from_list(self.pickup_stop_list) or []
        selected_drop_stops = self.get_selected_stops_from_list(self.drop_stop_list) or []
        
        # Enable end zone if pickup stops are selected (drop stops are optional)
        if selected_pickup_stops:
            # Enable end stop list if present
            if hasattr(self, 'end_stop_list') and self.end_stop_list.count() > 0:
                self.end_stop_list.setEnabled(True)
        else:
            if hasattr(self, 'end_stop_list'):
                self.end_stop_list.setEnabled(False)
        
        self.check_form_completion()
    
    def populate_unselected_stops(self, target_list, exclude_list1, exclude_list2=None):
        """Populate target list with stops from current map, excluding stops in exclude lists"""
        if exclude_list2 is None:
            exclude_list2 = []
        
        target_list.clear()
        exclude_set = set(str(s) for s in (exclude_list1 or []) + (exclude_list2 or []))
        
        map_id = self.pickup_map_combo.currentData()
        if not map_id:
            self.logger.warning("No map_id found when populating unselected stops")
            return
        
        try:
            stops = self.csv_handler.read_csv('stops')
            added_stops = set()
            total_stops = 0
            excluded_count = 0
            
            for stop_data in stops:
                if str(stop_data.get('map_id', '')) != str(map_id):
                    continue
                total_stops += 1
                stop_id = str(stop_data.get('stop_id', '')).strip()
                if not stop_id or stop_id in added_stops:
                    continue
                if stop_id in exclude_set:
                    excluded_count += 1
                    continue
                stop_name = stop_data.get('name', stop_id)
                item = QListWidgetItem(f"{stop_name} ({stop_id})")
                item.setData(Qt.UserRole, stop_id)
                target_list.addItem(item)
                added_stops.add(stop_id)
            
            self.logger.info(f"Populated {len(added_stops)} stops (excluded {excluded_count}, total {total_stops} for map {map_id})")
        except Exception as e:
            self.logger.error(f"Error populating unselected stops: {e}", exc_info=True)
    
    def on_storing_check_stop_selection_changed(self):
        """Handle storing check stop selection - enable drop stops"""
        selected_check_stops = self.get_selected_stops_from_list(self.storing_check_stop_list) or []
        
        if selected_check_stops:
            self.storing_drop_stop_list.setEnabled(True)
            # Populate drop stops with stops not selected in check
            self.populate_unselected_stops_for_storing(self.storing_drop_stop_list, selected_check_stops, [])
        else:
            self.storing_drop_stop_list.setEnabled(False)
            self.storing_drop_stop_list.clear()
            self.storing_end_zone_combo.setEnabled(False)
        
        self.check_form_completion()
    
    def on_storing_drop_stop_selection_changed(self):
        """Handle storing drop stop selection - enable end zone"""
        selected_drop_stops = self.get_selected_stops_from_list(self.storing_drop_stop_list) or []
        
        if selected_drop_stops:
            self.storing_end_zone_combo.setEnabled(True)
        else:
            self.storing_end_zone_combo.setEnabled(False)
        
        self.check_form_completion()
    
    def populate_unselected_stops_for_storing(self, target_list, exclude_list1, exclude_list2=None):
        """Populate target list with stops for storing, excluding stops in exclude lists"""
        if exclude_list2 is None:
            exclude_list2 = []
        
        target_list.clear()
        exclude_set = set(str(s) for s in exclude_list1 + exclude_list2)
        
        map_id = self.storing_map_combo.currentData()
        if not map_id:
            return
        
        try:
            zones = self.csv_handler.read_csv('zones')
            selected_map_id = self.storing_map_combo.currentData()
            from_zone = self.storing_from_zone_combo.currentData()
            to_zone = self.storing_to_zone_combo.currentData()
            
            if not from_zone or not to_zone:
                return
            
            zone_path, zone_ids = self.find_path_between_zones(selected_map_id, from_zone, to_zone, zones)
            
            if zone_ids:
                stops = self.csv_handler.read_csv('stops')
                added_stops = set()
                for zone_id in zone_ids:
                    for stop_data in stops:
                        zone_connection_id = stop_data.get('zone_connection_id', '')
                        stop_id = stop_data.get('stop_id', '')
                        
                        if (str(zone_connection_id) == str(zone_id) and 
                            stop_id and 
                            stop_id not in added_stops and
                            stop_id not in exclude_set):
                            stop_name = stop_data.get('name', stop_id)
                            item = QListWidgetItem(f"{stop_name} ({stop_id})")
                            item.setData(Qt.UserRole, stop_id)
                            target_list.addItem(item)
                            added_stops.add(stop_id)
        except Exception as e:
            self.logger.error(f"Error populating unselected stops for storing: {e}")
    
    def on_stop_selection_changed(self):
        """
        Handle stop selection changes - recalculate distance and refresh devices.
        Called when user selects/deselects stops in the drop_stop_list.
        """
        try:
            # Get current task context
            task_type = self.task_type_combo.currentData()
            
            if task_type == 'picking':
                # New picking semantics: just record selection and reload devices
                selected_stops = self.get_selected_stops_from_list(self.drop_stop_list)
                stop_count = len(selected_stops) if selected_stops else 0
                self.logger.info(f"Picking stop selection changed: {stop_count} stops selected")

                # Required distance for picking is approximated elsewhere; we
                # don't recompute it per selection now, but we do refresh
                # device suggestions when possible.
                if hasattr(self, 'device_list') and self.device_list.isEnabled():
                    self.load_devices()
                return

            elif task_type == 'storing':
                map_id = self.storing_map_combo.currentData()
                from_zone = self.storing_from_zone_combo.currentData()
                to_zone = self.storing_to_zone_combo.currentData()
                stop_list = self.pickup_stop_list
            else:
                return  # Auditing doesn't have selectable stops
        
            if not map_id or not from_zone or not to_zone:
                return
        
            # Get selected stops
            selected_stops = self.get_selected_stops_from_list(stop_list)
        
            # Recalculate distance with selected stops
            include_all = (selected_stops is None or len(selected_stops) == 0)
            self.required_distance = self.distance_calculator.calculate_path_distance(
                map_id, from_zone, to_zone,
                selected_stops=selected_stops,
                include_all_stops=include_all
            )
        
            stop_count = len(selected_stops) if selected_stops else "all"
            self.logger.info(f"Distance recalculated with {stop_count} stops: {self.required_distance}mm")
        
            # Reload devices with new distance calculation
            if hasattr(self, 'device_list') and self.device_list.isEnabled():
                self.load_devices()
        
        except Exception as e:
            self.logger.error(f"Error handling stop selection change: {e}")


    def populate_pickup_maps_for_storing(self):
        """Populate pickup maps dropdown with existing maps for storing section"""
        self.storing_map_combo.clear()
        self.storing_map_combo.addItem("Select Storing Map", "")
        
        # Load maps using the CSV handler
        try:
            maps = self.csv_handler.read_csv('maps')
            for map_data in maps:
                map_id = map_data.get('id', '')
                map_name = map_data.get('name', map_id)
                if map_id:
                    self.storing_map_combo.addItem(map_name, map_id)
            
            # Connect map selection to zone population if not already connected
            try:
                self.storing_map_combo.currentIndexChanged.disconnect(self.on_storing_map_selected)
            except TypeError:
                # Signal was not connected, that's fine
                pass
            self.storing_map_combo.currentIndexChanged.connect(self.on_storing_map_selected)
        except Exception as e:
            self.logger.error(f"Error loading maps for storing section: {e}")

    def on_storing_map_selected(self, index):
        """Handle map selection change and populate zones for storing section"""
        # Clear and disable zone dropdowns
        self.storing_from_zone_combo.clear()
        self.storing_to_zone_combo.clear()
        self.storing_from_zone_combo.addItem("Select From Zone", "")
        self.storing_to_zone_combo.addItem("Select To Zone", "")
        self.storing_from_zone_combo.setEnabled(False)
        self.storing_to_zone_combo.setEnabled(False)
        
        # Disable device list
        if hasattr(self, 'device_list') and self.device_list is not None:
            self.device_list.setEnabled(False)
            self.device_list.clear()

        if index > 0:  # If a map is selected (not the default "Select" option)
            selected_map_id = self.storing_map_combo.currentData()

            # Enable from_zone_combo
            self.storing_from_zone_combo.setEnabled(True)

            # Load zones for the selected map using the CSV handler
            try:
                zones = self.csv_handler.read_csv('zones')
                # Get unique zone names
                unique_zones = set()
                for zone_data in zones:
                    map_id = zone_data.get('map_id', '')
                    if str(map_id) == str(selected_map_id):
                        from_zone = zone_data.get('from_zone', '')
                        to_zone = zone_data.get('to_zone', '')
                        if from_zone:
                            unique_zones.add(from_zone)
                        if to_zone:
                            unique_zones.add(to_zone)

                # Add unique zones to both dropdowns
                for zone in sorted(unique_zones):
                    self.storing_from_zone_combo.addItem(zone, zone)
                    self.storing_to_zone_combo.addItem(zone, zone)
            except Exception as e:
                self.logger.error(f"Error loading zones: {e}")

            # Connect zone selections to stop population if not already connected
            try:
                self.storing_from_zone_combo.currentIndexChanged.disconnect(self.on_storing_zone_selected)
                self.storing_to_zone_combo.currentIndexChanged.disconnect(self.on_storing_zone_selected)
            except TypeError:
                # Signal was not connected, that's fine
                pass
            except Exception as e:
                self.logger.error(f"Error disconnecting signal: {e}")

            try:
                self.storing_from_zone_combo.currentIndexChanged.connect(self.on_storing_zone_selected)
                self.storing_to_zone_combo.currentIndexChanged.connect(self.on_storing_zone_selected)
            except Exception as e:
                self.logger.error(f"Error connecting signal: {e}")
                
            # Clear the stops list when zones change
            self.pickup_stop_list.clear()
        
        # Check form completion after map selection
        self.check_form_completion()

    def find_path_between_zones(self, map_id, start_zone, end_zone, zones_data):
        """Find all zones in the path between start_zone and end_zone"""
        # Build a graph of zone connections
        graph = {}
        for zone in zones_data:
            if str(zone.get('map_id', '')) == str(map_id):
                from_zone = zone.get('from_zone', '')
                to_zone = zone.get('to_zone', '')
                if from_zone:
                    if from_zone not in graph:
                        graph[from_zone] = {}
                    graph[from_zone][to_zone] = zone.get('id', '')

        # Use BFS to find the path
        queue = [(start_zone, [start_zone], [])]
        visited = {start_zone}
        
        while queue:
            (current, path, zone_ids) = queue.pop(0)
            
            if current == end_zone:
                return path, zone_ids
                
            if current in graph:
                for next_zone, zone_id in graph[current].items():
                    if next_zone not in visited:
                        visited.add(next_zone)
                        queue.append((next_zone, path + [next_zone], zone_ids + [zone_id]))
        
        return [], []  # No path found

    def on_storing_zone_selected(self, index):
        """Handle zone selection change and populate check stops for storing section"""
        self.storing_check_stop_list.clear()
        self.storing_drop_stop_list.clear()
        
        # Disable all stop lists initially
        self.storing_check_stop_list.setEnabled(False)
        self.storing_drop_stop_list.setEnabled(False)
        self.storing_end_zone_combo.setEnabled(False)
        
        # Enable to_zone_combo when from_zone is selected
        if hasattr(self, 'storing_from_zone_combo') and self.storing_from_zone_combo.currentIndex() > 0:
            self.storing_to_zone_combo.setEnabled(True)
        
        # Disable device list if zones change
        if hasattr(self, 'device_list') and self.device_list is not None:
            self.device_list.setEnabled(False)
            self.device_list.clear()
        
        if index > 0:  # If a zone is selected (not the default "Select" option)
            from_zone = self.storing_from_zone_combo.currentData()
            to_zone = self.storing_to_zone_combo.currentData()
            
            if not from_zone:
                # Check form completion even if from_zone not selected
                self.check_form_completion()
                return
            
            # If from_zone is selected but to_zone is not, don't proceed with stops
            if not to_zone or self.storing_to_zone_combo.currentIndex() == 0:
                # Reset distance when zones incomplete
                self.required_distance = 0
                # Check form completion to update UI state
                self.check_form_completion()
                return
            
            # Calculate path distance when both zones are selected
            selected_map_id = self.storing_map_combo.currentData()
            if selected_map_id:
                self.required_distance = self.distance_calculator.calculate_path_distance(
                    selected_map_id, from_zone, to_zone,
                    selected_stops=None,
                    include_all_stops=False
                )
                self.logger.info(f"Path distance calculated: {self.required_distance}mm for {from_zone} -> {to_zone}")
                
            try:
                # Load zones and find the path between selected zones
                zones = self.csv_handler.read_csv('zones')
                selected_map_id = self.storing_map_combo.currentData()
                
                zone_path, zone_ids = self.find_path_between_zones(
                    selected_map_id, from_zone, to_zone, zones
                )
                
                if zone_ids:
                    # Populate End Zone combo with all zones from zones.csv for this map
                    unique_zones = set()
                    for zone_data in zones:
                        map_id = zone_data.get('map_id', '')
                        if str(map_id) == str(selected_map_id):
                            fz = zone_data.get('from_zone', '')
                            tz = zone_data.get('to_zone', '')
                            if fz:
                                unique_zones.add(str(fz))
                            if tz:
                                unique_zones.add(str(tz))
                    
                    def _zone_key(z):
                        s = str(z)
                        return (0, int(s)) if s.isdigit() else (1, s)
                    
                    self.storing_end_zone_combo.clear()
                    self.storing_end_zone_combo.addItem("Select End Zone", "")
                    for zone in sorted(unique_zones, key=_zone_key):
                        self.storing_end_zone_combo.addItem(zone, zone)
                    
                    # Enable check stops and populate with all stops in path
                    self.storing_check_stop_list.setEnabled(True)
                    # Load stops for all zones in the path
                    stops = self.csv_handler.read_csv('stops')
                    added_stops = set()  # To prevent duplicate stops
                    
                    for zone_id in zone_ids:
                        for stop_data in stops:
                            zone_connection_id = stop_data.get('zone_connection_id', '')
                            stop_id = stop_data.get('stop_id', '')
                            
                            if (str(zone_connection_id) == str(zone_id) and 
                                stop_id and 
                                stop_id not in added_stops):
                                    
                                stop_name = stop_data.get('name', stop_id)
                                item = QListWidgetItem(f"{stop_name} ({stop_id})")
                                item.setData(Qt.UserRole, stop_id)
                                self.storing_check_stop_list.addItem(item)
                                added_stops.add(stop_id)
                        
                    # Log the path found
                    self.logger.info(f"Found path between zones: {' → '.join(zone_path)}")
                else:
                    self.logger.warning(f"No path found between zones {from_zone} and {to_zone}")
                    
            except Exception as e:
                self.logger.error(f"Error loading stops for storing section: {e}")
        
        # Check form completion after zone selection
        self.check_form_completion()
    

    def populate_pickup_maps_for_auditing(self):
        """Populate pickup maps dropdown with existing maps for auditing section"""
        self.auditing_map_combo.clear()
        self.auditing_map_combo.addItem("Select Auditing Map", "")
    
        # Load maps using the CSV handler
        try:
            maps = self.csv_handler.read_csv('maps')
            for map_data in maps:
                map_id = map_data.get('id', '')
                map_name = map_data.get('name', map_id)
                if map_id:
                    self.auditing_map_combo.addItem(map_name, map_id)
        
            # Connect map selection to distance calculation
            try:
                self.auditing_map_combo.currentIndexChanged.disconnect(self.on_auditing_map_selected)
            except TypeError:
                pass
            self.auditing_map_combo.currentIndexChanged.connect(self.on_auditing_map_selected)
        except Exception as e:
            self.logger.error(f"Error loading maps for auditing section: {e}")
    def on_auditing_map_selected(self, index):
        """Handle auditing map selection and populate end zone"""
        # Disable device list when map changes
        if hasattr(self, 'device_list') and self.device_list is not None:
            self.device_list.setEnabled(False)
            self.device_list.clear()
    
        if index > 0:
            selected_map_id = self.auditing_map_combo.currentData()
            # Calculate map distance using DistanceCalculator
            self.current_map_distance = self.distance_calculator.calculate_map_distance(selected_map_id)
            self.required_distance = self.current_map_distance
            self.logger.info(f"Auditing map distance calculated: {self.current_map_distance}mm")
            
            # Populate End Zone combo with all zones from zones.csv for this map
            try:
                zones = self.csv_handler.read_csv('zones')
                unique_zones = set()
                for zone_data in zones:
                    map_id = zone_data.get('map_id', '')
                    if str(map_id) == str(selected_map_id):
                        from_zone = zone_data.get('from_zone', '')
                        to_zone = zone_data.get('to_zone', '')
                        if from_zone:
                            unique_zones.add(str(from_zone))
                        if to_zone:
                            unique_zones.add(str(to_zone))
                
                def _zone_key(z):
                    s = str(z)
                    return (0, int(s)) if s.isdigit() else (1, s)
                
                self.auditing_end_zone_combo.clear()
                self.auditing_end_zone_combo.addItem("Select End Zone", "")
                for zone in sorted(unique_zones, key=_zone_key):
                    self.auditing_end_zone_combo.addItem(zone, zone)
                self.auditing_end_zone_combo.setEnabled(True)
            except Exception as e:
                self.logger.error(f"Error loading zones for auditing: {e}")
        else:
            self.current_map_distance = 0
            self.required_distance = 0
            self.auditing_end_zone_combo.setEnabled(False)
    
        # Check form completion to enable device selection
        self.check_form_completion()

    def upload_csv_file(self):
        """Handle CSV file upload"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Upload CSV File",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if file_path:
            # Store the file path for later use
            self.uploaded_csv_file = file_path
            # Update the appropriate label to show the selected file name
            file_name = os.path.basename(file_path)
            
            # Determine which section is currently visible to update the correct label
            if (hasattr(self, 'picking_section') and self.picking_section.isVisible() and
                hasattr(self, 'uploaded_file_label')):
                self.uploaded_file_label.setText(f"File: {file_name}")
                self.uploaded_file_label.setStyleSheet("color: #3B82F6; font-size: 11px; padding: 5px;")
            elif (hasattr(self, 'storing_section') and self.storing_section.isVisible() and
                  hasattr(self, 'storing_uploaded_file_label')):
                self.storing_uploaded_file_label.setText(f"File: {file_name}")
                self.storing_uploaded_file_label.setStyleSheet("color: #3B82F6; font-size: 11px; padding: 5px;")
            elif (hasattr(self, 'auditing_section') and self.auditing_section.isVisible() and
                  hasattr(self, 'auditing_uploaded_file_label')):
                self.auditing_uploaded_file_label.setText(f"File: {file_name}")
                self.auditing_uploaded_file_label.setStyleSheet("color: #3B82F6; font-size: 11px; padding: 5px;")
