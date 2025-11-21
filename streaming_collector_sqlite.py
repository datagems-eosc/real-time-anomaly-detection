"""
基于SQLite的流式数据采集与存储系统
==========================================

使用SQLite数据库存储和管理气象数据流
- 无需安装额外软件（Python自带）
- 轻量级、高性能
- 支持滑动窗口查询
- 自动创建索引

Author: Weather Anomaly Detection Team
Date: 2025-11-20
"""

import sqlite3
import requests
import json
import time
import argparse
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import threading
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('streaming_collector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SQLiteDatabase:
    """
    SQLite数据库管理器
    专为时序气象数据优化
    """
    
    def __init__(self, db_path: str = 'weather_stream.db'):
        """
        初始化数据库连接
        
        Parameters:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._init_database()
    
    def _connect(self):
        """建立数据库连接"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # 使用字典式游标
            logger.info(f"成功连接到SQLite数据库: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"数据库连接失败: {e}")
            raise
    
    def _init_database(self):
        """初始化数据库表结构"""
        try:
            cursor = self.conn.cursor()
            
            # 1. 创建站点信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stations (
                    station_id TEXT PRIMARY KEY,
                    station_name_en TEXT,
                    station_name_gr TEXT,
                    latitude REAL,
                    longitude REAL,
                    elevation REAL,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("✓ 站点表已创建")
            
            # 2. 创建观测数据表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time TIMESTAMP NOT NULL,
                    station_id TEXT NOT NULL,
                    temp_out REAL,
                    hi_temp REAL,
                    low_temp REAL,
                    out_hum REAL,
                    bar REAL,
                    rain REAL,
                    wind_speed REAL,
                    wind_dir REAL,
                    wind_dir_str TEXT,
                    hi_speed REAL,
                    hi_dir REAL,
                    hi_dir_str TEXT,
                    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(time, station_id)
                )
            """)
            logger.info("✓ 观测表已创建")
            
            # 3. 创建索引（加速查询）
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_observations_station_time 
                ON observations (station_id, time DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_observations_time 
                ON observations (time DESC)
            """)
            logger.info("✓ 索引已创建")
            
            # 4. 创建数据采集日志表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS collection_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT,
                    stations_count INTEGER,
                    observations_count INTEGER,
                    message TEXT
                )
            """)
            logger.info("✓ 采集日志表已创建")
            
            self.conn.commit()
            logger.info("✓ 数据库初始化完成")
            
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"数据库初始化失败: {e}")
            raise
    
    def insert_station(self, station_id: str, info: Dict) -> bool:
        """
        插入或更新站点信息
        
        Parameters:
            station_id: 站点ID
            info: 站点信息字典
            
        Returns:
            成功返回True，失败返回False
        """
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                INSERT INTO stations (
                    station_id, station_name_en, station_name_gr,
                    latitude, longitude, elevation, first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(station_id) DO UPDATE SET
                    station_name_en = excluded.station_name_en,
                    station_name_gr = excluded.station_name_gr,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    elevation = excluded.elevation,
                    last_seen = CURRENT_TIMESTAMP
            """, (
                station_id, info.get('station_name_en'), info.get('station_name_gr'),
                info.get('latitude'), info.get('longitude'), info.get('elevation')
            ))
            
            self.conn.commit()
            return True
            
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"插入站点信息失败: {e}")
            return False
    
    def insert_observations_batch(self, observations: List[Tuple]) -> int:
        """
        批量插入观测数据
        
        Parameters:
            observations: 观测数据列表
            
        Returns:
            成功插入的数量
        """
        try:
            cursor = self.conn.cursor()
            
            cursor.executemany("""
                INSERT OR IGNORE INTO observations (
                    time, station_id, temp_out, hi_temp, low_temp, out_hum,
                    bar, rain, wind_speed, wind_dir, wind_dir_str,
                    hi_speed, hi_dir, hi_dir_str
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, observations)
            
            self.conn.commit()
            return cursor.rowcount
            
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"批量插入失败: {e}")
            return 0
    
    def log_collection(self, status: str, stations_count: int, obs_count: int, message: str = ""):
        """记录数据采集日志"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO collection_log (status, stations_count, observations_count, message)
                VALUES (?, ?, ?, ?)
            """, (status, stations_count, obs_count, message))
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            logger.error(f"记录采集日志失败: {e}")
    
    def get_station_window(self, station_id: str, window_size: int = 6) -> List[Dict]:
        """
        获取某个站点的最新N条数据（滑动窗口）
        
        Parameters:
            station_id: 站点ID
            window_size: 窗口大小
            
        Returns:
            观测数据列表
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT 
                    strftime('%s', time) as timestamp,
                    time,
                    station_id,
                    temp_out, hi_temp, low_temp, out_hum,
                    bar, rain, wind_speed, wind_dir, wind_dir_str,
                    hi_speed, hi_dir, hi_dir_str
                FROM observations
                WHERE station_id = ?
                ORDER BY time DESC
                LIMIT ?
            """, (station_id, window_size))
            
            return [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
            logger.error(f"查询窗口数据失败: {e}")
            return []
    
    def get_stats(self) -> Dict:
        """获取数据库统计信息"""
        try:
            cursor = self.conn.cursor()
            
            # 基础统计
            cursor.execute("SELECT COUNT(*) as count FROM stations")
            stations_count = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM observations")
            observations_count = cursor.fetchone()['count']
            
            # 时间范围
            cursor.execute("""
                SELECT 
                    MIN(time) as earliest,
                    MAX(time) as latest
                FROM observations
            """)
            time_range = cursor.fetchone()
            
            # 最近采集
            cursor.execute("""
                SELECT * FROM collection_log 
                ORDER BY timestamp DESC 
                LIMIT 1
            """)
            last_collection = cursor.fetchone()
            
            # 数据库大小
            db_size = Path(self.db_path).stat().st_size / (1024 * 1024)  # MB
            
            return {
                'stations_count': stations_count,
                'observations_count': observations_count,
                'earliest_data': time_range['earliest'] if time_range['earliest'] else None,
                'latest_data': time_range['latest'] if time_range['latest'] else None,
                'last_collection': dict(last_collection) if last_collection else None,
                'database_size_mb': f"{db_size:.2f} MB"
            }
            
        except sqlite3.Error as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("数据库连接已关闭")


class StreamingCollector:
    """
    流式数据采集器
    持续从GeoJSON源获取数据并存储到SQLite
    """
    
    def __init__(self, 
                 geojson_url: str,
                 db: SQLiteDatabase,
                 interval_seconds: int = 600):
        """
        初始化采集器
        
        Parameters:
            geojson_url: 数据源URL
            db: SQLite数据库实例
            interval_seconds: 采集间隔（秒）
        """
        self.geojson_url = geojson_url
        self.db = db
        self.interval_seconds = interval_seconds
        self.running = False
        self.thread = None
    
    def fetch_and_store(self) -> Tuple[bool, str]:
        """
        获取并存储一批数据
        
        Returns:
            (成功与否, 消息)
        """
        try:
            logger.info(f"正在从 {self.geojson_url} 获取数据...")
            response = requests.get(self.geojson_url, timeout=30)
            response.raise_for_status()
            
            geojson_data = response.json()
            features = geojson_data.get('features', [])
            
            if not features:
                msg = "未获取到任何数据"
                logger.warning(msg)
                self.db.log_collection('WARNING', 0, 0, msg)
                return False, msg
            
            # 准备批量插入数据
            station_info_list = []
            observations_list = []
            
            for feature in features:
                props = feature['properties']
                coords = feature['geometry']['coordinates']
                
                station_id = props.get('station_file', props.get('fid', ''))
                if not station_id:
                    continue
                
                # 站点信息
                station_info = {
                    'station_id': station_id,
                    'station_name_en': props.get('station_name_en'),
                    'station_name_gr': props.get('station_name_gr'),
                    'latitude': coords[1],
                    'longitude': coords[0],
                    'elevation': coords[2] if len(coords) > 2 else None
                }
                station_info_list.append(station_info)
                
                # 观测数据
                timestamp = props.get('ts', 0)
                if timestamp > 0:
                    time_dt = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    obs = (
                        time_dt, station_id,
                        props.get('temp_out'), props.get('hi_temp'), props.get('low_temp'),
                        props.get('out_hum'), props.get('bar'), props.get('rain'),
                        props.get('wind_speed'), props.get('wind_dir'), props.get('wind_dir_str'),
                        props.get('hi_speed'), props.get('hi_dir'), props.get('hi_dir_str')
                    )
                    observations_list.append(obs)
            
            # 批量存储站点信息
            stations_count = 0
            for info in station_info_list:
                if self.db.insert_station(info['station_id'], info):
                    stations_count += 1
            
            # 批量存储观测数据
            observations_count = self.db.insert_observations_batch(observations_list)
            
            msg = f"成功存储 {stations_count} 个站点的 {observations_count} 条观测数据"
            logger.info(msg)
            self.db.log_collection('SUCCESS', stations_count, observations_count, msg)
            
            return True, msg
            
        except requests.exceptions.RequestException as e:
            msg = f"网络请求失败: {e}"
            logger.error(msg)
            self.db.log_collection('ERROR', 0, 0, msg)
            return False, msg
        except Exception as e:
            msg = f"数据处理失败: {e}"
            logger.error(msg)
            self.db.log_collection('ERROR', 0, 0, msg)
            return False, msg
    
    def start(self):
        """启动持续采集"""
        if self.running:
            logger.warning("采集器已在运行中")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._collection_loop, daemon=True)
        self.thread.start()
        logger.info("流式采集器已启动")
    
    def stop(self):
        """停止采集"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("流式采集器已停止")
    
    def _collection_loop(self):
        """采集循环"""
        logger.info(f"采集循环已启动，间隔: {self.interval_seconds} 秒")
        
        while self.running:
            cycle_start = time.time()
            
            # 执行采集
            success, msg = self.fetch_and_store()
            
            # 计算下次采集时间
            elapsed = time.time() - cycle_start
            sleep_time = max(0, self.interval_seconds - elapsed)
            
            if self.running and sleep_time > 0:
                next_collection = datetime.now() + timedelta(seconds=sleep_time)
                logger.info(f"下次采集时间: {next_collection.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 分段睡眠，以便快速响应停止信号
                for _ in range(int(sleep_time)):
                    if not self.running:
                        break
                    time.sleep(1)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='基于SQLite的流式气象数据采集系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 启动持续采集（每10分钟）
  python streaming_collector_sqlite.py --continuous
  
  # 采集一次并查看统计
  python streaming_collector_sqlite.py --once --stats
  
  # 自定义采集间隔（5分钟）
  python streaming_collector_sqlite.py --continuous --interval 300
  
  # 指定数据库文件
  python streaming_collector_sqlite.py --continuous --database my_weather.db
        """
    )
    
    # 数据库配置
    parser.add_argument('--database', type=str, default='weather_stream.db', help='数据库文件路径')
    
    # 数据源配置
    parser.add_argument(
        '--url',
        type=str,
        default='https://stratus.meteo.noa.gr/data/stations/latestValues_Datagems.geojson',
        help='GeoJSON数据源URL'
    )
    
    # 采集配置
    parser.add_argument('--interval', type=int, default=600, help='采集间隔（秒）')
    
    # 运行模式
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--once', action='store_true', help='只采集一次')
    mode_group.add_argument('--continuous', action='store_true', help='持续采集')
    
    parser.add_argument('--stats', action='store_true', help='显示统计信息')
    
    args = parser.parse_args()
    
    # 初始化数据库
    logger.info("连接SQLite数据库...")
    db = SQLiteDatabase(args.database)
    
    # 显示统计信息
    if args.stats:
        stats = db.get_stats()
        print(f"\n{'='*80}")
        print("SQLite 数据库统计")
        print(f"{'='*80}")
        print(f"数据库文件: {args.database}")
        print(f"数据库大小: {stats.get('database_size_mb', 'N/A')}")
        print(f"站点数量: {stats.get('stations_count', 0)}")
        print(f"观测数量: {stats.get('observations_count', 0)}")
        print(f"最早数据: {stats.get('earliest_data', 'N/A')}")
        print(f"最新数据: {stats.get('latest_data', 'N/A')}")
        
        if stats.get('last_collection'):
            print(f"\n最近采集:")
            print(f"  时间: {stats['last_collection']['timestamp']}")
            print(f"  状态: {stats['last_collection']['status']}")
            print(f"  站点: {stats['last_collection']['stations_count']}")
            print(f"  观测: {stats['last_collection']['observations_count']}")
        
        print(f"{'='*80}\n")
    
    # 创建采集器
    collector = StreamingCollector(args.url, db, args.interval)
    
    if args.once:
        # 单次采集
        success, msg = collector.fetch_and_store()
        if success:
            logger.info("✓ 采集成功")
            if args.stats:
                stats = db.get_stats()
                print(f"更新后观测总数: {stats.get('observations_count', 0)}")
        else:
            logger.error("✗ 采集失败")
        db.close()
    
    else:  # continuous
        # 持续采集
        print(f"\n{'='*80}")
        print("SQLite 流式数据采集系统")
        print(f"{'='*80}")
        print(f"数据源: {args.url}")
        print(f"数据库: {args.database}")
        print(f"采集间隔: {args.interval} 秒")
        print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("按 Ctrl+C 停止")
        print(f"{'='*80}\n")
        
        # 设置信号处理
        def signal_handler(sig, frame):
            print("\n\n正在停止采集器...")
            collector.stop()
            db.close()
            print("已安全退出")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # 启动采集
        collector.start()
        
        # 保持主线程运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            collector.stop()
            db.close()


if __name__ == '__main__':
    main()

