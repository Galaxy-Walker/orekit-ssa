# 阶段 2：单星单站最小定轨

## 1. 目标与完成范围

在阶段 1 传播能力上完成：**真值传播 → 可见观测生成 → 带偏差初轨 → EKF → 真值误差与协方差诊断**。
本阶段是已有近似初轨的序贯改进，不求解仅凭观测初始化轨道的 IOD 问题。

实现顺序：

1. 测站、观测、估计状态与后端无关的数据契约。
2. WGS84 北京站、惯性系测站位置/速度、采样点仰角筛选及带噪声观测。
3. Orekit 数值传播的笛卡尔状态转移矩阵、NumPy EKF。
4. 可复现实验、逐观测 CSV 和物理/接口回归验证。

## 2. 分层

```text
orbit_determination.py                  实验组合根、指标、CSV
    ├── ssa.observations                测站/观测契约、几何模型、仿真
    ├── ssa.estimation                  StateEstimate、EKF、过程噪声
    ├── ssa.propagation                 传播/线性化工厂、物理时间端口
    └── ssa.orekit
          ├── backend                  传播、STM、OrekitClock
          └── stations                 测站惯性 PV 与仰角
```

`domain`、`propagation`、`observations` 仅依赖标准库。`estimation` 用 NumPy 做矩阵运算，
无 Java 依赖，不启动 JVM。Java 对象只存在于 `ssa/orekit/`；应用显式初始化。

## 3. 观测模型

### 坐标与约定

- 测站：WGS84 大地纬度/经度（弧度）、椭球高（m）；`ITRF(IERS_2010, simpleEOP=True)`。
- `TopocentricFrame.getPVCoordinates(date, frame)` 返回指定惯性系中的测站位置与速度，包含地球自转。
- 卫星、测站 PV 必须在同一历元和同一惯性系（GCRF 或 EME2000）。
- 观测包含卫星标识、测站标识、UTC 历元、距离（m）、距离率（m/s）、两项测量标准差。
- 正距离率表示远离；两项噪声独立，`R = diag(σρ², σρ̇²)`。

令 `d = r_sat - r_sta`、`w = v_sat - v_sta`、`u = d / |d|`：

```text
ρ  = |d|
ρ̇ = uᵀ w
H  = [ uᵀ                     0ᵀ ]
     [ (w - ρ̇u)ᵀ / ρ         uᵀ ]
```

这是**同历元瞬时几何观测**。没有光行时、收发双程、大气延迟、站钟/星钟误差、
相对论修正或测站参数估计；距离率也不是带载频定义的多普勒 Hz。
它与 Orekit `Range` / `RangeRate` 的完整信号传播模型不能直接混用。

`simulate_observations` 仅在**真值**仰角达到门限时生成测量，使用局部 `random.Random(seed)`；
不修改全局随机数状态。可见性是采样点筛选，没有求精确窗口边界，过大的步长可能漏掉短弧段。
滤波更新不按估计轨道仰角再次删观测，避免初轨偏差导致有效观测被拒绝。

## 4. 状态转移与 EKF

状态为惯性笛卡尔 `x = [x, y, z, vx, vy, vz]`；估计与真值分别建传播器。
`StateEstimate` 保存同历元、同坐标系的 `OrbitState` 和不可变 6×6 协方差，
要求有限、对称、正定；位置块单位 m²，速度块单位 m²/s²，交叉块单位 m²/s。

### 状态转移矩阵

`OrekitPropagatorFactory.create_linearized(initial)` 只支持 `NUMERICAL`。
内部 `setOrbitType(CARTESIAN)` 并调用：

```python
harvester = native.setupMatricesComputation("ssa-stm", None, None)
state = native.propagate(reference_date, target_date)
phi = harvester.getStateTransitionMatrix(state)
```

`None` 初始 STM 表示单位阵。返回的 `LinearizedState` 只有 Python 状态和矩阵元组；
Φ 总是相对该实例固定初值。普通 `create` 不启用矩阵计算。
参考：[Orekit 13.1.1 AbstractPropagator API](https://www.orekit.org/site-orekit-13.1.1/apidocs/org/orekit/propagation/AbstractPropagator.html)。

### 预测与更新

```text
x⁻ = f(x⁺, t)
P⁻ = Φ P⁺ Φᵀ + Q
y  = z - h(x⁻)
S  = H P⁻ Hᵀ + R
K  = P⁻ Hᵀ S⁻¹
x⁺ = x⁻ + K y
P⁺ = (I - KH) P⁻ (I - KH)ᵀ + K R Kᵀ
```

实现通过 `numpy.linalg.solve` 解线性系统，不显式求逆；协方差更新采用 Joseph 形式，
随后对称化。每次预测用最新后验 PV / 历元重建传播器，保留 μ、质量与动力学工厂配置。

- `process(observation)` 原子地预测到观测历元并联合更新距离/距离率；失败不提交新估计。
- `predict_to(epoch)` 支持无观测时间段的状态/协方差外推。
- 时间差通过 `OrekitClock` 的 `AbsoluteDate.durationFrom` 计算，正确处理闰秒与等价时间文本。
- 拒绝倒序观测及卫星/测站标识不匹配；相同物理历元可以更新独立观测。
  调用方应避免重复送入同一条测量，否则会重复计入信息。
- `FilterUpdate` 返回先验创新、非线性后验残差、`NIS = yᵀ S⁻¹ y` 和后验估计。
  当前仅记录 NIS，不做离群值剔除。

可配置惯性轴独立的连续白加速度谱密度 `q`（m²/s³）：

```text
Q = q [ Δt³/3 I   Δt²/2 I ]
      [ Δt²/2 I   Δt I    ]
```

这是局部匀速近似的过程噪声离散化，不是沿完整非线性轨道积分的噪声协方差。
默认示例真值和估计均为二体动力学，因此取 `q=0`。复杂摄动与长间隔下应重新评估 Q。

## 5. 复现实验

```bash
uv sync
uv run python orbit_determination.py
uv run python orbit_determination.py --seed 42 --output od-diagnostics.csv
uv run python -m unittest discover -s tests -v
```

默认参数：

| 项目 | 设置 |
|---|---|
| 真值初始历元 / 坐标系 | 2002-01-01 00:00:00 UTC / GCRF |
| 初始根数 | a=7000 km，e=0.001，i=55°，ω=30°，Ω=45°，M=60° |
| 真值 / 估计传播 | 解析二体 / 数值二体 |
| 北京站 | 纬度 39.9042°、经度 116.4074°、椭球高 50 m |
| 仿真时长 / 采样 / 最低仰角 | 86400 s / 30 s / 10° |
| 测量标准差 | 10 m / 0.1 m/s |
| 先验历元 | 首个可见采样点；此前只进行真值和可见性仿真 |
| 注入位置偏差 | (100, -80, 60) m |
| 注入速度偏差 | (0.1, -0.08, 0.06) m/s |
| 先验协方差 | 位置各轴 σ=200 m，速度各轴 σ=0.2 m/s，无相关项 |

真值只用于生成观测、注入实验初轨偏差及误差评估，不传给 EKF 更新。
未使用观测的开环基线从相同带偏差初轨传播；所有末次误差在最后一个观测历元比较，
不是默认仿真终点。默认首个可见点约在第 14.3 小时，短时长可能无观测，会明确报错。

当前依赖及数据、随机种子 42 的参考输出：

| 指标 | 结果 |
|---|---|
| 可见观测 | 86 组；14:18:30–22:56:00 UTC |
| 初始位置偏差 | 141.421 m |
| 末次开环位置误差 | 2591.935 m |
| 末次 EKF 位置 / 速度误差 | 7.297 m / 0.012304 m/s |
| 末次位置标准差 RSS | 5.728 m |
| 后验测距 / 距离率残差 RMS | 7.667 m / 0.085913 m/s |

位置标准差 RSS 是 `sqrt(trace(P_rr))`，不是三维置信球半径。
单次误差与该量比较不能替代 Monte Carlo 一致性分析；后验残差 RMS 也不是创新统计检验。
CSV 保存逐观测误差、开环误差、标准差 RSS、先验创新、后验残差和 NIS。

### 初轨精度限制

EKF 是局部线性化方法，单站短弧段的部分方向约束较弱。开发时曾试用十倍先验偏差及标准差
（初始位置偏差约 1.414 km），该场景末次位置误差约 56.7 m，而估计标准差 RSS 仅约 5.7 m，
出现明显过度自信。因此默认采用较近的先验；本阶段不承诺公里级初轨的稳健收敛。
后续可增加批最小二乘初始化、迭代滤波及多种子 NEES/NIS 一致性评估。

## 6. 验证与下一阶段衔接

`tests/test_estimation.py` 覆盖：

- 观测解析 Jacobian 对照中心差分；测站自转速度及距离率对照时间差分。
- 仰角 / 遮挡、固定种子、协方差与噪声参数校验。
- 标量可解析 Kalman 更新、卫星/测站错配、倒序观测、失败不修改状态。
- 数值二体和月球摄动 STM 对照六维独立差分、初始单位阵、随机查询不改参考初值。
- 无观测预测、过程噪声、闰秒和等价 UTC 历元。
- 全日闭环收敛、后验协方差正定、残差量级及 CSV 导出。

阶段 3 可复用带 `station_id` 的观测和 `StateEstimate`，把单一观测模型替换为按站标识路由的模型表，
在同一估计状态上按时间处理多站观测。相关噪声、重复观测、时钟和站偏差需在融合层显式建模。
