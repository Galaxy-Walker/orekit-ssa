# Orekit SSA：空间态势感知仿真

航天器观测规划研究/学习仓库：从单星单站最小定轨起步，逐步走向强化学习观测调度。

开发主线：**轨道传播 → 单星单站定轨 → 单星多站融合 → 多星单站调度 → 多星多站调度**。

> [!NOTE]
> 本项目仍处于初步开发阶段，代码由 AI 辅助编写，本人仍在学习航天器动力学与轨道确定，代码可能存在错误或不严谨之处，欢迎指正，请谨慎参考。

## 当前进度

- 单星单站最小定轨（`src/main.py`）：纯仿真环境（LEO 卫星 + 北京站），用测距与多普勒测量通过 EKF 估计轨道，并与真值比较。
- Nyx 中文教程（`tutorial/nyx/`）：基于 nyx-space 2.5.0，含飞船建模、任务设计、轨道确定三个可运行样例。


## 运行

需要 Python 3.14、JDK 11+（当前环境 JDK 21）和 uv。

```bash
uv sync
uv run python main.py
uv run python main.py --method numerical --duration 3600 --step 600
uv run python main.py --method numerical --third-body sun --third-body moon
uv run python -m unittest discover -s tests -v
```

默认数据来自 `orekitdata` 包；可用 `--data-dir` 指定本地数据目录。
默认初轨沿用原始示例，输出包含卫星标识、坐标系、UTC、位置和速度模长。

## 代码导航

| 路径 | 职责 |
|---|---|
| `ssa/domain.py` | 不可变初值、历元、状态、状态转移矩阵契约 |
| `ssa/propagation.py` | 传播器 / 工厂 / 线性化端口及轨迹采样 |
| `ssa/orekit/runtime.py` | 显式、幂等 JVM 与参考数据初始化 |
| `ssa/orekit/backend.py` | Orekit 对象创建、传播、数据转换 |
| `ssa/orekit/config.py` | 传播策略和积分器配置 |
| `ssa/orekit/forces.py` | 可插拔摄动力模型 |
| `main.py` | 示例装配入口 |
| `tests/test_propagation.py` | 物理回归与接口契约验证 |

设计与扩展方式见 [阶段 1 架构](docs/architecture/stage-1-propagation.md)。
Orekit 使用细节见 [中文教程](docs/tutorials/index.md)。
