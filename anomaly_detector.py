#!/usr/bin/env python3
"""
气象数据异常检测系统
基于滑动窗口 + 3σ规则的时序异常检测
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import argparse
import json
import warnings
warnings.filterwarnings('ignore')


class WindowDataLoader:
    """滑动窗口数据加载器"""
    
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
    
    def get_window_data(self, station_id: str, start_time: str = None, 
                       end_time: str = None, window_hours: int = None) -> pd.DataFrame:
        """
        获取指定站点的滑动窗口数据
        
        支持两种模式:
        1. 指定 start_time + end_time: 使用精确时间范围
        2. 指定 end_time + window_hours: 从end_time往前推window_hours小时
        """
        # 模式1: 指定了起始和结束时间
        if start_time and end_time:
            start_dt = pd.to_datetime(start_time)
            end_dt = pd.to_datetime(end_time)
        
        # 模式2: 指定结束时间 + 窗口长度
        elif end_time and window_hours:
            end_dt = pd.to_datetime(end_time)
            start_dt = end_dt - timedelta(hours=window_hours)
        
        else:
            raise ValueError("必须指定: (start_time + end_time) 或 (end_time + window_hours)")
        
        # 查询数据
        query = """
            SELECT time, temp_out, out_hum, wind_speed, bar, rain
            FROM observations
            WHERE station_id = ? AND time BETWEEN ? AND ?
            ORDER BY time ASC
        """
        df = pd.read_sql_query(query, self.conn, 
                               params=(station_id, start_dt.strftime('%Y-%m-%d %H:%M:%S'),
                                     end_dt.strftime('%Y-%m-%d %H:%M:%S')))
        df['time'] = pd.to_datetime(df['time'])
        return df
    
    def get_all_stations(self) -> pd.DataFrame:
        """获取所有站点信息"""
        return pd.read_sql_query("SELECT station_id, station_name_en FROM stations", self.conn)
    
    def close(self):
        if self.conn:
            self.conn.close()




class StatisticalDetector:
    """统计异常检测器"""
    
    @staticmethod
    def detect_3sigma(values: np.ndarray, threshold: float = 3.0) -> Tuple[np.ndarray, Dict]:
        """3σ规则异常检测"""
        if len(values) < 3:
            return np.zeros(len(values), dtype=bool), {}
        
        mean, std = np.mean(values), np.std(values)
        
        if std == 0:  # 数据无变化
            return np.zeros(len(values), dtype=bool), {
                'mean': mean, 'std': 0, 'upper_bound': mean, 
                'lower_bound': mean, 'is_constant': True
            }
        
        upper, lower = mean + threshold * std, mean - threshold * std
        anomalies = (values > upper) | (values < lower)
        
        return anomalies, {
            'mean': mean, 'std': std, 
            'upper_bound': upper, 'lower_bound': lower
        }
    
    @staticmethod
    def detect_iqr(values: np.ndarray, k: float = 1.5) -> Tuple[np.ndarray, Dict]:
        """IQR箱线图法"""
        if len(values) < 4:
            return np.zeros(len(values), dtype=bool), {}
        
        q1, q3 = np.percentile(values, [25, 75])
        iqr = q3 - q1
        
        if iqr == 0:
            median = np.median(values)
            return np.zeros(len(values), dtype=bool), {
                'q1': q1, 'q3': q3, 'iqr': 0, 'median': median, 'is_constant': True
            }
        
        lower = q1 - k * iqr
        upper = q3 + k * iqr
        anomalies = (values < lower) | (values > upper)
        
        return anomalies, {
            'q1': q1, 'q3': q3, 'iqr': iqr, 'median': np.median(values),
            'lower_bound': lower, 'upper_bound': upper
        }
    
    @staticmethod
    def detect_mad(values: np.ndarray, threshold: float = 3.5) -> Tuple[np.ndarray, Dict]:
        """MAD中位数绝对偏差法"""
        if len(values) < 3:
            return np.zeros(len(values), dtype=bool), {}
        
        median = np.median(values)
        mad = np.median(np.abs(values - median))
        
        if mad == 0:
            mad = np.mean(np.abs(values - median))
            if mad == 0:
                return np.zeros(len(values), dtype=bool), {
                    'median': median, 'mad': 0, 'is_constant': True
                }
        
        mad_scaled = 1.4826 * mad
        deviations = np.abs(values - median) / mad_scaled
        anomalies = deviations > threshold
        
        return anomalies, {
            'median': median, 'mad': mad, 'mad_scaled': mad_scaled,
            'threshold': threshold, 'std': mad_scaled
        }
    
    @staticmethod
    def detect_zscore(values: np.ndarray, threshold: float = 3.0) -> Tuple[np.ndarray, Dict]:
        """改进的Z-score方法（基于MAD）"""
        if len(values) < 3:
            return np.zeros(len(values), dtype=bool), {}
        
        median = np.median(values)
        mad = np.median(np.abs(values - median))
        
        if mad == 0:
            return np.zeros(len(values), dtype=bool), {
                'median': median, 'mad': 0, 'is_constant': True
            }
        
        modified_z_scores = 0.6745 * (values - median) / mad
        anomalies = np.abs(modified_z_scores) > threshold
        
        return anomalies, {
            'median': median, 'mad': mad, 'threshold': threshold,
            'std': mad * 1.4826
        }
    
    @staticmethod
    def detect_percentile(values: np.ndarray, lower: float = 1, upper: float = 99) -> Tuple[np.ndarray, Dict]:
        """百分位数方法"""
        if len(values) < 10:
            return np.zeros(len(values), dtype=bool), {}
        
        lower_bound = np.percentile(values, lower)
        upper_bound = np.percentile(values, upper)
        anomalies = (values < lower_bound) | (values > upper_bound)
        
        return anomalies, {
            'lower_percentile': lower, 'upper_percentile': upper,
            'lower_bound': lower_bound, 'upper_bound': upper_bound,
            'median': np.median(values), 'std': np.std(values)
        }
    
    @staticmethod
    def detect_sudden_change(values: np.ndarray, max_change: float) -> np.ndarray:
        """检测突变（相邻值变化过大）"""
        if len(values) < 2:
            return np.zeros(len(values), dtype=bool)
        
        diffs = np.abs(np.diff(values))
        anomalies = np.zeros(len(values), dtype=bool)
        anomalies[1:] = diffs > max_change
        return anomalies


class TimeSeriesDetector:
    """时间序列异常检测器 - 考虑时序依赖性"""
    
    @staticmethod
    def detect_arima_residuals(values: np.ndarray, threshold: float = 3.0) -> Tuple[np.ndarray, Dict]:
        """
        ARIMA残差分析法
        原理: 用ARIMA预测，预测误差过大的为异常
        优势: 考虑时序自相关性
        """
        try:
            from statsmodels.tsa.arima.model import ARIMA
        except ImportError:
            return np.zeros(len(values), dtype=bool), {'error': 'statsmodels not installed'}
        
        if len(values) < 20:
            return np.zeros(len(values), dtype=bool), {'error': 'insufficient data'}
        
        try:
            model = ARIMA(values, order=(1, 0, 1))
            fitted = model.fit()
            residuals = fitted.resid
            
            std_resid = np.std(residuals)
            if std_resid == 0:
                return np.zeros(len(values), dtype=bool), {}
            
            anomalies = np.abs(residuals) > threshold * std_resid
            
            return anomalies, {
                'mean_residual': float(np.mean(residuals)),
                'std_residual': float(std_resid),
                'aic': float(fitted.aic)
            }
        except Exception as e:
            return np.zeros(len(values), dtype=bool), {'error': str(e)}
    
    @staticmethod
    def detect_stl_residuals(values: np.ndarray, period: int = 6, 
                            threshold: float = 3.0) -> Tuple[np.ndarray, Dict]:
        """
        STL季节-趋势分解
        原理: 分解为趋势+季节+残差，残差异常为真异常
        优势: 自动处理周期性和趋势
        """
        try:
            from statsmodels.tsa.seasonal import STL
        except ImportError:
            return np.zeros(len(values), dtype=bool), {'error': 'statsmodels not installed'}
        
        if len(values) < 2 * period:
            return np.zeros(len(values), dtype=bool), {'error': f'need at least {2*period} points'}
        
        try:
            stl = STL(values, period=period, robust=True)
            result = stl.fit()
            residuals = result.resid
            
            median_resid = np.median(residuals)
            mad_resid = np.median(np.abs(residuals - median_resid))
            
            if mad_resid == 0:
                return np.zeros(len(values), dtype=bool), {}
            
            mad_scaled = 1.4826 * mad_resid
            anomalies = np.abs(residuals - median_resid) > threshold * mad_scaled
            
            return anomalies, {
                'median_residual': float(median_resid),
                'mad_residual': float(mad_resid)
            }
        except Exception as e:
            return np.zeros(len(values), dtype=bool), {'error': str(e)}


class MLDetector:
    """机器学习异常检测器"""
    
    @staticmethod
    def detect_isolation_forest(values: np.ndarray, contamination: float = 0.1) -> Tuple[np.ndarray, Dict]:
        """
        孤立森林
        原理: 异常点更容易被孤立（划分）
        优势: 无需假设数据分布，适合高维数据
        """
        try:
            from sklearn.ensemble import IsolationForest
        except ImportError:
            return np.zeros(len(values), dtype=bool), {'error': 'sklearn not installed'}
        
        if len(values) < 10:
            return np.zeros(len(values), dtype=bool), {}
        
        X = values.reshape(-1, 1)
        clf = IsolationForest(contamination=contamination, random_state=42)
        predictions = clf.fit_predict(X)
        anomalies = predictions == -1
        
        return anomalies, {
            'contamination': contamination,
            'n_anomalies': int(np.sum(anomalies))
        }
    
    @staticmethod
    def detect_lof(values: np.ndarray, contamination: float = 0.1) -> Tuple[np.ndarray, Dict]:
        """
        局部离群因子 (LOF)
        原理: 基于局部密度，密度明显低于邻居的为异常
        优势: 适合密度不均匀的数据
        """
        try:
            from sklearn.neighbors import LocalOutlierFactor
        except ImportError:
            return np.zeros(len(values), dtype=bool), {'error': 'sklearn not installed'}
        
        if len(values) < 10:
            return np.zeros(len(values), dtype=bool), {}
        
        X = values.reshape(-1, 1)
        clf = LocalOutlierFactor(contamination=contamination)
        predictions = clf.fit_predict(X)
        anomalies = predictions == -1
        
        return anomalies, {
            'contamination': contamination,
            'n_anomalies': int(np.sum(anomalies))
        }
    
    @staticmethod
    def detect_one_class_svm(values: np.ndarray, contamination: float = 0.1) -> Tuple[np.ndarray, Dict]:
        """
        One-Class SVM
        原理: 学习"正常数据"的边界，超出边界为异常
        优势: 适合单类别问题
        """
        try:
            from sklearn.svm import OneClassSVM
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            return np.zeros(len(values), dtype=bool), {'error': 'sklearn not installed'}
        
        if len(values) < 10:
            return np.zeros(len(values), dtype=bool), {}
        
        X = values.reshape(-1, 1)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        clf = OneClassSVM(nu=contamination, kernel='rbf', gamma='auto')
        predictions = clf.fit_predict(X_scaled)
        anomalies = predictions == -1
        
        return anomalies, {
            'contamination': contamination,
            'n_anomalies': int(np.sum(anomalies))
        }


class SpatialDetector:
    """空间异常检测器 - 考虑地理位置相关性"""
    
    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        计算两点间的地理距离（公里）
        Haversine公式
        """
        R = 6371  # 地球半径（公里）
        
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))
        
        return R * c
    
    @staticmethod
    def find_neighbors(station_idx: int, locations: np.ndarray, 
                      max_distance: float = 100) -> List[int]:
        """
        找出某站点的邻近站点
        
        参数:
            station_idx: 站点索引
            locations: [[lat1, lon1, elev1], [lat2, lon2, elev2], ...]
            max_distance: 最大距离阈值（公里）
        """
        neighbors = []
        target_lat, target_lon = locations[station_idx, 0], locations[station_idx, 1]
        
        for i, loc in enumerate(locations):
            if i == station_idx:
                continue
            
            dist = SpatialDetector.haversine_distance(
                target_lat, target_lon, loc[0], loc[1]
            )
            
            if dist <= max_distance:
                neighbors.append(i)
        
        return neighbors
    
    @staticmethod
    def elevation_adjusted_value(value: float, elev_diff: float, 
                                 var_type: str = 'temp') -> float:
        """
        根据海拔差异调整变量值
        
        气象学经验:
        - 温度: 每升高100m降低0.65°C (干绝热递减率)
        - 气压: 每升高10m降低约1.2hPa
        - 湿度: 海拔影响较小，不调整
        """
        if var_type == 'temp':
            # 温度随海拔降低: -0.65°C/100m
            return value + (elev_diff / 100) * 0.65
        elif var_type == 'bar':
            # 气压随海拔降低: -1.2hPa/10m
            return value + (elev_diff / 10) * 1.2
        else:
            # 其他变量不调整
            return value
    
    @staticmethod
    def detect_spatial_anomalies(
        station_data: Dict[str, Dict],  # {station_id: {var: value, lat, lon, elev}}
        variable: str,
        threshold: float = 3.0,
        max_distance: float = 100,
        min_neighbors: int = 2
    ) -> Tuple[List[str], Dict]:
        """
        检测空间异常
        
        原理:
        1. 对每个站点，找出邻近站点（距离 < max_distance）
        2. 计算邻近站点该变量的均值/中位数（考虑海拔修正）
        3. 如果该站点的值与邻近均值差异过大 → 空间异常
        
        返回:
            anomalous_stations: 异常站点ID列表
            details: 详细信息
        """
        station_ids = list(station_data.keys())
        n_stations = len(station_ids)
        
        if n_stations < min_neighbors + 1:
            return [], {'error': 'insufficient stations'}
        
        # 提取位置和值
        locations = np.array([
            [station_data[sid]['latitude'], 
             station_data[sid]['longitude'],
             station_data[sid]['elevation']]
            for sid in station_ids
        ])
        
        values = np.array([station_data[sid].get(variable, np.nan) for sid in station_ids])
        
        # 检测每个站点
        anomalous_stations = []
        details = {}
        
        for i, station_id in enumerate(station_ids):
            if np.isnan(values[i]):
                continue
            
            # 找邻近站点
            neighbor_indices = SpatialDetector.find_neighbors(i, locations, max_distance)
            
            if len(neighbor_indices) < min_neighbors:
                continue  # 邻居太少，无法判断
            
            # 获取邻近站点的值（考虑海拔修正）
            target_elev = locations[i, 2]
            neighbor_values_adjusted = []
            
            for j in neighbor_indices:
                if np.isnan(values[j]):
                    continue
                
                elev_diff = locations[j, 2] - target_elev  # 邻居海拔 - 目标海拔
                adjusted_val = SpatialDetector.elevation_adjusted_value(
                    values[j], elev_diff, var_type=variable
                )
                neighbor_values_adjusted.append(adjusted_val)
            
            if len(neighbor_values_adjusted) < min_neighbors:
                continue
            
            # 计算邻近站点的统计量（使用中位数更鲁棒）
            neighbor_median = np.median(neighbor_values_adjusted)
            neighbor_mad = np.median(np.abs(np.array(neighbor_values_adjusted) - neighbor_median))
            
            if neighbor_mad == 0:
                neighbor_mad = np.std(neighbor_values_adjusted)
                if neighbor_mad == 0:
                    continue
            
            # 计算偏离程度
            deviation = abs(values[i] - neighbor_median) / (1.4826 * neighbor_mad)
            
            if deviation > threshold:
                anomalous_stations.append(station_id)
                details[station_id] = {
                    'value': float(values[i]),
                    'neighbor_median': float(neighbor_median),
                    'neighbor_mad': float(neighbor_mad),
                    'deviation': float(deviation),
                    'n_neighbors': len(neighbor_values_adjusted),
                    'neighbor_ids': [station_ids[j] for j in neighbor_indices]
                }
        
        return anomalous_stations, details


class AnomalyDetector:
    """异常检测主控制器"""
    
    # 支持的检测方法
    AVAILABLE_METHODS = {
        # 统计方法（基于分布）
        '3sigma': '3σ规则 - 假设正态分布',
        'iqr': 'IQR箱线图法 - 鲁棒，适合偏态数据',
        'mad': 'MAD中位数绝对偏差 - 抗噪声',
        'zscore': '改进Z-score - 基于MAD',
        'percentile': '百分位数法 - 定义稀有度',
        
        # 时序方法（考虑时间依赖）
        'arima': 'ARIMA残差法 - 考虑自相关性',
        'stl': 'STL分解法 - 处理趋势和周期',
        
        # 机器学习方法
        'isolation_forest': '孤立森林 - 无分布假设',
        'lof': '局部离群因子 - 基于密度',
        'ocsvm': 'One-Class SVM - 学习正常边界',
        
        # 空间方法（考虑地理位置）
        'spatial': '空间异常检测 - 基于邻近站点相关性'
    }
    
    # 检测变量配置
    DETECTION_VARS = {
        'temp_out': {'name': '温度', 'unit': '°C', 'threshold': 3, 'sudden_change': 5.0},
        'out_hum': {'name': '湿度', 'unit': '%', 'threshold': 3},
        'wind_speed': {'name': '风速', 'unit': 'km/h', 'threshold': 3},
        'bar': {'name': '气压', 'unit': 'hPa', 'threshold': 3, 'sudden_change': 10.0}
    }
    
    def __init__(self, db_path: str = 'weather_stream.db', 
                 start_time: str = None, end_time: str = None, window_hours: int = None,
                 method: str = '3sigma'):
        """
        初始化异常检测器
        
        参数:
            db_path: 数据库路径
            start_time: 窗口起始时间 (格式: 'YYYY-MM-DD HH:MM:SS')
            end_time: 窗口结束时间 (格式: 'YYYY-MM-DD HH:MM:SS')
            window_hours: 窗口长度（小时）
            method: 检测方法 (见AVAILABLE_METHODS)
            
        使用方式:
            # 统计方法
            detector = AnomalyDetector(end_time='2025-11-20 16:00:00', window_hours=6, method='iqr')
            
            # 时序方法
            detector = AnomalyDetector(end_time='2025-11-20 16:00:00', window_hours=6, method='arima')
            
            # 机器学习方法
            detector = AnomalyDetector(end_time='2025-11-20 16:00:00', window_hours=6, method='lof')
        """
        self.start_time = start_time
        self.end_time = end_time
        self.window_hours = window_hours
        
        # 验证参数
        if not ((start_time and end_time) or (end_time and window_hours)):
            raise ValueError("必须指定: (start_time + end_time) 或 (end_time + window_hours)")
        
        # 验证检测方法
        if method not in self.AVAILABLE_METHODS:
            raise ValueError(f"不支持的方法: {method}. 可用: {list(self.AVAILABLE_METHODS.keys())}")
        
        self.method = method
        self.loader = WindowDataLoader(db_path)
        self.stat_detector = StatisticalDetector()
        self.ts_detector = TimeSeriesDetector()
        self.ml_detector = MLDetector()
    
    def detect_station(self, station_id: str) -> Dict:
        """检测单个站点的异常"""
        # 加载数据
        df = self.loader.get_window_data(station_id, 
                                         start_time=self.start_time,
                                         end_time=self.end_time, 
                                         window_hours=self.window_hours)
        
        # 数据验证
        if df.empty:
            return {'station_id': station_id, 'status': 'no_data', 'message': '无数据'}
        if len(df) < 3:
            return {'station_id': station_id, 'status': 'insufficient_data', 
                   'message': f'数据不足（仅{len(df)}条）'}
        
        # 初始化结果
        result = {
            'station_id': station_id,
            'window_start': str(df['time'].min()),
            'window_end': str(df['time'].max()),
            'data_count': len(df),
            'anomalies': {},
            'has_anomaly': False
        }
        
        # 对每个变量检测异常
        for var, config in self.DETECTION_VARS.items():
            anomaly_info = self._detect_variable(df, var, config)
            if anomaly_info:
                result['anomalies'][var] = anomaly_info
                result['has_anomaly'] = True
        
        return result
    
    def _detect_variable(self, df: pd.DataFrame, var: str, config: Dict) -> Optional[Dict]:
        """检测单个变量的异常"""
        if var not in df.columns:
            return None
        
        values = df[var].values
        if np.all(np.isnan(values)):
            return None
        
        # 根据方法选择检测器
        if self.method == '3sigma':
            anomaly_mask, stats = self.stat_detector.detect_3sigma(values, config['threshold'])
        elif self.method == 'iqr':
            anomaly_mask, stats = self.stat_detector.detect_iqr(values, k=1.5)
        elif self.method == 'mad':
            anomaly_mask, stats = self.stat_detector.detect_mad(values, threshold=3.5)
        elif self.method == 'zscore':
            anomaly_mask, stats = self.stat_detector.detect_zscore(values, threshold=3.0)
        elif self.method == 'percentile':
            anomaly_mask, stats = self.stat_detector.detect_percentile(values, lower=1, upper=99)
        elif self.method == 'arima':
            anomaly_mask, stats = self.ts_detector.detect_arima_residuals(values, threshold=3.0)
        elif self.method == 'stl':
            anomaly_mask, stats = self.ts_detector.detect_stl_residuals(values, period=6, threshold=3.0)
        elif self.method == 'isolation_forest':
            anomaly_mask, stats = self.ml_detector.detect_isolation_forest(values, contamination=0.1)
        elif self.method == 'lof':
            anomaly_mask, stats = self.ml_detector.detect_lof(values, contamination=0.1)
        elif self.method == 'ocsvm':
            anomaly_mask, stats = self.ml_detector.detect_one_class_svm(values, contamination=0.1)
        else:
            # 默认3sigma
            anomaly_mask, stats = self.stat_detector.detect_3sigma(values, config['threshold'])
        
        # 检查是否有错误
        if 'error' in stats:
            return None
        
        # 突变检测（作为额外检测，如果配置了）
        if 'sudden_change' in config:
            sudden_mask = self.stat_detector.detect_sudden_change(values, config['sudden_change'])
            anomaly_mask = anomaly_mask | sudden_mask
        
        # 如果没有异常，返回None
        if not np.any(anomaly_mask):
            return None
        
        # 构建异常记录
        anomaly_indices = np.where(anomaly_mask)[0]
        anomaly_records = []
        
        for idx in anomaly_indices:
            record = {
                'time': str(df.iloc[idx]['time']),
                'value': float(values[idx])
            }
            
            # 计算偏离度（根据方法）
            if self.method in ['3sigma', 'zscore', 'arima', 'stl'] and stats.get('std', 0) > 0:
                mean_val = stats.get('mean', stats.get('median', 0))
                record['deviation'] = float(abs(values[idx] - mean_val) / stats['std'])
            elif self.method == 'iqr' and stats.get('iqr', 0) > 0:
                record['deviation'] = float(abs(values[idx] - stats['median']) / stats['iqr'])
            elif self.method == 'mad' and stats.get('mad_scaled', 0) > 0:
                record['deviation'] = float(abs(values[idx] - stats['median']) / stats['mad_scaled'])
            else:
                record['deviation'] = 0.0
            
            anomaly_records.append(record)
        
        return {
            'name': config['name'],
            'unit': config['unit'],
            'count': int(np.sum(anomaly_mask)),
            'method': self.method,
            'statistics': {k: float(v) for k, v in stats.items() if k not in ['is_constant', 'error']},
            'anomaly_records': anomaly_records
        }
    
    def detect_all_stations(self) -> List[Dict]:
        """检测所有站点"""
        stations_df = self.loader.get_all_stations()
        results = []
        
        for _, row in stations_df.iterrows():
            result = self.detect_station(row['station_id'])
            result['station_name'] = row['station_name_en']
            results.append(result)
        
        return results
    
    def detect_spatial_anomalies(self, timestamp: str = None, 
                                max_distance: float = 100,
                                threshold: float = 3.0) -> Dict:
        """
        空间异常检测 - 检测某一时刻所有站点的空间异常
        
        参数:
            timestamp: 检测时刻 (None表示使用窗口最新时刻)
            max_distance: 邻近站点最大距离（公里）
            threshold: 异常阈值（几倍MAD）
        """
        # 获取所有站点信息
        stations_df = self.loader.get_all_stations()
        
        # 获取指定时刻的数据
        if timestamp is None:
            # 使用窗口结束时刻
            timestamp = self.end_time
        
        # 查询所有站点在该时刻的数据
        query = """
            SELECT o.station_id, o.temp_out, o.out_hum, o.wind_speed, o.bar,
                   s.latitude, s.longitude, s.elevation, s.station_name_en
            FROM observations o
            JOIN stations s ON o.station_id = s.station_id
            WHERE o.time = ?
        """
        
        df = pd.read_sql_query(query, self.loader.conn, params=(timestamp,))
        
        if df.empty:
            return {'error': 'no data at specified time', 'timestamp': timestamp}
        
        # 准备站点数据字典
        station_data = {}
        for _, row in df.iterrows():
            station_data[row['station_id']] = {
                'latitude': row['latitude'],
                'longitude': row['longitude'],
                'elevation': row['elevation'],
                'temp_out': row['temp_out'],
                'out_hum': row['out_hum'],
                'wind_speed': row['wind_speed'],
                'bar': row['bar'],
                'station_name': row['station_name_en']
            }
        
        # 对每个变量进行空间检测
        results = {
            'timestamp': timestamp,
            'n_stations': len(station_data),
            'max_distance': max_distance,
            'threshold': threshold,
            'variables': {}
        }
        
        spatial_detector = SpatialDetector()
        
        for var, config in self.DETECTION_VARS.items():
            anomalous_stations, details = spatial_detector.detect_spatial_anomalies(
                station_data, var, threshold, max_distance, min_neighbors=2
            )
            
            if anomalous_stations:
                results['variables'][var] = {
                    'name': config['name'],
                    'unit': config['unit'],
                    'anomalous_stations': anomalous_stations,
                    'details': details
                }
        
        return results
    
    def close(self):
        self.loader.close()


class ReportGenerator:
    """报告生成器"""
    
    @staticmethod
    def generate_text_report(results: List[Dict], window_info: str = None, method: str = '3sigma') -> str:
        """生成文本格式报告"""
        method_names = {
            '3sigma': '3σ规则', 'iqr': 'IQR箱线图法', 'mad': 'MAD中位数绝对偏差',
            'zscore': '改进Z-score', 'percentile': '百分位数法',
            'arima': 'ARIMA残差法', 'stl': 'STL分解法',
            'isolation_forest': '孤立森林', 'lof': '局部离群因子', 'ocsvm': 'One-Class SVM'
        }
        
        lines = [
            "=" * 100,
            "异常检测报告",
            "=" * 100,
            f"检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"检测窗口: {window_info}" if window_info else "",
            f"检测方法: {method_names.get(method, method)}",
            ""
        ]
        
        # 统计信息
        total = len(results)
        anomaly_count = sum(1 for r in results if r.get('has_anomaly', False))
        
        lines.extend([
            f"总站点数: {total}",
            f"异常站点数: {anomaly_count}",
            f"正常站点数: {total - anomaly_count}",
            "",
            " 所有站点数据正常" if anomaly_count == 0 else f"⚠️  发现 {anomaly_count} 个站点存在异常",
            "=" * 100,
            ""
        ])
        
        # 详细异常信息
        for result in results:
            if result.get('has_anomaly'):
                lines.extend(ReportGenerator._format_station_anomalies(result))
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_station_anomalies(result: Dict) -> List[str]:
        """格式化单个站点的异常信息"""
        lines = [
            f"【站点: {result['station_id']} - {result.get('station_name', 'Unknown')}】",
            f"  窗口: {result['window_start']} ~ {result['window_end']}",
            f"  数据量: {result['data_count']} 条",
            ""
        ]
        
        for var, info in result['anomalies'].items():
            stats = info['statistics']
            lines.append(f"  ⚠️  {info['name']} 异常:")
            lines.append(f"      异常次数: {info['count']}")
            lines.append(f"      检测方法: {info.get('method', 'unknown')}")
            
            # 根据不同方法显示统计信息
            if 'mean' in stats and 'std' in stats:
                lines.append(f"      统计信息: 均值={stats['mean']:.2f}{info['unit']}, 标准差={stats['std']:.2f}{info['unit']}")
            elif 'median' in stats and 'std' in stats:
                lines.append(f"      统计信息: 中位数={stats['median']:.2f}{info['unit']}, 标准差={stats['std']:.2f}{info['unit']}")
            elif 'median' in stats and 'iqr' in stats:
                lines.append(f"      统计信息: 中位数={stats['median']:.2f}{info['unit']}, IQR={stats['iqr']:.2f}{info['unit']}")
            
            # 显示正常范围
            if 'lower_bound' in stats and 'upper_bound' in stats:
                lines.append(f"      正常范围: [{stats['lower_bound']:.2f}, {stats['upper_bound']:.2f}] {info['unit']}")
            
            # 显示前3个异常
            for record in info['anomaly_records'][:3]:
                lines.append(f"      • {record['time']}: {record['value']:.2f}{info['unit']} "
                           f"(偏离 {record['deviation']:.1f}σ)")
            
            if len(info['anomaly_records']) > 3:
                lines.append(f"      ... 还有 {len(info['anomaly_records']) - 3} 个异常")
            lines.append("")
        
        lines.extend(["-" * 100, ""])
        return lines
    
    @staticmethod
    def save_json_report(results: List[Dict], window_info: dict = None, filename: str = None) -> str:
        """保存JSON格式报告"""
        if filename is None:
            filename = f"anomaly_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        report_data = {
            'detection_time': datetime.now().isoformat(),
            'results': results
        }
        
        if window_info:
            report_data['window_info'] = window_info
        
        with open(filename, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        return filename





def main():
    parser = argparse.ArgumentParser(
        description='气象数据异常检测系统 - 支持多种检测方法',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基础统计方法
  python anomaly_detector.py --end "2025-11-20 16:00:00" --window 6 --method 3sigma
  python anomaly_detector.py --end "2025-11-20 16:00:00" --window 6 --method iqr
  
  # 时序方法（需要statsmodels）
  python anomaly_detector.py --end "2025-11-20 16:00:00" --window 6 --method arima
  python anomaly_detector.py --end "2025-11-20 16:00:00" --window 6 --method stl
  
  # 机器学习方法（需要sklearn）
  python anomaly_detector.py --end "2025-11-20 16:00:00" --window 6 --method lof
  python anomaly_detector.py --end "2025-11-20 16:00:00" --window 6 --method isolation_forest
  
  # 列出所有方法
  python anomaly_detector.py --list-methods
        """
    )
    
    parser.add_argument('--db', default='weather_stream.db', help='数据库文件路径')
    parser.add_argument('--start', help='窗口起始时间 (格式: YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--end', help='窗口结束时间 (格式: YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--window', type=int, help='滑动窗口大小（小时）')
    parser.add_argument('--method', default='3sigma',
                       choices=list(AnomalyDetector.AVAILABLE_METHODS.keys()),
                       help='检测方法 (默认: 3sigma)')
    parser.add_argument('--station', help='指定检测的站点ID')
    parser.add_argument('--save', action='store_true', help='保存结果到JSON文件')
    parser.add_argument('--quiet', action='store_true', help='静默模式')
    parser.add_argument('--list-methods', action='store_true', help='列出所有检测方法')
    
    args = parser.parse_args()
    
    # 列出检测方法
    if args.list_methods:
        print("\n" + "="*80)
        print("可用的异常检测方法:")
        print("="*80)
        for method, desc in AnomalyDetector.AVAILABLE_METHODS.items():
            print(f"  {method:20s} - {desc}")
        print("="*80 + "\n")
        return
    
    # 验证参数
    if not ((args.start and args.end) or (args.end and args.window)):
        parser.error("必须指定: (--start 和 --end) 或 (--end 和 --window)")
    
    # 准备窗口信息
    if args.start and args.end:
        window_info_str = f"{args.start} ~ {args.end}"
        window_info_dict = {'start_time': args.start, 'end_time': args.end}
    else:
        window_info_str = f"结束于 {args.end} (往前 {args.window} 小时)"
        window_info_dict = {'end_time': args.end, 'window_hours': args.window}
    
    window_info_dict['method'] = args.method
    
    # 执行检测
    detector = AnomalyDetector(
        db_path=args.db, 
        start_time=args.start,
        end_time=args.end,
        window_hours=args.window,
        method=args.method
    )
    
    try:
        # 检测
        if args.station:
            results = [detector.detect_station(args.station)]
        else:
            results = detector.detect_all_stations()
        
        # 生成报告
        report = ReportGenerator.generate_text_report(results, window_info_str, method=args.method)
        
        if not args.quiet:
            print(report)
        
        # 保存JSON
        if args.save:
            filename = ReportGenerator.save_json_report(results, window_info_dict)
            print(f"\n✅ 检测结果已保存到: {filename}")
    
    finally:
        detector.close()


if __name__ == '__main__':
    main()


## 用统计方法 - 快速发现异常值
# python anomaly_detector.py --end "2025-11-21 02:00:00" --window 6 --method mad