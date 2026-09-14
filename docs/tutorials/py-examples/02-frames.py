# 0. 启动 JVM 与加载 Orekit 数据
import orekit_jpype as orekit
# 启动 Java 虚拟机
orekit.initVM()

from orekit_jpype.pyhelpers import setup_orekit_data
# 加载 Orekit 数据文件
setup_orekit_data()

from org.orekit.time import TimeScalesFactory, AbsoluteDate
from org.orekit.frames import FramesFactory, TopocentricFrame
from org.orekit.bodies import OneAxisEllipsoid, GeodeticPoint
from org.orekit.orbits import CartesianOrbit
from org.orekit.propagation.analytical import KeplerianPropagator
from org.orekit.utils import Constants, IERSConventions, PVCoordinates
from org.hipparchus.geometry.euclidean.threed import Vector3D
from org.hipparchus.util import FastMath


# 1. 时间、引力常数、惯性参考系
# 取 UTC 时间
utc = TimeScalesFactory.getUTC()
# 历元：2026-09-12 09:29:15 UTC
initial_date = AbsoluteDate(2026, 9, 12, 9, 29, 15.0, utc)
# 地球引力系数 μ = GM (m^3/s^2)。单位一律 SI（米、秒、弧度、千克）
mu = 3.986004415e14
# 惯性参考系：EME2000（J2000 平赤道平春分点）
inertial_frame = FramesFactory.getEME2000()

# 2. 初始状态与轨道
# 卫星初始状态：位置 (m)、速度 (m/s)
# 量级：|r|≈7066 km（约 690 km 高度）、|v|≈7512 m/s ≈ 该高度的圆轨道速度 → 近圆 LEO
pv_sat = PVCoordinates(
    Vector3D(-6142438.668, 3492467.560, -25767.25680),
    Vector3D(505.8479685, 942.7809215, 7435.922231)
)

# 用笛卡尔状态构造轨道：PVCoordinates + 参考系 + 历元 + μ
# 注意：CartesianOrbit 内部会由 (r, v, μ) 反解出 a、e、i、Ω、ω、M 等，供后续使用
# 初始化轨道
initial_orbit = CartesianOrbit(
    pv_sat,
    inertial_frame,
    initial_date,
    mu
)

# 开普勒传播器：只做二体解析传播（无 J2 摄动、无大气阻力、无三体）
kepler = KeplerianPropagator(initial_orbit)


# 3. 地球模型与地固系
# TIRF = 地心中间地球自转系（Terrestrial Intermediate Reference Frame）
# 已包含地球自转（以 UT1 计的 Earth Rotation Angle），但不含极移
earth_frame = FramesFactory.getTIRF(IERSConventions.IERS_2010, True)

# 地球形状模型：旋转椭球体
# 第三个参数 earth_frame 表示"该椭球体的本体坐标系"，即椭球随 TIRF 一起转动
earth = OneAxisEllipsoid(
    Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
    Constants.WGS84_EARTH_FLATTENING,
    earth_frame
)

# 测站大地坐标
# 高程 0.0 m 是相对椭球面（不是海拔/平均海平面）
# 这里对应 25°N, 45°E —— 阿拉伯半岛内陆
station = GeodeticPoint(
    FastMath.toRadians(25.0),   # 纬度
    FastMath.toRadians(45.0),   # 经度
    0.0                         # 高程
)

# 站心系（topocentric frame）：原点在测站，坐标轴约为 东(x) - 北(y) - 天顶(z)
#   - 它属于"地固"类坐标系（在 earth 的本体帧 TIRF 中静止），因此**随地球自转**；
#     所以卫星在该系中的速度 = 卫星相对测站的速度（已扣除地球自转牵连速度）
#   - 第三个参数只是站点名称，仅用于打印/调试
station_frame = TopocentricFrame(
    earth,
    station,
    "Station"
)

# 4. 时间循环：转换坐标系并计算多普勒速度
print("\ttime\tdoppler(m/s)")

# 结束时刻
final_date = initial_date.shiftedBy(6000.0)

extrap_date = initial_date

# 循环条件必须显式用 compareTo；Python 的 < / <= 对 Java 对象不可靠
# <= 0 表示"含端点"，故共 11 个采样点（0, 600, ..., 6000 s）
while extrap_date.compareTo(final_date) <= 0:
    # 1) 传播到 extrap_date，取该时刻在【惯性系 EME2000】中的位置与速度 (m, m/s)
    pv_inertial = kepler.propagate(extrap_date).getPVCoordinates()

    # 2) 坐标转换：把 PV 从 EME2000 转到站心系 station_frame，且在 extrap_date 这一刻
    #    getTransformTo(dest, date)：得到"把旧系(EME2000)中表达的坐标变换到新系(station_frame)"的变换
    #    变换里包含：
    #      - 旋转（EME2000 相对 TIRF 的姿态，含岁差/章动/自转，需 EOP）
    #      - 平移（减去测站在 EME2000 中的位置）
    #      - 速度合成（扣除测站速度，含地球自转 ω×r，赤道地表约 465 m/s）
    #    所以 transformPVCoordinates 得到的是卫星**相对测站**的位置与速度——正是多普勒所需
    pv_station = inertial_frame.getTransformTo(
        station_frame,
        extrap_date
    ).transformPVCoordinates(pv_inertial)

    # 3) 径向速度：range-rate = d|R|/dt = (R·V)/|R|
    #    物理含义：视线方向上的速度分量。为负表示接近测站，为正表示远离
    #    真实多普勒频移 Δf ≈ -f0 · range-rate / c（本例只算 range-rate，不作实际测量建模）
    #    注：这里没有考虑光行时、大气折射、相对论项；要"像真的观测"应使用
    #    org.orekit.estimation.measurements（第 5 章可见性之后的内容）
    doppler = (Vector3D.dotProduct(pv_station.getPosition(), pv_station.getVelocity()) / pv_station.getPosition().getNorm())

    # "%s" 会触发 JPype 代理对象的 str()，进而调用 Java 的 AbsoluteDate.toString()，
    # 输出 ISO-8601 形如 2026-09-12T09:29:15.000Z（末尾 Z 表示 UTC）
    print("%s\t%9.3f" % (extrap_date, doppler))

    # 步长 600 s（注意写 600.0，避免误命中 int 重载）
    extrap_date = extrap_date.shiftedBy(600.0)

# ---------------------------------------------------------------------------
# 5. 预期输出与结果解读
# ---------------------------------------------------------------------------
# 	time	doppler(m/s)
# 2026-09-12T09:29:15.000Z   -3679.623   <- 接近测站（range-rate < 0）
# 2026-09-12T09:39:15.000Z    2569.659
# 2026-09-12T09:49:15.000Z    4823.764   <- 过顶前后，远离速度最大
# 2026-09-12T09:59:15.000Z    4215.239
# 2026-09-12T10:09:15.000Z    2775.614
# 2026-09-12T10:19:15.000Z    1020.813
# 2026-09-12T10:29:15.000Z    -751.431
# 2026-09-12T10:39:15.000Z   -2274.576
# 2026-09-12T10:49:15.000Z   -3255.386
# 2026-09-12T10:59:15.000Z   -3266.430
# 2026-09-12T11:09:15.000Z   -1656.050   <- 再次接近（下一圈）
#
# 符号由负转正再转负 = 卫星先接近、过顶、再远离，符合 LEO 过境规律；
# 数值量级 ~±5 km/s 与 7.5 km/s 的轨道速度相符。
