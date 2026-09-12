# Orekit 教程：Java 官方源码与 Python 对照

本系列教程基于 **Orekit 13.1** 官方教程（`orekit-tutorials` 仓库，GitLab: `https://gitlab.orekit.org/orekit/orekit-tutorials`），每一章都给出：

- **官方 Java 源码**（原样摘录，标注源文件路径）
- **Python 等价实现**（基于 `orekit_jpype`，本项目已验证可运行）

> 官方教程站点：https://www.orekit.org/site-orekit-tutorials-13.1/
> 官方教程源码（Java）：`src/main/java/org/orekit/tutorials/...`（GitLab main 分支）
> 官方教程文档（Markdown）：`src/site/markdown/tutorials/...`

## 为什么 Java 教程能直接在 Python 用

本项目用的是 **`orekit_jpype`**（Orekit 官方维护的 Python 封装，基于 JPype 启动 JVM）。
它**不是**一套新 API，而是把 Java 的 `org.orekit.*` 类原封不动地暴露给 Python。
因此：

- Java 类名、包名、方法名、常量在 Python 里**完全一致**；
- Java 教程代码只需做少量机械转换即可运行；
- 唯一的显著差异是 **Java 接口（interface）的实现方式**，见第 0 章。

## 学习路线（建议顺序）

| 章节 | 主题 | 官方 Java 源码 | 状态 |
|------|------|---------------|------|
| [00 环境准备](./00-environment.md) | 安装、初始化、接口实现 | — | ✅ |
| [01 时间系统](./01-time.md) | `AbsoluteDate` / 时间尺度 / 闰秒 | `time/Time1.java` | ✅ |
| [02 坐标系](./02-frames.md) | 惯性系/地固系/站心系、多普勒 | `frames/Frames1.java` | ✅ |
| [03 轨道与开普勒外推](./03-keplerian-propagation.md) | 轨道类型、步进处理 | `propagation/KeplerianPropagation.java` | ✅ |
| [04 数值外推](./04-numerical-propagation.md) | 积分器、力模型、`NumericalPropagator` | `propagation/NumericalPropagation.java` | ✅ |
| [05 事件与可见性](./05-events-visibility.md) | `EventDetector`、地面站可见性 | `propagation/VisibilityCheck.java` | ✅ |
| [06 姿态](./06-attitude.md) | 姿态律、日/夜切换 | `attitude/EarthObservation.java` | ✅ |
| [07 机动](./07-maneuvers.md) | 脉冲机动、节点降轨 | `maneuvers/ImpulseAtNode.java` | ✅ |
| [08 进阶专题](./08-advanced.md) | TLE / 轨道确定 / GNSS / CR3BP | 多文件 | ✅ |

## 快速开始（最小可运行片段）

```python
import orekit_jpype
orekit_jpype.initVM()                                    # 1. 启动 JVM
from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()                                      # 2. 加载 orekit-data（来自 pip 包）

from org.orekit.time import TimeScalesFactory, AbsoluteDate
from org.orekit.frames import FramesFactory
from org.orekit.orbits import KeplerianOrbit, PositionAngleType
from org.hipparchus.util import FastMath

utc  = TimeScalesFactory.getUTC()
date = AbsoluteDate(2004, 1, 1, 23, 30, 0.0, utc)
orbit = KeplerianOrbit(24396159.0, 0.72831215,
                       FastMath.toRadians(7.0), FastMath.toRadians(180.0),
                       FastMath.toRadians(261.0), 0.0,
                       PositionAngleType.MEAN, FramesFactory.getEME2000(), date,
                       3.986004415e14)
print("semi-major axis:", orbit.getA(), "m")
```

## 运行方式

本项目的依赖已写入 `pyproject.toml`（`orekit-jpype>=13.1.7.1` 与 `orekitdata`），
在项目根目录用 uv 运行：

```bash
uv run python docs/tutorials/py-examples/01-time.py
```

> **注意**：从 13.x 版本开始，导入模块名从 `orekit` 改成了 **`orekit_jpype`**（老资料里的 `import orekit` 已经过时）。

## Java → Python 对照速查表

| Java | Python |
|------|--------|
| `import org.orekit.time.*;` | `from org.orekit.time import ...` |
| `FastMath.toRadians(x)` | `FastMath.toRadians(x)`（或 `math.radians(x)`） |
| `new Vector3D(x, y, z)` | `Vector3D(x, y, z)` |
| `new AbsoluteDate(y, mo, d, h, mi, s, utc)` | `AbsoluteDate(y, mo, d, h, mi, s, utc)` |
| `DateComponents` / `TimeComponents` 分开构造 | 同左，直接传 |
| 接口 `interface I { ... }` | `@JImplements(I)` + `@JOverride`（见 00 章） |
| lambda / 匿名类 | `@JImplements` 具名类，或用 `@JImplement` 包装 |
| `boolean` 参数 `true` / `false` | `True` / `False` |
| 数组 `double[]` | `JArray('d')([...])`（少数场合需要） |
