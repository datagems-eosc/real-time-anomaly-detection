# 🌦️ Real-Time Weather Anomaly Detection System

Real-time monitoring and anomaly detection for 14 meteorological stations from the National Observatory of Athens (NOA).

> **Note**: This system now uses a **Dual-Verification Strategy** (Temporal + Spatial) to distinguish between device failures and extreme weather events.

📖 **[View Full Documentation](https://datagems-eosc.github.io/real-time-anomaly-detection/)** | 🌐 **[GitHub Repository](https://github.com/datagems-eosc/real-time-anomaly-detection)**

---

## 🧠 Core Logic: Time-Space Dual Verification

This system uses a two-step verification process to minimize false alarms.

```mermaid
flowchart TD
    A[Start Detection] --> B{1. Temporal Check}
    B -- Normal --> C[✅ safe]
    B -- Anomalous? --> D{2. Spatial Check}
    D -- Trend Matches Neighbors --> E[🌧️ Weather Event]
    D -- Trend Contradicts Neighbors --> F[🔴 Device Failure]
```

### Step 1: Temporal Detection ("Self-Check")
*   **Question**: "Is the station's current value consistent with its own history?"
*   **Method**: **ARIMA** (AutoRegressive Integrated Moving Average) predicts the next value based on the past 6 hours.
*   **Result**: If the actual value deviates significantly from the prediction, it is flagged as a **Suspect**.

### Step 2: Spatial Verification ("Neighbor-Check")
*   **Question**: "Are neighboring stations behaving similarly?"
*   **Method**: **Pearson Correlation** is calculated between the suspect station and its neighbors (within 100km).
*   **Result**:
    *   **High Correlation (>0.6)**: Neighbors are doing the same thing (e.g., all dropping temp). -> **Ignored as Weather**.
    *   **Low Correlation (<0.3)**: Only this station is acting up. -> **Confirmed as Device Failure**.

---

## 📦 Installation & Requirements

### 1. Environment Setup
It is recommended to use Conda or venv to manage dependencies.

```bash
# Activate your environment
source ~/software/miniconda3/bin/activate datagem
# OR
conda activate datagem
```

### 2. Install Dependencies
Install the required Python packages using the provided `requirements.txt`.

```bash
pip install -r requirements.txt
```

**Core Dependencies**:
*   `pandas` & `numpy`: Data manipulation.
*   `sqlite3`: Lightweight database for streaming data.
*   `statsmodels`: For ARIMA and Time Series analysis.
*   `scikit-learn`: For Isolation Forest and other ML models.
*   `folium`: For map visualization.

---

## 🌊 System Architecture

### 1. Data Flow (Streaming)
The system follows a **Pull-Based Streaming Architecture**:

1.  **Ingest (`streaming_collector_sqlite.py`)**: 
    *   Runs as a background service (daemon).
    *   Fetches GeoJSON data from NOA API **every 10 minutes**.
    *   Parses and saves data into the local `weather_stream.db`.

2.  **Detect (`anomaly_detector.py`)**:
    *   **Short-term Detection**: Uses a **Sliding Window** (e.g., last 6 hours) for real-time anomaly detection using temporal + spatial dual-verification
    *   **Long-term Health Check**: Analyzes sensor health over days/weeks to detect chronic issues:
        -  **Stalled sensors**: Wind speed stuck at zero (>30% zero readings)
        -  **Failed sensors**: Excessive missing data (>50% data loss)
        -  **Degraded sensors**: Abnormally low variance (<0.1)
        -  **Data completeness tracking**: Monitors overall data quality per station
    *   Triggered on-demand or via cron/scheduler.

### 2. Database Schema
Data is stored in a single optimized SQLite table `observations`.

```sql
CREATE TABLE observations (
    time TIMESTAMP,          -- Observation time
    station_id TEXT,         -- Unique station identifier
    temp_out REAL,           -- Temperature
    out_hum REAL,            -- Humidity
    wind_speed REAL,         -- Wind Speed
    bar REAL,                -- Pressure
    rain REAL,               -- Rain
    PRIMARY KEY (time, station_id)
);
```

## 🔮 Future Roadmap: Scaling Up

While SQLite is excellent for standalone deployment, the system is designed to scale.

### Transition to TimescaleDB (PostgreSQL)
For enterprise-scale monitoring (e.g., thousands of stations, years of history), we recommend migrating to **TimescaleDB**.

**Migration Steps**:
1.  **Deploy TimescaleDB**: Use Docker to start a TimescaleDB instance.
2.  **Update Connection**: Change the DB connection string in `streaming_collector_sqlite.py` from file path to PostgreSQL URL (`postgresql://user:pass@host:5432/weather`).
3.  **Enable Hypertable**:
    ```sql
    SELECT create_hypertable('observations', 'time');
    ```
    This automatically partitions data by time for rapid query performance.

---

## 📊 Data Sample

A glimpse of the real-time weather data collected from the stations.

**Data Source**: [NOA DataGEMS Feed](https://stratus.meteo.noa.gr/data/stations/latestValues_Datagems.geojson) (Updates every 10 minutes)

| time | station_id | temp_out (°C) | out_hum (%) | wind_speed (km/h) | bar (hPa) | rain (mm) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2025-11-22 17:00:00 | uth_volos | 10.1 | 85 | 12.5 | 1013.2 | 0.0 |
| 2025-11-22 17:00:00 | volos | 10.4 | 83 | 10.8 | 1013.5 | 0.0 |
| 2025-11-22 17:00:00 | zagora | 8.2 | 91 | 15.2 | 985.4 | 0.2 |
| 2025-11-22 16:50:00 | uth_volos | 10.3 | 84 | 11.9 | 1013.1 | 0.0 |
| 2025-11-22 16:50:00 | volos | 10.6 | 82 | 10.5 | 1013.4 | 0.0 |

**Key Variables**:
*   **`temp_out`**: Outdoor Temperature (Primary indicator for weather events)
*   **`out_hum`**: Outdoor Humidity
*   **`wind_speed`**: Wind Speed (Often fluctuates, triggers anomalies easily)
*   **`bar`**: Barometric Pressure (Useful for detecting storms)
*   **`rain`**: Rainfall rate

---

## 🗺️ Station Network Visualization

Understanding the spatial relationships between stations is crucial for the dual-verification strategy.

👉 **[Interactive Map: View Station Neighbors](https://datagems-eosc.github.io/real-time-anomaly-detection/spatial_network_map.html)**

*   **Blue Dots**: Weather stations.
*   **Red Lines**: Connect stations that are considered "neighbors" (within 100km).
*   **Logic**: If Station A is anomalous, the system checks these connected neighbors for verification.

---

## 🔬 Supported Detection Methods

### 1. Temporal Methods (Time Dimension)
Used in **Step 1** to detect if a single station is behaving abnormally compared to its past.

| Method | Description | Best For |
| :--- | :--- | :--- |
| **`arima`** | AutoRegressive Integrated Moving Average | **Complex Trends** (Weather, Stocks). Best overall accuracy. |
| **`3sigma`** | 3-Sigma Rule (Z-Score) | **Extreme Outliers**. Simple and fast, assuming normal distribution. |
| **`iqr`** | Interquartile Range | **Boxplot Logic**. Good for exploratory analysis. |
| **`isolation_forest`** | Isolation Forest (ML) | **Multidimensional**. Can find subtle anomalies in high-dimensional space. |
| **`stl`** | Seasonal-Trend Decomposition | **Seasonality**. If data has strong daily/weekly cycles. |
| **`lof`** | Local Outlier Factor | **Density**. Finding outliers in clusters. |

### 2. Spatial Methods (Space Dimension)
Used in **Step 2** to verify if the anomaly is isolated or widespread.

> **Note on Missing Data**: We use **Linear Interpolation** to fill gaps in neighbor data before comparison, ensuring robust correlation even with occasional data loss.

| Method | Description | Logic |
| :--- | :--- | :--- |
| **`pearson`** | Pearson Correlation (Trend) | Checks if neighbor trends match (`>0.6` = Match, `<0.3` = Mismatch). |
| **`distance`** | MAD Deviation (Static) | **Fallback method**. Checks if current value deviates from neighbors' median (`> 3 * MAD`). |

---

## 🚀 Usage Guide

### 1. Short-Term Anomaly Detection (Hours)

For real-time detection of sudden anomalies in the last few hours.

**Basic Syntax**:
```bash
python anomaly_detector.py --end "TIMESTAMP" --window HOURS --temporal-method METHOD --spatial-verify
```

**Example Command**:
```bash
python anomaly_detector.py \
  --end "2025-11-22 17:00:00" \
  --window 6 \
  --temporal-method 3sigma \
  --spatial-verify
```

| Argument | Description | Recommended Value |
| :--- | :--- | :--- |
| `--end` | The target timestamp to detect | Specific time (e.g., `"2025-11-22 17:00:00"`) |
| `--window` | Length of historical data to analyze (hours) | `6` |
| `--temporal-method` | Algorithm for Step 1 (Temporal) | `arima` (best) or `3sigma` |
| `--spatial-verify` | **Enable Step 2 (Spatial Verification)** | Always include this flag |
| `--save` | Save report to JSON file | Optional |

**Example Detection Run**:

```bash
python anomaly_detector.py --end "2025-11-23 09:00:00" --window 6 --temporal-method 3sigma --spatial-verify
```

**Example Output**:

```
Connected to SQLite: weather_stream.db
Date: 2025-11-25 00:25:36
Window: Last 6h from 2025-11-23 09:00:00
--------------------------------------------------
Total: 14 | Anomalous: 4
[Station: dodoni]
  ⚠️  wind_speed: 1 anomalies
    • 2025-11-23 05:40:00: 11.3 -> 🔴 Device Failure (Trend Inconsistent (Corr: -0.17))
    📊 DETAILED DIAGNOSIS - Device Failure at dodoni
    Variable: wind_speed | Window: Last 6h from 2025-11-23 09:00:00
    ======================================================================
    Time                 |       dodoni |      grevena |
    ----------------------------------------------------------------------
    2025-11-23 05:40     |        11.30 |         0.00 |
    2025-11-23 06:00     |         3.20 |         0.00 |
    2025-11-23 07:00     |         3.20 |         0.00 |
    2025-11-23 08:00     |         0.00 |         1.60 |
    2025-11-23 09:00     |         3.20 |         1.60 |
    ======================================================================
    💡 Analysis: Station dodoni shows trend inconsistent with 1 neighbors
    Correlation: -0.17 (< 0.3 indicates likely sensor failure)

[Station: makrinitsa]
  ⚠️  temp_out: 1 anomalies
    • 2025-11-23 09:00:00: 11.9 -> 🌧️ Weather Event (Trend Consistent (Corr: 0.77))

[Station: uth_volos]
  ⚠️  wind_speed: 1 anomalies
    • 2025-11-23 09:00:00: 19.3 -> 🌧️ Weather Event (Trend Consistent (Corr: 0.75))
```

**Key Observations**:
- ✅ **Weather Events**: `makrinitsa`, `uth_volos`, and `volos-port` showed high correlation (>0.7) with neighbors → Normal extreme weather
- 🔴 **Device Failure**: `dodoni` showed negative correlation (-0.17) → Sensor malfunction detected
- 📊 **Detailed Diagnosis**: For device failures, the system displays a comparison table with neighboring stations to visualize the inconsistency

---

### 2. Long-Term Sensor Health Check (Days/Weeks) 

For detecting chronic sensor problems like stalled wind sensors or excessive data loss over extended time periods.

**Basic Syntax**:
```bash
python anomaly_detector.py --health-check --days DAYS [--station STATION_ID] [--save FILENAME]
```

**Example Commands**:
```bash
# Check specific problem station for the last 7 days
python anomaly_detector.py --health-check --days 7 --station grevena --save health_report.json
```

| Argument | Description | Recommended Value |
| :--- | :--- | :--- |
| `--health-check` | Enable long-term health check mode | Required flag |
| `--days` | Number of days to analyze | `7` (weekly), `30` (monthly) |
| `--station` | Check specific station only | Optional (default: all stations) |
| `--save` | Save detailed JSON report | Optional (e.g., `health_report.json`) |

**What it Detects**:
- **Stalled wind sensors**: >30% zero values in wind_speed (e.g., sensor physically stuck)
- **High data loss**: >50% missing observations (e.g., communication failures)
- **Stuck sensors**: Abnormally low variance (< 0.1, sensor not responding to changes)
- **Data completeness**: Tracks percentage of expected observations received

**Example Console Output**:
```text
═══════════════════════════════════════════════════════════════════════════════
📊 LONG-TERM SENSOR HEALTH CHECK
Period: Last 7 days
Station              Status       Completeness    Issues
--------------------------------------------------------------------------------
amfissa              ✅ HEALTHY   57.4%           0 problems
dodoni               ✅ HEALTHY   57.6%           0 problems
embonas              ✅ HEALTHY   58.0%           0 problems
grevena              🔴 CRITICAL  58.0%           1 problems
  └─ wind_speed: High zero ratio (71.6%) - sensor may be stalled
heraclion            ✅ HEALTHY   57.9%           0 problems
kolympari            ✅ HEALTHY   56.1%           0 problems
...
--------------------------------------------------------------------------------

Report exported to: health_report_20251124_233705.json
```

**JSON Report Structure**:
The system exports detailed machine-readable reports in JSON format:

```json
{
  "station_id": "grevena",
  "analysis_period_days": 7,
  "data_completeness": 0.58,
  "total_data_points": 585,
  "overall_status": "critical",
  "variable_reports": [
    {
      "variable": "wind_speed",
      "zero_ratio": 0.716,
      "null_ratio": 0.0,
      "variance": 1.37,
      "issues": ["High zero ratio (71.6%) - sensor may be stalled"],
      "severity": "critical"
    }
  ]
}
```

**JSON Fields Explained**:
- `data_completeness`: Percentage of expected data received (0.58 = 58%)
- `overall_status`: "healthy", "warning", or "critical"
- `variable_reports`: Array of metrics per monitored variable
  - `zero_ratio`: Proportion of zero values (0.716 = 71.6%)
  - `null_ratio`: Proportion of missing values
  - `variance`: Statistical variance (low values indicate stuck sensors)
---

### 3. Output Explanation (Short-Term Detection)

The system prints a human-readable report to the console for short-term anomaly detection.

#### A. Summary Section
Quickly see if any *real* action is needed.

```text
Total Stations: 14
Anomalous Stations: 1
Normal Stations: 13

Anomaly Breakdown:
  🔴 Device Failures: 0      <-- CHECK THIS (Real Hardware Issues)
  🌧️ Weather Events: 1       <-- IGNORE THIS (Just Weather)
  ⚠️ Suspected:      0       <-- MANUAL CHECK (Uncertain Cases)
```

#### B. Detailed Report Section
Shows exactly *why* a station was flagged.

```text
[ STATION: uth_volos (Volos - University) ]
  ⚠️  Temperature Anomaly:
      Method: arima
      Expected: 12.5°C | Actual: 10.1°C
      • 2025-11-22 17:00:00: 10.10°C -> 🌧️ Extreme Weather / Env Change
        └─ Diag: Trend Consistent (Corr: 0.85, 3 neighbors)
```

*   **Method**: Which temporal algorithm flagged it (`arima`).
*   **Expected/Actual**: The deviation magnitude.
*   **Arrow (`->`)**: The final classification after Spatial Verification.
    *   `🌧️ Extreme Weather`: Because `Trend Consistent` (Correlation 0.85 > 0.6).
    *   `🔴 Device Failure`: If it had said `Trend Inconsistent` (Correlation < 0.3).

---

## 📁 Project Structure

```text
├── anomaly_detector.py            # [CORE] Detection engine (Short-term + Long-term health check)
├── streaming_collector_sqlite.py  # [CORE] Real-time data collector (daemon)
├── generate_map.py                # [TOOL] Generate station network visualization
├── view_data.py                   # [TOOL] Query and export database data
├── manage_collector.sh            # [OPS] Collector service management (start/stop/status)
│
├── weather_stream.db              # [DATA] SQLite database (time-series observations)
├── spatial_network_map.html       # [OUTPUT] Interactive station network map
│
├── requirements.txt               # Python dependencies
├── docs_requirements.txt          # Documentation dependencies (MkDocs)
├── mkdocs.yml                     # Documentation configuration
├── stream_detection/docs/         # Documentation source files
│
└── README.md                      # Project overview (this file)
```

**Core Capabilities**:
- ✅ **Short-term Detection**: Real-time anomaly detection (hours) with time-space dual verification
- ✅ **Long-term Health Check**: Sensor health monitoring (days/weeks) - detects stalled sensors, data loss, and degradation 🆕
- ✅ **Spatial Verification**: Distinguish weather events from device failures using neighbor correlation
- ✅ **Multiple Detection Methods**: ARIMA, 3-Sigma, MAD, IQR, Isolation Forest, STL, LOF
- ✅ **JSON Export**: Machine-readable reports for integration with monitoring systems


