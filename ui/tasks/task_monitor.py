from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QComboBox, QMessageBox, QFrame, QSplitter,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QDialog, QProgressBar)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from datetime import datetime, timedelta
from ui.common.table_widget import DataTableWidget
from ui.tasks.task_details_dialog import TaskDetailsDialog
from ui.common.base_dialog import BaseDialog
from api.client import APIClient
from api.tasks import TasksAPI
from api.devices import DevicesAPI
from data_manager.csv_handler import CSVHandler
from data_manager.device_data_handler import DeviceDataHandler
from config.constants import TASK_STATUS, TASK_TYPES, PRIORITY_LEVELS
from utils.logger import setup_logger
from services.path_planner_service import plan_and_write_path
from utils.zone_navigation_manager import get_zone_navigation_manager


class TaskMonitorWidget(QWidget):
    task_updated = pyqtSignal(dict)
    
    def __init__(self, api_client: APIClient, csv_handler: CSVHandler):
        super().__init__()
        self.api_client = api_client
        self.csv_handler = csv_handler
        self.tasks_api = TasksAPI(api_client)
        self.devices_api = DevicesAPI(api_client)
        self.logger = setup_logger('task_monitor')
        self.device_data_handler = DeviceDataHandler()
        self._status_dialog = None
        self._status_dialog_label = None
        self._handshake_timer = None
        self._handshake_deadline = None
        self._handshake_context = None
        self._completion_watchers = {}

        self.current_tasks = []
        self.selected_task = None
        self.selected_task_index = None

        self.setup_ui()
        self.setup_timer()
        self.refresh_data()
        
    def setup_ui(self):
        """Setup task monitor UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Header with filters removed; filters will be in the tasks table layout

        # Main content area
        splitter = QSplitter(Qt.Horizontal)

        # Tasks table
        self.create_tasks_table(splitter)

        # Task details panel removed

        # Set splitter proportions
        splitter.setSizes([800, 400])
        layout.addWidget(splitter)

        # Action buttons
        self.create_action_buttons(layout)

    # create_header removed; filters will be in the tasks table layout
    def create_tasks_table(self, parent):
        """Create tasks table"""
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.setContentsMargins(0, 0, 0, 0)

        # Filters and Table title in the same row
        title_filter_layout = QHBoxLayout()
        # Table title
        table_title = QLabel("Tasks List")
        table_title.setFont(QFont("Arial", 14, QFont.Bold))
        table_title.setStyleSheet("color: #ffffff; margin-bottom: 10px;")
        title_filter_layout.addWidget(table_title)
        title_filter_layout.addStretch()
        # Filters
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(15)
        # Status filter
        status_label = QLabel("Status:")
        status_label.setStyleSheet("color: #cccccc;")
        filter_layout.addWidget(status_label)
        self.status_filter = QComboBox()
        self.status_filter.addItem("All Statuses", "")
        for key, value in TASK_STATUS.items():
            self.status_filter.addItem(value, key)
        self.status_filter.currentTextChanged.connect(self.filter_tasks)
        self.apply_combo_style(self.status_filter)
        filter_layout.addWidget(self.status_filter)
        # Type filter
        type_label = QLabel("Type:")
        type_label.setStyleSheet("color: #cccccc;")
        filter_layout.addWidget(type_label)
        self.type_filter = QComboBox()
        self.type_filter.addItem("All Types", "")
        for key, value in TASK_TYPES.items():
            self.type_filter.addItem(value, key)
        self.type_filter.currentTextChanged.connect(self.filter_tasks)
        self.apply_combo_style(self.type_filter)
        filter_layout.addWidget(self.type_filter)

        title_filter_layout.addLayout(filter_layout)
        table_layout.addLayout(title_filter_layout)

        # Tasks table
        self.tasks_table = DataTableWidget([
            "Task ID", "Task Name", "Type", "Status", "Assigned Device(s)",
            "Assigned User", "Progress", "Created", "Duration"
        ], searchable=True, selectable=True)

        self.tasks_table.row_selected.connect(self.on_task_selected)
        self.tasks_table.row_double_clicked.connect(self.on_task_double_clicked)
        table_layout.addWidget(self.tasks_table)

        parent.addWidget(table_widget)

    # create_details_panel removed
    def create_action_buttons(self, parent_layout):
        """Create action buttons"""
        action_layout = QHBoxLayout()

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_data)
        self.apply_button_style(refresh_btn)
        action_layout.addWidget(refresh_btn)

        # Auto refresh toggle
        self.auto_refresh_btn = QPushButton("⏸️ Pause Auto-Refresh")
        self.auto_refresh_btn.clicked.connect(self.toggle_auto_refresh)
        self.apply_button_style(self.auto_refresh_btn)
        action_layout.addWidget(self.auto_refresh_btn)

        action_layout.addStretch()
        # Generate Path Planning button (before Start Task)
        self.generate_path_btn = QPushButton("🧭 Generate Path Planning")
        self.generate_path_btn.clicked.connect(self.generate_path_planning_for_selected_task)
        self.generate_path_btn.setEnabled(False)
        self.apply_button_style(self.generate_path_btn)
        action_layout.addWidget(self.generate_path_btn)

        # Task action buttons (moved from details panel)
        self.start_task_btn = QPushButton("▶️ Start Task")
        self.start_task_btn.clicked.connect(self.start_selected_task)
        self.start_task_btn.setEnabled(False)
        self.start_task_btn.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)
        action_layout.addWidget(self.start_task_btn)

        self.complete_task_btn = QPushButton("✅ Complete Task")
        self.complete_task_btn.clicked.connect(self.complete_selected_task)
        self.complete_task_btn.setEnabled(False)
        self.complete_task_btn.setStyleSheet("""
            QPushButton {
                background-color: #8B5CF6;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7C3AED;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)
        action_layout.addWidget(self.complete_task_btn)

        self.cancel_task_btn = QPushButton("❌ Cancel Task")
        self.cancel_task_btn.clicked.connect(self.cancel_selected_task)
        self.cancel_task_btn.setEnabled(False)
        self.cancel_task_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF4444;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #DC2626;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
        """)
        action_layout.addWidget(self.cancel_task_btn)

        self.view_details_btn = QPushButton("📋 View Full Details")
        self.view_details_btn.clicked.connect(self.view_task_details)
        self.view_details_btn.setEnabled(False)
        self.apply_button_style(self.view_details_btn)
        action_layout.addWidget(self.view_details_btn)

        # Export button
        export_btn = QPushButton("📤 Export Tasks")
        export_btn.clicked.connect(self.export_tasks)
        self.apply_button_style(export_btn)
        action_layout.addWidget(export_btn)

        parent_layout.addLayout(action_layout)
        
    def apply_combo_style(self, combo):
        """Apply combobox styling"""
        combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                border: 1px solid #555555;
                padding: 6px;
                border-radius: 4px;
                color: #ffffff;
                min-width: 120px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: #ffffff;
                selection-background-color: #ff6b35;
            }
        """)
        
    def apply_button_style(self, button):
        """Apply button styling"""
        button.setStyleSheet("""
            QPushButton {
                background-color: #555555;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666666;
            }
        """)
        
    def setup_timer(self):
        """Setup refresh timer"""
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(1000)  # Refresh every 15 seconds
        self.auto_refresh_enabled = True
        
    def refresh_data(self):
        """Refresh task data"""
        self.load_tasks()
        
    def load_tasks(self):
        """Load tasks from API or CSV"""
        try:
            # Try API first
            if self.api_client.is_authenticated():
                response = self.tasks_api.list_tasks()
                if 'error' not in response:
                    tasks_data = response.get('results', response) if isinstance(response, dict) else response
                    self.current_tasks = tasks_data
                    self.apply_filters()
                    return

            # Fallback to CSV
            tasks = self.csv_handler.read_csv('tasks')
            self.current_tasks = tasks
            self.apply_filters()

        except Exception as e:
            self.logger.error(f"Error loading tasks: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load tasks: {e}")
            
    def apply_filters(self):
        """Apply current filters and populate table"""
        filtered_tasks = self.current_tasks.copy()

        # Apply status filter
        status_filter = self.status_filter.currentData()
        if status_filter:
            filtered_tasks = [t for t in filtered_tasks if t.get('status', '').lower() == status_filter]

        # Apply type filter
        type_filter = self.type_filter.currentData()
        if type_filter:
            filtered_tasks = [t for t in filtered_tasks if t.get('task_type', '').lower() == type_filter]

        self.populate_tasks_table(filtered_tasks)
        
    def filter_tasks(self):
        """Handle filter changes"""
        self.apply_filters()
        
    def populate_tasks_table(self, tasks):
        """Populate tasks table"""
        self.tasks_table.clear_data()

        for task in tasks:
            # Get assigned device info (supports multiple)
            device_text = "Unassigned"
            devices = self.csv_handler.read_csv('devices')
            multi_ids = [s.strip() for s in str(task.get('assigned_device_ids') or '').split(',') if s.strip()]
            if multi_ids:
                names = []
                for did in multi_ids:
                    dev = next((d for d in devices if str(d.get('id')) == str(did) or str(d.get('device_id')) == str(did)), None)
                    if dev:
                        names.append(f"{dev.get('device_name', '')} ({dev.get('device_id', '')})")
                    else:
                        names.append(str(did))
                device_text = ", ".join(names)
            elif task.get('assigned_device_id'):
                dev = next((d for d in devices if str(d.get('id')) == str(task.get('assigned_device_id')) or str(d.get('device_id')) == str(task.get('assigned_device_id'))), None)
                if dev:
                    device_text = f"{dev.get('device_name', '')} ({dev.get('device_id', '')})"
                else:
                    device_text = f"Device ID: {task.get('assigned_device_id')}"

            # Get assigned user info
            user_text = "Unassigned"
            if task.get('assigned_user_id'):
                # Look up user name from CSV
                users = self.csv_handler.read_csv('users')
                user = next((u for u in users if str(u.get('id')) == str(task.get('assigned_user_id'))), None)
                if user:
                    user_text = user.get('username', f"User ID: {task.get('assigned_user_id')}")
                else:
                    user_text = f"User ID: {task.get('assigned_user_id')}"

            # Calculate progress
            progress = self.calculate_task_progress(task)

            # Format duration
            duration_text = "-"
            if task.get('actual_duration'):
                duration_text = f"{task.get('actual_duration')} min"
            elif task.get('estimated_duration'):
                duration_text = f"~{task.get('estimated_duration')} min"

            row_data = [
                task.get('task_id', ''),
                task.get('task_name', ''),
                task.get('task_type', '').title(),
                task.get('status', '').title(),
                device_text,
                user_text,
                progress,
                task.get('created_at', '')[:16] if task.get('created_at') else '',  # Date and time
                duration_text
            ]
            self.tasks_table.add_row(row_data)
            
    def calculate_task_progress(self, task):
        """Calculate task progress percentage"""
        status = task.get('status', '').lower()

        if status == 'completed':
            return "100%"
        elif status == 'failed' or status == 'cancelled':
            return "Failed"
        elif status == 'running':
            return "In Progress"
        elif status == 'pending':
            return "0%"
        else:
            return "Unknown"
            
    def on_task_selected(self, row):
        """Handle task selection"""
        # Get the filtered tasks to match the row index
        filtered_tasks = self.get_filtered_tasks()
        if row < len(filtered_tasks):
            self.selected_task = filtered_tasks[row]
            # Find the index in the original tasks list
            self.selected_task_index = self.current_tasks.index(self.selected_task)
            #self.show_task_details(self.selected_task)
            self.update_action_buttons()
            
    def get_filtered_tasks(self):
        """Get currently filtered tasks"""
        filtered_tasks = self.current_tasks.copy()

        status_filter = self.status_filter.currentData()
        if status_filter:
            filtered_tasks = [t for t in filtered_tasks if t.get('status', '').lower() == status_filter]

        type_filter = self.type_filter.currentData()
        if type_filter:
            filtered_tasks = [t for t in filtered_tasks if t.get('task_type', '').lower() == type_filter]

        return filtered_tasks
        
    def on_task_double_clicked(self, row):
        """Handle task double click"""
        self.view_task_details()
        
    def show_task_details(self, task):
        """Show task details in table row"""
        # This method is now handled by the tasks table and TaskDetailsDialog
        # No need to update UI elements as they have been removed
        pass
        
    def update_action_buttons(self):
        """Update action button states"""
        if not self.selected_task:
            self.start_task_btn.setEnabled(False)
            self.complete_task_btn.setEnabled(False)
            self.cancel_task_btn.setEnabled(False)
            self.view_details_btn.setEnabled(False)
            if hasattr(self, 'generate_path_btn'):
                self.generate_path_btn.setEnabled(False)
            return

        status = self.selected_task.get('status', '').lower()

        self.start_task_btn.setEnabled(status in ['pending', 'completed'])
        self.complete_task_btn.setEnabled(status == 'running')
        self.cancel_task_btn.setEnabled(status in ['pending', 'running'])
        self.view_details_btn.setEnabled(True)
        if hasattr(self, 'generate_path_btn'):
            self.generate_path_btn.setEnabled(status in ['pending', 'running'])
            
    def check_device_availability(self, device_id):
        """Check if a device is available (not running another task)."""
        if not device_id:
            return True
        tasks = self.csv_handler.read_csv('tasks')
        for t in tasks:
            if str(t.get('status', '')).lower() != 'running':
                continue
            if str(t.get('assigned_device_id') or '') == str(device_id):
                return False
            mids = [s.strip() for s in str(t.get('assigned_device_ids') or '').split(',') if s.strip()]
            if str(device_id) in mids:
                return False
        return True

    def start_selected_task(self):
        """Start selected task with device handshake and popup flow."""
        if not self.selected_task:
            return
        device_ref = self.selected_task.get('assigned_device_id') or (
            [s for s in str(self.selected_task.get('assigned_device_ids') or '').split(',') if s.strip()][0]
            if str(self.selected_task.get('assigned_device_ids') or '').strip() else None
        )
        if not device_ref:
            QMessageBox.warning(self, "No Device", "Assign a device to this task before starting.")
            return
        if not self.check_device_availability(device_ref):
            QMessageBox.warning(
                self,
                "Device Busy",
                "The device assigned to this task is currently running another task. "
                "Please wait for the device to complete its current task or assign a different device."
            )
            return
        # Show popup while we request execution
        self._show_status_popup("Please wait, we are checking robot's current status...")
        # Write the 'run_task' command to <device_id>_task.csv for this task
        task_id_str = self.selected_task.get('task_id')
        try:
            self.device_data_handler.set_task_status_for_task(device_ref, task_id_str, 'run_task')
        except Exception as e:
            self.logger.error(f"Failed to write run_task command: {e}")
        # Start polling for 'executing_task'
        self._handshake_context = {
            'task_pk': self.selected_task.get('id'),
            'task_id': task_id_str,
            'device_ref': device_ref,
        }
        from datetime import datetime, timedelta
        self._handshake_deadline = datetime.now() + timedelta(seconds=30)
        if self._handshake_timer:
            try:
                self._handshake_timer.stop()
            except Exception:
                pass
        from PyQt5.QtCore import QTimer
        self._handshake_timer = QTimer(self)
        self._handshake_timer.setInterval(1000)
        self._handshake_timer.timeout.connect(self._poll_handshake_status)
        self._handshake_timer.start()

    def complete_selected_task(self):
        """Complete selected task"""
        if not self.selected_task:
            return
        task_name = self.selected_task.get('task_name', 'Unknown')
        reply = QMessageBox.question(
            self, "Complete Task",
            f"Mark task '{task_name}' as completed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.change_task_status('completed', 'completed_at')

    def cancel_selected_task(self):
        """Cancel selected task"""
        if not self.selected_task:
            return
        task_name = self.selected_task.get('task_name', 'Unknown')
        reply = QMessageBox.question(
            self, "Cancel Task",
            f"Cancel task '{task_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.change_task_status('cancelled')

    def change_task_status(self, new_status, timestamp_field=None):
        """Change task status in CSV"""
        try:
            task_id = self.selected_task.get('id')
            # First try API if available
            if self.api_client.is_authenticated():
                if new_status == 'running':
                    response = self.tasks_api.start_task(task_id)
                elif new_status == 'completed':
                    response = self.tasks_api.complete_task(task_id)
                else:
                    # For cancel or other status changes, update directly
                    response = self.tasks_api.update_task(task_id, {'status': new_status})
                if 'error' not in response:
                    QMessageBox.information(self, "Success", f"Task {new_status} successfully!")
                    self.refresh_data()
                    return
                else:
                    self.logger.warning(f"API call failed: {response['error']}, falling back to CSV")
            # Fallback to CSV update
            update_data = {'status': new_status}
            # Add timestamp if specified
            if timestamp_field:
                from datetime import datetime
                update_data[timestamp_field] = datetime.now().isoformat()
            # If completing a task, calculate actual duration
            if new_status == 'completed' and self.selected_task.get('started_at'):
                try:
                    from datetime import datetime
                    started_time = datetime.fromisoformat(self.selected_task['started_at'].replace('Z', ''))
                    completed_time = datetime.now()
                    duration_minutes = int((completed_time - started_time).total_seconds() / 60)
                    update_data['actual_duration'] = duration_minutes
                except Exception as e:
                    self.logger.warning(f"Could not calculate duration: {e}")
            if self.csv_handler.update_csv_row('tasks', task_id, update_data):
                QMessageBox.information(self, "Success", f"Task {new_status} successfully!")
                # Update the current task data
                self.selected_task.update(update_data)
                self.current_tasks[self.selected_task_index].update(update_data)
                # Refresh the display
                self.apply_filters()
                self.show_task_details(self.selected_task)
                self.update_action_buttons()
            else:
                raise Exception("Failed to update CSV")
        except Exception as e:
            self.logger.error(f"Error changing task status: {e}")
            QMessageBox.critical(self, "Error", f"Failed to change task status: {e}")

    def _poll_handshake_status(self):
        try:
            ctx = self._handshake_context or {}
            if not ctx:
                return
            latest = self.device_data_handler.get_latest_task_status_for_task(ctx['device_ref'], ctx['task_id'])
            if str(latest).lower() == 'executing_task':
                self._update_status_popup("Executing the task...")
                self._close_status_popup()
                self._silent_update_task_status_by_row_id(ctx['task_pk'], 'running', 'started_at')
                if self._handshake_timer:
                    self._handshake_timer.stop()
                    self._handshake_timer = None
                self._start_completion_watcher(ctx['task_id'], ctx['device_ref'], ctx['task_pk'])
                return
            if str(latest).lower() == 'task_completed':
                self._close_status_popup()
                if self._handshake_timer:
                    self._handshake_timer.stop()
                    self._handshake_timer = None
                self._silent_update_task_status_by_row_id(ctx['task_pk'], 'completed', 'completed_at')
                return
            from datetime import datetime
            if datetime.now() > (self._handshake_deadline or datetime.now()):
                self._update_status_popup("Device did not acknowledge execution in time.")
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(1500, self._close_status_popup)
                if self._handshake_timer:
                    self._handshake_timer.stop()
                    self._handshake_timer = None
        except Exception as e:
            self.logger.error(f"Handshake polling failed: {e}")
            try:
                self._close_status_popup()
            except Exception:
                pass
            if self._handshake_timer:
                self._handshake_timer.stop()
                self._handshake_timer = None

    def _start_completion_watcher(self, task_id: str, device_ref, task_pk):
        try:
            if task_id in self._completion_watchers:
                try:
                    self._completion_watchers[task_id].stop()
                except Exception:
                    pass
            from PyQt5.QtCore import QTimer
            timer = QTimer(self)
            timer.setInterval(1000)
            timer.timeout.connect(lambda tid=task_id, dev=device_ref, pk=task_pk: self._poll_completion_status(tid, dev, pk))
            self._completion_watchers[task_id] = timer
            timer.start()
        except Exception as e:
            self.logger.error(f"Failed to start completion watcher for {task_id}: {e}")

    def _poll_completion_status(self, task_id: str, device_ref, task_pk):
        try:
            latest = self.device_data_handler.get_latest_task_status_for_task(device_ref, task_id)
            if str(latest).lower() == 'task_completed':
                try:
                    t = self._completion_watchers.get(task_id)
                    if t:
                        t.stop()
                        del self._completion_watchers[task_id]
                except Exception:
                    pass
                self._silent_update_task_status_by_row_id(task_pk, 'completed', 'completed_at')
        except Exception as e:
            self.logger.error(f"Completion polling failed for {task_id}: {e}")

    def _show_status_popup(self, message: str):
        try:
            dlg = BaseDialog(self)
            dlg.setWindowTitle("Task Status")
            dlg.setModal(False)
            from PyQt5.QtWidgets import QVBoxLayout
            layout = QVBoxLayout(dlg)
            lbl = QLabel(message)
            lbl.setStyleSheet("color: #ffffff;")
            prg = QProgressBar()
            prg.setRange(0, 0)
            layout.addWidget(lbl)
            layout.addWidget(prg)
            dlg.setStyleSheet("QDialog { background-color: #2b2b2b; }")
            dlg.setFixedSize(360, 120)
            self._status_dialog = dlg
            self._status_dialog_label = lbl
            dlg.show()
        except Exception as e:
            self.logger.error(f"Failed to show status popup: {e}")

    def _update_status_popup(self, message: str):
        try:
            if self._status_dialog_label:
                self._status_dialog_label.setText(message)
        except Exception:
            pass

    def _close_status_popup(self):
        try:
            if self._status_dialog:
                self._status_dialog.close()
        finally:
            self._status_dialog = None
            self._status_dialog_label = None

    def _silent_update_task_status_by_row_id(self, row_pk: str, new_status: str, timestamp_field: str = None):
        try:
            update_data = {'status': new_status}
            if timestamp_field:
                from datetime import datetime
                update_data[timestamp_field] = datetime.now().isoformat()
            if new_status == 'completed':
                try:
                    from datetime import datetime
                    task = next((t for t in self.current_tasks if str(t.get('id')) == str(row_pk)), None)
                    if task and task.get('started_at'):
                        started_time = datetime.fromisoformat(task['started_at'].replace('Z', ''))
                        completed_time = datetime.now()
                        duration_minutes = int((completed_time - started_time).total_seconds() / 60)
                        update_data['actual_duration'] = duration_minutes
                except Exception as e:
                    self.logger.warning(f"Could not calculate duration silently: {e}")
            try:
                if self.api_client.is_authenticated():
                    if new_status == 'running':
                        self.tasks_api.start_task(row_pk)
                    elif new_status == 'completed':
                        self.tasks_api.complete_task(row_pk)
                    else:
                        self.tasks_api.update_task(row_pk, {'status': new_status})
            except Exception:
                pass
            if self.csv_handler.update_csv_row('tasks', row_pk, update_data):
                for i, t in enumerate(self.current_tasks):
                    if str(t.get('id')) == str(row_pk):
                        self.current_tasks[i].update(update_data)
                        break
                if self.selected_task and str(self.selected_task.get('id')) == str(row_pk):
                    self.selected_task.update(update_data)
                self.apply_filters()
                self.update_action_buttons()
        except Exception as e:
            self.logger.error(f"Silent status update failed for row {row_pk}: {e}")
            
    def view_task_details(self):
        """View full task details in dialog"""
        if self.selected_task:
            dialog = TaskDetailsDialog(self, self.selected_task)
            dialog.exec_()
            
    def toggle_auto_refresh(self):
        """Toggle auto refresh"""
        if self.auto_refresh_enabled:
            self.refresh_timer.stop()
            self.auto_refresh_btn.setText("▶️ Resume Auto-Refresh")
            self.auto_refresh_enabled = False
        else:
            self.refresh_timer.start()
            self.auto_refresh_btn.setText("⏸️ Pause Auto-Refresh")
            self.auto_refresh_enabled = True
            
    def export_tasks(self):
        """Export tasks to CSV"""
        from PyQt5.QtWidgets import QFileDialog
        import shutil

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Tasks", "tasks_export.csv", "CSV Files (*.csv)"
        )

        if file_path:
            try:
                tasks_csv_path = self.csv_handler.CSV_FILES['tasks']
                shutil.copy2(tasks_csv_path, file_path)
                QMessageBox.information(self, "Success", f"Tasks exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Export failed: {e}")

    def _parse_task_map_and_path(self, task: dict):
        """Extract routing-relevant fields from task_details JSON.

        For Picking tasks this returns:
        - map_id: pickup_map_id
        - from_zone/to_zone: legacy values (may be None for new design)
        - zone_path: legacy zone path list
        - pickup_stops: ordered list of pickup stop_ids (user selection order preserved)
        - pickup_racks: ordered list of pickup rack_ids (user selection order preserved)
        - drop_zone: single zone id representing the final drop zone

        For other task types the additional fields are returned as empty.
        """
        import json

        map_id = str(task.get('map_id') or '').strip() or None
        from_zone = None
        to_zone = None
        zone_path: list[str] = []
        pickup_stops: list[str] = []
        pickup_racks: list[str] = []
        drop_zone: str | None = None

        raw = task.get('task_details') or ''
        try:
            details = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        except Exception:
            details = {}

        # Prefer map_id from task_details for Picking/Auditing
        map_id = str(
            details.get('pickup_map_id')
            or details.get('auditing_map_id')
            or details.get('charging_map_id')
            or map_id
            or ''
        ).strip() or None

        # Legacy zone path support
        zp = details.get('zone_path') or []
        if isinstance(zp, list) and len(zp) >= 2:
            zone_path = [str(z) for z in zp]
            from_zone, to_zone = zone_path[0], zone_path[1]
        else:
            from_zone = str(details.get('from_zone') or '').strip() or None
            to_zone = str(details.get('to_zone') or '').strip() or None
            
            # Handle charging station as to_zone
            if not to_zone:
                to_zone = str(details.get('charging_station') or '').strip() or None

            if from_zone and to_zone:
                zone_path = [from_zone, to_zone]

        # New picking semantics: pickup_stops + check_stops + drop_stops + end_zone
        try:
            raw_pickup = details.get('pickup_stops') or []
            if isinstance(raw_pickup, list):
                pickup_stops = [
                    str(s) for s in raw_pickup
                ]
        except Exception:
            pickup_stops = []

        try:
            raw_racks = details.get('pickup_racks') or []
            if isinstance(raw_racks, list):
                pickup_racks = [str(r) for r in raw_racks]
        except Exception:
            pickup_racks = []

        # Parse new stop types
        check_stops: list[str] = []
        try:
            raw_check = details.get('check_stops') or []
            if isinstance(raw_check, list):
                check_stops = [str(s) for s in raw_check]
        except Exception:
            check_stops = []

        drop_stops: list[str] = []
        try:
            raw_drop = details.get('drop_stops') or []
            if isinstance(raw_drop, list):
                drop_stops = [str(s) for s in raw_drop]
        except Exception:
            drop_stops = []

        # Prefer end_zone, fallback to drop_zone for backward compatibility
        # Also check for end_stop_id (new approach) and resolve it to zone
        end_zone: str | None = None
        end_stop_id: str | None = None
        
        # First, try to resolve end_stop_id to a zone
        end_stop_id = details.get('end_stop_id')
        if end_stop_id:
            try:
                stops = CSVHandler().read_csv('stops')
                for stop in stops:
                    if str(stop.get('stop_id')).strip() == str(end_stop_id).strip():
                        zone_conn_id = stop.get('zone_connection_id')
                        if zone_conn_id:
                            zones_data = CSVHandler().read_csv('zones')
                            for zone_row in zones_data:
                                if (str(zone_row.get('id')).strip() == str(zone_conn_id).strip() and 
                                    str(zone_row.get('map_id')).strip() == str(map_id).strip()):
                                    end_zone = str(zone_row.get('to_zone')).strip()
                                    break
                        break
            except Exception as e:
                self.logger.warning(f"Could not resolve end_stop_id {end_stop_id} to zone: {e}")
        
        # If end_stop_id resolution failed, fall back to end_zone or drop_zone
        if not end_zone:
            dz = details.get('end_zone') or details.get('drop_zone') or details.get('drop_zone_id')
            if dz is not None and str(dz).strip():
                end_zone = str(dz).strip()
        drop_zone = end_zone  # Keep drop_zone for backward compatibility

        return map_id, from_zone, to_zone, zone_path, pickup_stops, pickup_racks, drop_zone, check_stops, drop_stops, end_zone, end_stop_id

    def generate_path_planning_for_selected_task(self):
        """Generate and write path commands for the selected task/device."""
        try:
            if not self.selected_task:
                return

            # Resolve device IDs to use for path generation (supports multi-device assignment)
            ids_str = str(self.selected_task.get('assigned_device_ids') or '').strip()
            if ids_str:
                pk_list = [s.strip() for s in ids_str.split(',') if s.strip()]
            else:
                single = self.selected_task.get('assigned_device_id')
                pk_list = [str(single)] if single else []
            if not pk_list:
                QMessageBox.warning(self, "No Device", "Assign a device to this task before generating the path.")
                return

            devices = self.csv_handler.read_csv('devices')
            (
                map_id,
                from_zone,
                to_zone,
                zone_path,
                pickup_stops,
                pickup_racks,
                drop_zone,
                check_stops,
                drop_stops,
                end_zone,
                end_stop_id,
            ) = self._parse_task_map_and_path(self.selected_task)

            if not map_id:
                QMessageBox.critical(self, "Missing Map", "Task is missing map_id in details.")
                return

            task_type = str(self.selected_task.get('task_type') or '').lower()

            results = []
            for pk in pk_list:
                dev_row = next(
                    (d for d in devices if str(d.get('id')) == str(pk) or str(d.get('device_id')) == str(pk)),
                    None,
                )
                device_id = (dev_row.get('device_id') if dev_row else None) or str(pk)

                # Build zone_sequence based on task type
                if task_type in ('auditing', 'audit', 'auduting'):
                    start_zone = self._derive_start_zone_for_audit(device_id, map_id)
                    zone_sequence = self._build_full_map_sequence(map_id, start_zone)
                else:
                    if task_type == 'picking' and (pickup_stops or pickup_racks) and drop_zone:

                        # Round-trip picking: for each stop, generate path:
                        # current position -> stop edge (PICKUP only for that stop) -> drop zone (DROP)
                        # Then repeat for next stop starting from drop zone.
                        
                        # Import needed function
                        from services.path_planner_service import plan_and_write_picking_path

                        try:
                            # Use new path generation with stop operations
                            from services.path_planner_service import plan_and_write_path
                            
                            # Get current zone
                            current_zone = None
                            try:
                                nav = get_zone_navigation_manager()
                                nav_info = nav.get_navigation_info(device_id)
                                current_zone = nav_info.get('current_zone')
                            except Exception:
                                current_zone = self._derive_start_zone_for_audit(device_id, map_id)
                            
                            # Build zone sequence that visits all stops in order
                            # Need to find which zone connections contain each stop
                            zones = self.csv_handler.read_csv('zones')
                            stops_data = self.csv_handler.read_csv('stops')
                            
                            # Auto-insert charging stop when battery is low (no user selection needed)
                            charging_stop_ids = []
                            try:
                                battery_val = dev_row.get('battery_level') if dev_row else None
                                battery = int(float(battery_val)) if battery_val not in (None, '') else 100
                            except Exception:
                                battery = 100
                            battery_low_threshold = 20
                            if battery <= battery_low_threshold:
                                for srow in stops_data:
                                    if str(srow.get('map_id')) != str(map_id):
                                        continue
                                    sf = str(srow.get('stop_function') or '').strip().lower()
                                    if sf == 'charging':
                                        sid = str(srow.get('stop_id') or '').strip()
                                        if sid:
                                            charging_stop_ids = [sid]
                                            break
                                if charging_stop_ids:
                                    self.logger.warning(
                                        f"Battery low ({battery}%). Inserting charging stop {charging_stop_ids[0]} into path."
                                    )
                            
                            # Map stop_id to zone connection (from_zone, to_zone)
                            stop_to_zone_conn = {}
                            for stop_row in stops_data:
                                if str(stop_row.get('map_id')) != str(map_id):
                                    continue
                                stop_id = str(stop_row.get('stop_id', '')).strip()
                                conn_id = str(stop_row.get('zone_connection_id', '')).strip()
                                if stop_id and conn_id:
                                    # Find the zone connection
                                    for zone_row in zones:
                                        if str(zone_row.get('id')) == conn_id:
                                            from_z = str(zone_row.get('from_zone', ''))
                                            to_z = str(zone_row.get('to_zone', ''))
                                            if from_z and to_z:
                                                stop_to_zone_conn[stop_id] = (from_z, to_z)
                                            break
                            
                            # Build zone sequence: visit all stops in order (pickup → check → drop) then end zone
                            zone_sequence = []
                            last_zone = str(current_zone) if current_zone else None
                            
                            # Collect all stops in order
                            all_stops_ordered = []
                            if pickup_stops:
                                all_stops_ordered.extend([(s, 'pickup') for s in pickup_stops])
                            if check_stops:
                                all_stops_ordered.extend([(s, 'check') for s in check_stops])
                            if drop_stops:
                                all_stops_ordered.extend([(s, 'drop') for s in drop_stops])
                            
                            # Add end_stop_id to zone_sequence so CALL,END is generated
                            if end_stop_id and end_stop_id in stop_to_zone_conn:
                                all_stops_ordered.append((end_stop_id, 'end'))
                            
                            # Build zone sequence visiting each stop
                            visited_edges = set()
                            for stop_id, _ in all_stops_ordered:
                                if stop_id in stop_to_zone_conn:
                                    from_z, to_z = stop_to_zone_conn[stop_id]
                                    edge_key = (from_z, to_z)
                                    
                                    # If we haven't visited this edge yet, add it to sequence
                                    if edge_key not in visited_edges:
                                        # If we're not at the from_zone, add path to get there
                                        if last_zone and last_zone != from_z:
                                            # Use A* or direct path - for now, add direct connection if exists
                                            # Check if there's a direct path
                                            found_path = False
                                            for z_row in zones:
                                                if (str(z_row.get('map_id')) == str(map_id) and
                                                    str(z_row.get('from_zone')) == str(last_zone) and
                                                    str(z_row.get('to_zone')) == from_z):
                                                    zone_sequence.append((str(last_zone), from_z))
                                                    last_zone = from_z
                                                    found_path = True
                                                    break
                                            # If no direct path, add the edge anyway (A* will handle it)
                                            if not found_path:
                                                zone_sequence.append((str(last_zone), from_z))
                                                last_zone = from_z
                                        
                                        # Add the edge containing the stop
                                        zone_sequence.append((from_z, to_z))
                                        visited_edges.add(edge_key)
                                        last_zone = to_z
                            
                            # Finally, go to end zone if not already there (fallback if end_stop_id not found)
                            if end_zone and last_zone != str(end_zone):
                                # Only add if end_stop_id wasn't already added
                                if not end_stop_id or end_stop_id not in stop_to_zone_conn:
                                    # Check if there's a direct path to end zone
                                    found_path = False
                                    for z_row in zones:
                                        if (str(z_row.get('map_id')) == str(map_id) and
                                            str(z_row.get('from_zone')) == str(last_zone) and
                                            str(z_row.get('to_zone')) == str(end_zone)):
                                            zone_sequence.append((str(last_zone), str(end_zone)))
                                            found_path = True
                                            break
                                    if not found_path:
                                        zone_sequence.append((str(last_zone), str(end_zone)))
                                    last_zone = str(end_zone)
                            
                            # Extract charging stops from task details (for CHARGING label section, not zone_sequence)
                            # Charging stops should NOT be in zone_sequence - they're called conditionally from END logic
                            charging_stops_from_task = []
                            try:
                                import json
                                raw = self.selected_task.get('task_details') or ''
                                details = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
                                charging_stops_from_task = [str(s) for s in details.get('charging_stops', [])]
                            except Exception:
                                pass
                            
                            # Combine all charging stops (for CHARGING label section only)
                            all_charging_stops = list(set(charging_stop_ids + charging_stops_from_task))
                            
                            # If no zone sequence built, create a simple one
                            if not zone_sequence:
                                start_z = str(current_zone) if current_zone else '1'
                                end_z = str(end_zone) if end_zone else (str(drop_zone) if drop_zone else '1')
                                zone_sequence = [(start_z, end_z)]
                            
                            initial_direction = 'north'
                            try:
                                nav = get_zone_navigation_manager()
                                nav_info = nav.get_navigation_info(device_id)
                                initial_direction = (nav_info.get('locked_direction') or 'north')
                            except Exception:
                                pass
                            
                            self.logger.info(f"Building path with zone_sequence: {zone_sequence}, stops: pickup={pickup_stops}, check={check_stops}, drop={drop_stops}")
                            
                            # Extract charging stops from task details (if specified)
                            charging_stops_from_task = []
                            try:
                                import json
                                raw = self.selected_task.get('task_details') or ''
                                details = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
                                charging_stops_from_task = [str(s) for s in details.get('charging_stops', [])]
                            except Exception:
                                pass
                            
                            # Combine charging stops (from task or auto-detected)
                            all_charging_stops = list(set(charging_stop_ids + charging_stops_from_task))
                            
                            out_path = plan_and_write_path(
                                device_id=device_id,
                                map_id=str(map_id),
                                zone_sequence=zone_sequence,
                                initial_direction=str(initial_direction).lower(),
                                task_type='picking',
                                pickup_stops=pickup_stops,
                                check_stops=check_stops,
                                drop_stops=drop_stops,
                                end_zone=str(end_zone) if end_zone else str(drop_zone) if drop_zone else None,
                                end_stop_id=str(end_stop_id) if end_stop_id else None,
                                charging_stops=all_charging_stops if all_charging_stops else None,
                            )
                            results.append(f"{device_id}: {out_path}")
                        except Exception as e:
                            self.logger.error(f"Failed to generate picking path: {e}", exc_info=True)
                            QMessageBox.critical(self, "Error", f"Failed to generate picking path: {e}")
                            return
                        continue  # Skip the standard plan_and_write_path call below

                    else:
                        # Legacy/other task types: storing, old picking without drop_zone, charging
                        base_from = from_zone or (zone_path[0] if zone_path else None)
                        hub = to_zone or (zone_path[1] if len(zone_path) > 1 else None)
                        
                        current_zone = None
                        try:
                            nav = get_zone_navigation_manager()
                            nav_info2 = nav.get_navigation_info(device_id)
                            current_zone = nav_info2.get('current_zone')
                        except Exception:
                            current_zone = None
                        if not current_zone:
                            current_zone = self._derive_start_zone_for_audit(device_id, map_id)

                        # For charging tasks, if base_from is missing, use current_zone
                        if task_type == 'charging' and not base_from:
                            base_from = current_zone

                        if not base_from or not hub:
                            QMessageBox.critical(self, "Missing Zones", "Task is missing from/to zones.")
                            return

                        zone_sequence = []
                        if current_zone and str(current_zone) != str(base_from):
                            zone_sequence.append((str(current_zone), str(base_from)))
                        zone_sequence.append((str(base_from), str(hub)))

                # Determine initial direction from navigation manager
                try:
                    nav = get_zone_navigation_manager()
                    nav_info = nav.get_navigation_info(device_id)
                    initial_direction = (nav_info.get('locked_direction') or 'north')
                except Exception:
                    initial_direction = 'north'

                # For storing tasks, extract check_stops and drop_stops from task_details
                storing_check_stops = []
                storing_drop_stops = []
                storing_end_zone = None
                if task_type == 'storing':
                    try:
                        import json
                        raw = self.selected_task.get('task_details') or ''
                        details = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
                        storing_check_stops = [str(s) for s in details.get('check_stops', [])]
                        storing_drop_stops = [str(s) for s in details.get('drop_stops', [])]
                        storing_end_zone = str(details.get('end_zone') or '') or None
                    except Exception:
                        pass
                
                # For auditing tasks, extract end_zone
                auditing_end_zone = None
                if task_type == 'auditing':
                    try:
                        import json
                        raw = self.selected_task.get('task_details') or ''
                        details = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
                        auditing_end_zone = str(details.get('end_zone') or '') or None
                    except Exception:
                        pass

                out_path = plan_and_write_path(
                    device_id=device_id,
                    map_id=str(map_id),
                    zone_sequence=zone_sequence,
                    initial_direction=str(initial_direction).lower(),
                    task_type=task_type,
                    selected_stop_ids=pickup_stops if task_type == 'picking' else None,
                    selected_rack_ids=pickup_racks if task_type == 'picking' else None,
                    drop_zone=drop_zone if task_type == 'picking' else None,  # Backward compatibility
                    end_zone=end_zone if task_type == 'picking' else (storing_end_zone if task_type == 'storing' else auditing_end_zone),
                    check_stops=check_stops if task_type == 'picking' else (storing_check_stops if task_type == 'storing' else None),
                    drop_stops=drop_stops if task_type == 'picking' else (storing_drop_stops if task_type == 'storing' else None),
                )

                results.append(f"{device_id}: {out_path}")

            QMessageBox.information(
                self,
                "Path Generated",
                "Path commands written for devices:\n" + "\n".join(results),
            )
        except Exception as e:
            self.logger.error(f"Path planning failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to generate path: {e}")

    def _derive_start_zone_for_audit(self, device_id: str, map_id: str) -> str:
        """Try to derive a reasonable start zone for auditing runs.
        Preference order: device_logs current_location -> smallest zone id in map.
        """
        import os, csv
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        log_path = os.path.join(base_dir, 'data', 'device_logs', f"{device_id}.csv")
        current_zone = None
        try:
            if os.path.exists(log_path):
                with open(log_path, 'r', newline='') as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        current_zone = r.get('current_location') or current_zone
        except Exception:
            current_zone = None

        zones = self.csv_handler.read_csv('zones')
        zone_ids = set()
        for z in zones:
            if str(z.get('map_id')) == str(map_id):
                zone_ids.add(str(z.get('from_zone')))
                zone_ids.add(str(z.get('to_zone')))
        zone_ids = {z for z in zone_ids if z}
        if current_zone and str(current_zone) in zone_ids:
            return str(current_zone)

        def zone_key(z: str):
            s = str(z)
            return (0, int(s)) if s.isdigit() else (1, s)

        return sorted(zone_ids, key=zone_key)[0] if zone_ids else None

    def _build_full_map_sequence(self, map_id: str, start_zone: str = None, only_edges_with_stops: bool = False) -> list:
        """Build a chained (from_zone,to_zone) sequence that traverses the whole map.
        - If only_edges_with_stops=True, include only edges having stops.
        - Otherwise include all edges for the map.
        The sequence ensures continuity by inserting transitions (cur -> next_from) when needed.
        """
        zones = self.csv_handler.read_csv('zones')
        zones = [z for z in zones if str(z.get('map_id')) == str(map_id)]
        if not zones:
            return []
        stop_ids = set()
        if only_edges_with_stops:
            stops = self.csv_handler.read_csv('stops')
            stop_ids = {str(s.get('zone_connection_id')) for s in stops if str(s.get('map_id')) == str(map_id)}

        edges = []  # (id_int, from, to)
        for z in zones:
            cid = str(z.get('id'))
            if only_edges_with_stops and cid not in stop_ids:
                continue
            try:
                id_int = int(z.get('id')) if z.get('id') is not None else 0
            except Exception:
                id_int = 0
            edges.append((id_int, str(z.get('from_zone')), str(z.get('to_zone'))))
        edges.sort(key=lambda e: e[0])

        if not start_zone:
            zone_ids = set()
            for z in zones:
                zone_ids.add(str(z.get('from_zone')))
                zone_ids.add(str(z.get('to_zone')))
            zone_ids = {z for z in zone_ids if z}

            def zone_key(z):
                s = str(z)
                return (0, int(s)) if s.isdigit() else (1, s)

            start_zone = sorted(zone_ids, key=zone_key)[0] if zone_ids else None

        current = start_zone or (edges[0][1] if edges else None)
        if not current:
            return []

        seq = []
        visited = set()
        for _ in range(len(edges)):
            # Try to find next edge starting from current
            pick = -1
            for i in range(len(edges)):
                if i in visited:
                    continue
                if edges[i][1] == current:
                    pick = i
                    break
            if pick < 0:
                # take the next unvisited
                for i in range(len(edges)):
                    if i not in visited:
                        pick = i
                        break
            if pick < 0:
                break
            fz, tz = edges[pick][1], edges[pick][2]
            if current != fz:
                seq.append((str(current), str(fz)))
            seq.append((str(fz), str(tz)))
            visited.add(pick)
            current = tz

        return seq