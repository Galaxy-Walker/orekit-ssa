# 第 3 章 轨道表示与开普勒外推（Orbits & Keplerian Propagation）

对应官方教程：
- Java 源码：`orekit-tutorials/src/main/java/org/orekit/tutorials/propagation/KeplerianPropagation.java`
- 官方文档：`src/site/markdown/tutorials/propagation.md` → https://www.orekit.org/site-orekit-tutorials-13.1/tutorials/propagation.html

## 3.1 要解决的问题

官方 `KeplerianPropagation` 演示：

- 用**轨道根数**（a, e, i, ω, Ω, M）定义一条轨道 → `KeplerianOrbit`；
- 用 `KeplerianPropagator` 做**二体/开普勒外推**；
- 按固定时间步长，逐个时刻取卫星状态（`SpacecraftState`）与轨道。

> 背景知识：Orekit 的 `Orbit` 抽象类有多个子类：
> `KeplerianOrbit`（经典根数）、`CartesianOrbit`（位置+速度，见第 2 章）、
> `CircularOrbit`、`EquinoctialOrbit`。它们之间可以 `OrbitType.X.convertType(orbit)` 互相转换。

## 3.2 官方 Java 源码（`KeplerianPropagation.java`，核心部分）

```java
final double a = 24396159;                 // semi major axis in meters
final double e = 0.72831215;               // eccentricity
final double i = FastMath.toRadians(7);    // inclination
final double omega = FastMath.toRadians(180); // perigee argument
final double raan = FastMath.toRadians(261);  // right ascension of ascending node
final double lM = 0;                       // mean anomaly

final Frame inertialFrame = FramesFactory.getEME2000();
final TimeScale utc = TimeScalesFactory.getUTC();
final AbsoluteDate initialDate = new AbsoluteDate(2004, 01, 01, 23, 30, 00.000, utc);
final double mu = 3.986004415e+14;

final Orbit initialOrbit = new KeplerianOrbit(a, e, i, omega, raan, lM, PositionAngleType.MEAN,
                                              inertialFrame, initialDate, mu);

final KeplerianPropagator kepler = new KeplerianPropagator(initialOrbit);

final double duration = 600.;
final AbsoluteDate finalDate = initialDate.shiftedBy(duration);
final double stepT = 60.;

int cpt = 1;
for (AbsoluteDate extrapDate = initialDate;
     extrapDate.compareTo(finalDate) <= 0;
     extrapDate = extrapDate.shiftedBy(stepT)) {

    final SpacecraftState currentState = kepler.propagate(extrapDate);
    System.out.format(Locale.US, "step %2d %s %s%n",
                      cpt++, currentState.getDate(), currentState.getOrbit());
}
```

## 3.3 Python 等价实现

```python
import orekit_jpype
orekit_jpype.initVM()
from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()

from org.orekit.time import TimeScalesFactory, AbsoluteDate
from org.orekit.frames import FramesFactory
from org.orekit.orbits import KeplerianOrbit, PositionAngleType
from org.orekit.propagation.analytical import KeplerianPropagator
from org.hipparchus.util import FastMath

a = 24396159.0
e = 0.72831215
i = FastMath.toRadians(7.0)
omega = FastMath.toRadians(180.0)
raan = FastMath.toRadians(261.0)
lM = 0.0

inertialFrame = FramesFactory.getEME2000()
utc = TimeScalesFactory.getUTC()
initialDate = AbsoluteDate(2004, 1, 1, 23, 30, 0.0, utc)
mu = 3.986004415e14

initialOrbit = KeplerianOrbit(a, e, i, omega, raan, lM, PositionAngleType.MEAN,
                              inertialFrame, initialDate, mu)
kepler = KeplerianPropagator(initialOrbit)

duration = 600.0
finalDate = initialDate.shiftedBy(duration)
stepT = 60.0

cpt = 1
extrapDate = initialDate
while extrapDate.compareTo(finalDate) <= 0:
    currentState = kepler.propagate(extrapDate)
    print("step %2d %s %s" % (cpt, currentState.getDate(), currentState.getOrbit()))
    cpt += 1
    extrapDate = extrapDate.shiftedBy(stepT)
```

## 3.4 更 OOP 的方式：固定步长处理器（Step Handler）

官方在数值外推教程里用到了"步进处理"模式。它把"每 60 秒打一行"封装成
一个处理器对象，交给传播器自动调用，比手动 `while` 循环更简洁。

**Java：**

```java
// Java：实现 OrekitFixedStepHandler 接口
private static class TutorialStepHandler implements OrekitFixedStepHandler {
    @Override
    public void init(final SpacecraftState s0, final AbsoluteDate t, final double step) {
        System.out.println("          date                a           e");
    }
    @Override
    public void handleStep(final SpacecraftState currentState) {
        final KeplerianOrbit o =
            (KeplerianOrbit) OrbitType.KEPLERIAN.convertType(currentState.getOrbit());
        System.out.format(Locale.US, "%s %12.3f %10.8f%n",
                          currentState.getDate(), o.getA(), o.getE());
    }
    @Override
    public void finish(final SpacecraftState finalState) {
        System.out.println("this was the last step");
    }
}

// 使用
kepler.getMultiplexer().add(60., new TutorialStepHandler());
kepler.propagate(initialDate.shiftedBy(630.));
```

**Python（`@JImplements` + `@JOverride`）：**

```python
from jpype import JImplements, JOverride
from org.orekit.propagation.sampling import OrekitFixedStepHandler
from org.orekit.orbits import OrbitType

@JImplements(OrekitFixedStepHandler)
class TutorialStepHandler:
    @JOverride
    def init(self, s0, t, step):
        print("          date                a           e")

    @JOverride
    def handleStep(self, currentState):
        o = OrbitType.KEPLERIAN.convertType(currentState.getOrbit())
        print("%s %12.3f %10.8f" % (currentState.getDate(), o.getA(), o.getE()))

    @JOverride
    def finish(self, finalState):
        print("this was the last step")

kepler.getMultiplexer().add(60.0, TutorialStepHandler())
kepler.propagate(initialDate.shiftedBy(630.0))
```

> ⚠️ **务必把接口里的所有方法（包括 default 的 `init`/`finish`）都实现**，
> 否则 JPype 代理在 Java 侧调用 default 方法时会抛 `NoSuchMethodError`。见第 0 章。

## 3.5 运行结果（节选）

开普勒外推下，半长轴 a 与偏心率 e 严格守恒：

```
          date                a           e
2004-01-01T23:30:00.000Z 24396159.000 0.72831215
2004-01-01T23:31:00.000Z 24396159.000 0.72831215
2004-01-01T23:32:00.000Z 24396159.000 0.72831215
...
2004-01-01T23:40:00.000Z 24396159.000 0.72831215
this was the last step
```

## 3.6 Java → Python 对照说明

| Java | Python | 说明 |
|------|--------|------|
| `new KeplerianOrbit(...)` | `KeplerianOrbit(...)` | 根数顺序：a, e, i, ω, Ω, ν, 角度类型 |
| `PositionAngleType.MEAN` | 完全一样 | 真近点角 / 偏近点角 / 平近点角 |
| `new KeplerianPropagator(orbit)` | 完全一样 | |
| `propagate(date)` | 完全一样 | 返回 `SpacecraftState` |
| `getOrbit()` | 完全一样 | 可再 `convertType` 转成 `KeplerianOrbit` |
| 接口实现 | `@JImplements` + `@JOverride` | 关键差异 |

## 3.7 练习

1. 把 `lM`（平近点角）从 0 改为 90，观察输出轨道的变化。
2. 用 `OrbitType.CARTESIAN.convertType(orbit)` 打印笛卡尔坐标（位置/速度）。
3. 用 `getMultiplexer().add(...)` 步进模式打印速度，理解步进处理 vs 手动循环。
