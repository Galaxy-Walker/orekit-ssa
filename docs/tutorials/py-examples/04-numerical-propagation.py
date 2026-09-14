"""第 4 章配套代码：数值外推与力模型（NumericalPropagator）。
与官方版本的结构差异：官方用 OrekitFixedStepHandler（Java 接口）在积分过程中
回调打印 a/e；Python 里实现 Java 接口必须写 @JImplements/@JOverride 装饰器
（属高阶语法）。本代码改用"循环 + propagate(采样时刻)"达到同样效果：
NumericalPropagator.propagate() 是有状态的，每次调用接着上次的状态继续积分
（见下方注释），所以循环采样 = 在采样时刻分段积分 = 步进处理器所见的状态列。
"""

# 0. 启动 JVM —— 之后才能导入 org.*
import orekit_jpype as orekit
orekit.initVM()

from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()

from org.hipparchus.ode.nonstiff import DormandPrince853Integrator
from org.hipparchus.util import FastMath
from org.orekit.forces.gravity import HolmesFeatherstoneAttractionModel
from org.orekit.forces.gravity.potential import GravityFieldFactory
from org.orekit.frames import FramesFactory
from org.orekit.orbits import KeplerianOrbit, OrbitType, PositionAngleType
from org.orekit.propagation import SpacecraftState
from org.orekit.propagation.numerical import NumericalPropagator
from org.orekit.time import AbsoluteDate, TimeScalesFactory
from org.orekit.utils import IERSConventions

# 1. 初始轨道：与第 3 章完全相同的一组大偏心率轨道
mu = 3.986004415e14  # GM [m^3/s^2] = Constants.EIGEN5C_EARTH_MU
utc = TimeScalesFactory.getUTC()
initial_date = AbsoluteDate(2004, 1, 1, 23, 30, 0.0, utc)
inertial_frame = FramesFactory.getEME2000()

initial_orbit = KeplerianOrbit(
    24396159.0,                      # a [m]，半长轴
    0.72831215,                      # e [-]，偏心率（近地点只有约 6600 km）
    FastMath.toRadians(7.0),         # i [rad]
    FastMath.toRadians(180.0),       # ω [rad]
    FastMath.toRadians(261.0),       # Ω [rad]
    0.0,                             # 平近点角 M [rad]
    PositionAngleType.MEAN,          # 最后一个角度是"平近点角"
    inertial_frame, initial_date, mu,
)
# 状态 = 轨道 +（可选）质量/姿态。本例无阻力与光压，质量取默认 1000 kg 也用不到
initial_state = SpacecraftState(initial_orbit)


def build_propagator(state, degree, order, orbit_type):
    """按给定的引力场阶/次和积分变量类型组装数值外推器。

    degree/order：地球引力场展开的最高阶数与次数；
    orbit_type  ：外推器内部积分的变量，KEPLERIAN = 对轨道根数积分，
                  CARTESIAN = 直接对位置速度积分（练习 3 对比用）。
    """
    # 自适应步长积分器 Dormand-Prince 8(5,3)：8 阶主公式 + 5 阶从公式 + 3 阶误差估计
    # 参数：最小步长[s]、最大步长[s]、绝对容差、相对容差
    # 容差作用在积分器内部的缩放变量上，限制的是"每步误差"而非输出精度；
    # 步长自动调整，与下面 60 s 的采样步长无关。
    # 官方 Java 用 ToleranceProvider.of(CartesianToleranceProvider.of(10.0)) 直接给
    # 10 m 位置误差，本代码的 (1e-3, 1e-3) 与它在 630 s 弧段内差 <1 mm（二者都对）
    integrator = DormandPrince853Integrator(0.001, 1000.0, 1.0e-3, 1.0e-3)

    propagator = NumericalPropagator(integrator)
    propagator.setOrbitType(orbit_type)  # 默认就是 KEPLERIAN

    # 力模型：degree x order 阶归一化球谐引力场（系数从 orekit-data 读取）
    #     地球的扁平等信息在 ITRF 地固系中定义，故需传入随地球自转的 ITRF 框架
    provider = GravityFieldFactory.getNormalizedProvider(degree, order)
    earth_frame = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
    gravity_field = HolmesFeatherstoneAttractionModel(earth_frame, provider)

    # 把力模型注册进外推器：可反复 addForceModel 叠加（阻力、光压、第三体…）
    # 注意：NumericalPropagator 默认一个力模型都没有；只加这一个就能飞，
    # 是因为球谐展开的 0 阶项本身就是二体中心引力 mu/r^2，无需另外再加。
    propagator.addForceModel(gravity_field)

    propagator.setInitialState(state)  # 积分起点
    return propagator


# 2. 采样循环（代替官方 OrekitFixedStepHandler）
duration = 630.0                               # 外推时长 [s]
sample_step = 60.0                             # 采样步长 [s]
final_date = initial_date.shiftedBy(duration)  # 末状态时刻（不落在采样点上）

# 三组配置：(说明, 阶数, 次数, 积分变量类型)
#   后两组对应章末练习 1 与练习 3，做对照实验
configs = [
    ("10x10 阶引力场 + KEPLERIAN 根数积分（官方配置）", 10, 10, OrbitType.KEPLERIAN),
    ("2x0 阶（只保留 J2 项）→ 练习 1", 2, 0, OrbitType.KEPLERIAN),
    ("10x10 阶引力场 + CARTESIAN 直角坐标积分 → 练习 3", 10, 10, OrbitType.CARTESIAN),
]

for title, degree, order, orbit_type in configs:
    propagator = build_propagator(initial_state, degree, order, orbit_type)
    print("\n=== %s ===" % title)
    print("      t [s]                date            a [m]            e           da [m]")

    # Java 对象不能用 Python 的 <= 比较，必须显式调用 compareTo
    sample_date = initial_date
    while sample_date.compareTo(final_date) <= 0:
        # propagate(date) 返回该时刻的 SpacecraftState。
        # 它是有状态的：第一次调用从 setInitialState 的时刻起积，之后每次
        # 都从"上一次算到的状态"接着积（往回传日期则重新从初始状态起积）。
        # 所以循环正好复现固定步长处理器看到的状态序列（分段会导致截断误差
        # 与一次积到底相差亚米级，本例约 0.5 m，属正常数值差异）。
        state = propagator.propagate(sample_date)
        # CARTESIAN 配置下状态里存的是 CartesianOrbit，
        # convertType 用同一组位置速度现算出开普勒根数，才能放在一起比较
        orbit = OrbitType.KEPLERIAN.convertType(state.getOrbit())
        t = sample_date.durationFrom(initial_date)
        print(f"{t:11.1f} {state.getDate()} {orbit.getA():14.3f} {orbit.getE():11.8f} {orbit.getA() - initial_orbit.getA():12.3f}")
        sample_date = sample_date.shiftedBy(sample_step)

    # 末状态：从最后一次采样时刻（600 s）继续积到 630 s，
    # 相当于处理器 finish() 回调时看到的末状态
    final_state = propagator.propagate(final_date)
    o = OrbitType.KEPLERIAN.convertType(final_state.getOrbit())
    print("  final: %s  a=%.3f m  e=%.8f  i=%.6f deg  raan=%.6f deg"
          % (final_state.getDate(), o.getA(), o.getE(),
             FastMath.toDegrees(o.getI()),
             FastMath.toDegrees(o.getRightAscensionOfAscendingNode())))

# 3. 结果解读
# - 与第 3 章对比：开普勒外推里 a、e 严格守恒，这里却逐点漂移几千至上万米，
#   这就是 HolmesFeatherstone 力模型（J2 及更高阶项）在起作用。
# - 10x10 与 2x0 的曲线几乎重合 → 这条大偏心率轨道在 630 s 弧段上的 a/e 变化
#   由 J2 主导，10x10 的高阶项贡献很小（练习 1）。
# - KEPLERIAN 与 CARTESIAN 结果一致（属积分容差量级）→ 积分变量只是数值实现
#   的选择，物理结果相同（练习 3）。
# - 已知小坑：CARTESIAN 配置打印的 raan = -99.017°，与 KEPLERIAN 的 260.983°
#   是同一角度——由位置速度反算根数时 Ω 会归算到 (-180°, 180°]，而根数型积分
#   保持连续值（0~360°）。比较两种配置时要先把角度归一化，别误判成"方向变了"。
#
# 练习 2（日月第三体引力）的力模型写法，需要长弧段（几天~几十天）才看得出长周期项：
#   from org.orekit.bodies import CelestialBodyFactory
#   from org.orekit.forces.gravity import ThirdBodyAttraction
#   propagator.addForceModel(ThirdBodyAttraction(CelestialBodyFactory.getSun()))
#   propagator.addForceModel(ThirdBodyAttraction(CelestialBodyFactory.getMoon()))
#
# 实际输出（节选）：
#   === 10x10 阶引力场 + KEPLERIAN 根数积分（官方配置） ===
#         t [s]                date            a [m]            e           da [m]
#           0.0  2004-01-01T23:30:00.000Z    24396159.000   0.72831215         0.000
#          60.0  2004-01-01T23:31:00.000Z    24395672.952   0.72830573      -486.048
#         120.0  2004-01-01T23:32:00.000Z    24394149.118   0.72828580     -2009.882
#         180.0  2004-01-01T23:33:00.000Z    24391676.585   0.72825352     -4482.415
#         ...
#     final: 2004-01-01T23:40:30.000Z  a=24359529.825 m  e=0.72783366  i=6.996697 deg
