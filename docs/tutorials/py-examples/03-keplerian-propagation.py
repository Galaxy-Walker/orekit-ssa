# 0. 启动 JVM 并加载 Orekit 数据（时间尺度、EOP、闰秒等）
import orekit_jpype as orekit
orekit.initVM()

from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()

from jpype import JImplements, JOverride
from org.hipparchus.util import FastMath
from org.orekit.frames import FramesFactory
from org.orekit.orbits import KeplerianOrbit, OrbitType, PositionAngleType
from org.orekit.propagation.analytical import KeplerianPropagator
from org.orekit.propagation.sampling import OrekitFixedStepHandler
from org.orekit.time import AbsoluteDate, TimeScalesFactory


# 1. 用经典轨道根数定义初始轨道
sma = 24396159.0  # 半长轴 a [m]
ecc = 0.72831215  # 偏心率 e [-]
inc = FastMath.toRadians(7.0)  # 倾角 i [rad]
pa = FastMath.toRadians(180.0)  # 近地点幅角 ω [rad]
raan = FastMath.toRadians(261.0)  # 升交点赤经 Ω [rad]
mean_anomaly = 0.0  # 平近点角 M [rad]（官方 Java 教程里叫 lM）

utc = TimeScalesFactory.getUTC()
initial_date = AbsoluteDate(2004, 1, 1, 23, 30, 0.0, utc)

mu = 3.986004415e14  # 地球引力常数 GM [m^3/s^2]
# 惯性参考系：EME2000（J2000 平赤道平春分点），轨道根数就定义在这个系里
inertial_frame = FramesFactory.getEME2000()

# PositionAngleType.MEAN 表示最后一个角度是"平近点角"（还有 ECCENTRIC/TRUE 可选）
initial_orbit = KeplerianOrbit(
    sma, ecc, inc, pa, raan, mean_anomaly,
    PositionAngleType.MEAN, inertial_frame, initial_date, mu,
)
print("初始轨道：%s" % initial_orbit)

# 2. 开普勒传播器 + 手动循环采样（手动复刻第 3 节处理器的行为）
# KeplerianPropagator 只做二体解析外推，无摄动
# 因此 a、e、i、Ω、ω 严格守恒，只有平近点角 M 随时间线性增长（n = sqrt(mu/a^3)）。
kepler = KeplerianPropagator(initial_orbit)

# 外推时长取 630 s（与第 3 节一致）：采样点只落在 60 s 的整数倍上，
# 最后一个是 600 s；600→630 s 的末段没有采样点，对应处理器的 finish 回调，
# 这里在循环结束后手动打印一行来对齐。
duration = 630.0  # 外推时长 [s]
final_date = initial_date.shiftedBy(duration)
step_t = 60.0  # 采样步长 [s]

print("\n=== 2. 手动 while 循环（每 %.0f s 一个状态，输出与第 3 节一致）===" % step_t)
count = 1
extrap_date = initial_date
# Java 对象不能用 Python 的 < / <= 比较，必须显式调用 compareTo
while extrap_date.compareTo(final_date) <= 0:
    # propagate(date) 内部用二体解析式直接算出该时刻的状态，
    # 与"从上一时刻继续积分"不同：每次调用都从历元重新计算，结果与调用顺序无关。
    # 返回的 SpacecraftState = 时刻 + 轨道 + （可选）质量、姿态、附加数据
    current_state = kepler.propagate(extrap_date)
    # getOrbit() 返回 KeplerianOrbit（本例传播器保持 KEPLERIAN 类型），
    # toString 输出根数形式：a, e, i, ω, Ω, ν(真近点角) 等
    print("step %2d %s %s" % (count, current_state.getDate(), current_state.getOrbit()))
    count += 1
    extrap_date = extrap_date.shiftedBy(step_t)
# 循环最后一次取到 600 s（23:40），630 s 的末状态不采样，对应处理器的 finish
print("this was the last step")


# 5. 预期输出（节选）
# 初始轨道：Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 0.0;}

# === 2. 手动 while 循环 ===
# step  1 2004-01-01T23:30:00.000Z Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 0.0;}
# step  2 2004-01-01T23:31:00.000Z Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 5.281383633573694;}
# step  3 2004-01-01T23:32:00.000Z Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 10.525261309411585;}
# step  4 2004-01-01T23:33:00.000Z Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 15.695876839823306;}
# step  5 2004-01-01T23:34:00.000Z Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 20.76077035517381;}
# step  6 2004-01-01T23:35:00.000Z Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 25.691961427063767;}
# step  7 2004-01-01T23:36:00.000Z Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 30.466680460539763;}
# step  8 2004-01-01T23:37:00.000Z Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 35.06763907945756;}
# step  9 2004-01-01T23:38:00.000Z Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 39.48289615024968;}
# step 10 2004-01-01T23:39:00.000Z Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 43.70541689946282;}
# step 11 2004-01-01T23:40:00.000Z Keplerian parameters: {a: 2.4396159E7; e: 0.72831215; i: 7.0; pa: 180.0; raan: 261.0; v: 47.732436294590705;}
# this was the last step
