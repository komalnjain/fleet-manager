from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QComboBox, QMessageBox, QFrame, QSplitter,
                             QTabWidget, QTabBar, QScrollArea, QSpinBox, QDoubleSpinBox,
                             QLineEdit, QListWidget, QListWidgetItem, QCheckBox,
                             QFormLayout, QGroupBox, QGridLayout, QTextEdit,
                             QTableWidget, QAbstractItemView, QFileDialog,
                             QTableWidgetItem, QHeaderView, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPointF, QRectF, QDateTime
from PyQt5.QtGui import QFont, QPainter, QPen, QBrush, QColor
from datetime import datetime
import csv
import json

from .map_viewer import MapViewerWidget
from ui.common.table_widget import DataTableWidget
from api.client import APIClient
from api.maps import MapsAPI
from ui.common.base_dialog import BaseDialog
from data_manager.csv_handler import CSVHandler
from data_manager.sync_manager import SyncManager
from utils.logger import setup_logger
from ui.common.input_validators import apply_no_special_chars_validator
from config.settings import DATA_DIR


class MapManagementWidget(QWidget):
    map_updated = pyqtSignal()

    def __init__(self, api_client: APIClient, csv_handler: CSVHandler):
        super().__init__()
        self.api_client = api_client
        self.csv_handler = csv_handler
        self.maps_api = MapsAPI(api_client)
        self.sync_manager = SyncManager(api_client, csv_handler)
        self.logger = setup_logger('map_management')

        # Data storage
        self.current_maps = []
        self.current_zones = []
        self.current_stops = []
        self.current_stop_groups = []
        self.selected_map_id = None
        self.current_zone_alignment = []  # rows from zone_alignment.csv for selected map
        
        # Edit mode state
        self.zone_edit_mode = False
        self.editing_zone_id = None
        self.stop_edit_mode = False
        self.editing_stop_id = None
        
        # Ensure widget is visible
        self.setVisible(True)

        self.setup_ui()
        self.refresh_data()
        
        # Initialize tab accessibility without switching tabs
        self.update_tab_accessibility()
        
        # Ensure we start on the overview tab (index 0) during initialization
        self.tab_widget.setCurrentIndex(0)
        
        # Log initialization
        self.logger.info("Map Management widget initialized")

    def setup_ui(self):
        """Setup map management UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Main content
        self.create_main_content(layout)

        # Action buttons
        self.create_action_buttons(layout)

    def create_header(self, parent_layout):
        """Create header with map selection"""
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 15px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)

        # Title
        title = QLabel("Map Management")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setStyleSheet("color: #ffffff;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Map selection
        map_label = QLabel("Current Map:")
        map_label.setStyleSheet("color: #cccccc; font-weight: bold;")
        header_layout.addWidget(map_label)

        self.map_selector = QComboBox()
        self.map_selector.addItem("No Map Selected", "")
        self.map_selector.currentTextChanged.connect(self.on_map_selected)
        self.apply_combo_style(self.map_selector)
        header_layout.addWidget(self.map_selector)

        # New map button
        new_map_btn = QPushButton("➕ Create New Map")
        new_map_btn.clicked.connect(self.create_new_map)
        new_map_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                border: none;
                padding: 10px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        header_layout.addWidget(new_map_btn)

        parent_layout.addWidget(header_frame)

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
        
        # Ensure tab widget is visible and tabs are at the top
        self.tab_widget.setVisible(True)
        self.tab_widget.setTabPosition(QTabWidget.North)

        # We'll add a custom top row with tabs (left) and controls (right)

        # Tab 1: Map Overview
        self.overview_tab = self.create_overview_tab()
        self.tab_widget.addTab(self.overview_tab, "🗺️ Map Overview")

        # Tab 2: Zone Management
        self.zones_tab = self.create_zones_tab()
        self.tab_widget.addTab(self.zones_tab, "🏗️ Zone Management")

        # Tab 3: Stop Management
        self.stops_tab = self.create_stops_tab()
        self.tab_widget.addTab(self.stops_tab, "📍 Stop Management")

        # Tab 4: Rack Configuration (new)
        self.rack_config_tab = self.create_rack_config_tab()
        self.tab_widget.addTab(self.rack_config_tab, "🗄️ Rack Configuration")

        # Tab 5: Map Settings
        self.settings_tab = self.create_settings_tab()
        self.tab_widget.addTab(self.settings_tab, "⚙️ Map Settings")

        # Tab 6: Zone Alignment setting
        self.zone_alignment_tab = self.create_zone_alignment_tab()
        self.tab_widget.addTab(self.zone_alignment_tab, "🎯 Zone Alignment setting")

        # Tab 7: Charging Station (new)
        self.charging_station_tab = self.create_charging_station_tab()
        self.tab_widget.addTab(self.charging_station_tab, "🔋 Charging Station")

        # Build a custom top row with our own QTabBar and right-aligned controls
        top_row_container = QWidget()
        top_row_layout = QHBoxLayout(top_row_container)
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(8)

        # Create custom tab bar mirroring the QTabWidget tabs
        self.custom_tab_bar = QTabBar()
        self.custom_tab_bar.setExpanding(False)
        self.custom_tab_bar.setDrawBase(False)
        self.custom_tab_bar.setElideMode(Qt.ElideRight)
        # Copy tabs
        for i in range(self.tab_widget.count()):
            self.custom_tab_bar.addTab(self.tab_widget.tabText(i))
        self.custom_tab_bar.setCurrentIndex(self.tab_widget.currentIndex())
        # Sync selection both ways
        self.custom_tab_bar.currentChanged.connect(self.tab_widget.setCurrentIndex)
        self.tab_widget.currentChanged.connect(self.custom_tab_bar.setCurrentIndex)

        # Style custom tab bar similar to original
        self.custom_tab_bar.setStyleSheet("""
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

        top_row_layout.addWidget(self.custom_tab_bar)
        top_row_layout.addStretch(1)

        # Right controls
        self.map_label = QLabel("Current Map:")
        self.map_label.setStyleSheet("color: #cccccc; font-weight: bold;")
        top_row_layout.addWidget(self.map_label)

        self.map_selector = QComboBox()
        self.map_selector.addItem("No Map Selected", "")
        self.map_selector.currentTextChanged.connect(self.on_map_selected)
        self.apply_combo_style(self.map_selector)
        self.map_selector.setMinimumWidth(160)
        self.map_selector.setMaximumWidth(260)
        top_row_layout.addWidget(self.map_selector)

        self.new_map_btn = QPushButton("➕ Create New Map")
        self.new_map_btn.clicked.connect(self.create_new_map)
        self.new_map_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                border: none;
                padding: 10px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        top_row_layout.addWidget(self.new_map_btn)

        # Hide the original tab bar and insert the custom top row above the QTabWidget
        self.tab_widget.tabBar().hide()
        parent_layout.addWidget(top_row_container)
        parent_layout.addWidget(self.tab_widget)

    def create_overview_tab(self):
        """Create map overview tab with scrollable content"""
        # Create main tab widget with explicit visibility
        tab_widget = QWidget()
        tab_widget.setVisible(True)  # Explicitly set tab visibility
        tab_widget.setSizePolicy(tab_widget.sizePolicy().Expanding, tab_widget.sizePolicy().Expanding)
        tab_widget.setAttribute(Qt.WA_StyledBackground, True)  # Enable background styling
        
        # Create scroll area to contain all content
        scroll_area = QScrollArea(tab_widget)
        scroll_area.setVisible(True)  # Explicitly set scroll area visibility
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameStyle(QFrame.NoFrame)
        scroll_area.setAttribute(Qt.WA_StyledBackground, True)  # Enable background styling for scroll area
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #404040;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #ff6b35;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #e55a2b;
            }
        """)
        
        # Create scrollable content widget
        scroll_content = QWidget()
        scroll_content.setSizePolicy(scroll_content.sizePolicy().Expanding, scroll_content.sizePolicy().Preferred)
        
        # Use horizontal layout for side-by-side arrangement
        layout = QHBoxLayout(scroll_content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Left panel - Map information and statistics
        left_panel = self.create_map_info_section()
        layout.addWidget(left_panel, 1)  # Fixed width ratio
        
        # Map info section
        #info_section = self.create_map_info_section()
        #layout.addWidget(info_section)

        # Right panel - Map viewer
        # Map viewer with explicit visibility
        self.map_viewer = MapViewerWidget(self.api_client, self.csv_handler)
        self.map_viewer.setVisible(True)  # Explicitly set visibility
        self.map_viewer.stop_selected.connect(self.on_stop_selected)
        # Set minimum size for map viewer
        self.map_viewer.setMinimumWidth(600)
        self.map_viewer.setMinimumHeight(400)  # Ensure minimum height
        # Set size policy to expand in both directions
        self.map_viewer.setSizePolicy(
            self.map_viewer.sizePolicy().Expanding,
            self.map_viewer.sizePolicy().Expanding
        )
        layout.addWidget(self.map_viewer, 2)  # Takes more space
        self.map_viewer.show()  # Force show after adding to layout
        # layout.addWidget(self.map_viewer)
        
        # Set the scroll content
        scroll_area.setWidget(scroll_content)
        
        # Layout for the main tab widget
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll_area)

        return tab_widget


    def create_rack_config_tab(self):
        """Create rack configuration tab with only Rack Configuration layout"""
        tab_widget = QWidget()
        tab_widget.setSizePolicy(tab_widget.sizePolicy().Expanding, tab_widget.sizePolicy().Expanding)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        # Rack Configuration container
        rack_container = QFrame(tab_widget)
        rack_container.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 16px;
            }
        """)
        rack_layout = QVBoxLayout(rack_container)
        rack_layout.setContentsMargins(15, 15, 15, 15)
        rack_layout.setSpacing(12)

        # Title (left)
        title_left = QLabel("Rack Configuration")
        title_left.setFont(QFont("Arial", 14, QFont.Bold))
        title_left.setStyleSheet("color: #ff6b35;")
        rack_layout.addWidget(title_left)

        # Form for Rack Configuration
        rack_form = QFormLayout()

        # Rack ID
        self.rack_id_input = QLineEdit()
        self.rack_id_input.setPlaceholderText("Enter unique Rack ID")
        self.apply_input_style(self.rack_id_input)
        self.rack_id_input.textChanged.connect(self.on_rack_inputs_changed)
        rack_form.addRow("Rack ID *:", self.rack_id_input)

        # Zone selector (for selected map)
        self.rack_zone_combo = QComboBox()
        self.apply_combo_style(self.rack_zone_combo)
        self.rack_zone_combo.addItem("Select Zone", "")
        self.rack_zone_combo.currentIndexChanged.connect(self.on_rack_zone_changed)
        rack_form.addRow("Zone:", self.rack_zone_combo)

        # Stop selector (for selected zone)
        self.rack_stop_combo = QComboBox()
        self.apply_combo_style(self.rack_stop_combo)
        self.rack_stop_combo.addItem("Select Stop", "")
        self.rack_stop_combo.currentIndexChanged.connect(self.on_rack_inputs_changed)
        rack_form.addRow("Stop:", self.rack_stop_combo)

        # Rack distance input (mm)
        self.rack_distance_input = QSpinBox()
        self.rack_distance_input.setRange(0, 1000000)
        self.rack_distance_input.setSingleStep(10)
        self.rack_distance_input.setSuffix(" mm")
        self.apply_input_style(self.rack_distance_input)
        self.rack_distance_input.valueChanged.connect(self.on_rack_inputs_changed)
        rack_form.addRow("Distance from ground:", self.rack_distance_input)

        rack_layout.addLayout(rack_form)

        # Add rack button
        self.add_rack_btn = QPushButton("➕ Add Rack")
        self.add_rack_btn.clicked.connect(self.on_add_rack_clicked)
        self.apply_button_style(self.add_rack_btn)
        self.add_rack_btn.setEnabled(False)
        rack_layout.addWidget(self.add_rack_btn)

        main_layout.addWidget(rack_container, 1)

        # Outer tab layout
        outer = QVBoxLayout(tab_widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(main_layout)

        # Populate initial combos
        self.populate_rack_zone_combo()
        self.populate_rack_stop_combo()

        return tab_widget

    def on_rack_inputs_changed(self):
        """Enable add button only when inputs are valid"""
        rack_id = self.rack_id_input.text().strip() if hasattr(self, 'rack_id_input') else ""
        zone_id = self.rack_zone_combo.currentData() if hasattr(self, 'rack_zone_combo') else None
        stop_id = self.rack_stop_combo.currentData() if hasattr(self, 'rack_stop_combo') else None
        distance_ok = hasattr(self, 'rack_distance_input') and (self.rack_distance_input.value() > 0)
        can_add = bool(rack_id) and bool(zone_id) and bool(stop_id) and distance_ok
        if hasattr(self, 'add_rack_btn'):
            self.add_rack_btn.setEnabled(can_add)

    def populate_rack_zone_combo(self):
        """Populate rack tab zone combo with zones for the selected map"""
        if not hasattr(self, 'rack_zone_combo'):
            return
        self.rack_zone_combo.blockSignals(True)
        self.rack_zone_combo.clear()
        self.rack_zone_combo.addItem("Select Zone", "")
        for zone in getattr(self, 'current_zones', []) or []:
            zone_text = f"{zone.get('from_zone', '')} → {zone.get('to_zone', '')}"
            self.rack_zone_combo.addItem(zone_text, zone.get('id'))
        self.rack_zone_combo.blockSignals(False)

    def populate_rack_stop_combo(self):
        """Populate rack tab stop combo with stops for selected zone"""
        if not hasattr(self, 'rack_stop_combo'):
            return
        self.rack_stop_combo.blockSignals(True)
        self.rack_stop_combo.clear()
        self.rack_stop_combo.addItem("Select Stop", "")
        # Get selected zone id
        zone_id = self.rack_zone_combo.currentData() if hasattr(self, 'rack_zone_combo') else None
        if zone_id:
            for stop in getattr(self, 'current_stops', []) or []:
                if str(stop.get('zone_connection_id')) == str(zone_id):
                    stop_id = stop.get('stop_id')
                    name = stop.get('name', '')
                    display = f"{name} ({stop_id})" if stop_id else name
                    self.rack_stop_combo.addItem(display, stop_id)
        self.rack_stop_combo.blockSignals(False)
        # Update add button state
        self.on_rack_inputs_changed()

    def on_rack_zone_changed(self):
        """Handle zone selection change in rack tab"""
        self.populate_rack_stop_combo()
        self.on_rack_inputs_changed()

    # SKU Location panel removed from Rack Configuration tab

    def on_add_rack_clicked(self):
        """Persist a new rack entry to racks.csv with id mapname_stopid_n"""
        try:
            if not self.selected_map_id:
                QMessageBox.warning(self, "No Map", "Please select a map first")
                return
            zone_id = self.rack_zone_combo.currentData()
            stop_id = self.rack_stop_combo.currentData()
            distance_mm = self.rack_distance_input.value()
            if not zone_id or not stop_id or distance_mm <= 0:
                QMessageBox.warning(self, "Missing Data", "Please select zone and stop, and enter a valid distance")
                return

            # Get map name
            selected_map = next((m for m in self.current_maps if str(m.get('id')) == str(self.selected_map_id)), None)
            map_name = selected_map.get('name', 'map') if selected_map else 'map'

            rack_id = self.rack_id_input.text().strip()
            if not rack_id:
                QMessageBox.warning(self, "Missing Data", "Please enter a Rack ID")
                return

            # Check for uniqueness
            existing = self.csv_handler.read_csv('racks')
            if existing and any(str(row.get('rack_id')).strip() == rack_id for row in existing):
                QMessageBox.warning(self, "Duplicate ID", f"Rack ID '{rack_id}' already exists. Please choose a unique ID.")
                return

            # Build zone display name (from_zone -> to_zone)
            zone = next((z for z in self.current_zones if str(z.get('id')) == str(zone_id)), None)
            zone_name = f"{zone.get('from_zone', '')} -> {zone.get('to_zone', '')}" if zone else ""

            # Prepare row matching required schema
            rack_row = {
                'rack_id': rack_id,
                'map_name': map_name,
                'zone_name': zone_name,
                'stop_id': stop_id,
                'rack_distance_mm': distance_mm,
            }

            if self.csv_handler.append_to_csv('racks', rack_row):
                QMessageBox.information(self, "Success", f"Rack added: {rack_id}")
                # Reset inputs
                self.rack_id_input.clear()
                self.rack_distance_input.setValue(0)
                
                # Reload map data to show the new rack on the viewer
                self.load_map_data(self.selected_map_id)
                
                # Also refresh SKU rack combo so the new rack appears immediately
                if hasattr(self, 'populate_sku_rack_combo'):
                    self.populate_sku_rack_combo()
                if hasattr(self, 'on_sku_inputs_changed'):
                    self.on_sku_inputs_changed()
            else:
                QMessageBox.warning(self, "Error", "Failed to save rack entry")

        except Exception as e:
            self.logger.error(f"Error adding rack: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add rack: {e}")

    def create_map_info_section(self):
        """Create map information section"""
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 15px;
            }
        """)
        info_layout = QGridLayout(info_frame)

        # Map stats
        self.map_name_label = QLabel("Map: Not Selected")
        self.map_name_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.map_name_label.setStyleSheet("color: #ff6b35;")
        info_layout.addWidget(self.map_name_label, 0, 0, 1, 2)

        # Stats
        stats = [
            ("Zones:", "zones_count_label"),
            ("Stops:", "stops_count_label"),
            ("Stop Groups:", "groups_count_label"),
            ("Dimensions:", "dimensions_label")
        ]

        for i, (label_text, attr_name) in enumerate(stats):
            label = QLabel(label_text)
            label.setStyleSheet("color: #cccccc; font-weight: bold;")
            info_layout.addWidget(label, 1 + i // 2, (i % 2) * 2)

            value_label = QLabel("0")
            value_label.setStyleSheet("color: #ffffff;")
            setattr(self, attr_name, value_label)
            info_layout.addWidget(value_label, 1 + i // 2, (i % 2) * 2 + 1)

        return info_frame

    def create_zones_tab(self):
        """Create zones management tab with flexible scrollable layout"""
        # Main tab widget
        tab_widget = QWidget()
        tab_widget.setSizePolicy(tab_widget.sizePolicy().Expanding, tab_widget.sizePolicy().Expanding)
        
        # Create scroll area to contain all content
        scroll_area = QScrollArea(tab_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameStyle(QFrame.NoFrame)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #404040;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #ff6b35;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #e55a2b;
            }
            QScrollBar:horizontal {
                background-color: #404040;
                height: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background-color: #ff6b35;
                border-radius: 6px;
                min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #e55a2b;
            }
        """)
        
        # Create scrollable content widget
        scroll_content = QWidget()
        scroll_content.setSizePolicy(scroll_content.sizePolicy().Expanding, scroll_content.sizePolicy().Preferred)
        
        # Main content layout with flexible sizing
        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(20)

        # Add warning message for new maps without zones
        self.zone_warning_label = QLabel("⚠️ Configure zones first to enable Stop Management and Map Settings tabs")
        self.zone_warning_label.setStyleSheet("""
            QLabel {
                background-color: #ff6b35;
                color: white;
                padding: 10px;
                border-radius: 6px;
                font-weight: bold;
                text-align: center;
            }
        """)
        self.zone_warning_label.setVisible(False)  # Initially hidden
        main_layout.addWidget(self.zone_warning_label)

        # Main section - Zone management with map on right and zone controls at bottom
        main_section = self.create_responsive_zone_section()
        main_layout.addWidget(main_section)
        
        # Add some bottom padding for better scrolling
        main_layout.addSpacing(20)

        # Set the scroll content
        scroll_area.setWidget(scroll_content)
        
        # Layout for the main tab widget
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll_area)

        return tab_widget

    def create_responsive_zone_section(self):
        """Create responsive zone section with form and table"""
        section_frame = QFrame()
        section_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
            }
        """)
        section_frame.setSizePolicy(section_frame.sizePolicy().Expanding, section_frame.sizePolicy().Preferred)
        
        # Main layout - vertical to stack top and bottom sections
        main_layout = QVBoxLayout(section_frame)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)
        
        # Top section - Zone creation form
        left_panel = self.create_zone_creation_form()
        left_panel.setMinimumWidth(600)  # Increased width since map is removed
        left_panel.setSizePolicy(left_panel.sizePolicy().Expanding, left_panel.sizePolicy().Preferred)
        main_layout.addWidget(left_panel)
        
        # Bottom section - Zone connections table (full width)
        bottom_panel = self.create_zones_table_section()
        bottom_panel.setMinimumHeight(400)  # Increased height for better visibility
        bottom_panel.setSizePolicy(bottom_panel.sizePolicy().Expanding, bottom_panel.sizePolicy().Preferred)
        main_layout.addWidget(bottom_panel)
        
        return section_frame
    

    def create_zone_management_panel(self):
        """Create combined zone management panel with forms and table"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 20px;
            }
        """)
        layout = QVBoxLayout(panel)
        
        # Title
        title = QLabel("Zone Connections Management")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #ff6b35; margin-bottom: 15px;")
        layout.addWidget(title)
        
        # Zone creation form
        form_section = self.create_zone_creation_form()
        layout.addWidget(form_section)
        
        # Zone list table
        table_section = self.create_zones_table_section()
        layout.addWidget(table_section)
        
        return panel
    
    def create_zone_creation_form(self):
        """Create zone creation form section"""
        form_frame = QFrame()
        form_frame.setStyleSheet("""
            QFrame {
                background-color: #404040;
                border: 1px solid #666666;
                border-radius: 6px;
                padding: 15px;
                margin-bottom: 15px;
            }
        """)
        form_layout = QVBoxLayout(form_frame)
        
        # Sub-title
        self.zone_form_subtitle = QLabel("Create New Zone Connection")
        self.zone_form_subtitle.setFont(QFont("Arial", 12, QFont.Bold))
        self.zone_form_subtitle.setStyleSheet("color: #ffffff; margin-bottom: 10px;")
        form_layout.addWidget(self.zone_form_subtitle)
        
        # Form inputs in grid layout
        inputs_layout = QFormLayout()
        
        # From Zone
        self.from_zone_input = QLineEdit()
        self.from_zone_input.setPlaceholderText("e.g., Zone A, Storage 1")
        self.apply_input_style(self.from_zone_input)
        inputs_layout.addRow("From Zone:", self.from_zone_input)
        
        # To Zone
        self.to_zone_input = QLineEdit()
        self.to_zone_input.setPlaceholderText("e.g., Zone B, Packing 1")
        self.apply_input_style(self.to_zone_input)
        inputs_layout.addRow("To Zone:", self.to_zone_input)
        
        # Distance and direction in same row
        # Direction
        dir_layout = QHBoxLayout()
        self.zone_magnitude_input = QDoubleSpinBox()
        self.zone_magnitude_input.setRange(0.1, 1000.0)
        self.zone_magnitude_input.setValue(50.0)
        self.zone_magnitude_input.setSuffix(" m")
        self.apply_input_style(self.zone_magnitude_input)
        dir_layout.addWidget(self.zone_magnitude_input)

        self.zone_direction_input = QComboBox()
        self.zone_direction_input.addItems(["north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest"])
        self.apply_combo_style(self.zone_direction_input)
        dir_layout.addWidget(self.zone_direction_input)
        
        inputs_layout.addRow("Distance & Direction:", dir_layout)
        
        form_layout.addLayout(inputs_layout)
        
        # Create/Update button
        self.zone_action_btn = QPushButton("➕ Create Zone Connection")
        self.zone_action_btn.clicked.connect(self.create_zone_connection)
        self.zone_action_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6b35;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-weight: bold;
                margin-top: 15px;
            }
            QPushButton:hover {
                background-color: #e55a2b;
            }
        """)
        form_layout.addWidget(self.zone_action_btn)
        
        return form_frame
    
    def create_zones_table_section(self):
        """Create zones table section with improved visibility"""
        table_frame = QFrame()
        table_frame.setStyleSheet("""
            QFrame {
                background-color: #404040;
                border: 1px solid #666666;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        table_frame.setSizePolicy(table_frame.sizePolicy().Expanding, table_frame.sizePolicy().Expanding)
        table_layout = QVBoxLayout(table_frame)
        table_layout.setSpacing(8)
        
        # Compact header with title and search on same row
        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)
        
        # Table title
        table_title = QLabel("Zone Connections")
        table_title.setFont(QFont("Arial", 12, QFont.Bold))
        table_title.setStyleSheet("color: #ffffff;")
        header_layout.addWidget(table_title)
        
        header_layout.addStretch()
        
        # Compact search field
        search_label = QLabel("Search:")
        search_label.setStyleSheet("color: #cccccc; font-size: 11px;")
        header_layout.addWidget(search_label)
        
        # Custom search input for the table
        self.zones_search_input = QLineEdit()
        self.zones_search_input.setPlaceholderText("Filter zones...")
        self.zones_search_input.setMaximumWidth(150)
        self.zones_search_input.setStyleSheet("""
            QLineEdit {
                background-color: #555555;
                border: 1px solid #777777;
                padding: 4px 8px;
                border-radius: 4px;
                color: #ffffff;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #ff6b35;
            }
        """)
        self.zones_search_input.textChanged.connect(self.filter_zones_table)
        header_layout.addWidget(self.zones_search_input)
        
        # Zones table with increased height
        self.zones_table = DataTableWidget([
            "From Zone", "To Zone", "Distance", "Direction", "Created", "Edited"
        ], searchable=False, selectable=True)  # Disable built-in search since we have custom
        self.zones_table.row_selected.connect(self.on_zone_selected)
        
        # Set minimum height for better visibility
        self.zones_table.setMinimumHeight(250)
        self.zones_table.setSizePolicy(self.zones_table.sizePolicy().Expanding, self.zones_table.sizePolicy().Expanding)
        
        table_layout.addWidget(self.zones_table)
        
        # Compact zone actions
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        
        edit_zone_btn = QPushButton("✏️ Edit")
        edit_zone_btn.clicked.connect(self.edit_selected_zone)
        edit_zone_btn.setMaximumWidth(80)
        edit_zone_btn.setStyleSheet("""
            QPushButton {
                background-color: #555555;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #666666;
            }
        """)
        actions_layout.addWidget(edit_zone_btn)
        
        delete_zone_btn = QPushButton("🗑️ Delete")
        delete_zone_btn.clicked.connect(self.delete_selected_zone)
        delete_zone_btn.setMaximumWidth(80)
        delete_zone_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        actions_layout.addWidget(delete_zone_btn)
        
        actions_layout.addStretch()
        
        # Row count display
        self.zones_count_display = QLabel("0 zones")
        self.zones_count_display.setStyleSheet("color: #888888; font-size: 10px;")
        actions_layout.addWidget(self.zones_count_display)
        
        table_layout.addLayout(actions_layout)
        
        return table_frame
    
    def create_zone_creation_panel(self):
        """Create zone creation panel"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 20px;
            }
        """)
        layout = QVBoxLayout(panel)

        # Title
        title = QLabel("Create Zone Connection")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #ff6b35; margin-bottom: 15px;")
        layout.addWidget(title)

        # Form
        form_layout = QFormLayout()

        # From Zone
        self.from_zone_input = QLineEdit()
        self.from_zone_input.setPlaceholderText("e.g., Zone A, Storage 1")
        self.apply_input_style(self.from_zone_input)
        form_layout.addRow("From Zone:", self.from_zone_input)

        # To Zone
        self.to_zone_input = QLineEdit()
        self.to_zone_input.setPlaceholderText("e.g., Zone B, Packing 1")
        self.apply_input_style(self.to_zone_input)
        form_layout.addRow("To Zone:", self.to_zone_input)

        # Distance
        self.magnitude_input = QDoubleSpinBox()
        self.magnitude_input.setRange(0.1, 1000.0)
        self.magnitude_input.setValue(50.0)
        self.magnitude_input.setSuffix(" meters")
        self.magnitude_input.setDecimals(1)
        self.apply_input_style(self.magnitude_input)
        form_layout.addRow("Distance:", self.magnitude_input)

        # Direction
        self.direction_combo = QComboBox()
        directions = ["north", "south", "east", "west"]
        self.direction_combo.addItems(directions)
        self.apply_combo_style(self.direction_combo)
        form_layout.addRow("Direction:", self.direction_combo)

        layout.addLayout(form_layout)

        # Create button
        create_zone_btn = QPushButton("➕ Create Zone Connection")
        create_zone_btn.clicked.connect(self.create_zone_connection)
        create_zone_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6b35;
                color: white;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-weight: bold;
                margin-top: 15px;
            }
            QPushButton:hover {
                background-color: #e55a2b;
            }
        """)
        layout.addWidget(create_zone_btn)

        layout.addStretch()
        return panel

    def create_zones_list_panel(self):
        """Create zones list panel"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 20px;
            }
        """)
        layout = QVBoxLayout(panel)

        # Title
        title = QLabel("Zone Connections")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #ff6b35; margin-bottom: 15px;")
        layout.addWidget(title)

        # Zones table
        self.zones_table = DataTableWidget([
            "From Zone", "To Zone", "Distance", "Direction", "Created"
        ], searchable=True, selectable=True)
        self.zones_table.row_selected.connect(self.on_zone_selected)
        layout.addWidget(self.zones_table)

        # Zone actions
        actions_layout = QHBoxLayout()

        edit_zone_btn = QPushButton("✏️ Edit Zone")
        edit_zone_btn.clicked.connect(self.edit_selected_zone)
        self.apply_button_style(edit_zone_btn)
        actions_layout.addWidget(edit_zone_btn)

        delete_zone_btn = QPushButton("🗑️ Delete Zone")
        delete_zone_btn.clicked.connect(self.delete_selected_zone)
        delete_zone_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        actions_layout.addWidget(delete_zone_btn)

        layout.addLayout(actions_layout)
        return panel

    def create_stops_tab(self):
        """Create stops management tab with scrollable content"""
        # Create main tab widget
        tab_widget = QWidget()
        tab_widget.setSizePolicy(tab_widget.sizePolicy().Expanding, tab_widget.sizePolicy().Expanding)
        
        # Create scroll area to contain all content
        scroll_area = QScrollArea(tab_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameStyle(QFrame.NoFrame)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #404040;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #ff6b35;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #e55a2b;
            }
        """)
        
        # Create scrollable content widget
        scroll_content = QWidget()
        scroll_content.setSizePolicy(scroll_content.sizePolicy().Expanding, scroll_content.sizePolicy().Preferred)
        
        # Main content layout
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(15, 15, 15, 15)
        content_layout.setSpacing(20)

        # Stop generation controls section
        controls_section = self.create_stop_controls_section()
        controls_section.setMinimumHeight(200)
        content_layout.addWidget(controls_section)
        
        # Stop Details section - give it more space and allow expansion
        stop_details_section = self.create_stop_details_section()
        content_layout.addWidget(stop_details_section, 1)  # Add stretch factor of 1


        # Set the scroll content
        scroll_area.setWidget(scroll_content)
        
        # Layout for the main tab widget
        tab_layout = QVBoxLayout(tab_widget)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll_area)

        return tab_widget


    def create_settings_tab(self):
        """Create map settings tab"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(20, 20, 20, 20)

        # Map properties
        properties_section = QFrame()
        properties_section.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 20px;
            }
        """)
        properties_layout = QFormLayout(properties_section)

        # Title
        title = QLabel("Map Properties")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #ff6b35; margin-bottom: 15px;")
        properties_layout.addRow(title)

        # Map settings
        self.map_name_input = QLineEdit()
        self.map_name_input.setPlaceholderText("Enter map name")
        self.apply_input_style(self.map_name_input)
        apply_no_special_chars_validator(self.map_name_input)
        properties_layout.addRow("Map Name:", self.map_name_input)

        self.map_description_input = QTextEdit()
        self.map_description_input.setPlaceholderText("Enter map description")
        self.map_description_input.setMaximumHeight(80)
        self.apply_input_style(self.map_description_input)
        apply_no_special_chars_validator(self.map_description_input)
        properties_layout.addRow("Description:", self.map_description_input)

        dimensions_layout = QHBoxLayout()

        self.map_width_input = QSpinBox()
        self.map_width_input.setRange(500, 5000)
        self.map_width_input.setValue(1000)
        self.map_width_input.setSuffix(" px")
        self.apply_input_style(self.map_width_input)
        dimensions_layout.addWidget(self.map_width_input)

        dimensions_layout.addWidget(QLabel("×"))

        self.map_height_input = QSpinBox()
        self.map_height_input.setRange(400, 4000)
        self.map_height_input.setValue(800)
        self.map_height_input.setSuffix(" px")
        self.apply_input_style(self.map_height_input)
        dimensions_layout.addWidget(self.map_height_input)

        properties_layout.addRow("Dimensions:", dimensions_layout)

        self.map_meter_input = QSpinBox()
        self.map_meter_input.setRange(10, 1000)
        self.map_meter_input.setValue(150)
        self.map_meter_input.setSuffix(" px")
        self.apply_input_style(self.map_meter_input)
        properties_layout.addRow("1 meter in pixel:", self.map_meter_input)

        layout.addWidget(properties_section)

        # Save button
        save_btn = QPushButton("💾 Save Map Settings")
        save_btn.clicked.connect(self.save_map_settings)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: bold;
                margin-top: 20px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        layout.addWidget(save_btn)

        layout.addStretch()
        return tab_widget

    def create_zone_alignment_tab(self):
        """Create Zone Alignment setting tab with improved UI.

        Shows a table with columns 'Zone Name' and 'Alignment Enabled' for the
        currently selected map. Includes bulk actions and improved styling.
        """
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Container Frame
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 0px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 20, 20, 20)
        container_layout.setSpacing(15)

        # Header Section
        header_layout = QHBoxLayout()
        
        title_chem = QVBoxLayout()
        title = QLabel("Zone Alignment Settings")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setStyleSheet("color: #ff6b35; border: none; background: transparent;")
        title_chem.addWidget(title)
        
        subtitle = QLabel("Configure standard (No) or alternate (Yes) alignment for path planning per zone.")
        subtitle.setStyleSheet("color: #cccccc; font-size: 12px; border: none; background: transparent;")
        title_chem.addWidget(subtitle)
        
        header_layout.addLayout(title_chem)
        header_layout.addStretch()
        
        container_layout.addLayout(header_layout)

        # Bulk Actions Toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(10)
        
        enable_all_btn = QPushButton("✅ Enable All")
        enable_all_btn.setToolTip("Set alignment to 'Yes' for all zones")
        enable_all_btn.clicked.connect(lambda: self.set_all_zones_alignment("Yes"))
        enable_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 1px solid #666666;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
                border-color: #10B981;
                color: #10B981;
            }
        """)
        toolbar_layout.addWidget(enable_all_btn)

        disable_all_btn = QPushButton("⛔ Disable All") 
        disable_all_btn.setToolTip("Set alignment to 'No' for all zones")
        disable_all_btn.clicked.connect(lambda: self.set_all_zones_alignment("No"))
        disable_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #ffffff;
                border: 1px solid #666666;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #505050;
                border-color: #dc3545;
                color: #dc3545;
            }
        """)
        toolbar_layout.addWidget(disable_all_btn)
        
        toolbar_layout.addStretch()
        container_layout.addLayout(toolbar_layout)

        # Table
        self.zone_alignment_table = QTableWidget()
        self.zone_alignment_table.setColumnCount(2)
        self.zone_alignment_table.setHorizontalHeaderLabels(["Zone Name", "Alignment Enabled"])
        
        # Configure Header
        header = self.zone_alignment_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.zone_alignment_table.setColumnWidth(1, 150)
        
        self.zone_alignment_table.verticalHeader().setVisible(False)
        self.zone_alignment_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.zone_alignment_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.zone_alignment_table.setFocusPolicy(Qt.NoFocus)
        self.zone_alignment_table.setShowGrid(False)
        self.zone_alignment_table.setAlternatingRowColors(True)
        
        # Styling
        self.zone_alignment_table.setStyleSheet("""
            QTableWidget {
                background-color: #2b2b2b;
                alternate-background-color: #323232;
                border: 1px solid #555555;
                border-radius: 4px;
                gridline-color: #444444;
                color: #ffffff;
            }
            QTableWidget::item {
                padding: 5px;
                border-bottom: 1px solid #444444;
            }
            QHeaderView::section {
                background-color: #404040;
                color: #ffffff;
                padding: 10px;
                border: none;
                border-right: 1px solid #555555;
                border-bottom: 2px solid #ff6b35;
                font-weight: bold;
                font-size: 13px;
            }
            QHeaderView::section:first {
                border-top-left-radius: 4px;
            }
            QHeaderView::section:last {
                border-top-right-radius: 4px;
                border-right: none;
            }
        """)
        
        container_layout.addWidget(self.zone_alignment_table)

        # Footer Actions
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        
        save_btn = QPushButton("💾 Save Configuration")
        save_btn.clicked.connect(self.save_zone_alignment_settings)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                border: none;
                padding: 10px 24px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        footer_layout.addWidget(save_btn)
        
        container_layout.addLayout(footer_layout)
        
        layout.addWidget(container)
        return tab_widget

    def set_all_zones_alignment(self, value):
        """Bulk set alignment for all zones in the table."""
        if not hasattr(self, 'zone_alignment_table'):
            return
            
        row_count = self.zone_alignment_table.rowCount()
        for r in range(row_count):
            widget = self.zone_alignment_table.cellWidget(r, 1)
            if widget:
                combo = widget.findChild(QComboBox)
                if combo:
                    combo.setCurrentText(value)

    def create_charging_station_tab(self):
        """Create Charging Station management tab"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header with Add Button
        header_layout = QHBoxLayout()
        title = QLabel("Charging Station Management")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setStyleSheet("color: #ff6b35;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        add_btn = QPushButton("➕ Add Charging Station")
        add_btn.clicked.connect(self.show_add_charging_station_dialog)
        self.apply_button_style(add_btn)
        header_layout.addWidget(add_btn)
        
        layout.addLayout(header_layout)

        # Table
        self.charging_zones_table = DataTableWidget(
            headers=["Charging Zone", "Occupied", "Device ID", "Actions"],
            searchable=True,
            selectable=False
        )
        # Apply specific table styling for visibility
        self.charging_zones_table.table.verticalHeader().setDefaultSectionSize(45)
        self.charging_zones_table.table.verticalHeader().setVisible(False)
        
        # Configure Actions column width
        header = self.charging_zones_table.table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.charging_zones_table.table.setColumnWidth(3, 100)
        
        layout.addWidget(self.charging_zones_table)
        
        return tab_widget

    def show_add_charging_station_dialog(self):
        """Show dialog to add a new charging station"""
        if not self.selected_map_id:
            QMessageBox.warning(self, "No Map", "Please select a map first")
            return

        # Get all unique zones for the selected map
        zones = set()
        for z in self.current_zones:
            if z.get('from_zone'): zones.add(z.get('from_zone'))
            if z.get('to_zone'): zones.add(z.get('to_zone'))
        
        if not zones:
            QMessageBox.warning(self, "No Zones", "No zones found for this map. Please configure zones first.")
            return

        dialog = BaseDialog(self)
        dialog.setWindowTitle("Add Charging Station")
        dialog.setFixedSize(300, 150)
        
        main_layout = QVBoxLayout(dialog)
        form_layout = QFormLayout()
        
        zone_combo = QComboBox()
        zone_combo.addItems(sorted(list(zones)))
        self.apply_combo_style(zone_combo)
        form_layout.addRow("Select Zone:", zone_combo)
        
        main_layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        add_btn = QPushButton("Add")
        
        self.apply_button_style(cancel_btn)
        self.apply_button_style(add_btn)
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        
        cancel_btn.clicked.connect(dialog.reject)
        add_btn.clicked.connect(dialog.accept)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(add_btn)
        main_layout.addLayout(button_layout)
        
        if dialog.exec_() == dialog.Accepted:
            selected_zone = zone_combo.currentText()
            
            # Check if already exists
            existing = self.csv_handler.read_csv('charging_zones')
            if any(str(row.get('map_id')) == str(self.selected_map_id) and row.get('zone') == selected_zone for row in existing):
                QMessageBox.warning(self, "Duplicate", f"Zone '{selected_zone}' is already a charging station.")
                return
            
            new_row = {
                'map_id': self.selected_map_id,
                'zone': selected_zone,
                'occupied': 'No',
                'device_id': 'NA'
            }
            
            if self.csv_handler.append_to_csv('charging_zones', new_row):
                self.populate_charging_zones_table()
            else:
                QMessageBox.warning(self, "Error", "Failed to save charging station.")

    def populate_charging_zones_table(self):
        """Populate the charging zones table with dynamic occupancy check"""
        if not hasattr(self, 'charging_zones_table'):
            return
            
        self.charging_zones_table.clear_data()
        
        if not self.selected_map_id:
            return
            
        # Load charging zones for this map
        all_charging_zones = self.csv_handler.read_csv('charging_zones')
        map_charging_zones = [z for z in all_charging_zones if str(z.get('map_id')) == str(self.selected_map_id)]
        
        if not map_charging_zones:
            return
            
        # Load devices for occupancy check
        devices = self.csv_handler.read_csv('devices')
        
        table_data = []
        for cz in map_charging_zones:
            zone_name = cz.get('zone', '')
            cz_id = cz.get('id', '')
            
            # Check occupancy: Device in this zone AND status is 'charging'
            occupant = next((d for d in devices if str(d.get('current_location')) == zone_name and str(d.get('status')).lower() == 'charging'), None)
            
            occupied = "Yes" if occupant else "No"
            device_id = occupant.get('device_id', 'NA') if occupant else "NA"
            
            # Add data for the first 3 columns
            table_data.append([zone_name, occupied, device_id])
            
        self.charging_zones_table.set_data(table_data)

        # Add Delete buttons to the Actions column
        for row, cz in enumerate(map_charging_zones):
            cz_id = cz.get('id')
            
            delete_btn = QPushButton("Delete")
            delete_btn.setToolTip("Delete Charging Station")
            delete_btn.setFixedSize(32, 32)
            delete_btn.setCursor(Qt.PointingHandCursor)
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #dc3545;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #c82333;
                }
                QPushButton:pressed {
                    background-color: #bd2130;
                }
            """)
            delete_btn.clicked.connect(lambda checked, i=cz_id: self.delete_charging_station(i))
            
            # Center the button in a widget
            container = QWidget()
            container.setStyleSheet("background-color: transparent;")
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(5, 2, 5, 2)
            container_layout.setSpacing(5)
            container_layout.addWidget(delete_btn)
            container_layout.setAlignment(Qt.AlignCenter)
            
            self.charging_zones_table.table.setCellWidget(row, 3, container)

    def delete_charging_station(self, charging_zone_id):
        """Delete a charging station from CSV and refresh table"""
        if not charging_zone_id:
            return

        reply = QMessageBox.question(
            self, 'Confirm Deletion',
            "Are you sure you want to delete this charging station?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.csv_handler.delete_csv_row('charging_zones', charging_zone_id):
                self.logger.info(f"Deleted charging station ID: {charging_zone_id}")
                self.populate_charging_zones_table()
            else:
                QMessageBox.warning(self, "Error", "Failed to delete charging station.")

    def create_action_buttons(self, parent_layout):
        """Create action buttons"""
        action_layout = QHBoxLayout()

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh Data")
        refresh_btn.clicked.connect(self.refresh_data)
        self.apply_button_style(refresh_btn)
        action_layout.addWidget(refresh_btn)

        # Sync button
        sync_btn = QPushButton("🔄 Sync with API")
        sync_btn.clicked.connect(self.sync_with_api)
        self.apply_button_style(sync_btn)
        action_layout.addWidget(sync_btn)

        action_layout.addStretch()

        # Delete map button
        self.delete_map_btn = QPushButton("🗑️ Delete Current Map")
        self.delete_map_btn.clicked.connect(self.delete_current_map)
        self.delete_map_btn.setEnabled(False)
        self.delete_map_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)
        action_layout.addWidget(self.delete_map_btn)

        parent_layout.addLayout(action_layout)

    def apply_combo_style(self, combo):
        """Apply combobox styling with visible dropdown arrow"""
        combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 8px 25px 8px 8px;
                border-radius: 4px;
                color: #ffffff;
                min-width: 150px;
            }
            QComboBox:focus {
                border: 2px solid #ff6b35;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #666666;
                background-color: #555555;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
            }
            QComboBox::drop-down:hover {
                background-color: #666666;
            }
            QComboBox::down-arrow {
                image: none;
                border: 2px solid #ffffff;
                width: 6px;
                height: 6px;
                border-top: none;
                border-right: none;
                transform: rotate(45deg);
                margin: 2px;
            }
            QComboBox::down-arrow:hover {
                border-color: #ff6b35;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #ff6b35;
                border: 1px solid #555555;
                outline: none;
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

    def apply_input_style(self, widget):
        """Apply input styling"""
        widget.setStyleSheet("""
            QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 8px;
                border-radius: 4px;
                color: #ffffff;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
                border: 2px solid #ff6b35;
            }
        """)

    def refresh_data(self):
        """Refresh all map data"""
        # Store current tab index to preserve it after refresh
        current_tab_index = self.tab_widget.currentIndex()
        self.logger.debug(f"Refreshing data - current tab index: {current_tab_index}")
        
        self.load_maps()
        if self.selected_map_id:
            self.load_map_data(self.selected_map_id)
        
        # Restore the current tab index to prevent automatic navigation to overview tab
        if current_tab_index >= 0 and current_tab_index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(current_tab_index)
            self.logger.debug(f"Restored tab index to: {current_tab_index}")
        else:
            self.logger.debug(f"Could not restore tab index: {current_tab_index} (valid range: 0-{self.tab_widget.count()-1})")

    def load_maps(self):
        """Load available maps"""
        try:
            # Try API first, then fallback to CSV
            if self.api_client.is_authenticated():
                response = self.maps_api.list_maps()
                if 'error' not in response:
                    maps_data = response.get('results', response) if isinstance(response, dict) else response
                    self.current_maps = maps_data
                    self.populate_map_selector()
                    return

            # Fallback to CSV
            maps = self.csv_handler.read_csv('maps')
            self.current_maps = maps
            self.populate_map_selector()

        except Exception as e:
            self.logger.error(f"Error loading maps: {e}")
            self.current_maps = []
            self.populate_map_selector()

    def populate_map_selector(self):
        """Populate map selector"""
        current_selection = self.map_selector.currentData()
        current_index = self.map_selector.currentIndex()
        self.map_selector.clear()
        self.map_selector.addItem("No Map Selected", "")

        for map_item in self.current_maps:
            map_name = map_item.get('name', 'Unnamed Map')
            map_id = map_item.get('id')
            self.map_selector.addItem(map_name, map_id)

        # Restore selection if possible
        if current_selection:
            index = self.map_selector.findData(current_selection)
            if index >= 0:
                self.map_selector.setCurrentIndex(index)
            else:
                # If the previously selected map is not found, keep the current tab
                # and don't trigger the on_map_selected method by temporarily blocking signals
                self.map_selector.blockSignals(True)
                self.map_selector.setCurrentIndex(0)  # Set to "No Map Selected"
                self.map_selector.blockSignals(False)
                # Don't call update_tab_accessibility here to preserve current tab
        else:
            # If no previous selection, just set to first item without triggering signals
            self.map_selector.blockSignals(True)
            self.map_selector.setCurrentIndex(0)
            self.map_selector.blockSignals(False)

    def on_map_selected(self):
        """Handle map selection"""
        map_id = self.map_selector.currentData()
        if map_id:
            self.selected_map_id = map_id
            self.load_map_data(map_id)
            self.delete_map_btn.setEnabled(True)
            self.populate_zones_combo()
            self.update_tab_accessibility()
            if hasattr(self, 'populate_charging_zones_table'):
                self.populate_charging_zones_table()
        else:
            self.selected_map_id = None
            self.delete_map_btn.setEnabled(False)
            self.clear_map_data()
            self.update_tab_accessibility()

    def populate_zones_combo(self):
        """Populate zones combo for stop generation"""
        self.zone_for_stops_combo.clear()
        self.zone_for_stops_combo.addItem("Select Zone", "")

        for zone in self.current_zones:
            zone_text = f"{zone.get('from_zone', '')} → {zone.get('to_zone', '')}"
            self.zone_for_stops_combo.addItem(zone_text, zone.get('id'))

    def load_map_data(self, map_id):
        """Load data for specific map"""
        try:
            # Load zones, stops, and stop groups for this map
            zones = self.csv_handler.read_csv('zones')
            self.current_zones = [z for z in zones if str(z.get('map_id')) == str(map_id)]

            stops = self.csv_handler.read_csv('stops')
            self.current_stops = [s for s in stops if str(s.get('map_id')) == str(map_id)]

            stop_groups = self.csv_handler.read_csv('stop_groups')
            self.current_stop_groups = [sg for sg in stop_groups if str(sg.get('map_id')) == str(map_id)]

            # Load racks for this map
            selected_map = next((m for m in self.current_maps if str(m.get('id')) == str(map_id)), None)
            map_name = selected_map.get('name', '') if selected_map else ''
            all_racks = self.csv_handler.read_csv('racks')
            self.current_racks = [r for r in all_racks if str(r.get('map_name')) == map_name]

            # Load zone alignment rows for this map
            try:
                all_align_rows = self.csv_handler.read_csv('zone_alignment')
                self.current_zone_alignment = [r for r in all_align_rows if str(r.get('map_id')) == str(map_id)]
            except Exception:
                self.current_zone_alignment = []

            # Update UI
            self.update_map_info()
            self.populate_zones_table()
            self.populate_zones_combo()
            self.refresh_stop_details_table()

            # Refresh rack configuration combos if tab exists
            if hasattr(self, 'populate_rack_zone_combo'):
                self.populate_rack_zone_combo()
            if hasattr(self, 'populate_rack_stop_combo'):
                self.populate_rack_stop_combo()
            # Refresh Add SKU Location combos if tab exists
            if hasattr(self, 'populate_sku_zone_combo'):
                self.populate_sku_zone_combo()
            if hasattr(self, 'populate_sku_stop_combo'):
                self.populate_sku_stop_combo()
            if hasattr(self, 'populate_sku_rack_combo'):
                self.populate_sku_rack_combo()

            # Get map dimensions from settings
            map_width = self.map_width_input.value() if hasattr(self, 'map_width_input') else 1000
            map_height = self.map_height_input.value() if hasattr(self, 'map_height_input') else 800
            # Update map viewer with explicit dimensions
            selected_map = next((m for m in self.current_maps if str(m.get('id')) == str(map_id)), None)
            self.map_viewer.set_map_data(
                zones=self.current_zones,
                stops=self.current_stops,
                stop_groups=self.current_stop_groups,
                map_width=map_width,
                map_height=map_height,
                map_data=selected_map,
                racks=self.current_racks
            )
            

            # Update settings
            selected_map = next((m for m in self.current_maps if str(m.get('id')) == str(map_id)), None)
            if selected_map:
                self.map_name_input.setText(selected_map.get('name', ''))
                self.map_description_input.setPlainText(selected_map.get('description', ''))
                self.map_width_input.setValue(int(selected_map.get('width', 1000)))
                self.map_height_input.setValue(int(selected_map.get('height', 800)))
                self.map_meter_input.setValue(int(selected_map.get('meter_in_pixels', 150)))

            # Populate zone alignment table
            if hasattr(self, 'zone_alignment_table'):
                self.populate_zone_alignment_table()

            # Populate charging zones table
            if hasattr(self, 'populate_charging_zones_table'):
                self.populate_charging_zones_table()

        except Exception as e:
            self.logger.error(f"Error loading map data: {e}")

    def update_map_info(self):
        """Update map information display"""
        if self.selected_map_id:
            selected_map = next((m for m in self.current_maps if str(m.get('id')) == str(self.selected_map_id)), None)
            if selected_map:
                self.map_name_label.setText(f"Map: {selected_map.get('name', 'Unnamed')}")

            self.zones_count_label.setText(str(len(self.current_zones)))
            self.stops_count_label.setText(str(len(self.current_stops)))
            self.groups_count_label.setText(str(len(self.current_stop_groups)))

            width = self.map_width_input.value() if hasattr(self, 'map_width_input') else 1000
            height = self.map_height_input.value() if hasattr(self, 'map_height_input') else 800
            self.dimensions_label.setText(f"{width} × {height} px")
        else:
            self.map_name_label.setText("Map: Not Selected")
            self.zones_count_label.setText("0")
            self.stops_count_label.setText("0")
            self.groups_count_label.setText("0")
            self.dimensions_label.setText("- × - px")

    def populate_zone_alignment_table(self):
        """Populate zone alignment table for the selected map.

        For each zone belonging to the current map, show a row with the
        zone identifier and a Yes/No combo box indicating alignment.
        """
        if not hasattr(self, 'zone_alignment_table'):
            return

        self.zone_alignment_table.setRowCount(0)

        if not self.selected_map_id:
            return

        # Build lookup from existing alignment rows: key = (map_id, zone)
        align_lookup = {}
        try:
            for row in self.current_zone_alignment or []:
                key = (str(row.get('map_id')), str(row.get('zone')))
                align_lookup[key] = str(row.get('alignment') or '').strip()
        except Exception:
            align_lookup = {}

        # Build unique list of individual zones for this map
        # We probably want to list zone CONNECTIONS (From -> To) not just loose zone names
        # BUT current code iterates unique zone IDs?
        # Let's check logic:
        # Original code used set of from_zone and to_zone.
        # This seems to mean alignment is per "Location", not per "Connection".
        # Validating understanding: "Zone" typically refers to a node/location.
        # Yes, standard vs alternate alignment usually applies to the arrival at a node.
        
        zone_ids = set()
        for zone in self.current_zones or []:
            fz = str(zone.get('from_zone', '')).strip()
            tz = str(zone.get('to_zone', '')).strip()
            if fz:
                zone_ids.add(fz)
            if tz:
                zone_ids.add(tz)

        for zone_id_str in sorted(zone_ids, key=lambda z: (len(z), z)):
            row_index = self.zone_alignment_table.rowCount()
            self.zone_alignment_table.insertRow(row_index)
            self.zone_alignment_table.setRowHeight(row_index, 40) # Increased height for readability

            zone_item = QTableWidgetItem(zone_id_str)
            zone_item.setFlags(zone_item.flags() & ~Qt.ItemIsEditable)
            zone_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.zone_alignment_table.setItem(row_index, 0, zone_item)

            combo = QComboBox()
            combo.addItems(["No", "Yes"])
            # Default is No
            existing = align_lookup.get((str(self.selected_map_id), zone_id_str), '')
            if existing.strip().lower().startswith('y'):
                combo.setCurrentText("Yes")
            else:
                combo.setCurrentText("No")
            
            # Custom styling for table combo
            combo.setStyleSheet("""
                QComboBox {
                    background-color: #404040;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 4px 8px;
                    color: #ffffff;
                }
                QComboBox:hover {
                    border-color: #ff6b35;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                }
                QComboBox::down-arrow {
                    image: none;
                    border: 2px solid #cccccc;
                    width: 6px;
                    height: 6px;
                    border-top: none;
                    border-right: none;
                    transform: rotate(45deg);
                }
            """)
            
            # Container for centering
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(5, 2, 5, 2)
            layout.setAlignment(Qt.AlignCenter)
            layout.addWidget(combo)
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            # Using setCellWidget directly on combo or wrapper
            # wrapper is safer for layout control
            self.zone_alignment_table.setCellWidget(row_index, 1, widget)

    def save_zone_alignment_settings(self):
        """Persist current zone alignment settings to zone_alignment.csv."""
        if not self.selected_map_id:
            QMessageBox.warning(self, "No Map", "Please select a map first")
            return

        try:
            map_id_str = str(self.selected_map_id)

            # Read all existing rows so we can update only this map's entries
            all_rows = self.csv_handler.read_csv('zone_alignment') or []
            # Keep rows for other maps as-is
            retained = [r for r in all_rows if str(r.get('map_id')) != map_id_str]

            # Build new rows for this map from the table
            new_rows = []
            row_count = self.zone_alignment_table.rowCount()
            for r in range(row_count):
                zone_item = self.zone_alignment_table.item(r, 0)
                widget = self.zone_alignment_table.cellWidget(r, 1)
                
                if not zone_item or not widget:
                    continue
                    
                combo = widget.findChild(QComboBox)
                if not combo:
                    continue
                    
                zone_label = zone_item.text().strip()
                alignment_text = combo.currentText().strip()
                # Default alignment is No; we always write explicit value
                new_rows.append({
                    'id': '',  # let CSVHandler assign id
                    'map_id': map_id_str,
                    'zone': zone_label,
                    'alignment': alignment_text,
                })

            # Combine and write back
            merged = retained + new_rows
            if self.csv_handler.write_csv('zone_alignment', merged):
                # Refresh in-memory cache for current map
                self.current_zone_alignment = [r for r in merged if str(r.get('map_id')) == map_id_str]
                QMessageBox.information(self, "Success", "Zone alignment settings saved")
            else:
                QMessageBox.warning(self, "Error", "Failed to save zone alignment settings")

        except Exception as e:
            self.logger.error(f"Error saving zone alignment settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save zone alignment settings: {e}")

    def populate_zones_table(self):
        """Populate zones table"""
        # Prepare all data first
        table_data = []
        for zone in self.current_zones:
            # Get direction and display it properly
            direction = zone.get('direction', 'north')  # Default to north for backward compatibility
            direction_display = direction.title() if direction else 'North'
            
            row_data = [
                zone.get('from_zone', ''),
                zone.get('to_zone', ''),
                f"{zone.get('magnitude', 0)} m",
                direction_display,
                # Format date with time if available
                self.format_datetime(zone.get('created_at', '')),
                self.format_datetime(zone.get('edited_at', ''))
            ]
            table_data.append(row_data)
        
        # Set all data at once - this will automatically optimize column widths
        self.zones_table.set_data(table_data)
        
        # Update zones count
        if hasattr(self, 'zones_count_display'):
            self.zones_count_display.setText(f"{len(self.current_zones)} zones")
        
        # Clear search when repopulating
        if hasattr(self, 'zones_search_input'):
            self.zones_search_input.clear()
    
    def format_datetime(self, date_value):
        """Format datetime string to show both date and time"""
        if not date_value:
            return 'N/A'
        
        try:
            # Format the date with time for better display
            dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            # If parsing fails, try to include time if available
            if len(date_value) >= 19:  # Length of 'YYYY-MM-DD HH:MM:SS'
                return date_value[:19]
            else:
                return date_value
    
    def filter_zones_table(self, search_text):
        """Filter zones table based on search text"""
        search_text = search_text.lower().strip()
        
        if not search_text:
            # If search is empty, show all zones
            self.populate_zones_table()
            return
        
        # Filter zones based on search text
        filtered_zones = []
        for zone in self.current_zones:
            # Search in various fields
            searchable_text = ' '.join([
                zone.get('from_zone', '').lower(),
                zone.get('to_zone', '').lower(),
                str(zone.get('magnitude', '')).lower(),
                zone.get('direction', '').lower()
            ])
            
            if search_text in searchable_text:
                filtered_zones.append(zone)
        
        # Prepare filtered data for display
        table_data = []
        for zone in filtered_zones:
            direction = zone.get('direction', 'north')
            direction_display = direction.title() if direction else 'North'
            
            row_data = [
                zone.get('from_zone', ''),
                zone.get('to_zone', ''),
                f"{zone.get('magnitude', 0)} m",
                direction_display,
                self.format_datetime(zone.get('created_at', '')),
                self.format_datetime(zone.get('edited_at', ''))
            ]
            table_data.append(row_data)
        
        # Update table with filtered data
        self.zones_table.set_data(table_data)
        
        # Update zones count to show filtered results
        if hasattr(self, 'zones_count_display'):
            total_zones = len(self.current_zones)
            filtered_count = len(filtered_zones)
            if filtered_count != total_zones:
                self.zones_count_display.setText(f"{filtered_count}/{total_zones} zones")
            else:
                self.zones_count_display.setText(f"{total_zones} zones")

    # Populate stops data method removed as part of UI cleanup

    def clear_map_data(self):
        """Clear all map data"""
        self.current_zones = []
        self.current_stops = []
        self.current_stop_groups = []
        self.current_zone_alignment = []
        self.zones_table.clear_data()
        self.zone_for_stops_combo.clear()
        self.zone_for_stops_combo.addItem("Select Zone", "")
        self.map_viewer.clear_map()
        
        # Clear embedded map viewer (if it exists)
        if hasattr(self, 'embedded_map_viewer'):
            self.embedded_map_viewer.clear_map()
            
        self.update_map_info()
        self.refresh_stop_details_table()
        self.clear_stop_form()
        if hasattr(self, 'zone_alignment_table'):
            self.zone_alignment_table.setRowCount(0)

    def create_new_map(self):
        """Create new map with improved dialog"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit, QSpinBox, QPushButton, \
            QHBoxLayout

        dialog = BaseDialog(self)
        dialog.setWindowTitle("Create New Map")
        dialog.setModal(True)
        dialog.setFixedSize(400, 350)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
        """)

        layout = QVBoxLayout(dialog)
        form_layout = QFormLayout()

        # Map name
        name_input = QLineEdit()
        name_input.setPlaceholderText("Enter map name")
        self.apply_input_style(name_input)
        apply_no_special_chars_validator(name_input)
        form_layout.addRow("Map Name *:", name_input)

        # Description
        desc_input = QTextEdit()
        desc_input.setPlaceholderText("Enter map description (optional)")
        desc_input.setMaximumHeight(60)
        self.apply_input_style(desc_input)
        apply_no_special_chars_validator(desc_input)
        form_layout.addRow("Description:", desc_input)

        # Dimensions
        width_input = QSpinBox()
        width_input.setRange(500, 5000)
        width_input.setValue(1000)
        width_input.setSuffix(" px")
        self.apply_input_style(width_input)
        form_layout.addRow("Width:", width_input)

        height_input = QSpinBox()
        height_input.setRange(400, 4000)
        height_input.setValue(800)
        height_input.setSuffix(" px")
        self.apply_input_style(height_input)
        form_layout.addRow("Height:", height_input)

        # Meter in pixels
        meter_input = QSpinBox()
        meter_input.setRange(10, 1000)
        meter_input.setValue(150)
        meter_input.setSuffix(" px")
        self.apply_input_style(meter_input)
        form_layout.addRow("1 meter in pixel:", meter_input)

        layout.addLayout(form_layout)

        # Buttons
        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        create_btn = QPushButton("Create Map")
        create_btn.setAutoDefault(False)

        self.apply_button_style(cancel_btn)
        cancel_btn.setAutoDefault(False)
        create_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)

        cancel_btn.clicked.connect(dialog.reject)

        def create_map():
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(dialog, "Error", "Map name is required")
                return

            map_data = {
                'name': name,
                'description': desc_input.toPlainText().strip(),
                'width': width_input.value(),
                'height': height_input.value(),
                'meter_in_pixels': meter_input.value(),
                'created_at': datetime.now().isoformat()
            }

            dialog.accept()
            self.save_new_map(map_data)

        create_btn.clicked.connect(create_map)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(create_btn)
        layout.addLayout(button_layout)

        dialog.exec_()

    def save_new_map(self, map_data):
        """Save new map"""
        try:
            # Try API first
            if self.api_client.is_authenticated():
                response = self.maps_api.create_map(map_data)
                if 'error' not in response:
                    QMessageBox.information(self, "Success", f"Map '{map_data['name']}' created successfully!")
                    self.refresh_data()
                    # Auto-select the new map
                    new_map_id = response.get('id')
                    if new_map_id:
                        index = self.map_selector.findData(new_map_id)
                        if index >= 0:
                            self.map_selector.setCurrentIndex(index)
                            
                            # Create pickup task CSV for the new map
                            try:
                                pickup_task_file = DATA_DIR / f"{new_map_id}_create_pickup_task.csv"
                                if not pickup_task_file.exists():
                                    with open(pickup_task_file, 'w', newline='', encoding='utf-8') as f:
                                        writer = csv.writer(f)
                                        writer.writerow(['stop_id', 'drop_zone', 'action'])
                                    self.logger.info(f"Created pickup task CSV: {pickup_task_file}")
                            except Exception as csv_err:
                                self.logger.error(f"Failed to create pickup task CSV: {csv_err}")

                            # Navigate to zone management tab for new map
                            self.tab_widget.setCurrentIndex(1)  # Zone Management tab
                            self.update_tab_accessibility()
                    return

            # Fallback to CSV
            map_data['id'] = self.csv_handler.get_next_id('maps')

            if self.csv_handler.append_to_csv('maps', map_data):
                QMessageBox.information(self, "Success", f"Map '{map_data['name']}' created!")
                self.refresh_data()
                # Auto-select the new map
                index = self.map_selector.findData(str(map_data['id']))
                if index >= 0:
                    self.map_selector.setCurrentIndex(index)
                    
                    # Create pickup task CSV for the new map
                    try:
                        pickup_task_file = DATA_DIR / f"{map_data['id']}_create_pickup_task.csv"
                        if not pickup_task_file.exists():
                            with open(pickup_task_file, 'w', newline='', encoding='utf-8') as f:
                                writer = csv.writer(f)
                                writer.writerow(['stop_id', 'drop_zone', 'action'])
                            self.logger.info(f"Created pickup task CSV: {pickup_task_file}")
                    except Exception as csv_err:
                        self.logger.error(f"Failed to create pickup task CSV: {csv_err}")

                    # Navigate to zone management tab for new map
                    self.tab_widget.setCurrentIndex(1)  # Zone Management tab
                    self.update_tab_accessibility()
            else:
                raise Exception("Failed to save to CSV")

        except Exception as e:
            self.logger.error(f"Error creating map: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create map: {e}")

    def create_zone_connection(self):
        """Create new zone connection"""
        if not self.selected_map_id:
            QMessageBox.warning(self, "No Map", "Please select a map first")
            return

        from_zone = self.from_zone_input.text().strip()
        to_zone = self.to_zone_input.text().strip()

        if not from_zone or not to_zone:
            QMessageBox.warning(self, "Missing Data", "Please enter both from and to zones")
            return

        zone_data = {
            'map_id': self.selected_map_id,
            'from_zone': from_zone,
            'to_zone': to_zone,
            'magnitude': self.zone_magnitude_input.value(),
            'direction': self.zone_direction_input.currentText()
        }
        
        now = datetime.now().isoformat()

        try:
            if self.zone_edit_mode and self.editing_zone_id:
                # Update existing zone
                zone_data['id'] = self.editing_zone_id
                # Keep original created_at
                existing_zone = next((z for z in self.current_zones if str(z.get('id')) == str(self.editing_zone_id)), {})
                zone_data['created_at'] = existing_zone.get('created_at', now)
                zone_data['edited_at'] = now
                
                # Check for zone renames
                renames = {}
                old_from = str(existing_zone.get('from_zone', ''))
                old_to = str(existing_zone.get('to_zone', ''))
                new_from = str(zone_data['from_zone'])
                new_to = str(zone_data['to_zone'])
                
                if old_from != new_from:
                    renames[old_from] = new_from
                if old_to != new_to:
                    renames[old_to] = new_to
                
                # Update in CSV
                if self.csv_handler.update_csv_row('zones', self.editing_zone_id, zone_data):
                    # Propagate renames if any
                    if renames:
                        self.propagate_zone_renames(self.selected_map_id, renames)
                    QMessageBox.information(self, "Success", "Zone connection updated!")
                    self.load_map_data(self.selected_map_id)
                    self.clear_zone_form()
                    self.update_tab_accessibility()
                else:
                    raise Exception("Failed to update CSV")
            else:
                # Create new zone
                zone_data['id'] = self.csv_handler.get_next_id('zones')
                zone_data['created_at'] = now
                zone_data['edited_at'] = ''
                
                # Try API first if authenticated
                if self.api_client.is_authenticated():
                    response = self.maps_api.create_zone_connection(self.selected_map_id, zone_data)
                    if 'error' not in response:
                        QMessageBox.information(self, "Success", "Zone connection created!")
                        self.load_map_data(self.selected_map_id)
                        self.clear_zone_form()
                        self.update_tab_accessibility()
                        return
                
                # Fallback to CSV
                if self.csv_handler.append_to_csv('zones', zone_data):
                    QMessageBox.information(self, "Success", "Zone connection created!")
                    self.load_map_data(self.selected_map_id)
                    self.clear_zone_form()
                    self.update_tab_accessibility()
                else:
                    raise Exception("Failed to save to CSV")

        except Exception as e:
            self.logger.error(f"Error handling zone: {e}")
            QMessageBox.critical(self, "Error", f"Failed to handle zone: {e}")

    def clear_zone_form(self):
        """Clear zone creation form and reset edit mode"""
        self.from_zone_input.clear()
        self.to_zone_input.clear()
        self.zone_magnitude_input.setValue(50.0)
        self.zone_direction_input.setCurrentIndex(0)
        
        # Reset edit mode
        self.zone_edit_mode = False
        self.editing_zone_id = None
        if hasattr(self, 'zone_form_subtitle'):
            self.zone_form_subtitle.setText("Create New Zone Connection")
        if hasattr(self, 'zone_action_btn'):
            self.zone_action_btn.setText("➕ Create Zone Connection")
            self.zone_action_btn.setStyleSheet(self.zone_action_btn.styleSheet().replace("#10B981", "#ff6b35"))

    def has_zones_configured(self, map_id):
        """Check if the specified map has zones configured"""
        if not map_id:
            return False
        
        zones = self.csv_handler.read_csv('zones')
        map_zones = [z for z in zones if str(z.get('map_id')) == str(map_id)]
        return len(map_zones) > 0

    def update_tab_accessibility(self):
        """Update tab accessibility based on zone configuration"""
        # Store current tab index to preserve it
        current_tab_index = self.tab_widget.currentIndex()
        self.logger.debug(f"Updating tab accessibility - current tab index: {current_tab_index}")
        
        if not self.selected_map_id:
            # No map selected - disable all tabs except overview
            self.tab_widget.setTabEnabled(0, True)   # Map Overview
            self.tab_widget.setTabEnabled(1, False)  # Zone Management
            self.tab_widget.setTabEnabled(2, False)  # Stop Management
            self.tab_widget.setTabEnabled(3, False)  # Rack Configuration
            self.tab_widget.setTabEnabled(4, False)  # Map Settings
            self.tab_widget.setTabEnabled(5, False)  # Zone Alignment setting
            
            # Set tooltips for disabled tabs
            self.tab_widget.setTabToolTip(1, "Select a map first to enable zone management")
            self.tab_widget.setTabToolTip(2, "Select a map first to enable stop management")
            self.tab_widget.setTabToolTip(3, "Select a map first to enable rack configuration")
            self.tab_widget.setTabToolTip(4, "Select a map first to enable map settings")
            self.tab_widget.setTabToolTip(5, "Select a map first to enable zone alignment settings")
            
            # Hide warning label if no map selected
            if hasattr(self, 'zone_warning_label'):
                self.zone_warning_label.setVisible(False)
            
            # If no map is selected, it's okay to be on overview tab
            return
        
        has_zones = self.has_zones_configured(self.selected_map_id)
        
        # Always enable overview and zone management tabs
        self.tab_widget.setTabEnabled(0, True)   # Map Overview
        self.tab_widget.setTabEnabled(1, True)   # Zone Management
        
        # Only enable other tabs if zones are configured
        self.tab_widget.setTabEnabled(2, has_zones)  # Stop Management
        self.tab_widget.setTabEnabled(3, has_zones)  # Rack Configuration
        self.tab_widget.setTabEnabled(4, has_zones)  # Map Settings
        self.tab_widget.setTabEnabled(5, has_zones)  # Zone Alignment setting
        
        # Show/hide warning label and set tooltips
        if hasattr(self, 'zone_warning_label'):
            self.zone_warning_label.setVisible(not has_zones)
        
        if not has_zones:
            self.tab_widget.setTabToolTip(2, "⚠️ Configure zones first to enable stop management")
            self.tab_widget.setTabToolTip(3, "⚠️ Configure zones first to enable rack configuration")
            self.tab_widget.setTabToolTip(4, "⚠️ Configure zones first to enable map settings")
            self.tab_widget.setTabToolTip(5, "⚠️ Configure zones first to enable zone alignment settings")
        else:
            self.tab_widget.setTabToolTip(2, "")
            self.tab_widget.setTabToolTip(3, "")
            self.tab_widget.setTabToolTip(4, "")
            self.tab_widget.setTabToolTip(5, "")
        
        # Restore the current tab index to prevent automatic navigation
        if current_tab_index >= 0 and current_tab_index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(current_tab_index)
            self.logger.debug(f"Restored tab index to: {current_tab_index} in update_tab_accessibility")
        else:
            self.logger.debug(f"Could not restore tab index: {current_tab_index} in update_tab_accessibility")

    def on_zone_selected(self, row):
        """Handle zone selection"""
        if row < len(self.current_zones):
            zone = self.current_zones[row]
            # Populate form with selected zone data
            self.from_zone_input.setText(zone.get('from_zone', ''))
            self.to_zone_input.setText(zone.get('to_zone', ''))
            self.zone_magnitude_input.setValue(float(zone.get('magnitude', 50)))
            
            # Restore direction combo
            direction = zone.get('direction', 'north')  # Default to north only if completely missing
            direction_index = self.zone_direction_input.findText(direction)
            if direction_index >= 0:
                self.zone_direction_input.setCurrentIndex(direction_index)
            else:
                self.zone_direction_input.setCurrentIndex(0)  # Default to first item if not found

    def edit_selected_zone(self):
        """Edit selected zone"""
        current_row = self.zones_table.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a zone to edit")
            return
            
        if current_row < len(self.current_zones):
            zone = self.current_zones[current_row]
            
            # Switch to edit mode
            self.zone_edit_mode = True
            self.editing_zone_id = zone.get('id')
            
            # Populate form
            self.from_zone_input.setText(zone.get('from_zone', ''))
            self.to_zone_input.setText(zone.get('to_zone', ''))
            self.zone_magnitude_input.setValue(float(zone.get('magnitude', 50)))
            
            direction = zone.get('direction', 'north')
            direction_index = self.zone_direction_input.findText(direction)
            if direction_index >= 0:
                self.zone_direction_input.setCurrentIndex(direction_index)
            
            # Update UI to reflect edit mode
            self.zone_form_subtitle.setText("Edit Zone Connection")
            self.zone_action_btn.setText("💾 Update Zone Connection")
            self.zone_action_btn.setStyleSheet(self.zone_action_btn.styleSheet().replace("#ff6b35", "#10B981"))
            
            # Scroll to form
            self.from_zone_input.setFocus()

    def delete_selected_zone(self):
        """Delete selected zone"""
        current_row = self.zones_table.table.currentRow()
        if current_row < len(self.current_zones):
            zone = self.current_zones[current_row]
            zone_name = f"{zone.get('from_zone', '')} → {zone.get('to_zone', '')}"

            reply = QMessageBox.question(
                self, "Confirm Delete",
                f"Delete zone connection '{zone_name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                try:
                    zone_id = zone.get('id')
                    if self.csv_handler.delete_csv_row('zones', zone_id):
                        QMessageBox.information(self, "Success", "Zone deleted!")
                        self.load_map_data(self.selected_map_id)
                        self.update_tab_accessibility()
                    else:
                        raise Exception("Failed to delete from CSV")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to delete zone: {e}")

    def generate_stops(self):
        """Generate stops for selected zone using intelligent position calculation (rack config removed)"""
        # Validate inputs first
        if hasattr(self, 'validate_stop_inputs') and not self.validate_stop_inputs():
            QMessageBox.warning(self, "Invalid Input", "Please fix the issues highlighted in the stop configuration before generating stops.")
            return

        zone_id = self.zone_for_stops_combo.currentData()
        if not zone_id:
            QMessageBox.warning(self, "No Zone", "Please select a zone first")
            return

        try:
            zone = next((z for z in self.current_zones if str(z.get('id')) == str(zone_id)), None)
            if not zone:
                QMessageBox.warning(self, "Error", "Selected zone not found")
                return

            # If Stop Type UI is present, use single-stop generation based on it
            if hasattr(self, 'stop_type_combo') and hasattr(self, 'distance_from_zone_input'):
                st = self.stop_type_combo.currentText().lower()
                dist_m = float(self.distance_from_zone_input.value())
                side_m = float(self.side_distance_input.value()) if st in ('left', 'right') else 0.0

                from_x = zone.get('from_x', 100)
                from_y = zone.get('from_y', 100)
                magnitude = float(zone.get('magnitude', 50))
                direction = zone.get('direction', 'east')
                direction_vectors = {
                    'north': (0, -1),
                    'south': (0, 1),
                    'east': (1, 0),
                    'west': (-1, 0),
                    'northeast': (0.707, -0.707),
                    'northwest': (-0.707, -0.707),
                    'southeast': (0.707, 0.707),
                    'southwest': (-0.707, 0.707)
                }
                dx, dy = direction_vectors.get(direction.lower(), (1, 0))
                to_x = from_x + dx * magnitude
                to_y = from_y + dy * magnitude

                # Clamp distance to the edge length to avoid overshoot in path planning
                dist_m = max(0.0, min(dist_m, magnitude))
                # Compute base along-line position from clamped distance
                progress = 0.0 if magnitude <= 0 else dist_m / magnitude
                base_x = from_x + (to_x - from_x) * progress
                base_y = from_y + (to_y - from_y) * progress

                # Compute lateral offset in pixels (1m ~ 1px in current mapping)
                import math
                seg_dx = to_x - from_x
                seg_dy = to_y - from_y
                seg_len = math.sqrt(seg_dx * seg_dx + seg_dy * seg_dy)
                if seg_len > 0:
                    seg_dx /= seg_len
                    seg_dy /= seg_len
                perp_lx = seg_dy
                perp_ly = -seg_dx
                perp_rx = -seg_dy
                perp_ry = seg_dx
                if st == 'left':
                    disp_x = base_x + perp_lx * side_m
                    disp_y = base_y + perp_ly * side_m
                elif st == 'right':
                    disp_x = base_x + perp_rx * side_m
                    disp_y = base_y + perp_ry * side_m
                else:
                    disp_x = base_x
                    disp_y = base_y
                # Read manual Stop ID and Stop Name
                manual_stop_id = self.stop_id_input.text().strip() if hasattr(self, 'stop_id_input') else ''
                manual_stop_name = self.stop_name_input.text().strip() if hasattr(self, 'stop_name_input') else ''

                # Final guard in case validation was bypassed
                if not manual_stop_id or not manual_stop_name:
                    QMessageBox.warning(self, "Invalid Input", "Stop ID and Stop Name are required.")
                    return

                # Enforce unique stop_id per map (ignore self if editing)
                for existing_stop in self.current_stops:
                    if self.stop_edit_mode and str(existing_stop.get('id')) == str(self.editing_stop_id):
                        continue
                    if str(existing_stop.get('map_id')) == str(self.selected_map_id) and str(existing_stop.get('stop_id', '')).strip() == manual_stop_id:
                        QMessageBox.warning(self, "Duplicate Stop ID", "A stop with this ID already exists on this map.")
                        return

                # Determine side-related values based on stop type
                if st == 'left':
                    left_count = 1
                    right_count = 0
                    left_dist = side_m
                    right_dist = 0.0
                elif st == 'right':
                    left_count = 0
                    right_count = 1
                    left_dist = 0.0
                    right_dist = side_m
                else:
                    left_count = 0
                    right_count = 0
                    left_dist = 0.0
                    right_dist = 0.0

                stop_row = {
                    'zone_connection_id': zone_id,
                    'map_id': self.selected_map_id,
                    'stop_id': manual_stop_id,
                    'name': manual_stop_name,
                    'x_coordinate': disp_x,
                    'y_coordinate': disp_y,
                    'display_x': disp_x,
                    'display_y': disp_y,
                    'left_bins_count': left_count,
                    'right_bins_count': right_count,
                    'left_bins_distance': left_dist,
                    'right_bins_distance': right_dist,
                    'distance_from_start': dist_m,
                    'stop_type': st,
                    'stop_function': (self.stop_function_combo.currentText().strip().lower() if hasattr(self, 'stop_function_combo') else 'pickup'),
                }

                if self.stop_edit_mode:
                    # Update existing stop
                    stop_row['id'] = self.editing_stop_id
                    existing_stop = next((s for s in self.current_stops if str(s.get('id')) == str(self.editing_stop_id)), {})
                    stop_row['created_at'] = existing_stop.get('created_at', datetime.now().isoformat())
                    
                    old_id = existing_stop.get('stop_id')
                    old_name = existing_stop.get('name')
                    
                    if self.csv_handler.update_csv_row('stops', self.editing_stop_id, stop_row):
                        # Propagate changes if ID or name changed
                        if old_id != manual_stop_id or old_name != manual_stop_name:
                            self.propagate_stop_changes(self.selected_map_id, old_id, manual_stop_id, old_name, manual_stop_name)
                        
                        QMessageBox.information(self, "Success", f"Stop '{manual_stop_id}' updated successfully.")
                        self.clear_stop_form()
                        self.load_map_data(self.selected_map_id)
                    else:
                        QMessageBox.warning(self, "Error", "Failed to update stop in CSV.")
                else:
                    # Create new stop
                    stop_row['id'] = self.csv_handler.get_next_id('stops')
                    stop_row['created_at'] = datetime.now().isoformat()
                    
                    if not self.csv_handler.append_to_csv('stops', stop_row):
                        raise Exception("Failed to save stop")

                    QMessageBox.information(self, "Success", f"Generated 1 stop at {dist_m:.2f}m ({st.title()})")
                    self.load_map_data(self.selected_map_id)
                return

            # Fallback to existing exact-bin generation if new UI not present
            from exact_bin_integration import ExactBinIntegration
            integration = ExactBinIntegration()

            from_x = zone.get('from_x', 100)
            from_y = zone.get('from_y', 100)
            magnitude = float(zone.get('magnitude', 50))
            direction = zone.get('direction', 'east')
            direction_vectors = {
                'north': (0, -1),
                'south': (0, 1),
                'east': (1, 0),
                'west': (-1, 0),
                'northeast': (0.707, -0.707),
                'northwest': (-0.707, -0.707),
                'southeast': (0.707, 0.707),
                'southwest': (-0.707, 0.707)
            }
            dx, dy = direction_vectors.get(direction.lower(), (1, 0))
            to_x = from_x + dx * magnitude
            to_y = from_y + dy * magnitude

            zone_data_for_calc = {
                'from_x': from_x,
                'from_y': from_y,
                'to_x': to_x,
                'to_y': to_y,
                'magnitude': magnitude,
                'left_bins_count': self.left_bins_input.value() if hasattr(self, 'left_bins_input') else 0,
                'right_bins_count': self.right_bins_input.value() if hasattr(self, 'right_bins_input') else 0,
                'bin_offset_distance': 2.0,
                'left_bins_distance': self.left_bin_distance_input.value() if hasattr(self, 'left_bin_distance_input') else 0.0,
                'right_bins_distance': self.right_bin_distance_input.value() if hasattr(self, 'right_bin_distance_input') else 0.0,
                'from_zone': zone.get('from_zone', 'A'),
                'to_zone': zone.get('to_zone', 'B')
            }
            exact_result = integration.calculate_bins_for_ui(zone_data_for_calc)
            if not exact_result.get('success'):
                raise Exception("Failed to calculate exact bin positions")
            sequential_stops = exact_result['calculated_bins']['sequential_stops']

            existing_stop_numbers = []
            for existing_stop in self.current_stops:
                stop_id = existing_stop.get('stop_id', '')
                if stop_id.startswith('STOP_'):
                    try:
                        parts = stop_id.split('_')
                        if len(parts) >= 2:
                            stop_number = int(parts[1])
                            existing_stop_numbers.append(stop_number)
                    except (ValueError, IndexError):
                        continue
            next_stop_number = max(existing_stop_numbers) + 1 if existing_stop_numbers else 1

            stops_saved = 0
            for i, stop_info in enumerate(sequential_stops):
                actual_stop_number = next_stop_number + i
                stop_data = {
                    'id': self.csv_handler.get_next_id('stops'),
                    'zone_connection_id': zone_id,
                    'map_id': self.selected_map_id,
                    'stop_id': f"STOP_{actual_stop_number:02d}_{stop_info['side'].upper()}{stop_info['bin_number']}",
                    'name': f"Stop {actual_stop_number} - {stop_info['side'].title()} Bin {stop_info['bin_number']}",
                    'x_coordinate': stop_info['coordinates']['x'],
                    'y_coordinate': stop_info['coordinates']['y'],
                    'display_x': stop_info['coordinates']['x'],
                    'display_y': stop_info['coordinates']['y'],
                    'left_bins_count': self.left_bins_input.value() if hasattr(self, 'left_bins_input') else 0,
                    'right_bins_count': self.right_bins_input.value() if hasattr(self, 'right_bins_input') else 0,
                    'left_bins_distance': self.left_bin_distance_input.value() if hasattr(self, 'left_bin_distance_input') else 0.0,
                    'right_bins_distance': self.right_bin_distance_input.value() if hasattr(self, 'right_bin_distance_input') else 0.0,
                    'distance_from_start': stop_info['distance_from_start'],
                    'created_at': datetime.now().isoformat()
                }
                if self.csv_handler.append_to_csv('stops', stop_data):
                    stops_saved += 1
            success_message = exact_result['message']
            summary_text = "Stop Positioning:"
            for i, stop_info in enumerate(sequential_stops):
                actual_stop_number = next_stop_number + i
                coords = stop_info['coordinates']
                summary_text += f"\nStop {actual_stop_number}: {stop_info['distance_from_start']:.2f}m from start"
                summary_text += f"\n  Position: ({coords['x']:.1f}, {coords['y']:.1f})"
                summary_text += f"\n  Bins: 1 (1 {stop_info['side']}, 0 other)"
            QMessageBox.information(self, "Success", f"{success_message}\n\n{summary_text}")
            self.load_map_data(self.selected_map_id)

        except Exception as e:
            self.logger.error(f"Error generating stops: {e}")
            QMessageBox.critical(self, "Error", f"Failed to generate stops: {e}")

    def save_map_settings(self):
        """Save map settings"""
        if not self.selected_map_id:
            QMessageBox.warning(self, "No Map", "Please select a map first")
            return

        map_data = {
            'name': self.map_name_input.text().strip(),
            'description': self.map_description_input.toPlainText().strip(),
            'width': self.map_width_input.value(),
            'height': self.map_height_input.value(),
            'meter_in_pixels': self.map_meter_input.value()
        }

        if not map_data['name']:
            QMessageBox.warning(self, "Error", "Map name is required")
            return

        try:
            # Try API first
            if self.api_client.is_authenticated():
                response = self.maps_api.update_map(self.selected_map_id, map_data)
                if 'error' not in response:
                    QMessageBox.information(self, "Success", "Map settings saved!")
                    self.refresh_data()
                    return

            # Fallback to CSV
            if self.csv_handler.update_csv_row('maps', self.selected_map_id, map_data):
                QMessageBox.information(self, "Success", "Map settings saved!")
                self.refresh_data()
            else:
                raise Exception("Failed to update CSV")

        except Exception as e:
            self.logger.error(f"Error saving map: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save map: {e}")

    def delete_current_map(self):
        """Delete current map"""
        if not self.selected_map_id:
            return

        selected_map = next((m for m in self.current_maps if str(m.get('id')) == str(self.selected_map_id)), None)
        map_name = selected_map.get('name', 'Unknown') if selected_map else 'Unknown'

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete map '{map_name}'?\n\nThis will also delete all zones, stops, and stop groups.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                # Delete from CSV
                if self.csv_handler.delete_csv_row('maps', self.selected_map_id):
                    # Delete related data
                    self.delete_map_related_data(self.selected_map_id)
                    QMessageBox.information(self, "Success", "Map deleted!")
                    self.selected_map_id = None
                    self.refresh_data()
                else:
                    raise Exception("Failed to delete from CSV")

            except Exception as e:
                self.logger.error(f"Error deleting map: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete map: {e}")

    def delete_map_related_data(self, map_id):
        """Delete all data related to a map"""
        try:
            # Get current data
            zones = self.csv_handler.read_csv('zones')
            stops = self.csv_handler.read_csv('stops')
            stop_groups = self.csv_handler.read_csv('stop_groups')

            # Filter out data for this map
            zones = [z for z in zones if str(z.get('map_id')) != str(map_id)]
            stops = [s for s in stops if str(s.get('map_id')) != str(map_id)]
            stop_groups = [sg for sg in stop_groups if str(sg.get('map_id')) != str(map_id)]

            # Write back filtered data
            self.csv_handler.write_csv('zones', zones)
            self.csv_handler.write_csv('stops', stops)
            self.csv_handler.write_csv('stop_groups', stop_groups)

        except Exception as e:
            self.logger.error(f"Error deleting related data: {e}")

    def propagate_zone_renames(self, map_id, renames):
        """
        Rename zones across all data files for a specific map.
        renames: dict {old_name: new_name}
        """
        if not renames:
            return

        self.logger.info(f"Propagating zone renames for map {map_id}: {renames}")

        try:
            # 1. Update other zone connections for this map
            zones = self.csv_handler.read_csv('zones')
            zones_updated = False
            for z in zones:
                if str(z.get('map_id')) == str(map_id):
                    fz = str(z.get('from_zone'))
                    tz = str(z.get('to_zone'))
                    if fz in renames:
                        z['from_zone'] = renames[fz]
                        zones_updated = True
                    if tz in renames:
                        z['to_zone'] = renames[tz]
                        zones_updated = True
            
            if zones_updated:
                self.csv_handler.write_csv('zones', zones)

            # 2. Update charging stations
            charging_zones = self.csv_handler.read_csv('charging_zones')
            charging_updated = False
            for cz in charging_zones:
                if str(cz.get('map_id')) == str(map_id):
                    zname = str(cz.get('zone'))
                    if zname in renames:
                        cz['zone'] = renames[zname]
                        charging_updated = True
            
            if charging_updated:
                self.csv_handler.write_csv('charging_zones', charging_zones)
                if hasattr(self, 'populate_charging_zones_table'):
                    self.populate_charging_zones_table()

            # 3. Update tasks
            tasks = self.csv_handler.read_csv('tasks')
            tasks_updated = False
            for t in tasks:
                row_map_id = str(t.get('map_id', ''))
                details_raw = t.get('task_details', '{}')
                try:
                    details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
                except:
                    details = {}

                task_map_id = row_map_id or str(details.get('pickup_map_id', '')) or str(details.get('charging_map_id', ''))
                
                if str(map_id) == str(task_map_id):
                    details_changed = False
                    
                    # Update drop_zone_name and charging_station in details
                    for key in ['drop_zone', 'drop_zone_name', 'charging_station']:
                        if key in details and str(details[key]) in renames:
                            details[key] = renames[str(details[key])]
                            details_changed = True
                    
                    if details_changed:
                        t['task_details'] = json.dumps(details)
                        tasks_updated = True
            
            if tasks_updated:
                self.csv_handler.write_csv('tasks', tasks)

            # 4. Update racks
            racks = self.csv_handler.read_csv('racks')
            racks_updated = False
            selected_map = next((m for m in self.current_maps if str(m.get('id')) == str(map_id)), None)
            map_name = selected_map.get('name', '') if selected_map else ''
            
            if map_name:
                for r in racks:
                    if str(r.get('map_name')) == map_name:
                        zn = str(r.get('zone_name'))
                        for old, new in renames.items():
                            parts = zn.split(" -> ")
                            if len(parts) == 2:
                                changed = False
                                if parts[0] == old:
                                    parts[0] = new
                                    changed = True
                                if parts[1] == old:
                                    parts[1] = new
                                    changed = True
                                if changed:
                                    r['zone_name'] = " -> ".join(parts)
                                    racks_updated = True
                if racks_updated:
                    self.csv_handler.write_csv('racks', racks)

        except Exception as e:
            self.logger.error(f"Error propagating zone renames: {e}")

    def on_stop_selected(self, stop_data):
        """Handle stop selection from map viewer"""
        # This will be implemented when map viewer is improved
        pass

    def sync_with_api(self):
        """Sync maps with API"""
        if not self.api_client.is_authenticated():
            QMessageBox.warning(self, "Not Connected", "Please connect to API first")
            return

        try:
            success = self.sync_manager.sync_data_type('maps')
            if success:
                QMessageBox.information(self, "Success", "Maps synced successfully!")
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Sync Failed", "Failed to sync maps")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Sync error: {e}")
    
    def create_stop_controls_section(self):
        """Create horizontal stop controls section (rack distances removed)"""
        controls_frame = QFrame()
        controls_frame.setStyleSheet("""
            QFrame {
                background-color: #353535;
                border: 1px solid #555555;
                border-radius: 6px;
                padding: 3px;
            }
        """)
        controls_frame.setSizePolicy(controls_frame.sizePolicy().Expanding, controls_frame.sizePolicy().Preferred)
        
        main_layout = QHBoxLayout(controls_frame)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        
        # Left side - Basic stop configuration
        left_panel = self.create_basic_stop_config_panel()
        left_panel.setSizePolicy(left_panel.sizePolicy().Expanding, left_panel.sizePolicy().Preferred)
        main_layout.addWidget(left_panel, 1)
        
        return controls_frame
    
    def create_basic_stop_config_panel(self):
        """Create basic stop configuration panel with presets and validation"""
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #404040;
                border: 1px solid #666666;
                border-radius: 8px;
                padding: 4px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Title with better styling
        title = QLabel("Basic Configuration")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #ff6b35; border: none; margin-bottom: 3px;")
        layout.addWidget(title)
        
        # Form layout for inputs with improved spacing
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form_layout.setVerticalSpacing(5)
        form_layout.setHorizontalSpacing(5)
        form_layout.setContentsMargins(0, 0, 0, 0)
        
        # Zone selection with validation indicator and improved styling
        zone_frame = QFrame()
        zone_frame.setStyleSheet("background-color: #454545; border-radius: 6px; padding: 6px;")
        zone_layout = QHBoxLayout(zone_frame)
        zone_layout.setContentsMargins(6, 6, 6, 6)
        zone_layout.setSpacing(8)
        
        self.zone_for_stops_combo = QComboBox()
        self.zone_for_stops_combo.addItem("Select Zone", "")
        self.zone_for_stops_combo.currentTextChanged.connect(self.validate_stop_inputs)
        
        # Enhanced combo box styling for better visibility and functionality
        self.zone_for_stops_combo.setStyleSheet("""
            QComboBox {
                background-color: #505050;
                border: 2px solid #666666;
                padding: 8px 10px;
                border-radius: 6px;
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
                min-width: 200px;
                min-height: 26px;
            }
            QComboBox:hover {
                border: 2px solid #ff6b35;
                background-color: #555555;
            }
            QComboBox:focus {
                border: 2px solid #ff6b35;
                background-color: #555555;
            }
            QComboBox::drop-down {
                border: 0px;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: url(:/icons/dropdown.png);
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #ff6b35;
                selection-color: white;
                border: 2px solid #666666;
                outline: none;
                padding: 4px;
                font-size: 13px;
            }
            QComboBox QAbstractItemView::item {
                padding: 12px 8px;
                border-bottom: 1px solid #666666;
                min-height: 25px;
            }
            QComboBox QAbstractItemView::item:hover {
                background-color: #ff6b35;
                color: #ffffff;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #ff6b35;
                color: #ffffff;
                font-weight: bold;
            }
        """)
        
        zone_layout.addWidget(self.zone_for_stops_combo)
        
        self.zone_validation_icon = QLabel("⚠️")
        self.zone_validation_icon.setStyleSheet("""
            color: #ff6b35; 
            font-size: 18px; 
            background-color: #505050; 
            border-radius: 4px; 
            padding: 8px;
        """)
        self.zone_validation_icon.setToolTip("Please select a zone")
        self.zone_validation_icon.setAlignment(Qt.AlignCenter)
        self.zone_validation_icon.setFixedSize(28, 28)
        zone_layout.addWidget(self.zone_validation_icon)
        
        form_layout.addRow("Zone:", zone_frame)
        
        # Stop ID (manual, required and unique per map)
        self.stop_id_input = QLineEdit()
        self.stop_id_input.setPlaceholderText("Enter unique Stop ID for this map")
        self.apply_input_style(self.stop_id_input)
        apply_no_special_chars_validator(self.stop_id_input)
        self.stop_id_input.textChanged.connect(self.validate_stop_inputs)
        form_layout.addRow("Stop ID *:", self.stop_id_input)
        
        # Stop Name (manual, required)
        self.stop_name_input = QLineEdit()
        self.stop_name_input.setPlaceholderText("Enter Stop Name")
        self.apply_input_style(self.stop_name_input)
        self.stop_name_input.textChanged.connect(self.validate_stop_inputs)
        form_layout.addRow("Stop Name *:", self.stop_name_input)
        
        # Stop type selection
        self.stop_type_combo = QComboBox()
        self.stop_type_combo.addItems(["Center", "Left", "Right"])
        self.stop_type_combo.currentTextChanged.connect(self.validate_stop_inputs)
        self.stop_type_combo.currentTextChanged.connect(self.update_stop_type_fields)
        self.apply_combo_style(self.stop_type_combo)
        form_layout.addRow("Stop Type:", self.stop_type_combo)

        # Stop function (logical operation)
        # This is used later in task creation to show only the right stops under Pickup/Check/Drop.
        self.stop_function_combo = QComboBox()
        self.stop_function_combo.addItems(["Pickup", "Check", "Drop", "Charging"])
        self.stop_function_combo.currentTextChanged.connect(self.validate_stop_inputs)
        self.apply_combo_style(self.stop_function_combo)
        form_layout.addRow("Stop Function:", self.stop_function_combo)
        
        # Distance from zone (meters)
        self.distance_from_zone_label = QLabel("Distance from Zone (m)")
        self.distance_from_zone_input = QDoubleSpinBox()
        self.distance_from_zone_input.setRange(0.0, 10000.0)
        self.distance_from_zone_input.setDecimals(2)
        self.distance_from_zone_input.setSingleStep(0.1)
        self.distance_from_zone_input.setValue(1.0)
        self.apply_input_style(self.distance_from_zone_input)
        form_layout.addRow(self.distance_from_zone_label, self.distance_from_zone_input)
        
        # Side distance (meters) - shown only for Left/Right
        self.side_distance_label = QLabel("Side Distance (m)")
        self.side_distance_input = QDoubleSpinBox()
        self.side_distance_input.setRange(0.0, 10000.0)
        self.side_distance_input.setDecimals(2)
        self.side_distance_input.setSingleStep(0.1)
        self.side_distance_input.setValue(2.0)
        self.apply_input_style(self.side_distance_input)
        form_layout.addRow(self.side_distance_label, self.side_distance_input)
        
        # Initialize visibility based on default Stop Type selection
        self.update_stop_type_fields()
        
        # Rack levels configuration removed
        
        # Add some spacing between form and validation
        layout.addLayout(form_layout)
        layout.addSpacing(6)
        
        # Validation summary with improved styling
        self.validation_label = QLabel("")
        self.validation_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 11px;
                padding: 6px;
                background-color: rgba(255, 107, 53, 0.2);
                border-radius: 6px;
                border: 1px solid #ff6b35;
                margin-top: 6px;
            }
        """)
        self.validation_label.setWordWrap(True)
        self.validation_label.setAlignment(Qt.AlignCenter)
        self.validation_label.hide()
        layout.addWidget(self.validation_label)
        
        # Add spacing before generate button
        layout.addSpacing(10)
        
        # Info text
        info = QLabel("Configure parameters and click to generate warehouse stops.")
        info.setWordWrap(True)
        info.setStyleSheet("""
            color: #cccccc;
            font-size: 12px;
            padding: 10px;
            text-align: center;
        """)
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        
        # Generate button
        self.generate_btn = QPushButton("🔧 Generate Stops")
        self.generate_btn.clicked.connect(self.generate_stops)
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #12c482, stop: 1 #0ea86f);
                color: white;
                border: none;
                padding: 15px 25px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #0ea86f, stop: 1 #059669);
            }
        """)
        layout.addWidget(self.generate_btn)
        
        return panel
    
    # Rack distances panel removed
    
    def create_stop_details_section(self):
        """Create a section to display stop details in a table format with dedicated scroll bar"""
        # Create the section widget
        stop_details_widget = QWidget()
        stop_details_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        stop_details_layout = QVBoxLayout(stop_details_widget)
        stop_details_layout.setContentsMargins(15, 15, 15, 15)
        stop_details_layout.setSpacing(10)

        # Create title and summary section
        title_layout = QHBoxLayout()
        
        # Title label
        title_label = QLabel("Stop Details")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        title_label.setStyleSheet("color: #ff6b35; margin-bottom: 10px;")
        title_layout.addWidget(title_label)
        
        title_layout.addStretch()
        
        # Summary statistics
        self.stop_summary_label = QLabel("Total Stops: 0 | Active: 0 | Total Bins: 0")
        self.stop_summary_label.setStyleSheet("""
            color: #cccccc; 
            font-size: 12px; 
            font-weight: bold; 
            background-color: #454545; 
            padding: 8px 12px; 
            border-radius: 6px; 
            border: 1px solid #666666;
        """)
        title_layout.addWidget(self.stop_summary_label)
        
        stop_details_layout.addLayout(title_layout)

        # Create the stop details table using DataTableWidget with enhanced scroll functionality
        self.stop_details_table = DataTableWidget([
            "Stop ID", "Stop Name", "Distance (m)",
            "Side Dist (m)", "Created", "Actions"
        ], searchable=False, selectable=True)
        
        # Configure Actions column width
        actions_header = self.stop_details_table.table.horizontalHeader()
        actions_header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.stop_details_table.table.setColumnWidth(5, 180) # Wide enough for Edit/Delete text buttons
        
        # Configure table size and scroll behavior for optimal scroll bar visibility
        self.stop_details_table.setMinimumHeight(250)  # Minimum height to ensure scroll bar appears
        self.stop_details_table.setMaximumHeight(400)  # Maximum height to force scroll bar when needed
        
        # Configure the internal table widget for dedicated scroll bar functionality
        table_widget = self.stop_details_table.table
        table_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table_widget.verticalHeader().setDefaultSectionSize(45)
        table_widget.verticalHeader().setVisible(False)
        
        # Force vertical scroll bar to always be visible for consistent UI
        table_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        table_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Enhanced scroll bar styling with better visibility
        enhanced_scroll_style = """
            QTableWidget {
                background-color: #404040;
                alternate-background-color: #454545;
                gridline-color: #555555;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 6px;
            }
            QTableWidget::item {
                padding: 8px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #ff6b35;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                padding: 12px 8px;
                border: 1px solid #666666;
                font-weight: bold;
                font-size: 12px;
                color: #ff6b35;
                margin: 1px;
                border-radius: 3px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QScrollBar:vertical {
                background-color: #353535;
                width: 16px;
                border-radius: 8px;
                margin: 2px;
                border: 1px solid #555555;
            }
            QScrollBar::handle:vertical {
                background-color: #ff6b35;
                border-radius: 6px;
                min-height: 30px;
                margin: 2px;
                border: 1px solid #e55a2b;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #e55a2b;
                border: 1px solid #d14d21;
            }
            QScrollBar::handle:vertical:pressed {
                background-color: #d14d21;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                background-color: #353535;
                height: 16px;
                border-radius: 8px;
                margin: 2px;
                border: 1px solid #555555;
            }
            QScrollBar::handle:horizontal {
                background-color: #ff6b35;
                border-radius: 6px;
                min-width: 30px;
                margin: 2px;
                border: 1px solid #e55a2b;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #e55a2b;
                border: 1px solid #d14d21;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                background: transparent;
            }
        """
        
        table_widget.setStyleSheet(enhanced_scroll_style)
        
        # Ensure scroll bars update properly when data changes
        table_widget.verticalScrollBar().setVisible(True)
        
        # Add the table to the layout with stretch factor to allow expansion
        stop_details_layout.addWidget(self.stop_details_table, 1)

        # Style the section widget with better contrast
        stop_details_widget.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border: 2px solid #ff6b35;
                border-radius: 10px;
                margin: 5px;
            }
        """)

        return stop_details_widget

    def calculate_stop_distances(self):
        """Calculate distance_from_start for stops that don't have it"""
        import math
        
        # Get zones for this map
        zones = self.current_zones
        if not zones:
            return
            
        # Group stops by zone_connection_id
        stops_by_zone = {}
        for stop in self.current_stops:
            zone_id = stop.get('zone_connection_id')
            if zone_id:
                if zone_id not in stops_by_zone:
                    stops_by_zone[zone_id] = []
                stops_by_zone[zone_id].append(stop)
        
        # Calculate distances for each zone's stops
        for zone_id, zone_stops in stops_by_zone.items():
            # Find the corresponding zone
            zone = next((z for z in zones if str(z.get('id')) == str(zone_id)), None)
            if not zone:
                continue
                
            # Get zone start and end coordinates
            from_x = float(zone.get('from_x', 100))
            from_y = float(zone.get('from_y', 100))
            magnitude = float(zone.get('magnitude', 50))
            direction = zone.get('direction', 'east')
            
            # Calculate end coordinates based on direction
            direction_vectors = {
                'north': (0, -1),   # UP (negative Y)
                'south': (0, 1),    # DOWN (positive Y)
                'east': (1, 0),     # RIGHT (positive X)
                'west': (-1, 0),    # LEFT (negative X)
                'northeast': (0.707, -0.707), 
                'northwest': (-0.707, -0.707),
                'southeast': (0.707, 0.707), 
                'southwest': (-0.707, 0.707)
            }
            
            dx, dy = direction_vectors.get(direction.lower(), (1, 0))
            to_x = from_x + dx * magnitude
            to_y = from_y + dy * magnitude
            
            # Calculate path vector
            path_dx = to_x - from_x
            path_dy = to_y - from_y
            path_length = math.sqrt(path_dx * path_dx + path_dy * path_dy)
            
            if path_length == 0:
                continue
                
            # Normalize path vector
            path_dx /= path_length
            path_dy /= path_length
            
            # Calculate distance for each stop
            for stop in zone_stops:
                # Skip if distance already calculated
                if stop.get('distance_from_start') and stop.get('distance_from_start') != 'N/A':
                    continue
                    
                # Get stop coordinates
                stop_x = float(stop.get('x_coordinate', stop.get('display_x', 0)))
                stop_y = float(stop.get('y_coordinate', stop.get('display_y', 0)))
                
                # Calculate projection onto the path
                # Vector from start to stop
                stop_dx = stop_x - from_x
                stop_dy = stop_y - from_y
                
                # Project onto path vector
                distance = stop_dx * path_dx + stop_dy * path_dy
                
                # Ensure distance is within bounds
                distance = max(0, min(distance, magnitude))
                
                # Update the stop data
                stop['distance_from_start'] = distance
                
                # Also update the CSV file
                self.csv_handler.update_csv_row('stops', stop.get('id'), {'distance_from_start': distance})

    def refresh_stop_details_table(self):
        """Refresh the stop details table with current map's stops"""
        if not hasattr(self, 'stop_details_table'):
            return
            
        # Clear existing data
        self.stop_details_table.clear_data()
        
        if not self.selected_map_id:
            # No map selected - show empty table
            if hasattr(self, 'stop_summary_label'):
                self.stop_summary_label.setText("Total Stops: 0 | Active: 0 | Total Bins: 0")
            return
            
        if not self.current_stops:
            # Map selected but no stops - show message row
            self.stop_details_table.set_data([["No stops available", "Generate stops using the controls above", "", "", ""]])
            
            # Update summary for no stops
            if hasattr(self, 'stop_summary_label'):
                self.stop_summary_label.setText("Total Stops: 0 | Active: 0 | Total Bins: 0")
            return
            
        # Calculate distances for stops that don't have them
        self.calculate_stop_distances()
            
        # Calculate summary statistics
        total_stops = len(self.current_stops)
        active_stops = sum(1 for stop in self.current_stops if stop.get('x_coordinate') and stop.get('y_coordinate'))
        total_bins = sum(
            (int(stop.get('left_bins_count', 0)) + int(stop.get('right_bins_count', 0))) 
            for stop in self.current_stops
        )
        
        # Update summary label
        if hasattr(self, 'stop_summary_label'):
            self.stop_summary_label.setText(f"Total Stops: {total_stops} | Active: {active_stops} | Total Bins: {total_bins}")
        
        # Prepare data for DataTableWidget
        table_data = []
        for stop in self.current_stops:
            # Stop ID
            stop_id = stop.get('stop_id', 'N/A')
            
            # Stop Name
            stop_name = stop.get('name', 'Unnamed Stop')
            
            # X Coordinate
            x_coord = stop.get('x_coordinate', stop.get('display_x', 'N/A'))
            x_coord_str = f"{x_coord:.2f}" if isinstance(x_coord, (int, float)) else str(x_coord)
            
            # Y Coordinate
            y_coord = stop.get('y_coordinate', stop.get('display_y', 'N/A'))
            y_coord_str = f"{y_coord:.2f}" if isinstance(y_coord, (int, float)) else str(y_coord)
            
            # Distance from Start
            distance = stop.get('distance_from_start', 'N/A')
            distance_str = f"{distance:.2f}m" if isinstance(distance, (int, float)) else str(distance)
            
            # Left/Right bins distance (robust parsing from CSV strings)
            def _to_float(value):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
            left_dist_raw = stop.get('left_bins_distance', 'N/A')
            right_dist_raw = stop.get('right_bins_distance', 'N/A')
            left_dist_val = _to_float(left_dist_raw)
            right_dist_val = _to_float(right_dist_raw)
            left_dist = left_dist_val if left_dist_val is not None else left_dist_raw
            right_dist = right_dist_val if right_dist_val is not None else right_dist_raw
            left_dist_str = f"{left_dist_val:.1f}m" if left_dist_val is not None else str(left_dist_raw)
            right_dist_str = f"{right_dist_val:.1f}m" if right_dist_val is not None else str(right_dist_raw)

            # Side Distance based on stop_type field (left/right/center)
            side_distance_value = None
            try:
                stop_type = str(stop.get('stop_type', '')).lower()
                if stop_type == 'right':
                    side_distance_value = right_dist_val
                elif stop_type == 'left':
                    side_distance_value = left_dist_val
                # center type or no type means no side distance
            except Exception:
                side_distance_value = None
            side_dist_str = f"{side_distance_value:.1f}" if side_distance_value is not None else "N/A"
            
            # Created Date/Time
            created_at = stop.get('created_at', 'N/A')
            if created_at and created_at != 'N/A':
                try:
                    # Format the datetime for better display
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    formatted_date = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    formatted_date = created_at[:19] if len(created_at) >= 19 else created_at
            else:
                formatted_date = 'N/A'
            
            # Add row data (empty string for Actions column)
            table_data.append([
                str(stop_id), str(stop_name), distance_str,
                side_dist_str, formatted_date, ""
            ])
        
        # Set data in DataTableWidget
        self.stop_details_table.set_data(table_data)

        # Add Action buttons (Edit/Delete)
        for row, stop in enumerate(self.current_stops):
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(5, 5, 5, 5)
            actions_layout.setSpacing(4)

            edit_btn = QPushButton("✏️ Edit")
            edit_btn.setToolTip("Edit Stop")
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3B82F6;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2563EB;
                }
            """)
            edit_btn.clicked.connect(lambda checked, s=stop: self.edit_selected_stop(s))
            actions_layout.addWidget(edit_btn)

            delete_btn = QPushButton("🗑️ Delete")
            delete_btn.setToolTip("Delete Stop")
            delete_btn.setCursor(Qt.PointingHandCursor)
            delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #EF4444;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #DC2626;
                }
            """)
            delete_btn.clicked.connect(lambda checked, s_id=stop.get('id'): self.delete_selected_stop(s_id))
            actions_layout.addWidget(delete_btn)

            self.stop_details_table.table.setCellWidget(row, 5, actions_widget)


    # ===== HELPER METHODS =====
    
    def match_bin_counts(self):
        """Match right bins to left bins count"""
        left_count = self.left_bins_input.value()
        self.right_bins_input.setValue(left_count)
        self.validate_stop_inputs()
    
    def update_stop_type_fields(self):
        """Show or hide side distance field based on selected stop type"""
        st = self.stop_type_combo.currentText().lower() if hasattr(self, 'stop_type_combo') else 'center'
        show_side = st in ('left', 'right')
        if hasattr(self, 'side_distance_label'):
            self.side_distance_label.setVisible(show_side)
        if hasattr(self, 'side_distance_input'):
            self.side_distance_input.setVisible(show_side)
            self.side_distance_input.setEnabled(show_side)
            if not show_side:
                self.side_distance_input.setValue(0.0)
    
    # Rack level change and height preview removed
    
    def validate_stop_inputs(self):
        """Validate stop generation inputs and show feedback"""
        issues = []
        
        # Check zone selection
        if not self.zone_for_stops_combo.currentData():
            issues.append("No zone selected")
            self.zone_validation_icon.show()
        else:
            self.zone_validation_icon.hide()
        
        # Validate manual Stop ID (required and unique per map)
        if hasattr(self, 'stop_id_input'):
            stop_id_text = self.stop_id_input.text().strip()
            if not stop_id_text:
                issues.append("Stop ID is required")
            else:
                for existing_stop in getattr(self, 'current_stops', []):
                    # If editing, ignore the stop being edited
                    if self.stop_edit_mode and str(existing_stop.get('id')) == str(self.editing_stop_id):
                        continue
                        
                    if str(existing_stop.get('map_id')) == str(self.selected_map_id) and str(existing_stop.get('stop_id', '')).strip() == stop_id_text:
                        issues.append(f"Stop ID '{stop_id_text}' already exists on this map")
                        break

        # Validate manual Stop Name (required)
        if hasattr(self, 'stop_name_input'):
            if not self.stop_name_input.text().strip():
                issues.append("Stop Name is required")
        
        # Validate stop type related fields
        if hasattr(self, 'stop_type_combo') and hasattr(self, 'distance_from_zone_input'):
            st = self.stop_type_combo.currentText().lower()
            if self.distance_from_zone_input.value() < 0:
                issues.append("Distance from zone must be >= 0m")
            if st in ('left', 'right'):
                if hasattr(self, 'side_distance_input') and self.side_distance_input.value() <= 0:
                    issues.append("Side distance must be > 0m for Left/Right")
        
        # Update validation display
        if issues:
            self.validation_label.setText("Issues: " + "; ".join(issues))
            self.validation_label.show()
        else:
            self.validation_label.hide()
        
        return len(issues) == 0

    def edit_selected_stop(self, stop):
        """Enter stop edit mode with selected stop data"""
        self.stop_edit_mode = True
        self.editing_stop_id = stop.get('id')
        
        # Populate form
        stop_id = stop.get('stop_id', '')
        self.stop_id_input.setText(stop_id)
        self.stop_name_input.setText(stop.get('name', ''))
        
        st = stop.get('stop_type', 'center').lower()
        idx = self.stop_type_combo.findText(st.title())
        if idx >= 0:
            self.stop_type_combo.setCurrentIndex(idx)

        # Stop function (pickup/check/drop/charging)
        if hasattr(self, 'stop_function_combo'):
            sf = (stop.get('stop_function') or 'pickup').strip().lower()
            sf_idx = self.stop_function_combo.findText(sf.title())
            if sf_idx >= 0:
                self.stop_function_combo.setCurrentIndex(sf_idx)
            else:
                self.stop_function_combo.setCurrentIndex(0)
            
        self.distance_from_zone_input.setValue(float(stop.get('distance_from_start', 1.0)))
        
        if st == 'left':
            self.side_distance_input.setValue(float(stop.get('left_bins_distance', 2.0)))
        elif st == 'right':
            self.side_distance_input.setValue(float(stop.get('right_bins_distance', 2.0)))
        else:
            self.side_distance_input.setValue(0.0)
            
        # Select the zone in combo
        zone_id = stop.get('zone_connection_id')
        idx = self.zone_for_stops_combo.findData(zone_id)
        if idx >= 0:
            self.zone_for_stops_combo.setCurrentIndex(idx)
            
        # Update UI
        if hasattr(self, 'generate_btn'):
            self.generate_btn.setText("💾 Update Stop")
            self.generate_btn.setStyleSheet(self.generate_btn.styleSheet().replace("#12c482", "#ff6b35").replace("#0ea86f", "#e55a2b"))
        
        # Focus on Stop ID
        self.stop_id_input.setFocus()

    def clear_stop_form(self):
        """Reset stop form and exit edit mode"""
        self.stop_edit_mode = False
        self.editing_stop_id = None
        
        self.stop_id_input.clear()
        self.stop_name_input.clear()
        self.stop_type_combo.setCurrentIndex(0)
        if hasattr(self, 'stop_function_combo'):
            self.stop_function_combo.setCurrentIndex(0)
        self.distance_from_zone_input.setValue(1.0)
        self.side_distance_input.setValue(2.0)
        self.zone_for_stops_combo.setCurrentIndex(0)
        
        if hasattr(self, 'generate_btn'):
            self.generate_btn.setText("🔧 Generate Stops")
            self.generate_btn.setStyleSheet(self.generate_btn.styleSheet().replace("#ff6b35", "#12c482").replace("#e55a2b", "#0ea86f"))

    def delete_selected_stop(self, stop_db_id):
        """Delete stop and propagate changes"""
        if not stop_db_id:
            return
            
        # Find stop
        stop = next((s for s in self.current_stops if str(s.get('id')) == str(stop_db_id)), None)
        if not stop:
            return
            
        stop_id = stop.get('stop_id')
        stop_name = stop.get('name')
        
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete stop '{stop_name}' ({stop_id})?\n\nThis will remove it from all tasks, racks, and groups.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.csv_handler.delete_csv_row('stops', stop_db_id):
                self.propagate_stop_deletion(self.selected_map_id, stop_id)
                QMessageBox.information(self, "Success", f"Stop '{stop_id}' deleted successfully.")
                self.load_map_data(self.selected_map_id)
            else:
                QMessageBox.warning(self, "Error", "Failed to delete stop from CSV.")

    def propagate_stop_changes(self, map_id, old_id, new_id, old_name, new_name):
        """Synchronize stop renaming across all modules"""
        if not old_id: return
        self.logger.info(f"Propagating stop changes for map {map_id}: {old_id} -> {new_id}")
        
        # 1. Update Racks
        racks = self.csv_handler.read_csv('racks')
        racks_updated = False
        selected_map = next((m for m in self.current_maps if str(m.get('id')) == str(map_id)), None)
        map_name = selected_map.get('name', '') if selected_map else ''
        
        for r in racks:
            if str(r.get('map_name')) == map_name and str(r.get('stop_id')) == str(old_id):
                r['stop_id'] = new_id
                racks_updated = True
        if racks_updated:
            self.csv_handler.write_csv('racks', racks)
            
        # 2. Update SKU Locations
        skus = self.csv_handler.read_csv('sku_location')
        skus_updated = False
        for s in skus:
            if str(s.get('map_name')) == map_name and str(s.get('stop_id')) == str(old_id):
                s['stop_id'] = new_id
                skus_updated = True
        if skus_updated:
            self.csv_handler.write_csv('sku_location', skus)
            
        # 3. Update Stop Groups
        groups = self.csv_handler.read_csv('stop_groups')
        groups_updated = False
        for g in groups:
            if str(g.get('map_id')) == str(map_id):
                stop_ids = g.get('stop_ids', '').split(',')
                if old_id in stop_ids:
                    stop_ids = [new_id if sid == old_id else sid for sid in stop_ids]
                    g['stop_ids'] = ','.join(stop_ids)
                    groups_updated = True
        if groups_updated:
            self.csv_handler.write_csv('stop_groups', groups)
            
        # 4. Update Tasks
        tasks = self.csv_handler.read_csv('tasks')
        tasks_updated = False
        for t in tasks:
            if str(t.get('map_id')) == str(map_id):
                # Update stop_ids column
                t_stop_ids = t.get('stop_ids', '').split(',')
                if old_id in t_stop_ids:
                    t_stop_ids = [new_id if sid == old_id else sid for sid in t_stop_ids]
                    t['stop_ids'] = ','.join(t_stop_ids)
                    tasks_updated = True
                
                # Update task_details JSON
                details_raw = t.get('task_details', '{}')
                try:
                    details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
                    changed = False
                    
                    # Update pickup_stops
                    if 'pickup_stops' in details:
                        if old_id in details['pickup_stops']:
                            details['pickup_stops'] = [new_id if sid == old_id else sid for sid in details['pickup_stops']]
                            changed = True
                    
                    # Update pickup_stop_names
                    if 'pickup_stop_names' in details:
                        old_display = f"Stop {old_id}" # Simplistic, but sometimes used
                        for i, name in enumerate(details['pickup_stop_names']):
                            if old_id in name or old_name in name:
                                details['pickup_stop_names'][i] = name.replace(old_id, new_id).replace(old_name, new_name)
                                changed = True
                    
                    if changed:
                        t['task_details'] = json.dumps(details)
                        tasks_updated = True
                except:
                    pass
        if tasks_updated:
            self.csv_handler.write_csv('tasks', tasks)

    def propagate_stop_deletion(self, map_id, stop_id):
        """Remove stop references across all modules"""
        if not stop_id: return
        
        # 1. Update Racks (maybe flag?)
        racks = self.csv_handler.read_csv('racks')
        racks = [r for r in racks if not (str(r.get('stop_id')) == str(stop_id))]
        self.csv_handler.write_csv('racks', racks)
            
        # 2. Update SKU Locations
        skus = self.csv_handler.read_csv('sku_location')
        skus = [s for s in skus if not (str(s.get('stop_id')) == str(stop_id))]
        self.csv_handler.write_csv('sku_location', skus)
            
        # 3. Update Stop Groups
        groups = self.csv_handler.read_csv('stop_groups')
        for g in groups:
            if str(g.get('map_id')) == str(map_id):
                stop_ids = g.get('stop_ids', '').split(',')
                if stop_id in stop_ids:
                    stop_ids.remove(stop_id)
                    g['stop_ids'] = ','.join(stop_ids)
        self.csv_handler.write_csv('stop_groups', groups)
            
        # 4. Update Tasks (remove from list)
        tasks = self.csv_handler.read_csv('tasks')
        for t in tasks:
            if str(t.get('map_id')) == str(map_id):
                t_stop_ids = t.get('stop_ids', '').split(',')
                if stop_id in t_stop_ids:
                    t_stop_ids.remove(stop_id)
                    t['stop_ids'] = ','.join(t_stop_ids)
                
                details_raw = t.get('task_details', '{}')
                try:
                    details = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
                    if 'pickup_stops' in details and stop_id in details['pickup_stops']:
                        idx = details['pickup_stops'].index(stop_id)
                        details['pickup_stops'].pop(idx)
                        if 'pickup_stop_names' in details and len(details['pickup_stop_names']) > idx:
                            details['pickup_stop_names'].pop(idx)
                        t['task_details'] = json.dumps(details)
                except:
                    pass
        self.csv_handler.write_csv('tasks', tasks)
