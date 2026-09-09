"""Keplerian propagation 示例（移植自 CS-SI/Orekit README）。

orekit-jpype 版注意事项：
- v13 的 Python 模块名是 orekit_jpype，不再是 orekit
- 所有 org.* / java.* 的导入必须在 initVM() 之后
- orekitdata 是 pip 安装的命名空间包，需手动注册到 DataProvidersManager
"""

import os
import orekit_jpype as orekit
import orekitdata


def load_orekit_data() -> None:
    """注册 orekitdata 包自带的参考数据（EOP、闰秒、重力场等）。"""
    from java.io import File
    from org.orekit.data import DataContext, DirectoryCrawler

    root = os.path.abspath(orekitdata.__path__[0])
    DataContext.getDefault().getDataProvidersManager().addProvider(
        DirectoryCrawler(File(root))
    )


def main() -> None:
    # 1. 启动 JVM —— 之后才能导入 Java 包
    orekit.initVM()

    # 2. 构造开普勒轨道（以下导入需在 JVM 启动后）
    from org.hipparchus.util import FastMath
    from org.orekit.data import DataContext, DirectoryCrawler
    from org.orekit.frames import FramesFactory
    from org.orekit.orbits import KeplerianOrbit, PositionAngleType
    from org.orekit.propagation.analytical import KeplerianPropagator
    from org.orekit.time import AbsoluteDate, TimeScalesFactory
    from org.orekit.utils import Constants
    from java.io import File

    load_orekit_data()

    sma = 7000e3                              # 半长轴 [m]
    ecc = 0.001                               # 偏心率 [-]
    inc = FastMath.toRadians(15.0)            # 倾角 [rad]
    pa = FastMath.toRadians(30.0)             # 近地点幅角 [rad]
    raan = FastMath.toRadians(45.0)           # 升交点赤经 [rad]
    anomaly = FastMath.toRadians(60.0)        # 平近点角 [rad]

    position_angle_type = PositionAngleType.MEAN
    inertial_frame = FramesFactory.getGCRF()  # 地心惯性系
    date = AbsoluteDate(
        2002, 1, 1, 0, 0, 0, TimeScalesFactory.getUTC()
    )
    mu = Constants.EIGEN5C_EARTH_MU           # EIGEN-5C 地球引力常数

    orbit = KeplerianOrbit(
        sma, ecc, inc, pa, raan, anomaly,
        position_angle_type, inertial_frame, date, mu,
    )
    print(orbit)

    # 3. 创建开普勒传播器并传播一天
    propagator = KeplerianPropagator(orbit)

    target_date = date.shiftedBy(Constants.JULIAN_DAY)
    propagated_state = propagator.propagate(target_date)
    print(propagated_state.getOrbit())


if __name__ == "__main__":
    main()
