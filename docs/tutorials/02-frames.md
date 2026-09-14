# 第 2 章 坐标系（Frames）

对应官方教程：
- Java 源码：`orekit-tutorials/src/main/java/org/orekit/tutorials/frames/Frames1.java`
- 官方文档：`src/site/markdown/tutorials/frames.md` → https://www.orekit.org/site-orekit-tutorials-13.1/tutorials/frames.html

## 2.1 要解决的问题

官方 `Frames1` 演示：计算卫星相对地面站的多普勒速度。
（注：精确的多普勒应使用测量生成功能，此处仅演示**坐标系转换**。）

涉及的概念与类：

- **惯性系** EME2000：`FramesFactory.getEME2000()`，轨道定义用；
- **地固系** ITRF：`FramesFactory.getITRF(IERS_2010, true)`，地球模型与站址用；
- **地球形状**：`OneAxisEllipsoid`（WGS84）；
- **站心系**：`TopocentricFrame`（以测站为原点，东-北-天）；
- **坐标转换**：`frame.getTransformTo(other, date).transformPVCoordinates(pv)`；
- 多普勒 ≈ `(R · V) / |R|`（星固系下视线方向的速度分量）。

## 2.2 官方 Java 源码（`Frames1.java`，核心部分）

```java
//  Initial state definition : date, orbit
final TimeScale utc = TimeScalesFactory.getUTC();
final AbsoluteDate initialDate = new AbsoluteDate(2008, 10, 01, 0, 0, 00.000, utc);
final double mu =  3.986004415e+14; // gravitation coefficient
final Frame inertialFrame = FramesFactory.getEME2000(); // inertial frame for orbit definition
final Vector3D posisat = new Vector3D(-6142438.668, 3492467.560, -25767.25680);
final Vector3D velosat = new Vector3D(505.8479685, 942.7809215, 7435.922231);
final PVCoordinates pvsat = new PVCoordinates(posisat, velosat);
final Orbit initialOrbit = new CartesianOrbit(pvsat, inertialFrame, initialDate, mu);

// Propagator : consider a simple Keplerian motion
final Propagator kepler = new KeplerianPropagator(initialOrbit);

// Earth and frame
final Frame earthFrame = FramesFactory.getITRF(IERSConventions.IERS_2010, true);
final BodyShape earth = new OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
                                             Constants.WGS84_EARTH_FLATTENING,
                                             earthFrame);

// Station
final double longitude = FastMath.toRadians(45.);
final double latitude  = FastMath.toRadians(25.);
final double altitude  = 0.;
final GeodeticPoint station = new GeodeticPoint(latitude, longitude, altitude);
final TopocentricFrame staF = new TopocentricFrame(earth, station, "station");

System.out.println("          time           doppler (m/s)");

// Stop date
final AbsoluteDate finalDate = initialDate.shiftedBy(6000);

// Loop
AbsoluteDate extrapDate = initialDate;
while (extrapDate.compareTo(finalDate) <= 0)  {
    // We can simply get the position and velocity of spacecraft in station frame at any time
    final PVCoordinates pvInert   = kepler.propagate(extrapDate).getPVCoordinates();
    final PVCoordinates pvStation = inertialFrame.getTransformTo(staF, extrapDate).transformPVCoordinates(pvInert);

    // And then calculate the Doppler signal
    final double doppler = Vector3D.dotProduct(pvStation.getPosition(), pvStation.getVelocity()) / pvStation.getPosition().getNorm();

    System.out.format(Locale.US, "%s   %9.3f%n", extrapDate, doppler);
    extrapDate = extrapDate.shiftedBy(600);
}
```

## 2.3 Python 等价实现

```python
import math

import orekit_jpype
orekit_jpype.initVM()
from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()

from org.orekit.time import TimeScalesFactory, AbsoluteDate
from org.orekit.frames import FramesFactory, TopocentricFrame
from org.orekit.bodies import OneAxisEllipsoid, GeodeticPoint
from org.orekit.orbits import CartesianOrbit
from org.orekit.propagation.analytical import KeplerianPropagator
from org.orekit.utils import Constants, IERSConventions, PVCoordinates
from org.hipparchus.geometry.euclidean.threed import Vector3D
from org.hipparchus.util import FastMath

utc = TimeScalesFactory.getUTC()
initial_date = AbsoluteDate(2008, 10, 1, 0, 0, 0.0, utc)
mu = 3.986004415e14
inertial_frame = FramesFactory.getEME2000()

pv_sat = PVCoordinates(Vector3D(-6142438.668, 3492467.560, -25767.25680),
                      Vector3D(505.8479685, 942.7809215, 7435.922231))
initial_orbit = CartesianOrbit(pv_sat, inertial_frame, initial_date, mu)
kepler = KeplerianPropagator(initial_orbit)

earth_frame = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
earth = OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
                         Constants.WGS84_EARTH_FLATTENING, earth_frame)

station = GeodeticPoint(FastMath.toRadians(25.0), FastMath.toRadians(45.0), 0.0)
station_frame = TopocentricFrame(earth, station, "station")

print("          time           doppler (m/s)")
final_date = initial_date.shiftedBy(6000.0)
extrap_date = initial_date
while extrap_date.compareTo(final_date) <= 0:
    pv_inertial = kepler.propagate(extrap_date).getPVCoordinates()
    pv_station = inertial_frame.getTransformTo(station_frame, extrap_date).transformPVCoordinates(pv_inertial)
    doppler = (Vector3D.dotProduct(pv_station.getPosition(), pv_station.getVelocity())
               / pv_station.getPosition().getNorm())
    print("%s   %9.3f" % (extrap_date, doppler))
    extrap_date = extrap_date.shiftedBy(600.0)
```

## 2.4 运行结果（节选）

```
          time           doppler (m/s)
2008-10-01T00:00:00.000Z   -5638.383
2008-10-01T00:10:00.000Z   -1700.424
2008-10-01T00:20:00.000Z    4155.941
...
2008-10-01T01:30:00.000Z   -3606.424
```

多普勒随卫星接近/远离测站由负变正，方向正确。

## 2.5 Java → Python 对照说明

| Java | Python | 说明 |
|------|--------|------|
| `new Vector3D(x,y,z)` | `Vector3D(x,y,z)` | 无 `new` |
| `new GeodeticPoint(lat, lon, alt)` | `GeodeticPoint(lat, lon, alt)` | 注意顺序是**纬度、经度、高程**（弧度、弧度、米） |
| `new TopocentricFrame(earth, p, name)` | 完全一样 | 第三个参数是站名 |
| `getTransformTo(frame, date)` | 完全一样 | 从"当前系"转到目标系 |
| `transformPVCoordinates(pv)` | 完全一样 | 同时转换位置与速度（含牵连速度） |
| `Vector3D.dotProduct(a, b)` | 完全一样 | 静态方法 |
| `System.out.format(...)` | `print("%s %9.3f" % ...)` | 语法差异 |

## 2.6 坐标转换的正确姿势

Orekit 的坐标转换是**时刻相关**的（ITRF 相对 EME2000 在旋转）：

```python
# 从 A 系转到 B 系，在 date 时刻
pv_in_b = a_frame.getTransformTo(b_frame, date).transformPVCoordinates(pv_in_a)

# 反向：用 getInverse()
pv_in_a = a_frame.getTransformTo(b_frame, date).getInverse().transformPVCoordinates(pv_in_b)
```

> 站心系给出 `getElevation()` / `getAzimuth()` / `getRange()`，这正是下一章
> "地面站可见性"（第 5 章）的基础。

## 2.7 练习

1. 改用 `TopocentricFrame` 的 `getElevation()`/`getAzimuth()` 输出卫星过顶时的仰角曲线。
2. 把轨道换成 `KeplerianOrbit`（半长轴/偏心率/倾角等根数定义），对比 `Frames1` 的笛卡尔定义。
3. 在 `TopocentricFrame` 上调用 `getHorizontalPosition()`，理解东-北-天坐标。
