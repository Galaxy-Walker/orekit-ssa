# 阶段 1：轨道传播架构

## 1. 在开发主线中的职责

阶段 1 提供后续所有阶段共用的动力学基础：给定卫星初值与动力学配置，查询任意历元的轨道状态。
单星是示例规模，不是核心接口限制：每组初值携带 `spacecraft_id`，工厂每次创建独立传播器。

当前实现解析二体传播、数值二体传播、日/月第三体摄动。
地球非球形引力、大气阻力、光压和机动可通过摄动力插件扩展。
当前没有观测、滤波、协方差传播、测站或调度算法。

## 2. 分层与依赖方向

```text
main.py：组合根（选择数据、初值、后端、采样参数）
    │
    ├── ssa.propagation：Propagator / PropagatorFactory / 轨迹采样
    │       └── ssa.domain：Epoch / InitialConditions / OrbitState
    │
    └── ssa.orekit：传播端口的具体实现
            ├── runtime：JVM、参考数据
            ├── backend：Java ↔ Python 转换及传播器构建
            ├── config：传播方法、积分器配置
            └── forces：摄动力工厂
```

- 领域模型和采样服务只依赖标准库，既不导入 Java，也不启动 JVM。
- `Protocol` 提供结构化接口；采样、未来观测模块只依赖端口，不依赖具体传播器。
- Java `Orbit`、`SpacecraftState`、`AbsoluteDate` 不泄漏到应用层。
- 数据模型和配置使用不可变 dataclass，初值变化通过新建传播器表达。
- 同一工厂可分别构建真值轨道和估计轨道，也可使用不同动力学配置构建二者。

## 3. 数据与时间约定

| 内容 | 契约 |
|---|---|
| 位置 / 速度 / 质量 | m / m·s⁻¹ / kg |
| 引力常数 | m³·s⁻²，默认 EIGEN-5C 地球 μ |
| 角度 | 弧度；近点角类型显式选择，默认平近点角 |
| 参考系 | 地心惯性系 GCRF 或 EME2000，输出始终与初值一致 |
| 历元 | `Epoch.utc`，以 `Z` 结尾的 UTC ISO 字符串，最多 9 位小数 |
| 状态向量顺序 | `[x, y, z, vx, vy, vz]` |

`Epoch` 保留 `23:59:60` 闰秒的表达能力，格式在领域层检查，日期交给 Orekit 解析。
时间运算交给 `AbsoluteDate`，不通过 Python `datetime` 相减或 UTC 字符串排序实现。
输出 UTC 保留 9 位秒小数（输出会量化到纳秒），Java 内部时间精度不受输出格式限制。
不同文本精度可能表示同一时刻，`Epoch` 的 dataclass 相等性仅表示文本相等，不能当作物理时间比较。

`KeplerianElements` 当前只接受椭圆根数；笛卡尔初值适用于从定轨结果重启传播。
数值积分采用笛卡尔变量，避免圆轨道、赤道轨道的经典根数奇异性。
核心不执行地固系转换；后续测站 / 观测适配器负责所需坐标变换。

## 4. 传播端口及查询语义

```python
class Propagator(Protocol):
    @property
    def initial_state(self) -> OrbitState: ...
    def propagate(self, epoch: Epoch) -> OrbitState: ...
    def propagate_after(self, elapsed_s: float) -> OrbitState: ...

class PropagatorFactory(Protocol):
    def create(self, initial: InitialConditions) -> Propagator: ...
```

- `propagate_after(600)` 永远表示初始历元之后 600 个物理秒，支持负数回推。
- 查询顺序不会改变初值；重复查询不会接着上次终点外推。
- Orekit 适配器显式传入起始历元，并关闭数值传播后的初值重置。
- 实例内部包含可变 Java 对象，不承诺线程安全；并发任务应各自构建传播器。
- `sample_trajectory` 返回迭代器，包含首尾；末段不足一个步长时仍输出终点，零时长输出一次。
- 输出采样间隔不等于积分器内部步长；位置容差是局部积分误差尺度，不是全局精度保证。

当前数值查询从固定初值重新积分，优先保证随机查询和评估的可复现性。
长弧段密集采样会增加计算量；后续可实现带有覆盖时间范围的星历缓存适配器，
让它同样实现 `Propagator`，保持观测、采样和调度调用方不变。

## 5. 使用与扩展

### 独立使用核心

```python
from ssa.domain import CartesianPV, Epoch, InitialConditions
from ssa.orekit import OrekitPropagatorFactory, initialize_orekit
from ssa.propagation import sample_trajectory

initialize_orekit()
initial = InitialConditions(
    spacecraft_id="sat-001",
    epoch=Epoch("2002-01-01T00:00:00Z"),
    orbit=CartesianPV((7000000.0, 0.0, 0.0), (0.0, 7500.0, 0.0)),
)
factory = OrekitPropagatorFactory()
propagator = factory.create(initial)
state = propagator.propagate_after(600.0)
same_epoch = propagator.propagate(state.epoch)
trajectory = sample_trajectory(propagator, duration_s=630.0, step_s=60.0)
```

### 添加摄动力

内置插件示例：

```python
from ssa.orekit import IntegratorConfig, OrekitPropagatorFactory, PropagationMethod
from ssa.orekit.forces import ThirdBody, ThirdBodyGravity

factory = OrekitPropagatorFactory(
    method=PropagationMethod.NUMERICAL,
    integrator=IntegratorConfig(position_tolerance_m=0.01),
    forces=(ThirdBodyGravity(ThirdBody.SUN), ThirdBodyGravity(ThirdBody.MOON)),
)
```

新插件实现 `ForceModelFactory.create(initial)`，每次返回新的 Java `ForceModel`。
例如阻力插件自身保存面积、阻力系数和大气模型配置，`initial` 提供质量等初始条件。
Java 导入放在 `create` 内；插件属于 Orekit 层，不应被领域层引用。
中心引力已经由数值传播器自动添加，插件不应重复添加中心引力。
开普勒策略传入摄动力会报错，避免配置被静默忽略。

### 更换传播后端

实现 `Propagator` 和 `PropagatorFactory` 即可，例如 TLE/SGP4、离线星历或测试替身。
不同初值格式可增加专属工厂或输入模型，不必让核心采样服务增加后端判断。

## 6. 向阶段 2–5 的扩展点

| 阶段 | 在已有产物上新增 | 接口衔接 |
|---|---|---|
| 2 单星单站定轨 | 测站、观测模型、滤波器、估计协方差 | 观测查询 `Propagator`；滤波状态经 `CartesianPV` 输入工厂 |
| 3 单星多站融合 | 带测站标识 / 时间戳的观测流、序贯更新 / 融合 | 共用传播器和估计状态，融合层管理相关性 |
| 4 多星单站调度 | 多目标轨道注册表、关联、资源约束、闭环动作 | 用 `spacecraft_id` 索引传播器；调度查询可见性和信息收益 |
| 5 多星多站调度 | 网络资源约束、多智能体环境 | 复用状态与收益接口，扩展资源和决策层 |

### 协方差贯穿主线的边界

阶段 1 输出确定性 `OrbitState`；协方差应属于后续的**估计状态**，不能把真值轨迹当作带零协方差的估计。
预留 `LinearizedPropagator.propagate_with_transition(epoch)`，返回：

```text
LinearizedState
  state                 目标历元的 OrbitState
  transition_matrix     Φ(t,t₀) = ∂x(t)/∂x(t₀)，6×6
```

Φ 的起点是该传播器的 `initial_state`，两端都使用其惯性系，变量顺序为位置 / 速度。
阶段 1 的具体适配器尚未实现该可选能力。阶段 2 可通过 Orekit 矩阵计算能力实现；
增加 `StateEstimate(state, covariance)`，由估计层维护同历元、同坐标系的协方差并计算：

```text
P⁻(t) = Φ(t,t₀) P⁺(t₀) Φ(t,t₀)ᵀ + Q(t,t₀)
```

过程噪声 Q 属于估计模型配置，观测更新属于滤波层。
后续站点融合、调度信息收益和 RL 奖励共用估计层输出，保持动力学层与决策层解耦。
滤波更新后，通过新历元、新 `CartesianPV` 和原动力学配置重建传播器，避免修改真值传播器。

## 7. 生命周期与验证

应用显式调用 `initialize_orekit()`；默认使用已安装 `orekitdata` 包。
初始化受进程内锁保护且幂等，不重复启动 JVM 或注册数据；本进程初始化后不能切换数据目录。
使用默认 Orekit `DataContext`，不清除外部提供器；可复现运行应由应用统一管理数据来源。
需要并存不同数据集时使用独立进程。库不关闭 JVM。

```bash
uv run python main.py
uv run python -m unittest discover -s tests -v
```

回归验证包括：一周期闭合、二体能量守恒、解析 / 数值对照、正反向随机查询、
UTC 闰秒和亚秒精度、笛卡尔重启、圆赤道轨道、摄动力有效性、实例隔离及纯 Python 采样契约。
