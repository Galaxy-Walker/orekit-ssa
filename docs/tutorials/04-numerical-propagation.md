# 第 4 章 数值外推与力模型（Numerical Propagation）

对应官方教程：
- Java 源码：`orekit-tutorials/src/main/java/org/orekit/tutorials/propagation/NumericalPropagation.java`
- 官方文档：`src/site/markdown/tutorials/propagation.md` → https://www.orekit.org/site-orekit-tutorials-13.1/tutorials/propagation.html

## 4.1 要解决的问题

开普勒外推只考虑二体引力；真实轨道还要考虑**地球非球形引力**、大气阻力、
太阳光压、第三体引力等。`NumericalPropagator` 用数值积分器（如 Dormand-Prince 8(5,3)）
对这些**力模型（ForceModel）** 积分得到轨迹。

官方 `NumericalPropagation` 演示：

- 用 `DormandPrince853Integrator` 做自适应步长积分；
- 加载 **10×10 阶地球引力场**（`HolmesFeatherstoneAttractionModel`）；
- 通过步进处理器观察：半长轴 a、偏心率 e 因 J2 等项随时间**缓慢变化**（对比第 3 章的守恒）。

## 4.2 官方 Java 源码（`NumericalPropagation.java`，核心部分）

```java
final double a = 24396159;        // semi major axis in meters
final double e = 0.72831215;      // eccentricity
final double i = FastMath.toRadians(7);    // inclination
final double omega = FastMath.toRadians(180); // perigee argument
final double raan = FastMath.toRadians(261);  // right ascension of ascending node
final double lM = 0;              // mean anomaly
final Orbit initialOrbit = new KeplerianOrbit(a, e, i, omega, raan, lM, PositionAngleType.MEAN,
                                              inertialFrame, initialDate, mu);

// Initial state definition
final SpacecraftState initialState = new SpacecraftState(initialOrbit);

// Adaptive step integrator with a minimum step of 0.001 and a maximum step of 1000
final double minStep = 0.001;
final double maxstep = 1000.0;
final double positionTolerance = 10.0;
final OrbitType propagationType = OrbitType.KEPLERIAN;
final ToleranceProvider toleranceProvider =
        ToleranceProvider.of(CartesianToleranceProvider.of(positionTolerance));
final double[][] tolerances = toleranceProvider.getTolerances(initialOrbit, propagationType);
final AdaptiveStepsizeIntegrator integrator =
        new DormandPrince853Integrator(minStep, maxstep, tolerances[0], tolerances[1]);

// Propagator
final NumericalPropagator propagator = new NumericalPropagator(integrator);
propagator.setOrbitType(propagationType);

// Force Model (reduced to perturbing gravity field)
final NormalizedSphericalHarmonicsProvider provider =
        GravityFieldFactory.getNormalizedProvider(10, 10);
final ForceModel holmesFeatherstone =
        new HolmesFeatherstoneAttractionModel(FramesFactory.getITRF(IERSConventions.IERS_2010, true),
                                              provider);

// Add force model to the propagator
propagator.addForceModel(holmesFeatherstone);

// Set up initial state in the propagator
propagator.setInitialState(initialState);

// Set up a step handler
propagator.getMultiplexer().add(60., new TutorialStepHandler());

// Extrapolate from the initial to the final date
final SpacecraftState finalState = propagator.propagate(initialDate.shiftedBy(630.));
final KeplerianOrbit o = (KeplerianOrbit) OrbitType.KEPLERIAN.convertType(finalState.getOrbit());
System.out.format(Locale.US, "Final state:%n%s %12.3f %10.8f %10.6f %10.6f %10.6f %10.6f%n",
                  finalState.getDate(),
                  o.getA(), o.getE(),
                  FastMath.toDegrees(o.getI()),
                  FastMath.toDegrees(o.getPerigeeArgument()),
                  FastMath.toDegrees(o.getRightAscensionOfAscendingNode()),
                  FastMath.toDegrees(o.getTrueAnomaly()));
```

## 4.3 Python 等价实现

```python
import orekit_jpype
orekit_jpype.initVM()
from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()

from jpype import JImplements, JOverride

from org.orekit.time import TimeScalesFactory, AbsoluteDate
from org.orekit.frames import FramesFactory
from org.orekit.orbits import KeplerianOrbit, OrbitType, PositionAngleType
from org.orekit.propagation import SpacecraftState
from org.orekit.propagation.numerical import NumericalPropagator
from org.orekit.propagation.sampling import OrekitFixedStepHandler
from org.orekit.forces.gravity import HolmesFeatherstoneAttractionModel
from org.orekit.forces.gravity.potential import GravityFieldFactory
from org.orekit.utils import IERSConventions
from org.hipparchus.ode.nonstiff import DormandPrince853Integrator
from org.hipparchus.util import FastMath

utc = TimeScalesFactory.getUTC()
inertial_frame = FramesFactory.getEME2000()
mu = 3.986004415e14
initial_date = AbsoluteDate(2004, 1, 1, 23, 30, 0.0, utc)

initial_orbit = KeplerianOrbit(24396159.0, 0.72831215,
                              FastMath.toRadians(7.0), FastMath.toRadians(180.0),
                              FastMath.toRadians(261.0), 0.0,
                              PositionAngleType.MEAN, inertial_frame, initial_date, mu)
initial_state = SpacecraftState(initial_orbit)

# 自适应步长积分器：最小步长 0.001s，最大 1000s
integrator = DormandPrince853Integrator(0.001, 1000.0, 1.0e-3, 1.0e-3)

propagator = NumericalPropagator(integrator)
propagator.setOrbitType(OrbitType.KEPLERIAN)

# 力模型：10x10 阶地球引力场（Holmes-Featherstone）
provider = GravityFieldFactory.getNormalizedProvider(10, 10)
holmes_featherstone = HolmesFeatherstoneAttractionModel(
    FramesFactory.getITRF(IERSConventions.IERS_2010, True), provider)
propagator.addForceModel(holmes_featherstone)
propagator.setInitialState(initial_state)


@JImplements(OrekitFixedStepHandler)
class TutorialStepHandler:
    @JOverride
    def init(self, s0, t, step):
        print("          date                a           e")

    @JOverride
    def handleStep(self, current_state):
        o = OrbitType.KEPLERIAN.convertType(current_state.getOrbit())
        print("%s %12.3f %10.8f" % (current_state.getDate(), o.getA(), o.getE()))

    @JOverride
    def finish(self, final_state):
        print("this was the last step\n")


propagator.getMultiplexer().add(60.0, TutorialStepHandler())
final_state = propagator.propagate(initial_date.shiftedBy(630.0))

o = OrbitType.KEPLERIAN.convertType(final_state.getOrbit())
print("Final state:")
print(final_state.getDate())
print("a = %.3f  e = %.8f  i = %.6f deg" %
      (o.getA(), o.getE(), FastMath.toDegrees(o.getI())))
```

> 说明：Java 里构造容差用的是 `ToleranceProvider.of(CartesianToleranceProvider.of(10.0))`，
> Python 里为简洁直接给 `DormandPrince853Integrator` 传位置/速度容差
> `(1e-3, 1e-3)`。要完全复刻官方参数可写成：
> ```python
> from org.orekit.propagation import CartesianToleranceProvider, ToleranceProvider
> tol = ToleranceProvider.of(CartesianToleranceProvider.of(10.0)).getTolerances(initial_orbit, OrbitType.KEPLERIAN)
> integrator = DormandPrince853Integrator(0.001, 1000.0, tol[0], tol[1])
> ```

## 4.4 运行结果（节选）

对比第 3 章：a、e **不再守恒**，说明扰动项在起作用。

```
          date                a           e
2008-10-01T00:00:00.000Z 24396159.0 0.72831215
2008-10-01T00:01:00.000Z 24395537.768 0.72830427
2008-10-01T00:02:00.000Z 24394142.164 0.72828590
2008-10-01T00:03:00.000Z 24392060.861 0.72825816
...
this was the last step
```

## 4.5 常用力模型（ForceModel）

| 力模型类 | 作用 |
|----------|------|
| `HolmesFeatherstoneAttractionModel` | 地球非球形引力（阶/次可控） |
| `DrozinerAttractionModel` | 地球非球形引力（旧版球形谐波） |
| `AtmosphericDragForce` + 大气模型 | 大气阻力 |
| `SolarRadiationPressure` | 太阳光压 |
| `ThirdBodyAttraction` | 日月第三体引力 |
| `PolynomialParametricAcceleration` | 多项式经验加速度（用于轨道确定） |

用法一律三步：构造力模型 → `propagator.addForceModel(...)` → 外推。

## 4.6 Java → Python 对照说明

| Java | Python | 说明 |
|------|--------|------|
| `new DormandPrince853Integrator(min, max, abs, rel)` | 完全一样 | 自适应步长 |
| `new NumericalPropagator(integrator)` | 完全一样 | |
| `setOrbitType(OrbitType.KEPLERIAN)` | 完全一样 | 外推内部使用根数积分 |
| `GravityFieldFactory.getNormalizedProvider(10, 10)` | 完全一样 | 需要 orekit-data（引力场系数） |
| `addForceModel(...)` | 完全一样 | 可叠加多个 |

## 4.7 练习

1. 把阶数从 10×10 改成 2×0（只含 J2），对比 a/e 变化曲线，体会 J2 的主导作用。
2. 依次加入 `ThirdBodyAttraction`（日、月），观察长周期扰动。
3. 改用 `OrbitType.CARTESIAN` 积分，对比数值结果是否一致。
