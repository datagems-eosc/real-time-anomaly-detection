# 🌦️ DataGEMS 气象数据异常检测系统

实时监控希腊国家天文台(NOA) 14个气象站数据的流式处理和异常检测系统。

---

## 📋 目录

1. [快速开始](#快速开始)
2. [系统组件](#系统组件)
3. [异常检测方法](#异常检测方法)
4. [使用示例](#使用示例)
5. [文件说明](#文件说明)

---

## 🚀 快速开始

### 1. 启动数据采集

```bash
cd /data/qwang/q/datagem/stream_detection
source ~/software/miniconda3/bin/activate datagem

# 启动后台采集（每10分钟一次）
bash manage_collector.sh start
```

### 2. 查看数据

```bash
# 查看最新数据
python view_data.py --realtime

# 查看特定站点
python view_data.py --station heraclion --latest 20
```

### 3. 异常检测

```bash
# 时序异常检测（单站点，不同时刻）
python anomaly_detector.py --end "2025-11-21 02:00:00" --window 6 --method mad

# 空间异常检测（所有站点，同一时刻）
python spatial_anomaly_detector.py --time "2025-11-21 02:00:00"
```

---

## 🔧 系统组件

### 📡 数据采集层
- **`streaming_collector_sqlite.py`** - 每10分钟从GeoJSON源获取数据
- **`weather_stream.db`** - SQLite数据库，存储所有历史数据
- **`manage_collector.sh`** - 管理采集进程（启动/停止/查看状态）

### 🔍 异常检测层
- **`anomaly_detector.py`** - 时序异常检测（同一站点，时间窗口内）
- **`spatial_anomaly_detector.py`** - 空间异常检测（不同站点，同一时刻）
- **`view_data.py`** - 数据查询和导出工具

---

## 📊 异常检测方法

### 🕐 时序方法（Temporal）
检测：**同一个站点在时间窗口内的异常**

| 方法 | 描述 | 推荐场景 |
|------|------|---------|
| **3sigma** | 3σ规则，假设正态分布 | 只关注极端异常 |
| **mad** ⭐ | 中位数绝对偏差，最鲁棒 | **气象数据首选** |
| **iqr** | 箱线图法，高敏感度 | 探索性分析 |
| **zscore** | 改进Z-score（基于MAD） | 与MAD效果类似 |
| **arima** | ARIMA残差分析 | 考虑时序自相关 |
| **stl** | 季节-趋势分解 | 有周期性数据 |
| **isolation_forest** | 孤立森林（机器学习） | 复杂模式 |
| **lof** | 局部离群因子 | 密度不均匀数据 |

**推荐组合**：
- 日常监控：`--method mad`（平衡敏感度和鲁棒性）
- 严重告警：`--method 3sigma`（只报极端情况）

### 🌍 空间方法（Spatial）
检测：**同一时刻，某站点相对邻近站点的异常**

**原理**：
1. 计算站点间地理距离（Haversine公式）
2. 找出邻近站点（默认100公里内）
3. 考虑海拔差异修正（温度: -0.65°C/100m，气压: -1.2hPa/10m）
4. 如果该站点值与邻近中位数差异过大 → 异常

**优势**：
- 区分"传感器故障"和"真实极端天气"
- 传感器故障：只有该站点异常，邻近站点正常
- 极端天气：该站点和邻近站点都异常

---

## 💡 使用示例

### 场景1: 日常监控（推荐MAD）

```bash
# 检测最近6小时的数据
python anomaly_detector.py \
  --end "2025-11-21 02:00:00" \
  --window 6 \
  --method mad

# 输出示例：
# ⚠️  发现 5 个站点存在异常
# 【站点: amfissa】温度异常: 8次
# 【站点: portaria】温度异常: 7次
```

### 场景2: 对比不同方法

```bash
# 保守检测（只抓极端值）
python anomaly_detector.py --end "2025-11-21 02:00:00" --window 6 --method 3sigma
# 结果: 1个异常站点

# 敏感检测（抓更多边界值）
python anomaly_detector.py --end "2025-11-21 02:00:00" --window 6 --method iqr
# 结果: 9个异常站点

# 推荐方法（平衡）
python anomaly_detector.py --end "2025-11-21 02:00:00" --window 6 --method mad
# 结果: 5个异常站点
```

### 场景3: 空间验证

```bash
# 时序检测发现异常
python anomaly_detector.py --end "2025-11-21 02:00:00" --window 6 --method mad
# 输出: heraclion站点风速24.10km/h异常

# 空间验证（是传感器故障还是真实极端天气？）
python spatial_anomaly_detector.py --time "2025-11-21 02:00:00"
# 如果只有heraclion异常，邻近站点正常 → 传感器故障
# 如果周边站点也异常 → 真实极端天气
```

### 场景4: 检测特定站点

```bash
# 只检测某个站点
python anomaly_detector.py \
  --end "2025-11-21 02:00:00" \
  --window 12 \
  --method mad \
  --station heraclion
```

### 场景5: 保存结果

```bash
# 保存JSON格式结果
python anomaly_detector.py \
  --end "2025-11-21 02:00:00" \
  --window 6 \
  --method mad \
  --save

# 生成文件: anomaly_report_20251121_023456.json
```

### 场景6: 批量检测不同时段

```bash
#!/bin/bash
# 检测每6小时窗口

for hour in 00 06 12 18; do
  python anomaly_detector.py \
    --end "2025-11-21 ${hour}:00:00" \
    --window 6 \
    --method mad \
    --save \
    --quiet
  echo "✓ 完成: ${hour}:00"
done
```

---

## 📁 文件说明

### ✅ 核心文件（正在使用）

#### 数据采集
```
streaming_collector_sqlite.py  - 数据采集主程序
weather_stream.db              - SQLite数据库
manage_collector.sh            - 管理脚本（启动/停止）
collector_output.log           - 采集日志
```

#### 异常检测
```
anomaly_detector.py            - 时序异常检测（11种方法）
spatial_anomaly_detector.py    - 空间异常检测
view_data.py                   - 数据查询工具
timeseries_anomaly_detector.py - 底层算法库
```

#### 文档
```
README.md                      - 本文档（完整使用指南）
```

### 📦 归档文件（ignore/）

```
ignore/
├── streaming_collector_timescale.py    - TimescaleDB版本（已废弃）
├── streaming_anomaly_detector_timescale.py
├── TIMESCALEDB_SETUP_GUIDE.md
├── requirements_timescale.txt
└── start_timescale_collector.sh
```

---

## 🔍 常见问题

### Q1: 数据保存在哪里？
**A**: `weather_stream.db` SQLite数据库，实时更新

### Q2: 如何查看最新数据？
```bash
python view_data.py --realtime
```

### Q3: 如何停止数据采集？
```bash
bash manage_collector.sh stop
```

### Q4: 推荐用哪个检测方法？
**A**: 
- **日常用**: `mad` - 平衡敏感度和鲁棒性
- **保守用**: `3sigma` - 只报极端异常
- **探索用**: `iqr` - 高敏感度，适合初步筛查

### Q5: 时序检测 vs 空间检测？
- **时序检测**: 一个站点，不同时刻，检测"是否异常"
- **空间检测**: 多个站点，同一时刻，检测"谁异常"
- **推荐**: 先时序检测发现异常，再空间验证排除误报

### Q6: 如何判断是传感器故障还是极端天气？
```bash
# 步骤1: 时序检测
python anomaly_detector.py --end "TIME" --window 6 --method mad
# 发现站点A温度异常

# 步骤2: 空间验证
python spatial_anomaly_detector.py --time "TIME"
# 如果只有站点A异常 → 传感器故障
# 如果站点A和邻近站点都异常 → 极端天气
```

---

## 📊 数据统计

**数据源**: https://stratus.meteo.noa.gr/data/stations/latestValues_Datagems.geojson

**站点数量**: 14个DataGEMS气象站

**变量**:
- 温度（temp_out, hi_temp, low_temp）
- 湿度（out_hum）
- 气压（bar）
- 风速/风向（wind_speed, wind_dir, hi_speed）
- 降雨（rain）
- 地理信息（latitude, longitude, elevation）

**更新频率**: 每10分钟

**数据存储**: 从2024-11-20开始的所有历史数据

---

## 🛠️ 技术栈

- **Python 3.x** - 主要开发语言
- **SQLite** - 轻量级数据库
- **pandas** - 数据处理
- **numpy** - 数值计算
- **statsmodels** (可选) - ARIMA/STL时序模型
- **scikit-learn** (可选) - 机器学习方法

---

## 📞 联系方式

- **项目位置**: `/data/qwang/q/datagem/stream_detection/`
- **服务器**: `qwang@172.27.96.38` (内网) / `193.48.200.25` (公网)
- **数据提供**: 希腊国家天文台 (NOA)

---

## 📝 更新日志


### 2024-11-20
- ✅ 完成数据采集系统
- ✅ 实现基础异常检测（3σ、MAD、IQR）

---

## 🎯 下一步计划
- [ ] 添加可视化dashboard
- [ ] 结合历史数据训练模型
---

**最后更新**: 2024-11-21  
**版本**: v2.0

