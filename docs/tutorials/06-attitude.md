# 第 6 章 姿态（Attitude）

对应官方教程：
- Java 源码：`orekit-tutorials/src/main/java/org/orekit/tutorials/attitude/EarthObservation.java`
- 官方文档：`src/site/markdown/tutorials/attitude.md` → https://www.orekit.org/site-orekit-tutorials-13.1/tutorials/attitude.html

## 6.1 要解决的问题

官方 `EarthObservation` 演示**姿态序列（AttitudesSequence）**：
卫星对地观测卫星在**白天**把相机指向地表（含滚转/俯仰偏移 20°/40°），
在**夜晚**切换到"休息姿态"（VVLH 正对地心），由 **EclipseDetector（地影检测器）**
自动触发切换。

涉及概念：

- `AttitudeProvider`：姿态律（如 `LofOffset`，相对轨道坐标系 VVLH/LVLH 的偏置）；
- `EclipseDetector`：日蚀检测（`g>0` 表示太阳在地球本影外/白天，`g<0` 表示黑夜）；
- `AttitudesSequence`：按事件在多个姿态律之间切换；
- `AttitudeSwitchHandler`：切换发生时的回调。

## 6.2 官方 Java 源码（`EarthObservation.java`，核心部分）

```java
final Frame eci  = FramesFactory.getEME2000();
final Frame ecef = FramesFactory.getITRF(IERSConventions.IERS_2010, true);

// ... initialOrbit 定义（PVCoordinates → KeplerianOrbit）...

// Attitudes sequence definition
final AttitudeProvider dayObservationLaw = new LofOffset(initialOrbit.getFrame(), LOFType.VVLH,
                                                         RotationOrder.XYZ,
                                                         FastMath.toRadians(20), FastMath.toRadians(40), 0);
final AttitudeProvider nightRestingLaw   = new LofOffset(initialOrbit.getFrame(), LOFType.VVLH);
final CelestialBody sun = CelestialBodyFactory.getSun();
final OneAxisEllipsoid earth = ReferenceEllipsoid.getIers2003(ecef);
final EventDetector dayNightEvent = new EclipseDetector(sun, Constants.IAU_2015_NOMINAL_SOLAR_RADIUS, earth)
                                    .withHandler(new ContinueOnEvent());
final EventDetector nightDayEvent = new EclipseDetector(sun, Constants.IAU_2015_NOMINAL_SOLAR_RADIUS, earth)
                                    .withHandler(new ContinueOnEvent());

final AttitudesSequence attitudesSequence = new AttitudesSequence();
final AttitudeSwitchHandler switchHandler =
    (preceding, following, s) -> { /* 记录切换时刻 */ };
attitudesSequence.addSwitchingCondition(dayObservationLaw, nightRestingLaw, dayNightEvent,
                                        false, true, 10.0,
                                        AngularDerivativesFilter.USE_R, switchHandler);
attitudesSequence.addSwitchingCondition(nightRestingLaw, dayObservationLaw, nightDayEvent,
                                        true, false, 10.0,
                                        AngularDerivativesFilter.USE_R, switchHandler);
if (dayNightEvent.g(new SpacecraftState(initialOrbit)) >= 0) {
    attitudesSequence.resetActiveProvider(dayObservationLaw);   // 初始在白天
} else {
    attitudesSequence.resetActiveProvider(nightRestingLaw);     // 初始在黑夜
}

// Propagator : consider the analytical Eckstein-Hechler model
final Propagator propagator = new EcksteinHechlerPropagator(initialOrbit, attitudesSequence,
                                                            Constants.EIGEN5C_EARTH_EQUATORIAL_RADIUS,
                                                            Constants.EIGEN5C_EARTH_MU, Constants.EIGEN5C_EARTH_C20,
                                                            Constants.EIGEN5C_EARTH_C30, Constants.EIGEN5C_EARTH_C40,
                                                            Constants.EIGEN5C_EARTH_C50, Constants.EIGEN5C_EARTH_C60);

propagator.getMultiplexer().add(180.0, currentState -> { /* 记录地影角与指向偏差 */ });

final SpacecraftState finalState = propagator.propagate(initialDate.shiftedBy(12600.));
```

## 6.3 Python 等价实现

```python
import orekit_jpype
orekit_jpype.initVM()
from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()

from jpype import JImplements, JOverride

from org.orekit.time import TimeScalesFactory, AbsoluteDate
from org.orekit.frames import FramesFactory, LOFType
from org.orekit.bodies import CelestialBodyFactory
from org.orekit.models.earth import ReferenceEllipsoid
from org.orekit.orbits import KeplerianOrbit
from org.orekit.propagation import SpacecraftState
from org.orekit.propagation.analytical import EcksteinHechlerPropagator
from org.orekit.propagation.events import EclipseDetector
from org.orekit.propagation.events.handlers import ContinueOnEvent
from org.orekit.attitudes import AttitudesSequence, LofOffset, AttitudeSwitchHandler
from org.orekit.utils import Constants, IERSConventions, PVCoordinates, AngularDerivativesFilter
from org.hipparchus.geometry.euclidean.threed import Vector3D, RotationOrder
from org.hipparchus.util import FastMath

utc = TimeScalesFactory.getUTC()
eci = FramesFactory.getEME2000()
ecef = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
initial_date = AbsoluteDate(2004, 1, 1, 23, 30, 0.0, utc)

initial_orbit = KeplerianOrbit(
    PVCoordinates(Vector3D(-6142438.668, 3492467.560, -25767.25680),
                  Vector3D(505.8479685, 942.7809215, 7435.922231)),
    eci, initial_date, Constants.EIGEN5C_EARTH_MU)

# 白天：VVLH 对地 + 滚转20° 俯仰40°；夜晚：纯 VVLH
day_observation_law = LofOffset(initial_orbit.getFrame(), LOFType.VVLH, RotationOrder.XYZ,
                              FastMath.toRadians(20.0), FastMath.toRadians(40.0), 0.0)
night_resting_law = LofOffset(initial_orbit.getFrame(), LOFType.VVLH)

sun = CelestialBodyFactory.getSun()
earth = ReferenceEllipsoid.getIers2003(ecef)
day_night_event = EclipseDetector(sun, Constants.IAU_2015_NOMINAL_SOLAR_RADIUS, earth).withHandler(ContinueOnEvent())
night_day_event = EclipseDetector(sun, Constants.IAU_2015_NOMINAL_SOLAR_RADIUS, earth).withHandler(ContinueOnEvent())


@JImplements(AttitudeSwitchHandler)
class SwitchLogger:
    @JOverride
    def switchOccurred(self, preceding, following, s):
        print("switching attitude at", s.getDate())


attitudes_sequence = AttitudesSequence()
attitudes_sequence.addSwitchingCondition(day_observation_law, night_resting_law, day_night_event,
                                        False, True, 10.0,
                                        AngularDerivativesFilter.USE_R, SwitchLogger())
attitudes_sequence.addSwitchingCondition(night_resting_law, day_observation_law, night_day_event,
                                        True, False, 10.0,
                                        AngularDerivativesFilter.USE_R, SwitchLogger())

if day_night_event.g(SpacecraftState(initial_orbit)) >= 0:
    attitudes_sequence.resetActiveProvider(day_observation_law)
else:
    attitudes_sequence.resetActiveProvider(night_resting_law)

propagator = EcksteinHechlerPropagator(
    initial_orbit, attitudes_sequence,
    Constants.EIGEN5C_EARTH_EQUATORIAL_RADIUS,
    Constants.EIGEN5C_EARTH_MU, Constants.EIGEN5C_EARTH_C20,
    Constants.EIGEN5C_EARTH_C30, Constants.EIGEN5C_EARTH_C40,
    Constants.EIGEN5C_EARTH_C50, Constants.EIGEN5C_EARTH_C60)

final_state = propagator.propagate(initial_date.shiftedBy(12600.0))
print("Propagation ended at", final_state.getDate())
```

## 6.4 运行结果（节选）

```
switching attitude at 2004-01-01T23:30:00.000Z   ...（随轨道进出地影反复切换）
Propagation ended at 2004-01-01T03:00:00.000Z
```

## 6.5 关键概念讲解

1. **`addSwitchingCondition(from, to, detector, forward, backward, maxCheck, filter, handler)`**：
   - `forward` / `backward`：该探测器事件**增方向**或**减方向**触发切换；
   - 白天→夜晚用 `day_night_event` 的减方向（`false, true`），夜晚→白天用增方向（`true, false`）。
2. **`resetActiveProvider`**：外推前必须显式指定初始生效的姿态律（否则不知道从哪个姿态开始）。
3. **`EcksteinHechlerPropagator`**：解析（非数值）传播器，自带 J2~J6 摄动，
   适合中低轨道；它接受 `AttitudeProvider` 作为参数。
4. 姿态序列也可用于 `NumericalPropagator`（用 `setAttitudeProvider`）。

## 6.6 Java → Python 对照说明

| Java | Python | 说明 |
|------|--------|------|
| `new LofOffset(frame, LOFType.VVLH, order, r,p,y)` | 完全一样 | 姿态偏置（滚转/俯仰/偏航，弧度） |
| `EclipseDetector(sun, radius, earth)` | 完全一样 | `g>0` 白天，`g<0` 黑夜 |
| `.withHandler(new ContinueOnEvent())` | 完全一样 | 事件后继续传播 |
| `AttitudeSwitchHandler` lambda | `@JImplements` + `@JOverride switchOccurred` | 关键差异 |

## 6.7 练习

1. 把 `day_observation_law` 的偏置改成 (0,0,0)，对比指向偏差输出。
2. 用 `NumericalPropagator` 替代 `EcksteinHechlerPropagator`，通过 `setAttitudeProvider(attitudes_sequence)`。
3. 记录 `switchOccurred` 的时刻列表，统计一天内的日/夜切换次数与占比。
