#!/usr/bin/env python3
"""
空间异常检测工具
检测某一时刻各站点相对于邻近站点的异常
"""

import argparse
from datetime import datetime
from anomaly_detector import AnomalyDetector, SpatialDetector


def format_spatial_report(results: dict) -> str:
    """格式化空间异常检测报告"""
    lines = [
        "=" * 100,
        "空间异常检测报告",
        "=" * 100,
        f"检测时刻: {results['timestamp']}",
        f"总站点数: {results['n_stations']}",
        f"邻近阈值: {results['max_distance']} 公里",
        f"异常阈值: {results['threshold']} × MAD",
        ""
    ]
    
    if 'error' in results:
        lines.append(f"❌ 错误: {results['error']}")
        return "\n".join(lines)
    
    # 统计异常数量
    total_anomalies = sum(len(var_info['anomalous_stations']) 
                         for var_info in results['variables'].values())
    
    lines.extend([
        f"检测到异常: {total_anomalies} 个",
        "=" * 100,
        ""
    ])
    
    if total_anomalies == 0:
        lines.append("✅ 所有站点数据正常（相对于邻近站点）")
        return "\n".join(lines)
    
    # 详细异常信息
    for var, var_info in results['variables'].items():
        if not var_info['anomalous_stations']:
            continue
        
        lines.extend([
            f"【变量: {var_info['name']} ({var_info['unit']})】",
            f"  异常站点数: {len(var_info['anomalous_stations'])}",
            ""
        ])
        
        for station_id in var_info['anomalous_stations']:
            detail = var_info['details'][station_id]
            lines.extend([
                f"  ⚠️  站点: {station_id}",
                f"      实际值: {detail['value']:.2f} {var_info['unit']}",
                f"      邻近中位数: {detail['neighbor_median']:.2f} {var_info['unit']}",
                f"      偏离程度: {detail['deviation']:.1f}σ",
                f"      邻近站点数: {detail['n_neighbors']}",
                f"      邻近站点: {', '.join(detail['neighbor_ids'])}",
                ""
            ])
        
        lines.append("-" * 100)
        lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='空间异常检测 - 基于邻近站点的相关性',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 检测最新时刻的空间异常
  python spatial_anomaly_detector.py --time "2025-11-21 02:00:00"
  
  # 调整邻近距离阈值
  python spatial_anomaly_detector.py --time "2025-11-21 02:00:00" --distance 50
  
  # 调整异常阈值
  python spatial_anomaly_detector.py --time "2025-11-21 02:00:00" --threshold 2.5
  
原理:
  1. 对每个站点，找出邻近站点（地理距离 < 阈值）
  2. 计算邻近站点的中位数（考虑海拔修正）
  3. 如果该站点偏离邻近中位数过大 → 空间异常
  
海拔修正:
  - 温度: 每升高100m降低0.65°C
  - 气压: 每升高10m降低1.2hPa
        """
    )
    
    parser.add_argument('--db', default='weather_stream.db', help='数据库路径')
    parser.add_argument('--time', required=True, 
                       help='检测时刻 (格式: YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--distance', type=float, default=100, 
                       help='邻近站点最大距离（公里，默认100）')
    parser.add_argument('--threshold', type=float, default=3.0,
                       help='异常阈值（几倍MAD，默认3.0）')
    parser.add_argument('--save', action='store_true', help='保存结果到JSON')
    
    args = parser.parse_args()
    
    # 创建检测器（需要提供end_time参数）
    detector = AnomalyDetector(
        db_path=args.db,
        end_time=args.time,
        window_hours=1,  # 空间检测不需要窗口，但参数必须提供
        method='mad'  # 默认方法
    )
    
    try:
        # 执行空间检测
        results = detector.detect_spatial_anomalies(
            timestamp=args.time,
            max_distance=args.distance,
            threshold=args.threshold
        )
        
        # 生成报告
        report = format_spatial_report(results)
        print(report)
        
        # 保存JSON
        if args.save:
            import json
            filename = f"spatial_anomaly_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n✅ 结果已保存到: {filename}")
    
    finally:
        detector.close()


if __name__ == '__main__':
    main()

#python spatial_anomaly_detector.py --time "2025-11-21 02:00:00"