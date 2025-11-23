#!/usr/bin/env python3
"""
Weather Data Anomaly Detection System (SQLite + PostgreSQL/TimescaleDB)
-------------------------------------
A comprehensive system for detecting anomalies in weather station data using:
1. Temporal Analysis (ARIMA, STL, Statistical methods)
2. Spatial Verification (Neighbor trend correlation)
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Union
import argparse
import json
import warnings
import sys
warnings.filterwarnings('ignore')

# Check for PostgreSQL support
try:
    import psycopg2
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False


class DataLoader:
    """Abstract Data Loader"""
    def get_window_data(self, station_id: str, start_time: str = None, end_time: str = None, window_hours: int = None) -> pd.DataFrame: raise NotImplementedError
    def get_all_stations(self) -> pd.DataFrame: raise NotImplementedError
    def get_spatial_data(self, timestamp: str, station_ids: List[str] = None, variable: str = None) -> pd.DataFrame: raise NotImplementedError
    def close(self): raise NotImplementedError


class SQLiteLoader(DataLoader):
    """Loads data from SQLite."""
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
    
    def get_window_data(self, station_id: str, start_time: str = None, end_time: str = None, window_hours: int = None) -> pd.DataFrame:
        if start_time and end_time:
            start_dt, end_dt = pd.to_datetime(start_time), pd.to_datetime(end_time)
        elif end_time and window_hours:
            end_dt = pd.to_datetime(end_time)
            start_dt = end_dt - timedelta(hours=window_hours)
        else: raise ValueError("Must specify time range")
        
        query = """
            SELECT time, temp_out, out_hum, wind_speed, bar, rain
            FROM observations
            WHERE station_id = ? AND time BETWEEN ? AND ?
            ORDER BY time ASC
        """
        df = pd.read_sql_query(query, self.conn, params=(station_id, start_dt.strftime('%Y-%m-%d %H:%M:%S'), end_dt.strftime('%Y-%m-%d %H:%M:%S')))
        df['time'] = pd.to_datetime(df['time'])
        return df

    def get_all_stations(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT station_id, station_name_en, latitude, longitude, elevation FROM stations", self.conn)

    def get_spatial_data(self, timestamp: str, station_ids: List[str] = None, variable: str = None) -> pd.DataFrame:
        # General spatial query logic used by detect_spatial_anomalies
        # If station_ids is None, fetch all for snapshot. If provided, fetch specific history for trend.
        pass # Implemented directly in anomaly methods via raw query for flexibility, or can refactor.
             # For now, let's keep the existing query style but adapted for DB type.
    
    def get_conn(self):
        return self.conn

    def close(self):
        if self.conn: self.conn.close()


class PostgresLoader(DataLoader):
    """Loads data from PostgreSQL/TimescaleDB."""
    def __init__(self, dsn: str):
        if not PG_AVAILABLE: raise ImportError("psycopg2 required")
        self.conn = psycopg2.connect(dsn)
    
    def get_window_data(self, station_id: str, start_time: str = None, end_time: str = None, window_hours: int = None) -> pd.DataFrame:
        if start_time and end_time:
            start_dt, end_dt = pd.to_datetime(start_time), pd.to_datetime(end_time)
        elif end_time and window_hours:
            end_dt = pd.to_datetime(end_time)
            start_dt = end_dt - timedelta(hours=window_hours)
        else: raise ValueError("Must specify time range")
        
        query = """
            SELECT time, temp_out, out_hum, wind_speed, bar, rain
            FROM observations
            WHERE station_id = %s AND time BETWEEN %s AND %s
            ORDER BY time ASC
        """
        df = pd.read_sql_query(query, self.conn, params=(station_id, start_dt, end_dt))
        df['time'] = pd.to_datetime(df['time'])
        return df

    def get_all_stations(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT station_id, station_name_en, latitude, longitude, elevation FROM stations", self.conn)

    def get_conn(self):
        return self.conn

    def close(self):
        if self.conn: self.conn.close()


# ... [StatisticalDetector, TimeSeriesDetector, MLDetector, SpatialDetector classes remain unchanged] ...
# Copying them back to ensure file integrity.

class StatisticalDetector:
    @staticmethod
    def detect_3sigma(values: np.ndarray, threshold: float = 3.0) -> Tuple[np.ndarray, Dict]:
        if len(values) < 3: return np.zeros(len(values), dtype=bool), {}
        mean, std = np.mean(values), np.std(values)
        if std == 0: return np.zeros(len(values), dtype=bool), {'mean': mean, 'std': 0, 'is_constant': True}
        upper, lower = mean + threshold * std, mean - threshold * std
        return (values > upper) | (values < lower), {'mean': mean, 'std': std, 'upper_bound': upper, 'lower_bound': lower}

    @staticmethod
    def detect_iqr(values: np.ndarray, k: float = 1.5) -> Tuple[np.ndarray, Dict]:
        if len(values) < 4: return np.zeros(len(values), dtype=bool), {}
        q1, q3 = np.percentile(values, [25, 75])
        iqr = q3 - q1
        if iqr == 0: return np.zeros(len(values), dtype=bool), {'iqr': 0, 'median': np.median(values), 'is_constant': True}
        lower, upper = q1 - k * iqr, q3 + k * iqr
        return (values < lower) | (values > upper), {'q1': q1, 'q3': q3, 'iqr': iqr, 'median': np.median(values), 'lower_bound': lower, 'upper_bound': upper}

    @staticmethod
    def detect_mad(values: np.ndarray, threshold: float = 3.5) -> Tuple[np.ndarray, Dict]:
        if len(values) < 3: return np.zeros(len(values), dtype=bool), {}
        median = np.median(values)
        mad = np.median(np.abs(values - median))
        if mad == 0: mad = np.mean(np.abs(values - median)) # Fallback
        if mad == 0: return np.zeros(len(values), dtype=bool), {'median': median, 'mad': 0, 'is_constant': True}
        mad_scaled = 1.4826 * mad
        return (np.abs(values - median) / mad_scaled) > threshold, {'median': median, 'mad': mad, 'mad_scaled': mad_scaled, 'threshold': threshold, 'std': mad_scaled}

    @staticmethod
    def detect_zscore(values: np.ndarray, threshold: float = 3.0) -> Tuple[np.ndarray, Dict]:
        if len(values) < 3: return np.zeros(len(values), dtype=bool), {}
        median = np.median(values)
        mad = np.median(np.abs(values - median))
        if mad == 0: return np.zeros(len(values), dtype=bool), {'median': median, 'mad': 0, 'is_constant': True}
        scores = 0.6745 * (values - median) / mad
        return np.abs(scores) > threshold, {'median': median, 'mad': mad, 'threshold': threshold, 'std': mad * 1.4826}

    @staticmethod
    def detect_percentile(values: np.ndarray, lower: float = 1, upper: float = 99) -> Tuple[np.ndarray, Dict]:
        if len(values) < 10: return np.zeros(len(values), dtype=bool), {}
        lb, ub = np.percentile(values, [lower, upper])
        return (values < lb) | (values > ub), {'lower_bound': lb, 'upper_bound': ub, 'median': np.median(values)}

    @staticmethod
    def detect_sudden_change(values: np.ndarray, max_change: float) -> np.ndarray:
        if len(values) < 2: return np.zeros(len(values), dtype=bool)
        anomalies = np.zeros(len(values), dtype=bool)
        anomalies[1:] = np.abs(np.diff(values)) > max_change
        return anomalies

class TimeSeriesDetector:
    @staticmethod
    def detect_arima_residuals(values: np.ndarray, threshold: float = 3.0) -> Tuple[np.ndarray, Dict]:
        try:
            from statsmodels.tsa.arima.model import ARIMA
            if len(values) < 20: return np.zeros(len(values), dtype=bool), {'error': 'insufficient data'}
            model = ARIMA(values, order=(1, 0, 1)).fit()
            resid = model.resid
            std = np.std(resid)
            if std == 0: return np.zeros(len(values), dtype=bool), {}
            return np.abs(resid) > threshold * std, {'mean_residual': float(np.mean(resid)), 'std_residual': float(std)}
        except Exception as e: return np.zeros(len(values), dtype=bool), {'error': str(e)}

    @staticmethod
    def detect_stl_residuals(values: np.ndarray, period: int = 6, threshold: float = 3.0) -> Tuple[np.ndarray, Dict]:
        try:
            from statsmodels.tsa.seasonal import STL
            if len(values) < 2 * period: return np.zeros(len(values), dtype=bool), {'error': 'insufficient data'}
            res = STL(values, period=period, robust=True).fit()
            resid = res.resid
            median, mad = np.median(resid), np.median(np.abs(resid - np.median(resid)))
            if mad == 0: return np.zeros(len(values), dtype=bool), {}
            return np.abs(resid - median) > threshold * (1.4826 * mad), {'median_residual': float(median)}
        except Exception as e: return np.zeros(len(values), dtype=bool), {'error': str(e)}

class MLDetector:
    @staticmethod
    def detect_isolation_forest(values: np.ndarray, contamination: float = 0.1) -> Tuple[np.ndarray, Dict]:
        try:
            from sklearn.ensemble import IsolationForest
            if len(values) < 10: return np.zeros(len(values), dtype=bool), {}
            return IsolationForest(contamination=contamination, random_state=42).fit_predict(values.reshape(-1, 1)) == -1, {'contamination': contamination}
        except ImportError: return np.zeros(len(values), dtype=bool), {'error': 'sklearn missing'}

    @staticmethod
    def detect_lof(values: np.ndarray, contamination: float = 0.1) -> Tuple[np.ndarray, Dict]:
        try:
            from sklearn.neighbors import LocalOutlierFactor
            if len(values) < 10: return np.zeros(len(values), dtype=bool), {}
            return LocalOutlierFactor(contamination=contamination).fit_predict(values.reshape(-1, 1)) == -1, {'contamination': contamination}
        except ImportError: return np.zeros(len(values), dtype=bool), {'error': 'sklearn missing'}

    @staticmethod
    def detect_one_class_svm(values: np.ndarray, contamination: float = 0.1) -> Tuple[np.ndarray, Dict]:
        try:
            from sklearn.svm import OneClassSVM
            from sklearn.preprocessing import StandardScaler
            if len(values) < 10: return np.zeros(len(values), dtype=bool), {}
            X = StandardScaler().fit_transform(values.reshape(-1, 1))
            return OneClassSVM(nu=contamination).fit_predict(X) == -1, {'contamination': contamination}
        except ImportError: return np.zeros(len(values), dtype=bool), {'error': 'sklearn missing'}

class SpatialDetector:
    @staticmethod
    def haversine_distance(lat1, lon1, lat2, lon2):
        R = 6371
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        a = np.sin((lat2-lat1)/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2-lon1)/2)**2
        return R * 2 * np.arcsin(np.sqrt(a))

    @staticmethod
    def find_neighbors(station_idx, locations, max_distance=100, max_elev_diff=500):
        neighbors = []
        t_lat, t_lon, t_elev = locations[station_idx]
        for i, loc in enumerate(locations):
            if i == station_idx: continue
            if abs(t_elev - loc[2]) > max_elev_diff: continue
            if SpatialDetector.haversine_distance(t_lat, t_lon, loc[0], loc[1]) <= max_distance:
                neighbors.append(i)
        return neighbors

    @staticmethod
    def elevation_adjusted_value(value, elev_diff, var_type='temp'):
        if var_type == 'temp': return value + (elev_diff / 100) * 0.65
        elif var_type == 'bar': return value + (elev_diff / 10) * 1.2
        return value

    @staticmethod
    def detect_spatial_anomalies(station_data, variable, threshold=3.0, max_distance=100, min_neighbors=2, max_elev_diff=500):
        ids = list(station_data.keys())
        if len(ids) < min_neighbors + 1: return [], {}
        locs = np.array([[station_data[sid]['latitude'], station_data[sid]['longitude'], station_data[sid]['elevation']] for sid in ids])
        vals = np.array([station_data[sid].get(variable, np.nan) for sid in ids])
        
        anomalies = []
        details = {}
        
        for i, sid in enumerate(ids):
            if np.isnan(vals[i]): continue
            nb_idxs = SpatialDetector.find_neighbors(i, locs, max_distance, max_elev_diff)
            if len(nb_idxs) < min_neighbors: continue
            
            nb_vals = []
            for j in nb_idxs:
                if not np.isnan(vals[j]):
                    diff = locs[j, 2] - locs[i, 2]
                    nb_vals.append(SpatialDetector.elevation_adjusted_value(vals[j], diff, variable))
            
            if len(nb_vals) < min_neighbors: continue
            
            med = np.median(nb_vals)
            mad = np.median(np.abs(np.array(nb_vals) - med))
            if mad == 0: mad = np.std(nb_vals) or 1e-6
            
            dev = abs(vals[i] - med) / (1.4826 * mad)
            if dev > threshold:
                anomalies.append(sid)
                details[sid] = {'value': float(vals[i]), 'neighbor_median': float(med), 'deviation': float(dev)}
        
        return anomalies, details


class AnomalyDetector:
    AVAILABLE_METHODS = {
        '3sigma': '3-Sigma Rule', 'mad': 'Median Absolute Deviation', 'zscore': 'Modified Z-Score',
        'percentile': 'Percentile', 'arima': 'ARIMA Residuals', 'stl': 'STL Decomposition',
        'isolation_forest': 'Isolation Forest', 'lof': 'Local Outlier Factor', 'ocsvm': 'One-Class SVM',
        'spatial': 'Spatial Correlation'
    }
    
    DETECTION_VARS = {
        'temp_out': {'name': 'Temp', 'unit': '°C', 'threshold': 3, 'sudden_change': 5.0},
        'out_hum': {'name': 'Humidity', 'unit': '%', 'threshold': 3},
        'wind_speed': {'name': 'Wind', 'unit': 'km/h', 'threshold': 3},
        'bar': {'name': 'Pressure', 'unit': 'hPa', 'threshold': 3, 'sudden_change': 10.0}
    }
    
    def __init__(self, db_path: str = None, pg_url: str = None,
                 start_time: str = None, end_time: str = None, window_hours: int = None,
                 temporal_method: str = '3sigma', spatial_method: str = 'mad', spatial_verify: bool = False):
        
        self.start_time = start_time
        self.end_time = end_time
        self.window_hours = window_hours
        self.temporal_method = temporal_method
        self.spatial_method = spatial_method
        self.spatial_verify = spatial_verify
        
        if not ((start_time and end_time) or (end_time and window_hours)):
            raise ValueError("Must specify time range")
        
        # Initialize Loader based on connection type
        if pg_url:
            if not PG_AVAILABLE: raise ImportError("psycopg2 required for PG")
            self.loader = PostgresLoader(pg_url)
            print(f"🔌 Connected to PostgreSQL: {pg_url}")
        else:
            self.loader = SQLiteLoader(db_path or 'weather_stream.db')
            print(f"🔌 Connected to SQLite: {db_path or 'weather_stream.db'}")

        self.stat_detector = StatisticalDetector()
        self.ts_detector = TimeSeriesDetector()
        self.ml_detector = MLDetector()

    def verify_spatial_trend(self, station_id: str, timestamp: str, variable: str, window_minutes: int = 30) -> Dict:
        dt = pd.to_datetime(timestamp)
        start_dt, end_dt = dt - timedelta(minutes=window_minutes), dt + timedelta(minutes=window_minutes)
        
        stations_df = self.loader.get_all_stations()
        locs = stations_df[['latitude', 'longitude', 'elevation']].values
        ids = stations_df['station_id'].tolist()
        
        try: target_idx = ids.index(station_id)
        except ValueError: return {'error': 'station not found'}
        
        nb_idxs = SpatialDetector.find_neighbors(target_idx, locs, 100, 500)
        if not nb_idxs: return {'status': 'no_neighbors', 'correlation': 0}
        
        nb_ids = [ids[i] for i in nb_idxs]
        all_ids = [station_id] + nb_ids
        
        # Flexible query for both DB types
        placeholders = ','.join(['%s' if isinstance(self.loader, PostgresLoader) else '?'] * len(all_ids))
        time_ph = '%s' if isinstance(self.loader, PostgresLoader) else '?'
        
        query = f"""
            SELECT time, station_id, {variable} FROM observations
            WHERE station_id IN ({placeholders}) AND time BETWEEN {time_ph} AND {time_ph}
            ORDER BY time
        """
        
        params = all_ids + [start_dt, end_dt]
        # Ensure params are correct types for driver
        if isinstance(self.loader, SQLiteLoader):
            params = all_ids + [start_dt.strftime('%Y-%m-%d %H:%M:%S'), end_dt.strftime('%Y-%m-%d %H:%M:%S')]

        df = pd.read_sql_query(query, self.loader.get_conn(), params=params)
        
        if df.empty: return {'status': 'no_data', 'correlation': 0}
        
        df['time'] = pd.to_datetime(df['time'])
        pivot = df.pivot(index='time', columns='station_id', values=variable)
        if station_id not in pivot.columns: return {'status': 'no_data', 'correlation': 0}
        
        pivot = pivot.interpolate(method='time', limit_direction='both', limit=2).dropna()
        if len(pivot) < 5: return {'status': 'insufficient_points', 'correlation': 0}
        
        corrs = []
        for nid in nb_ids:
            if nid in pivot.columns:
                c = pivot[station_id].corr(pivot[nid])
                if not np.isnan(c): corrs.append(c)
        
        if not corrs: return {'status': 'no_valid_correlations', 'correlation': 0}
        
        med_corr = np.median(corrs)
        return {
            'status': 'success', 'median_corr': med_corr, 'n_neighbors': len(corrs),
            'is_trend_consistent': med_corr > 0.6 or np.max(corrs) > 0.8
        }

    def detect_station(self, station_id: str) -> Dict:
        df = self.loader.get_window_data(station_id, self.start_time, self.end_time, self.window_hours)
        if df.empty or len(df) < 3: return {'station_id': station_id, 'status': 'insufficient_data', 'has_anomaly': False}
        
        res = {'station_id': station_id, 'window_start': str(df['time'].min()), 'window_end': str(df['time'].max()), 
               'data_count': len(df), 'anomalies': {}, 'has_anomaly': False}
        
        for var, cfg in self.DETECTION_VARS.items():
            info = self._detect_variable(df, var, cfg)
            if info:
                if self.spatial_verify:
                    for rec in info['anomaly_records']:
                        trend = self.verify_spatial_trend(station_id, rec['time'], var, self.window_hours * 60)
                        if trend.get('status') == 'success':
                            corr = trend['median_corr']
                            if trend['is_trend_consistent']:
                                rec.update({'type': 'weather_event', 'label': '🌧️ Weather Event', 'desc': f"Trend Consistent (Corr: {corr:.2f})"})
                            elif corr < 0.3:
                                rec.update({'type': 'critical_failure', 'label': '🔴 Device Failure', 'desc': f"Trend Inconsistent (Corr: {corr:.2f})"})
                            else:
                                rec.update({'type': 'warning', 'label': '⚠️ Suspected', 'desc': f"Weak Correlation (Corr: {corr:.2f})"})
                        else:
                             rec.update({'label': '⚠️ Unverified Anomaly', 'desc': f"Spatial Skip: {trend.get('status')}"})
                
                res['anomalies'][var] = info
                res['has_anomaly'] = True
        
        return res

    def _detect_variable(self, df, var, config):
        if var not in df.columns: return None
        vals = df[var].values
        if np.all(np.isnan(vals)): return None
        
        if self.temporal_method == 'arima': mask, stats = self.ts_detector.detect_arima_residuals(vals, 3.0)
        elif self.temporal_method == 'mad': mask, stats = self.stat_detector.detect_mad(vals, 3.5)
        elif self.temporal_method == 'isolation_forest': mask, stats = self.ml_detector.detect_isolation_forest(vals)
        else: mask, stats = self.stat_detector.detect_3sigma(vals, config['threshold'])
        
        if not np.any(mask) or 'error' in stats: return None
        
        recs = []
        for idx in np.where(mask)[0]:
            recs.append({'time': str(df.iloc[idx]['time']), 'value': float(vals[idx]), 'deviation': 0.0}) # Simplified deviation
            
        return {'name': config['name'], 'unit': config['unit'], 'count': int(np.sum(mask)), 
                'method': self.temporal_method, 'statistics': stats, 'anomaly_records': recs}

    def detect_all_stations(self):
        return [self.detect_station(row['station_id']) for _, row in self.loader.get_all_stations().iterrows()]

    def close(self):
        self.loader.close()

class ReportGenerator:
    @staticmethod
    def generate_text_report(results, window_info, method):
        lines = ["ANOMALY DETECTION REPORT", f"Date: {datetime.now()}", f"Window: {window_info}", "-"*50]
        anom = [r for r in results if r.get('has_anomaly')]
        lines.append(f"Total: {len(results)} | Anomalous: {len(anom)}")
        lines.append("-" * 50)
        for r in anom:
            lines.append(f"[Station: {r['station_id']}]")
            for v, info in r['anomalies'].items():
                lines.append(f"  ⚠️  {v}: {info['count']} anomalies")
                for rec in info['anomaly_records']:
                    lines.append(f"    • {rec['time']}: {rec['value']} -> {rec.get('label', 'Anomaly')} ({rec.get('desc', '')})")
            lines.append("")
        return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='weather_stream.db', help='SQLite DB path')
    parser.add_argument('--pg-url', help='PostgreSQL Connection String')
    parser.add_argument('--end', required=True, help='End Time')
    parser.add_argument('--window', type=int, required=True, help='Window Hours')
    parser.add_argument('--temporal-method', default='3sigma')
    parser.add_argument('--spatial-verify', action='store_true')
    parser.add_argument('--station')
    
    args = parser.parse_args()
    
    detector = AnomalyDetector(
        db_path=args.db, pg_url=args.pg_url,
        end_time=args.end, window_hours=args.window,
        temporal_method=args.temporal_method, spatial_verify=args.spatial_verify
    )
    
    try:
        results = [detector.detect_station(args.station)] if args.station else detector.detect_all_stations()
        print(ReportGenerator.generate_text_report(results, f"Last {args.window}h from {args.end}", args.temporal_method))
    finally:
        detector.close()

if __name__ == '__main__':
    main()

# 现在 (SQLite):
# python streaming_collector_sqlite.py --continuous
# python anomaly_detector.py --end "NOW" --window 6

# 未来 (TimescaleDB):
# 1. 采集数据到 PG
# python streaming_collector_sqlite.py --continuous --pg-url "postgresql://user:pass@localhost:5432/weather"
# # 2. 从 PG 读取检测
# python anomaly_detector.py --end "NOW" --window 6 --pg-url "postgresql://user:pass@localhost:5432/weather"