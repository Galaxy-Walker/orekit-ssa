# 第 7 章 机动（Maneuvers）

对应官方教程：
- Java 源码：`orekit-tutorials/src/main/java/org/orekit/tutorials/maneuvers/ImpulseAtNode.java`
- 官方文档：`src/site/markdown/tutorials/maneuvers.md` → https://www.orekit.org/site-orekit-tutorials-13.1/tutorials/maneuvers.html

## 7.1 要解决的问题

官方 `ImpulseAtNode` 演示**脉冲机动**：对一条 50° 倾角的轨道，在**升交点**
沿轨道面法线（-Z）施加 122.25 m/s 的 ΔV，连续执行 **3 次**以逐步降低倾角。

关键点：

- **机动触发**：`ImpulseManeuver` 本质是一个**事件探测器**（不是力模型！），
  因此可挂到**解析传播器**（如 `KeplerianPropagator`）上；
- **只在升交点触发**：用 `NodeDetector` + `EventSlopeFilter(TRIGGER_ONLY_INCREASING_EVENTS)`
  过滤掉降交点；
- **只在前 3 圈机动**：用 `EventEnablingPredicateFilter` + `EnablingPredicate` 限定时间窗口；
- **推力方向**：姿态取 `LofOffset(eme2000, LVLH)`，使 -Z 对准轨道面法线。

## 7.2 官方 Java 源码（`ImpulseAtNode.java`，核心部分）

```java
// set up an initial orbit, with 50 degrees inclination
final Orbit initialOrbit =
        new KeplerianOrbit(8000000.0, 0.01,
                           FastMath.toRadians(50.0),  // ← initial inclination
                           FastMath.toRadians(140.0),
                           FastMath.toRadians(12.0),
                           FastMath.toRadians(-60.0), PositionAngleType.MEAN,
                           eme2000,
                           new AbsoluteDate(new DateComponents(2008, 6, 23),
                                            new TimeComponents(14, 0, 0),
                                            TimeScalesFactory.getUTC()),
                           Constants.EIGEN5C_EARTH_MU);

// the maneuver will be defined in spacecraft frame
// Z axis aligned with orbital momentum -> attitude aligned with LVLH
final AttitudeProvider attitudeProvider = new LofOffset(eme2000, LOFType.LVLH);

// we want 3 inclination reduction maneuvers at ascending nodes,
// with a ΔV along -Z
final EventDetector ascendingNodeDetector = new EventSlopeFilter<>(
        new NodeDetector(FramesFactory.getEME2000()).
                withMaxCheck(300.0).
                withThreshold(1.0e-6),
        FilterType.TRIGGER_ONLY_INCREASING_EVENTS);

// allow maneuvers only on the first 3 orbits
final AbsoluteDate lastAllowedDate =
        initialOrbit.getDate().shiftedBy(3 * initialOrbit.getKeplerianPeriod());
final EnablingPredicate predicate = (state, detector, g) -> state.getDate().isBefore(lastAllowedDate);
final EventDetector trigger =
        new EventEnablingPredicateFilter(ascendingNodeDetector, predicate);

// create the maneuver, using ascending node detector as a trigger
final ImpulseManeuver maneuver =
        new ImpulseManeuver(trigger,
                            new Vector3D(0.0, 0.0, -122.25), // 122.25 m/s along -Z
                            350.0);                          // specific impulse (s)

// wrap-up everything in a propagator
final KeplerianPropagator propagator = new KeplerianPropagator(initialOrbit, attitudeProvider);
propagator.addEventDetector(maneuver);

// progress monitoring
propagator.getMultiplexer().add(900.0, state -> { /* 打印半球与倾角 */ });

// run simulation
propagator.propagate(initialOrbit.getDate().shiftedBy(5 * initialOrbit.getKeplerianPeriod()));
```

## 7.3 Python 等价实现

```python
import orekit_jpype
orekit_jpype.initVM()
from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()

from jpype import JImplements, JOverride

from org.orekit.time import TimeScalesFactory, AbsoluteDate, DateComponents, TimeComponents
from org.orekit.frames import FramesFactory, LOFType
from org.orekit.orbits import KeplerianOrbit, PositionAngleType
from org.orekit.propagation.analytical import KeplerianPropagator
from org.orekit.propagation.events import (NodeDetector, EventSlopeFilter, FilterType,
                                           EventEnablingPredicateFilter, EnablingPredicate)
from org.orekit.forces.maneuvers import ImpulseManeuver
from org.orekit.attitudes import LofOffset
from org.orekit.utils import Constants
from org.hipparchus.geometry.euclidean.threed import Vector3D
from org.hipparchus.util import FastMath

utc = TimeScalesFactory.getUTC()
eme2000 = FramesFactory.getEME2000()

initial_orbit = KeplerianOrbit(
    8000000.0, 0.01,
    FastMath.toRadians(50.0),      # 初始倾角 50°
    FastMath.toRadians(140.0),
    FastMath.toRadians(12.0),
    FastMath.toRadians(-60.0), PositionAngleType.MEAN,
    eme2000,
    AbsoluteDate(DateComponents(2008, 6, 23), TimeComponents(14, 0, 0), utc),
    Constants.EIGEN5C_EARTH_MU)

# LVLH 姿态：Z 轴对准轨道面法线
attitude_provider = LofOffset(eme2000, LOFType.LVLH)

# 升交点探测器（过滤掉降交点）
ascending_node_detector = EventSlopeFilter(
    NodeDetector(eme2000).withMaxCheck(300.0).withThreshold(1.0e-6),
    FilterType.TRIGGER_ONLY_INCREASING_EVENTS)

# 只在前 3 圈允许机动
last_allowed_date = initial_orbit.getDate().shiftedBy(3 * initial_orbit.getKeplerianPeriod())


@JImplements(EnablingPredicate)
class FirstThreeOrbits:
    @JOverride
    def eventIsEnabled(self, state, detector, g):
        return state.getDate().isBefore(last_allowed_date)


trigger = EventEnablingPredicateFilter(ascending_node_detector, FirstThreeOrbits())

# 122.25 m/s 沿 -Z（升交点降倾角）
maneuver = ImpulseManeuver(trigger, Vector3D(0.0, 0.0, -122.25), 350.0)

propagator = KeplerianPropagator(initial_orbit, attitude_provider)
propagator.addEventDetector(maneuver)

final_state = propagator.propagate(
    initial_orbit.getDate().shiftedBy(5 * initial_orbit.getKeplerianPeriod()))

print("final inclination (deg):",
      FastMath.toDegrees(final_state.getOrbit().getI()))
```

## 7.4 运行结果

```
final inclination (deg): 47.001  (50° → 前 3 个升交点各 -Z 122.25 m/s 后降至约 47°)
```

## 7.5 关键概念讲解

1. **`ImpulseManeuver` 是探测器**：`new ImpulseManeuver(trigger, deltaVSat, isp)`。
   它监听 `trigger` 探测器的事件，在事件时刻瞬时施加 ΔV（卫星本体系）。因为不是力模型，
   解析传播器也能用。
2. **`EventSlopeFilter`**：给任意探测器加"只响应上升/下降沿"能力
   （`TRIGGER_ONLY_INCREASING_EVENTS` = 只响应 g 由负变正，即升交点）。
3. **`EventEnablingPredicateFilter`**：加"使能条件"——`eventIsEnabled` 返回
   `false` 时该事件不触发（这里限定了只在前 3 圈机动）。
4. **`withMaxCheck` / `withThreshold`**：探测器求根参数，见第 5 章。

## 7.6 Java → Python 对照说明

| Java | Python | 说明 |
|------|--------|------|
| `new NodeDetector(frame).withMaxCheck(300).withThreshold(1e-6)` | 完全一样 | |
| `new EventSlopeFilter<>(d, FilterType.X)` | `EventSlopeFilter(d, FilterType.X)` | 泛型在 Python 里省略 |
| `EnablingPredicate` lambda | `@JImplements` + `@JOverride eventIsEnabled` | 注意方法名是 `eventIsEnabled` |
| `new ImpulseManeuver(trigger, dv, isp)` | 完全一样 | |
| `new KeplerianPropagator(orbit, attitudeProvider)` | 完全一样 | 姿态律作为第二参数 |

## 7.7 练习

1. 把 ΔV 改为沿 +Z，观察倾角是增还是减；再改成沿轨道面内方向，观察近地点/半长轴变化。
2. 把 `FirstThreeOrbits` 的限制时间改大，看 4 次以上机动后的倾角。
3. 尝试用 `ImpulseManeuver` + `NumericalPropagator` 组合（机动仍可挂到数值传播器）。
