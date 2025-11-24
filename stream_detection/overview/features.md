# Key Features

## Dual-Verification Strategy

The core innovation of this system is its ability to distinguish between device failures and extreme weather events through a two-step verification process.

### Why This Matters

Traditional anomaly detection systems generate numerous false alarms when extreme weather events occur, because they cannot distinguish between:

- **Genuine Equipment Failure**: Only one station is malfunctioning
- **Extreme Weather Event**: Multiple stations show similar anomalous patterns

Our dual-verification approach solves this by combining:

1. **Temporal Analysis** (Self-Check): "Is this station behaving differently than usual?"
2. **Spatial Verification** (Neighbor-Check): "Are nearby stations behaving similarly?"

## Multi-Method Detection

The system supports seven different temporal detection algorithms:

| Method | Best For | Computational Cost |
|--------|----------|-------------------|
| ARIMA | Complex trends, seasonal patterns | High |
| 3-Sigma | Quick outlier detection | Low |
| MAD | Robust to outliers | Medium |
| IQR | Exploratory analysis | Low |
| Isolation Forest | Multidimensional patterns | High |
| STL | Strong seasonality | High |
| LOF | Density-based outliers | Medium |

!!! tip "Recommended Method"
    For weather data, **ARIMA** provides the best balance between accuracy and false alarm reduction.

## Real-Time Processing

### Streaming Architecture

- **Ingestion Frequency**: Data collected every 10 minutes
- **Detection Window**: Configurable (default: 6 hours)
- **Sliding Stride**: Moves forward with each new data point
- **Latency**: Near real-time detection (< 1 minute processing time)

### Memory Efficiency

The sliding window mechanism ensures:

- **Constant Memory Usage**: O(1) regardless of database size
- **Fast Query Performance**: Only queries relevant time ranges
- **Scalable Storage**: Old data remains accessible but not loaded into memory

## Spatial Intelligence

### Neighbor Detection

The system automatically:

1. Calculates distances between all station pairs
2. Identifies neighbors within 100km radius
3. Computes correlation coefficients during anomalies
4. Interpolates missing data to ensure robust comparison

### Correlation Thresholds

| Correlation | Interpretation | Action |
|-------------|----------------|--------|
| > 0.6 | High correlation - Weather event | Ignore |
| 0.3 - 0.6 | Uncertain - Requires manual review | Flag as "Suspected" |
| < 0.3 | Low correlation - Device failure | Alert |

!!! note "Missing Data Handling"
    When neighbor data has gaps, the system uses **linear interpolation** to fill missing values before computing correlations.

## Scalable Database Backend

### SQLite Mode (Default)

Perfect for:

- Standalone deployment
- Development and testing
- Single-server installations
- < 100 stations

### TimescaleDB Mode (Enterprise)

Recommended for:

- Multi-server deployment
- > 100 stations
- Years of historical data
- Advanced analytics queries

Migration between backends requires minimal code changes - only the connection string needs updating.

## Interactive Visualization

The system generates:

- **Station Network Maps**: Interactive HTML maps showing station locations and neighbor connections
- **Anomaly Reports**: JSON format for integration with monitoring dashboards
- **Console Output**: Human-readable summaries for manual inspection

View an example: [Station Network Map](../system/station-network.md)

## API-First Design

While currently used as a command-line tool, the detection engine is designed with clear interfaces:

- Input: Time window + detection parameters
- Output: Structured anomaly reports
- Future-ready: Can be easily wrapped in a REST API

## Extensibility

Adding new features is straightforward:

- **New Detection Methods**: Implement the `TemporalDetector` interface
- **New Variables**: Add to the database schema and detector configuration
- **New Spatial Methods**: Extend the `SpatialVerifier` class
- **New Data Sources**: Replace the collector module

