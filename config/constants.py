# Device status options
DEVICE_STATUS = {
    'working': 'Working',
    'charging': 'Charging',
    'issues': 'Issues',
    'maintenance': 'Maintenance'
}

# Task types
TASK_TYPES = {
    'picking': 'Picking',
    'auditing': 'Auditing',
    'storing': 'Storing',
    'charging': 'Charging'
}

# Task status
TASK_STATUS = {
    'pending': 'Pending',
    'running': 'Running',
    'completed': 'Completed',
    'failed': 'Failed',
    'cancelled': 'Cancelled'
}

# Priority levels
PRIORITY_LEVELS = {
    'low': 'Low Priority',
    'medium': 'Medium Priority',
    'high': 'High Priority',
    'urgent': 'Urgent'
}

# Device types section removed

# Map visualization constants
MAP_COLORS = {
    'zone': '#3B82F6',
    'connection': '#10B981',
    'selected_stop': '#EF4444',
    'stop_group': '#8B5CF6',
    'background': '#F8FAFC'
}

# Stop configuration
DEFAULT_BIN_DISTANCE = 2.0

# CSV Headers
CSV_HEADERS = {
    'devices': ['id', 'device_id', 'device_name', 'device_model', 'forward_speed', 'turning_speed', 'vertical_speed', 'horizontal_speed', 'status', 'battery_level', 'current_map', 'current_location', 'wheel_diameter', 'distance_between_wheels', 'length', 'width', 'height', 'lifting_height', 'distance', 'created_at', 'updated_at'],
    'tasks': ['id', 'task_id', 'task_name', 'task_type', 'status', 'assigned_device_id', 'assigned_device_ids', 'assigned_user_id', 'description', 'estimated_duration', 'actual_duration', 'created_at', 'started_at', 'completed_at', 'map_id', 'zone_ids', 'stop_ids', 'task_details'],
    'users': ['id', 'username', 'email', 'employee_id', 'profile_picture', 'is_active', 'created_at'],
    'maps': ['id', 'name', 'description', 'width', 'height', 'meter_in_pixels', 'created_at'],
    'zones': ['id', 'map_id', 'from_zone', 'to_zone', 'magnitude', 'direction', 'created_at', 'edited_at'],
    # stop_function: logical operation the stop represents (pickup/check/drop/charging)
    'stops': ['id', 'zone_connection_id', 'map_id', 'stop_id', 'name', 'x_coordinate', 'y_coordinate', 'left_bins_count', 'right_bins_count', 'left_bins_distance', 'right_bins_distance', 'distance_from_start', 'stop_type', 'stop_function', 'created_at'],
    'stop_groups': ['id', 'map_id', 'name', 'stop_ids', 'created_at'],
    'zone_alignment': ['id', 'map_id', 'zone', 'alignment'],
    'products': ['id', 'product_id', 'product_name', 'sku_location_id', 'sku_weight', 'created_at', 'updated_at'],
    'charging_zones': ['id', 'map_id', 'zone', 'occupied', 'device_id']
}
