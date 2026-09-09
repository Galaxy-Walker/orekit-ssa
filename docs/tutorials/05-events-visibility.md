# 第 5 章 事件探测与地面站可见性（Events & Visibility）

对应官方教程：
- Java 源码：`orekit-tutorials/src/main/java/org/orekit/tutorials/propagation/VisibilityCheck.java`
- 官方文档：`src/site/markdown/tutorials/propagation.md` → https://www.orekit.org/site-orekit-tutorials-13.1/tutorials/propagation.html

> 本章是**观测规划**最相关的一章：如何让传播器自动寻找"卫星相对某地面站仰角
> 越过 5°"的时刻（上升/下降），并在事件发生时执行回调。

## 5.1 要解决的问题

给定一条轨道和一个地面站，求：卫星对该站的可见窗口。

Orekit 的事件机制：`EventDetector` 提供符号函数 `g(state)`（这里为 `仰角 - 5°`），
传播器在积分时**求根**找到 `g=0` 的时刻，并调用注册的 `EventHandler`。

`VisibilityCheck` 官方代码用到了两个关键封装：

- `ElevationDetector`：仰角探测器（相对某个 `TopocentricFrame`）；
- `withConstantElevation(5°)`：设定最小仰角（掩星/遮挡阈值）。

## 5.2 官方 Java 源码（`VisibilityCheck.java`，核心部分）

```java
// Propagator : consider a simple Keplerian motion (could be more elaborate)
final Propagator kepler = new KeplerianPropagator(initialOrbit);

// Earth and frame
final Frame ecef = FramesFactory.getITRF(IERSConventions.IERS_2010, true);
final BodyShape earth = ReferenceEllipsoid.getWgs84(ecef);

// Station
final double longitude = FastMath.toRadians(45.);
final double latitude  = FastMath.toRadians(25.);
final double altitude  = 0.;
final GeodeticPoint station1 = new GeodeticPoint(latitude, longitude, altitude);
final TopocentricFrame sta1Frame = new TopocentricFrame(earth, station1, "station1");

// Event definition
final double maxcheck  = 60.0;
final double threshold =  0.001;
final double elevation = FastMath.toRadians(5.0);
final EventDetector sta1Visi =
        new ElevationDetector(maxcheck, threshold, sta1Frame).
        withConstantElevation(elevation).
        withHandler((s, d, increasing) -> {
            System.out.println(" Visibility on " +
                               ((ElevationDetector) d).getTopocentricFrame().getName() +
                               (increasing ? " begins at " : " ends at ") +
                               s.getDate().toStringWithoutUtcOffset(utc, 3));
            return increasing ? Action.CONTINUE : Action.STOP;
        });

// Add event to be detected
kepler.addEventDetector(sta1Visi);

// Propagate from the initial date to the first raising or for the fixed duration
final SpacecraftState finalState = kepler.propagate(initialDate.shiftedBy(1500.));

System.out.println(" Final state duration from initial date (s) : " +
                   finalState.getDate().durationFrom(initialDate));
```

## 5.3 Python 等价实现

关键差异：Java 里的 lambda 处理器，Python 要用 `@JImplements(EventHandler)` 实现，
且 `init`/`finish`/`resetState` 这些 default 方法**也要一并实现**。

```python
import orekit_jpype
orekit_jpype.initVM()
from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()

from jpype import JImplements, JOverride

from org.orekit.time import TimeScalesFactory, AbsoluteDate
from org.orekit.frames import FramesFactory, TopocentricFrame
from org.orekit.bodies import GeodeticPoint
from org.orekit.models.earth import ReferenceEllipsoid
from org.orekit.orbits import KeplerianOrbit
from org.orekit.propagation.analytical import KeplerianPropagator
from org.orekit.propagation.events import ElevationDetector
from org.orekit.propagation.events.handlers import EventHandler
from org.orekit.utils import IERSConventions, PVCoordinates
from org.hipparchus.geometry.euclidean.threed import Vector3D
from org.hipparchus.ode.events import Action
from org.hipparchus.util import FastMath

utc = TimeScalesFactory.getUTC()
initialDate = AbsoluteDate(2004, 1, 1, 23, 30, 0.0, utc)
mu = 3.986004415e14
inertialFrame = FramesFactory.getEME2000()

pv = PVCoordinates(Vector3D(-6142438.668, 3492467.560, -25767.25680),
                   Vector3D(505.8479685, 942.7809215, 7435.922231))
initialOrbit = KeplerianOrbit(pv, inertialFrame, initialDate, mu)
kepler = KeplerianPropagator(initialOrbit)

ecef = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
earth = ReferenceEllipsoid.getWgs84(ecef)

station1 = GeodeticPoint(FastMath.toRadians(25.0), FastMath.toRadians(45.0), 0.0)
sta1Frame = TopocentricFrame(earth, station1, "station1")


@JImplements(EventHandler)
class VisibilityHandler:
    @JOverride
    def init(self, s0, t, detector):
        pass

    @JOverride
    def eventOccurred(self, s, detector, increasing):
        name = detector.getTopocentricFrame().getName()
        moment = s.getDate().toStringWithoutUtcOffset(utc, 3)
        if increasing:
            print(" Visibility on %s begins at %s" % (name, moment))
        else:
            print(" Visibility on %s ends at %s" % (name, moment))
        return Action.CONTINUE if increasing else Action.STOP

    @JOverride
    def finish(self, s, detector):
        pass

    @JOverride
    def resetState(self, detector, s):
        return s


sta1Visi = (ElevationDetector(60.0, 0.001, sta1Frame)
            .withConstantElevation(FastMath.toRadians(5.0))
            .withHandler(VisibilityHandler()))

kepler.addEventDetector(sta1Visi)

finalState = kepler.propagate(initialDate.shiftedBy(1500.0))
print(" Final state duration from initial date (s) :",
      finalState.getDate().durationFrom(initialDate))
```

## 5.4 运行结果

```
 Visibility on station1 begins at 2004-01-01T23:31:52.098
 Visibility on station1 ends at 2004-01-01T23:42:48.850
 Final state duration from initial date (s) : 768.850267132939
```

> 说明：传播从初始时刻开始，卫星先升到 5° 仰角以上（`begins`，`Action.CONTINUE` 继续），
> 最后降到 5° 以下（`ends`，`Action.STOP` 停止），因此 `propagate` 返回
> **该次可见窗口结束时刻**的状态，`duration = 768.85 s` 即为可见窗口长度。
> 用这种模式即可实现"求某次可观测窗口"的规划逻辑。

## 5.5 事件机制要点

1. **探测器（Detector）**：`g(state)` 符号函数 + 求根参数
   （`maxCheck` 最大检测步长、`threshold` 求根精度）。
2. **处理器（Handler）**：`eventOccurred` 返回 `Action` 控制传播走向：
   - `Action.CONTINUE`：继续；
   - `Action.STOP`：停止传播（此时 `propagate` 返回事件时刻的状态）；
   - `Action.RESET_STATE`：重置状态后继续。
3. **修饰器（Decorator）**：`withHandler(...)`、`withMaxCheck(...)`、
   `withThreshold(...)` 返回**新的探测器**（不可变风格），与 Python 链式调用一致。
4. 常用探测器：`ElevationDetector`、`NodeDetector`、`EclipseDetector`、
   `DateDetector`、`AltitudeDetector`、`ImpulseManeuver`（见第 7 章）等。

## 5.6 Java → Python 对照说明

| Java | Python | 说明 |
|------|--------|------|
| `new ElevationDetector(maxcheck, threshold, frame)` | 完全一样 | |
| `.withConstantElevation(elev)` | 完全一样 | 链式返回新探测器 |
| `.withHandler(lambda ...)` | `.withHandler(VisibilityHandler())` | **必须用 `@JImplements` 实现接口** |
| `(ElevationDetector) d` 强转 | 直接 `detector.getTopocentricFrame()` | 参数类型已是 `ElevationDetector` |
| `Action.CONTINUE / STOP` | 完全一样 | |

## 5.7 练习

1. 修改阈值仰角为 0° 和 30°，比较可见窗口长短。
2. 把初始时刻提前，让卫星先低于 5° 再升起，观察完整"升起→落下"两个事件。
3. 用 `kepler.propagate()` 的返回值配合 `Action.STOP`，实现"求首次可观测时刻"的规划逻辑。
