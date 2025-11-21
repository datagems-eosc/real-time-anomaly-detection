"""
Time-Series Based Anomaly Detection for Weather Data
====================================================

This module implements two types of anomaly detection:
1. Spatial Anomaly Detection (same time, different locations)
2. Temporal Anomaly Detection (same location, different times)

Author: Weather Anomaly Detection Team
Date: 2025-10-22
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from collections import defaultdict


@dataclass
class AnomalyAlert:
    """
    Data structure for anomaly detection results.
    """
    station_id: str
    timestamp: int
    datetime_str: str
    anomaly_type: str  # 'SPATIAL' or 'TEMPORAL'
    variable: str
    value: float
    severity: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    z_score: float
    deviation: float
    description: str
    neighbors_info: Optional[Dict] = None
    
    def to_dict(self):
        return asdict(self)


class SpatialAnomalyDetector:
    """
    Spatial Anomaly Detection: Compare each station with its K nearest neighbors at the same time.
    
    For each timestamp and each variable:
    - Find K nearest neighbors for each station
    - Compare the station's value with neighbors' mean
    - Flag if deviation exceeds threshold
    """
    
    def __init__(self, k_neighbors: int = 5, threshold: float = 3.0):
        """
        Initialize spatial anomaly detector.
        
        Parameters:
            k_neighbors: Number of nearest neighbors to consider
            threshold: Z-score threshold for anomaly detection
        """
        self.k_neighbors = k_neighbors
        self.threshold = threshold
        self.variables = ['temp_out', 'out_hum', 'wind_speed', 'bar', 'rain']
        
    def _calculate_distance(self, loc1: Tuple[float, float], loc2: Tuple[float, float]) -> float:
        """Calculate Euclidean distance between two locations."""
        return np.sqrt((loc1[0] - loc2[0])**2 + (loc1[1] - loc2[1])**2)
    
    def _get_nearest_neighbors(self, station_id: str, station_locations: Dict, k: int) -> List[str]:
        """
        Get K nearest neighbors for a station.
        
        Parameters:
            station_id: Target station ID
            station_locations: Dict mapping station_id -> (lat, lon)
            k: Number of neighbors
            
        Returns:
            List of neighbor station IDs
        """
        if station_id not in station_locations:
            return []
        
        target_loc = station_locations[station_id]
        distances = []
        
        for sid, loc in station_locations.items():
            if sid != station_id:
                dist = self._calculate_distance(target_loc, loc)
                distances.append((sid, dist))
        
        # Sort by distance and take top K
        distances.sort(key=lambda x: x[1])
        return [sid for sid, _ in distances[:k]]
    
    def detect(self, data: Dict, station_locations: Dict) -> List[AnomalyAlert]:
        """
        Detect spatial anomalies across all timestamps and variables.
        
        Parameters:
            data: Dict[station_id][timestamp] -> observation
            station_locations: Dict[station_id] -> (lat, lon)
            
        Returns:
            List of AnomalyAlert objects
        """
        alerts = []
        
        # Collect all unique timestamps
        all_timestamps = set()
        for station_data in data.values():
            all_timestamps.update(station_data.keys())
        
        all_timestamps = sorted(all_timestamps, key=lambda x: int(x))
        
        print(f"\n{'='*80}")
        print(f"Spatial Anomaly Detection")
        print(f"{'='*80}")
        print(f"Analyzing {len(all_timestamps)} timestamps × {len(self.variables)} variables")
        print(f"Total stations: {len(data)}")
        print(f"K neighbors: {self.k_neighbors}")
        print(f"Threshold: {self.threshold} sigma")
        
        # For each timestamp
        for ts_idx, timestamp in enumerate(all_timestamps):
            ts_int = int(timestamp)
            dt = datetime.fromtimestamp(ts_int)
            dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"\n  Processing timestamp {ts_idx+1}/{len(all_timestamps)}: {dt_str}")
            
            # For each variable
            for var in self.variables:
                # Collect all values at this timestamp for this variable
                station_values = {}
                for station_id, station_data in data.items():
                    if timestamp in station_data:
                        obs = station_data[timestamp]
                        if var in obs and obs[var] not in [None, "", "---"]:
                            try:
                                station_values[station_id] = float(obs[var])
                            except (ValueError, TypeError):
                                pass
                
                if len(station_values) < 10:  # Skip if too few stations
                    continue
                
                # For each station, compare with its neighbors
                anomaly_count = 0
                for station_id, value in station_values.items():
                    neighbors = self._get_nearest_neighbors(station_id, station_locations, self.k_neighbors)
                    
                    # Get neighbor values
                    neighbor_values = []
                    valid_neighbors = []
                    for neighbor_id in neighbors:
                        if neighbor_id in station_values:
                            neighbor_values.append(station_values[neighbor_id])
                            valid_neighbors.append(neighbor_id)
                    
                    if len(neighbor_values) < 3:  # Need at least 3 neighbors
                        continue
                    
                    # Calculate statistics
                    neighbors_mean = np.mean(neighbor_values)
                    neighbors_std = np.std(neighbor_values)
                    
                    if neighbors_std == 0:
                        continue
                    
                    # Calculate spatial deviation
                    z_score = (value - neighbors_mean) / neighbors_std
                    deviation = abs(value - neighbors_mean)
                    
                    # Check if anomalous
                    if abs(z_score) > self.threshold:
                        anomaly_count += 1
                        
                        # Determine severity
                        if abs(z_score) > 5:
                            severity = 'CRITICAL'
                        elif abs(z_score) > 4:
                            severity = 'HIGH'
                        elif abs(z_score) > 3:
                            severity = 'MEDIUM'
                        else:
                            severity = 'LOW'
                        
                        alert = AnomalyAlert(
                            station_id=station_id,
                            timestamp=ts_int,
                            datetime_str=dt_str,
                            anomaly_type='SPATIAL',
                            variable=var,
                            value=value,
                            severity=severity,
                            z_score=z_score,
                            deviation=deviation,
                            description=f"Station {station_id} has abnormal {var}={value:.2f}, "
                                      f"deviates {z_score:.2f}σ from {len(valid_neighbors)} neighbors (mean={neighbors_mean:.2f})",
                            neighbors_info={
                                'neighbor_ids': valid_neighbors,
                                'neighbor_mean': float(neighbors_mean),
                                'neighbor_std': float(neighbors_std),
                                'neighbor_values': [float(v) for v in neighbor_values]
                            }
                        )
                        alerts.append(alert)
                
                if anomaly_count > 0:
                    print(f"    {var}: {anomaly_count} anomalies detected")
        
        print(f"\n  Total spatial anomalies detected: {len(alerts)}")
        return alerts


class TemporalAnomalyDetector:
    """
    Temporal Anomaly Detection: Analyze time series for each station and variable.
    
    For each station and each variable:
    - Extract the time series (6 points in current window)
    - Calculate Z-scores within the series
    - Flag if any point deviates significantly
    """
    
    def __init__(self, threshold: float = 2.5):
        """
        Initialize temporal anomaly detector.
        
        Parameters:
            threshold: Z-score threshold for anomaly detection
        """
        self.threshold = threshold
        self.variables = ['temp_out', 'out_hum', 'wind_speed', 'bar', 'rain']
        
    def _calculate_zscore(self, values: List[float]) -> np.ndarray:
        """Calculate Z-scores for a time series."""
        values = np.array(values)
        mean = np.mean(values)
        std = np.std(values)
        
        if std == 0:
            return np.zeros_like(values)
        
        return (values - mean) / std
    
    def detect(self, data: Dict) -> List[AnomalyAlert]:
        """
        Detect temporal anomalies for each station's time series.
        
        Parameters:
            data: Dict[station_id][timestamp] -> observation
            
        Returns:
            List of AnomalyAlert objects
        """
        alerts = []
        
        print(f"\n{'='*80}")
        print(f"Temporal Anomaly Detection")
        print(f"{'='*80}")
        print(f"Analyzing {len(data)} stations × {len(self.variables)} variables")
        print(f"Threshold: {self.threshold} sigma")
        
        station_count = 0
        
        # For each station
        for station_id, station_data in data.items():
            station_count += 1
            
            if station_count % 100 == 0:
                print(f"  Processed {station_count}/{len(data)} stations...")
            
            # Get all timestamps for this station (should be 6)
            timestamps = sorted(station_data.keys(), key=lambda x: int(x))
            
            if len(timestamps) < 4:  # Need at least 4 points for meaningful analysis
                continue
            
            # For each variable
            for var in self.variables:
                # Extract time series
                time_series = []
                valid_timestamps = []
                
                for ts in timestamps:
                    obs = station_data[ts]
                    if var in obs and obs[var] not in [None, "", "---"]:
                        try:
                            value = float(obs[var])
                            time_series.append(value)
                            valid_timestamps.append(ts)
                        except (ValueError, TypeError):
                            pass
                
                if len(time_series) < 4:
                    continue
                
                # Calculate Z-scores
                z_scores = self._calculate_zscore(time_series)
                
                # Check each point
                for i, (ts, value, z_score) in enumerate(zip(valid_timestamps, time_series, z_scores)):
                    if abs(z_score) > self.threshold:
                        ts_int = int(ts)
                        dt = datetime.fromtimestamp(ts_int)
                        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
                        
                        # Determine severity
                        if abs(z_score) > 4:
                            severity = 'CRITICAL'
                        elif abs(z_score) > 3:
                            severity = 'HIGH'
                        elif abs(z_score) > 2.5:
                            severity = 'MEDIUM'
                        else:
                            severity = 'LOW'
                        
                        mean_val = np.mean(time_series)
                        deviation = abs(value - mean_val)
                        
                        alert = AnomalyAlert(
                            station_id=station_id,
                            timestamp=ts_int,
                            datetime_str=dt_str,
                            anomaly_type='TEMPORAL',
                            variable=var,
                            value=value,
                            severity=severity,
                            z_score=z_score,
                            deviation=deviation,
                            description=f"Station {station_id} at time {dt_str} has abnormal {var}={value:.2f}, "
                                      f"deviates {z_score:.2f}σ from its own time series (window mean={mean_val:.2f})",
                            neighbors_info={
                                'time_series': [float(v) for v in time_series],
                                'time_series_mean': float(mean_val),
                                'time_series_std': float(np.std(time_series)),
                                'point_index': i,
                                'window_length': len(time_series)
                            }
                        )
                        alerts.append(alert)
        
        print(f"\n  Total temporal anomalies detected: {len(alerts)}")
        return alerts


def export_alerts_summary(spatial_alerts: List[AnomalyAlert], 
                         temporal_alerts: List[AnomalyAlert],
                         output_file: str):
    """
    Export anomaly detection results with summary statistics.
    
    Parameters:
        spatial_alerts: List of spatial anomalies
        temporal_alerts: List of temporal anomalies
        output_file: Output JSON file path
    """
    # Convert alerts to dicts
    spatial_dicts = [alert.to_dict() for alert in spatial_alerts]
    temporal_dicts = [alert.to_dict() for alert in temporal_alerts]
    
    # Calculate statistics
    summary = {
        'detection_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_anomalies': len(spatial_alerts) + len(temporal_alerts),
        'spatial_anomalies': {
            'count': len(spatial_alerts),
            'by_severity': {},
            'by_variable': {},
            'by_timestamp': {}
        },
        'temporal_anomalies': {
            'count': len(temporal_alerts),
            'by_severity': {},
            'by_variable': {},
            'by_station': {}
        }
    }
    
    # Spatial statistics
    for alert in spatial_alerts:
        # By severity
        severity = alert.severity
        summary['spatial_anomalies']['by_severity'][severity] = \
            summary['spatial_anomalies']['by_severity'].get(severity, 0) + 1
        
        # By variable
        var = alert.variable
        summary['spatial_anomalies']['by_variable'][var] = \
            summary['spatial_anomalies']['by_variable'].get(var, 0) + 1
        
        # By timestamp
        ts_str = alert.datetime_str
        summary['spatial_anomalies']['by_timestamp'][ts_str] = \
            summary['spatial_anomalies']['by_timestamp'].get(ts_str, 0) + 1
    
    # Temporal statistics
    for alert in temporal_alerts:
        # By severity
        severity = alert.severity
        summary['temporal_anomalies']['by_severity'][severity] = \
            summary['temporal_anomalies']['by_severity'].get(severity, 0) + 1
        
        # By variable
        var = alert.variable
        summary['temporal_anomalies']['by_variable'][var] = \
            summary['temporal_anomalies']['by_variable'].get(var, 0) + 1
        
        # By station (top 10)
        station = alert.station_id
        summary['temporal_anomalies']['by_station'][station] = \
            summary['temporal_anomalies']['by_station'].get(station, 0) + 1
    
    # Sort and limit station counts
    if summary['temporal_anomalies']['by_station']:
        station_counts = sorted(summary['temporal_anomalies']['by_station'].items(), 
                               key=lambda x: x[1], reverse=True)[:10]
        summary['temporal_anomalies']['by_station'] = dict(station_counts)
    
    # Prepare output
    output = {
        'summary': summary,
        'spatial_alerts': spatial_dicts,
        'temporal_alerts': temporal_dicts
    }
    
    # Save to file
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n{'='*80}")
    print(f"Results saved to: {output_file}")
    print(f"{'='*80}")
    print(f"\nSummary:")
    print(f"  Total anomalies: {summary['total_anomalies']}")
    print(f"  - Spatial: {summary['spatial_anomalies']['count']}")
    print(f"  - Temporal: {summary['temporal_anomalies']['count']}")
    print(f"\nSpatial anomalies by severity:")
    for severity, count in summary['spatial_anomalies']['by_severity'].items():
        print(f"  {severity}: {count}")
    print(f"\nTemporal anomalies by severity:")
    for severity, count in summary['temporal_anomalies']['by_severity'].items():
        print(f"  {severity}: {count}")

