# Orekit SSA：空间态势感知仿真

航天器观测规划研究/学习仓库：从单星单站最小定轨起步，逐步走向强化学习观测调度。

开发主线：**轨道传播 → 单星单站定轨 → 单星多站融合 → 多星单站调度 → 多星多站调度**。

> [!NOTE]
> 本项目仍处于初步开发阶段，代码由 AI 辅助编写，本人仍在学习航天器动力学与轨道确定，代码可能存在错误或不严谨之处，欢迎指正，请谨慎参考。

## 当前进度

- 阶段 1 轨道传播（`main.py`）：开普勒 / 数值传播，可叠加日月第三体摄动。
- 阶段 2 单星单站最小定轨（`orbit_determination.py`）：LEO + 北京站，按仰角筛选带噪声的测距 / 距离率观测，通过笛卡尔 EKF 改进已有初轨，输出协方差、残差及真值误差。
- 下一阶段：单星多站融合。


## 运行

需要 Python 3.14、JDK 11+（当前环境 JDK 21）和 uv。

```bash
uv sync
uv run python main.py
uv run python main.py --method numerical --duration 3600 --step 600
uv run python main.py --method numerical --third-body sun --third-body moon
uv run python orbit_determination.py
uv run python orbit_determination.py --seed 42 --output od-diagnostics.csv
uv run python -m unittest discover -s tests -v
```

默认数据来自 `orekitdata` 包；可用 `--data-dir` 指定本地数据目录。
默认初轨沿用原始示例，输出包含卫星标识、坐标系、UTC、位置和速度模长。

定轨示例默认仿真一天、每 30 秒采样、10° 仰角门限；测量标准差为 10 m / 0.1 m/s。
采用瞬时几何距离率（m/s），未换算为多普勒频移（Hz）。固定种子 42 的参考结果：
86 组观测，初始位置偏差 141.4 m，末次位置误差约 7.3 m、速度误差约 0.012 m/s。
这是二体动力学、已有近似初轨的仿真闭环；模型假设与复现实验见阶段 2 文档。

## 代码导航

| 路径 | 职责 |
|---|---|
| `ssa/domain.py` | 不可变初值、历元、状态、状态转移矩阵契约 |
| `ssa/propagation.py` | 传播器 / 工厂 / 线性化端口及轨迹采样 |
| `ssa/observations.py` | 测站与观测契约、几何模型及可见观测仿真 |
| `ssa/estimation.py` | 估计状态、协方差、EKF 预测与更新（NumPy） |
| `ssa/orekit/runtime.py` | 显式、幂等 JVM 与参考数据初始化 |
| `ssa/orekit/backend.py` | Orekit 对象创建、传播、数据转换 |
| `ssa/orekit/config.py` | 传播策略和积分器配置 |
| `ssa/orekit/forces.py` | 可插拔摄动力模型 |
| `ssa/orekit/stations.py` | WGS84 测站、地球自转与仰角适配 |
| `main.py` | 示例装配入口 |
| `orbit_determination.py` | 单星单站实验装配与诊断 CSV |
| `tests/test_propagation.py` | 物理回归与接口契约验证 |
| `tests/test_estimation.py` | 观测 / STM 导数、EKF 解析解及收敛验证 |

设计与扩展方式见 [阶段 1 架构](docs/architecture/stage-1-propagation.md)、
[阶段 2：单星单站定轨](docs/architecture/stage-2-single-station-estimation.md)。
Orekit 使用细节见 [中文教程](docs/tutorials/index.md)。
