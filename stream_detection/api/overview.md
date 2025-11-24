# API Overview

The Real-Time Anomaly Detection system is primarily designed as a command-line tool but follows an API-first architecture that makes it easy to integrate into larger systems or wrap with a REST API.

## Command-Line Interface

### Basic Usage

```bash
python anomaly_detector.py [OPTIONS]
```

### Quick Examples

```bash
# Detect anomalies at current time
python anomaly_detector.py --end "NOW" --temporal-method arima --spatial-verify

# Analyze specific timestamp
python anomaly_detector.py --end "2025-11-22 17:00:00" --window 6 --temporal-method arima --spatial-verify

# Compare multiple methods
python anomaly_detector.py --end "NOW" --temporal-method 3sigma --spatial-verify --save report_3sigma.json
python anomaly_detector.py --end "NOW" --temporal-method arima --spatial-verify --save report_arima.json

# Quick check without spatial verification
python anomaly_detector.py --end "NOW" --temporal-method 3sigma
```

## Core Parameters

### Required Parameters

None - all parameters have sensible defaults.

### Optional Parameters

#### `--end`

**Type**: String (timestamp or "NOW")  
**Default**: "NOW"  
**Description**: The target timestamp to detect anomalies

**Formats**:

- `"NOW"`: Current time
- `"2025-11-22 17:00:00"`: ISO format
- `"2025-11-22T17:00:00"`: ISO format with T separator
- `"1732294800"`: Unix timestamp

**Examples**:

```bash
# Current time
--end "NOW"

# Specific time (useful for historical analysis)
--end "2025-11-22 17:00:00"

# Unix timestamp
--end "1732294800"
```

#### `--window`

**Type**: Integer  
**Default**: 6  
**Unit**: Hours  
**Description**: Length of historical data to analyze

**Recommendations**:

- Minimum: 1 hour (6 data points)
- Default: 6 hours (36 data points) - best for ARIMA
- Maximum: 24 hours (144 data points) - for STL with daily cycles

**Examples**:

```bash
# Quick check (1 hour)
--window 1

# Standard analysis (6 hours)
--window 6

# Full daily cycle (24 hours)
--window 24
```

#### `--temporal-method`

**Type**: String (enum)  
**Default**: "arima"  
**Options**: `arima`, `3sigma`, `mad`, `iqr`, `isolation_forest`, `stl`, `lof`  
**Description**: Algorithm for temporal anomaly detection

**Comparison**:

| Method | Speed | Accuracy | False Positives | Use Case |
|--------|-------|----------|-----------------|----------|
| arima | ⚡⚡ | ⭐⭐⭐⭐⭐ | Low | Default (best overall) |
| 3sigma | ⚡⚡⚡⚡⚡ | ⭐⭐⭐ | Medium | Quick checks |
| mad | ⚡⚡⚡⚡ | ⭐⭐⭐⭐ | High | Robust to outliers |
| iqr | ⚡⚡⚡⚡⚡ | ⭐⭐⭐ | Medium | Exploratory |
| isolation_forest | ⚡⚡⚡ | ⭐⭐⭐⭐ | Low | Multidimensional |
| stl | ⚡⚡ | ⭐⭐⭐⭐ | Medium | Seasonal data |
| lof | ⚡⚡ | ⭐⭐⭐ | Medium | Density-based |

**Examples**:

```bash
# Best accuracy (default)
--temporal-method arima

# Fastest
--temporal-method 3sigma

# Most robust
--temporal-method mad
```

See [Detection Methods](../system/detection-methods.md) for detailed comparisons.

#### `--spatial-verify`

**Type**: Flag (boolean)  
**Default**: False  
**Description**: Enable spatial verification to distinguish weather events from device failures

**Recommendation**: **Always use this flag** in production to reduce false positives by ~80%.

**Behavior**:

- **Without flag**: All temporal anomalies are reported as-is
- **With flag**: Temporal anomalies are verified against neighbors

**Examples**:

```bash
# Without spatial verification (more false positives)
python anomaly_detector.py --end "NOW"

# With spatial verification (recommended)
python anomaly_detector.py --end "NOW" --spatial-verify
```

#### `--spatial-method`

**Type**: String (enum)  
**Default**: "pearson"  
**Options**: `pearson`, `distance`  
**Description**: Method for spatial verification

**Options**:

- **`pearson`**: Trend correlation (default, recommended)
- **`distance`**: Static value comparison (fallback)

**Examples**:

```bash
# Default (correlation-based)
--spatial-method pearson

# Fallback (value-based)
--spatial-method distance
```

#### `--neighbor-radius`

**Type**: Float  
**Default**: 100.0  
**Unit**: Kilometers  
**Description**: Maximum distance for neighbor selection

**Recommendations**:

- Urban areas: 50-75 km
- Rural areas: 100-150 km
- Mountainous: 50 km (microclimates)

**Examples**:

```bash
# Default
--neighbor-radius 100

# Tighter neighborhood
--neighbor-radius 50

# Wider neighborhood
--neighbor-radius 150
```

#### `--save`

**Type**: String (file path)  
**Default**: None  
**Description**: Save report to JSON file

**Examples**:

```bash
# Save with timestamp
--save "report_$(date +%Y%m%d_%H%M%S).json"

# Save with method name
--save "report_arima.json"

# Full path
--save "/var/log/anomaly_reports/report.json"
```

#### `--variables`

**Type**: String (comma-separated)  
**Default**: "temp_out,out_hum,wind_speed,bar,rain"  
**Description**: Variables to analyze

**Available Variables**:

- `temp_out`: Outdoor temperature
- `out_hum`: Outdoor humidity
- `wind_speed`: Wind speed
- `bar`: Barometric pressure
- `rain`: Rainfall

**Examples**:

```bash
# Only temperature
--variables "temp_out"

# Temperature and pressure
--variables "temp_out,bar"

# All variables (default)
--variables "temp_out,out_hum,wind_speed,bar,rain"
```

#### `--verbose`

**Type**: Flag (boolean)  
**Default**: False  
**Description**: Enable detailed debug output

**Examples**:

```bash
# Standard output
python anomaly_detector.py --end "NOW" --spatial-verify

# Verbose output (for troubleshooting)
python anomaly_detector.py --end "NOW" --spatial-verify --verbose
```

## Response Format

### Console Output

Human-readable report with:

1. **Summary Section**: Quick overview
2. **Detailed Reports**: Per-station analysis
3. **Data Tables**: For manual inspection (when anomalies found)

Example:

```
═══════════════════════════════════════════════
 ANOMALY DETECTION REPORT
═══════════════════════════════════════════════
End Time: 2025-11-22 17:00:00
Window: 6 hours
Method: arima
Spatial Verification: Enabled

Total Stations: 14
Anomalous Stations: 1
Normal Stations: 13

Anomaly Breakdown:
  🔴 Device Failures: 0
  🌧️ Weather Events: 1
  ⚠️ Suspected: 0

═══════════════════════════════════════════════
 DETAILED REPORTS
═══════════════════════════════════════════════

[ STATION: uth_volos (Volos - University) ]
  ⚠️  Temperature Anomaly:
      Method: arima
      Expected: 12.5°C | Actual: 10.1°C
      • 2025-11-22 17:00:00: 10.10°C -> 🌧️ Extreme Weather / Env Change
        └─ Diag: Trend Consistent (Corr: 0.85, 3 neighbors)
```

### JSON Output

Structured format for programmatic processing:

```json
{
  "metadata": {
    "timestamp": "2025-11-22T17:00:00Z",
    "window_hours": 6,
    "temporal_method": "arima",
    "spatial_verify": true,
    "spatial_method": "pearson"
  },
  "summary": {
    "total_stations": 14,
    "anomalous_stations": 1,
    "normal_stations": 13,
    "device_failures": 0,
    "weather_events": 1,
    "suspected": 0
  },
  "anomalies": [
    {
      "station_id": "uth_volos",
      "station_name": "Volos - University",
      "variable": "temp_out",
      "timestamp": "2025-11-22T17:00:00Z",
      "actual_value": 10.1,
      "expected_value": 12.5,
      "deviation": -2.4,
      "temporal_method": "arima",
      "classification": "weather_event",
      "spatial_verification": {
        "enabled": true,
        "method": "pearson",
        "correlation": 0.85,
        "neighbors_checked": 3,
        "neighbors": ["volos", "zagora", "larissa"]
      }
    }
  ],
  "normal_stations": [
    "volos",
    "zagora",
    "pelion",
    "anavra",
    "domokos",
    "karditsa",
    "larissa",
    "trikala",
    "pyli",
    "metsovo",
    "ioannina",
    "agrinio",
    "preveza"
  ]
}
```

## Exit Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 0 | Success | Detection completed successfully |
| 1 | Error | General error (check error message) |
| 2 | Database Error | Cannot connect to database |
| 3 | Invalid Parameters | Invalid command-line arguments |
| 4 | Insufficient Data | Not enough historical data for analysis |

## Python API

While primarily a CLI tool, the detector can be imported as a Python module:

```python
from anomaly_detector import AnomalyDetector, TemporalConfig, SpatialConfig

# Initialize detector
detector = AnomalyDetector(database_path="weather_stream.db")

# Configure detection
temporal_config = TemporalConfig(
    method="arima",
    window_hours=6
)

spatial_config = SpatialConfig(
    enabled=True,
    method="pearson",
    neighbor_radius_km=100
)

# Run detection
results = detector.detect(
    end_time="2025-11-22 17:00:00",
    temporal_config=temporal_config,
    spatial_config=spatial_config,
    variables=["temp_out", "out_hum"]
)

# Process results
for anomaly in results.anomalies:
    print(f"Station {anomaly.station_id}: {anomaly.classification}")
    if anomaly.classification == "device_failure":
        send_alert(anomaly)
```

## REST API Wrapper (Future)

The system is designed to be easily wrapped in a REST API. Here's a proposed interface:

```http
POST /api/v1/detect
Content-Type: application/json

{
  "end_time": "2025-11-22T17:00:00Z",
  "window_hours": 6,
  "temporal_method": "arima",
  "spatial_verify": true,
  "variables": ["temp_out", "out_hum"]
}
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "summary": {
    "device_failures": 0,
    "weather_events": 1,
    "suspected": 0
  },
  "anomalies": [...]
}
```

See the [GitHub Issues](https://github.com/datagems-eosc/real-time-anomaly-detection/issues) for REST API development progress.

