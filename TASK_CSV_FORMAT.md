# Task CSV Upload Format Guide

## Overview
You can create tasks by uploading a CSV file instead of manually filling out the task creation form. The CSV file must contain specific fields depending on the task type.

---

## Main Task CSV Fields (tasks.csv)

These are the standard fields that apply to **ALL task types**:

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `id` | Integer | Auto-generated | Unique identifier | `1` |
| `task_id` | String | Auto-generated | Unique task ID | `TASK0001` |
| `task_name` | String | ✅ Yes | Name of the task | `Picking Task 1` |
| `task_type` | String | ✅ Yes | Type: `picking`, `auditing`, `storing`, or `charging` | `picking` |
| `status` | String | Auto | Status: `pending`, `running`, `completed`, `failed`, `cancelled` | `pending` |
| `assigned_device_id` | String | ✅ Yes | Device ID (for backward compatibility) | `1` |
| `assigned_device_ids` | String | ✅ Yes | Comma-separated device IDs | `1,2,3` |
| `assigned_user_id` | String | Optional | User/operator ID | `5` |
| `description` | String | Optional | Task description | `Pick items from zone A` |
| `estimated_duration` | String | Optional | Estimated time (minutes) | `30` |
| `actual_duration` | String | Auto | Actual time taken (filled after completion) | `35` |
| `created_at` | DateTime | Auto | Creation timestamp (ISO format) | `2026-02-05T23:18:12.534787` |
| `started_at` | DateTime | Auto | Task start time | `2026-02-06T10:30:00.000000` |
| `completed_at` | DateTime | Auto | Task completion time | `2026-02-06T11:05:00.000000` |
| `map_id` | String | Optional | Map ID where task occurs | `19` |
| `zone_ids` | String | Optional | Comma-separated zone IDs | `1,2,3` |
| `stop_ids` | String | Optional | Comma-separated stop IDs | `x,y,z` |
| `task_details` | JSON | Auto | JSON string with type-specific details | (see below) |

---

## Task Type Specific CSV Formats

### 1. **PICKING Task CSV**

**Required Fields:**
- `task_name`
- `task_type` = `picking`
- `assigned_device_id` or `assigned_device_ids`

**Additional Fields for Picking:**

| Field in task_details | Type | Description | Example |
|----------------------|------|-------------|---------|
| `pickup_map_id` | String | Map ID for pickup | `19` |
| `pickup_map_name` | String | Map name for pickup | `komal` |
| `pickup_stops` | JSON Array | List of pickup stop IDs | `["s1", "s2", "s3"]` |
| `pickup_stop_names` | JSON Array | Display names of pickup stops | `["Stop 1 (s1)", "Stop 2 (s2)"]` |
| `check_stops` | JSON Array | List of check stop IDs (optional) | `["s4", "s5"]` |
| `check_stop_names` | JSON Array | Display names of check stops | `["Check Stop 1 (s4)"]` |
| `drop_stops` | JSON Array | List of drop-off stop IDs | `["s10", "s11"]` |
| `drop_stop_names` | JSON Array | Display names of drop stops | `["Drop Stop 1 (s10)"]` |
| `end_zone` | String | End zone ID | `3` |
| `end_zone_name` | String | End zone display name | `Zone C` |

**Example Picking Task CSV:**
```csv
id,task_id,task_name,task_type,status,assigned_device_id,assigned_device_ids,assigned_user_id,description,estimated_duration,actual_duration,created_at,started_at,completed_at,map_id,zone_ids,stop_ids,task_details
1,TASK0001,Picking Task 1,picking,pending,1,1,5,Pick items from shelves,45,,2026-02-05T23:18:12.534787,,,19,3,"x,z,y","{""pickup_map_id"": ""19"", ""pickup_map_name"": ""komal"", ""pickup_stops"": [""x""], ""pickup_stop_names"": [""x (x)""], ""check_stops"": [""z""], ""check_stop_names"": [""z (z)""], ""drop_stops"": [""y""], ""drop_stop_names"": [""y (y)""], ""end_zone"": ""3"", ""end_zone_name"": ""3""}"
```

---

### 2. **AUDITING Task CSV**

**Required Fields:**
- `task_name`
- `task_type` = `auditing`
- `assigned_device_id` or `assigned_device_ids`

**Additional Fields for Auditing:**

| Field in task_details | Type | Description | Example |
|----------------------|------|-------------|---------|
| `auditing_map_id` | String | Map ID for audit | `19` |
| `auditing_map_name` | String | Map name for audit | `komal` |
| `barcode` | String | Barcode to audit | `BAR123456` |
| `csv_file_path` | String | Path to external CSV file with audit details | `/path/to/audit.csv` |
| `end_zone` | String | End zone ID | `3` |
| `end_zone_name` | String | End zone display name | `Zone C` |

**Example Auditing Task CSV:**
```csv
id,task_id,task_name,task_type,status,assigned_device_id,assigned_device_ids,assigned_user_id,description,estimated_duration,actual_duration,created_at,started_at,completed_at,map_id,zone_ids,stop_ids,task_details
2,TASK0002,Inventory Audit,auditing,pending,1,1,6,Audit zone inventory,60,,2026-02-05T23:18:12.534787,,,19,3,,"{""auditing_map_id"": ""19"", ""auditing_map_name"": ""komal"", ""barcode"": ""BAR123456"", ""end_zone"": ""3"", ""end_zone_name"": ""Zone C""}"
```

---

### 3. **STORING Task CSV**

**Required Fields:**
- `task_name`
- `task_type` = `storing`
- `assigned_device_id` or `assigned_device_ids`

**Additional Fields for Storing:**

| Field in task_details | Type | Description | Example |
|----------------------|------|-------------|---------|
| `storing_map_id` | String | Map ID for storage | `1` |
| `storing_map_name` | String | Map name for storage | `m12` |
| `from_zone` | String | Starting zone ID | `1` |
| `to_zone` | String | Destination zone ID | `3` |
| `zone_path` | JSON Array | Path through zones | `["1", "2", "3"]` |
| `pickup_zone_ids` | JSON Array | Zone IDs to pick from | `["13", "14"]` |
| `pickup_zone_name` | String | Display name for pickup path | `1 → 2 → 3` |
| `pickup_stops` | JSON Array | Stop IDs to pick from | `["x"]` |
| `pickup_stop_names` | JSON Array | Display names of pickup stops | `["x (x)"]` |

**Example Storing Task CSV:**
```csv
id,task_id,task_name,task_type,status,assigned_device_id,assigned_device_ids,assigned_user_id,description,estimated_duration,actual_duration,created_at,started_at,completed_at,map_id,zone_ids,stop_ids,task_details
3,TASK0003,Storage Task 1,storing,pending,1,1,5,Store items in zone 3,50,,2026-02-05T23:18:12.534787,,,1,"13,14",x,"{""storing_map_id"": ""1"", ""storing_map_name"": ""m12"", ""from_zone"": ""1"", ""to_zone"": ""3"", ""zone_path"": [""1"", ""2"", ""3""], ""pickup_zone_ids"": [""13"", ""14""], ""pickup_zone_name"": ""1 → 2 → 3"", ""pickup_stops"": [""x""], ""pickup_stop_names"": [""x (x)""]}"
```

---

### 4. **CHARGING Task CSV**

**Required Fields:**
- `task_name`
- `task_type` = `charging`
- `assigned_device_id` or `assigned_device_ids`

**Task Details:** Usually empty for charging tasks as they are auto-generated.

**Example Charging Task CSV:**
```csv
id,task_id,task_name,task_type,status,assigned_device_id,assigned_device_ids,assigned_user_id,description,estimated_duration,actual_duration,created_at,started_at,completed_at,map_id,zone_ids,stop_ids,task_details
4,TASK0004,Charging Device 1,charging,pending,1,1,,Charge device,120,,2026-02-05T23:18:12.534787,,,,,,"{}"
```

---

## CSV Format Guidelines

### General Rules:
1. **Headers must be in the first row** exactly as shown above
2. **Date/Time Format**: ISO 8601 format: `YYYY-MM-DDTHH:MM:SS.mmmmmm`
3. **JSON Fields**: The `task_details` column must be valid JSON string with escaped quotes
4. **Multiple IDs**: Use comma-separated values: `id1,id2,id3`
5. **Empty Fields**: Use empty string (nothing between commas) for optional fields

### task_details JSON Field Rules:
- Wrap the entire JSON object in double quotes
- Escape inner double quotes with backslash: `\"`
- Arrays should use square brackets: `[]`
- String values inside JSON should use double quotes

**Correct Example:**
```
"{""pickup_map_id"": ""19"", ""pickup_stops"": [""x"", ""y""]}"
```

**Incorrect Example:**
```
{pickup_map_id: 19}  ❌ Not quoted
"{pickup_map_id': '19'}"  ❌ Wrong quote type
```

---

## Important Notes

1. **Auto-generated Fields**: `id`, `task_id`, `created_at` will be auto-generated if not provided. You can pre-fill them if needed.

2. **Device IDs must exist**: The `assigned_device_id` or `assigned_device_ids` must reference existing devices in your system.

3. **Status field**: If you leave `status` empty or omit it, it defaults to `pending`.

4. **Map/Zone/Stop validation**: Referenced map IDs, zone IDs, and stop IDs must exist in your system.

5. **Timestamp format**: If you don't provide `created_at`, the system will use the current timestamp.

---

## Sample Complete CSV File

Here's a complete example with multiple tasks:

```csv
id,task_id,task_name,task_type,status,assigned_device_id,assigned_device_ids,assigned_user_id,description,estimated_duration,actual_duration,created_at,started_at,completed_at,map_id,zone_ids,stop_ids,task_details
,TASK0001,Morning Picking,picking,pending,1,1,5,Pick items from shelf A,45,,2026-02-06T08:00:00.000000,,,19,3,"x,z,y","{""pickup_map_id"": ""19"", ""pickup_map_name"": ""komal"", ""pickup_stops"": [""x""], ""pickup_stop_names"": [""x (x)""], ""check_stops"": [""z""], ""check_stop_names"": [""z (z)""], ""drop_stops"": [""y""], ""drop_stop_names"": [""y (y)""], ""end_zone"": ""3"", ""end_zone_name"": ""Zone C""}"
,TASK0002,Zone Audit,auditing,pending,2,2,6,Audit inventory in zone 1,60,,2026-02-06T09:00:00.000000,,,19,1,,"{""auditing_map_id"": ""19"", ""auditing_map_name"": ""komal"", ""barcode"": ""BAR001"", ""end_zone"": ""1"", ""end_zone_name"": ""Zone A""}"
,TASK0003,Storage Operation,storing,pending,3,3,5,Move items to zone 3,50,,2026-02-06T10:00:00.000000,,,1,"13,14",x,"{""storing_map_id"": ""1"", ""storing_map_name"": ""m12"", ""from_zone"": ""1"", ""to_zone"": ""3"", ""zone_path"": [""1"", ""2"", ""3""], ""pickup_zone_ids"": [""13"", ""14""], ""pickup_zone_name"": ""1 → 2 → 3"", ""pickup_stops"": [""x""], ""pickup_stop_names"": [""x (x)""]}"
```

---

## How to Use

1. **Create the CSV file** using the format specified above
2. **In the Task Creation UI**, click **"📁 Upload CSV File"** button
3. **Select your CSV file**
4. The task details will be parsed and loaded into the form
5. **Review the details** and click **"✓ Create Task"** to save

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| CSV not loading | Check headers match exactly, ensure it's valid UTF-8 encoding |
| Fields not populating | Verify task_details JSON is valid (use online JSON validator) |
| Device not found | Ensure device ID exists in devices.csv |
| Invalid date format | Use ISO format: `YYYY-MM-DDTHH:MM:SS.mmmmmm` |
| JSON parsing error | Escape inner quotes with backslash: `\""` |

