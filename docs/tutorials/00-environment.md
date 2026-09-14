# 第 0 章 环境准备

## 0.1 需要安装的东西

- **JDK 11+**：`orekit_jpype` 通过 JPype 启动 JVM，需要本机已安装 JDK（不是 JRE）。
- **Python 3.10+**（本项目要求 3.14）。
- **`orekit-jpype`** 与 **`orekitdata`**（Python 数据包，内含 IERS 参数、闰秒表、行星历表等）。

本项目的 `pyproject.toml` 已经声明了这两个依赖：

```toml
[project]
dependencies = [
    "orekit-jpype>=13.1.7.1",
    "orekitdata",
]

[tool.uv.sources]
orekitdata = { git = "https://gitlab.orekit.org/orekit/orekit-data.git" }
```

只需执行：

```bash
uv sync
```

## 0.2 与老版本的差异：`import orekit` 还是 `orekit_jpype`？

网上大量资料（以及 `orekit-python-wrapper` 的老 README）都写：

```python
import orekit
orekit.initVM()
```

这是 **旧版（≤12.x）** 的写法。**13.x 起** 顶层模块改名为 `orekit_jpype`：

```python
import orekit_jpype
orekit_jpype.initVM()
```

如果看到 `ModuleNotFoundError: No module named 'orekit'`，先检查版本和包名。

## 0.3 初始化模板（每个脚本开头都相同）

```python
import orekit_jpype
orekit_jpype.initVM()                    # 启动 JVM（一个进程只能启动一次）

from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()                      # 自动从已安装的 orekitdata pip 包加载数据
```

`setup_orekit_data()` 做了什么？它等价于 Java 里的这段配置（官方教程每个 `main` 都重复的样板代码）：

```java
// Java（官方教程固定样板）
final File orekitData = new File(System.getProperty("user.home"), "orekit-data");
final DataProvidersManager manager =
        DataContext.getDefault().getDataProvidersManager();
manager.addProvider(new DirectoryCrawler(orekitData));
```

> 差异：Java 教程要求你在用户主目录手动放置 `orekit-data` 文件夹；
> Python 端 `setup_orekit_data()` 默认直接从 pip 包读取，不用手动下载。

## 0.4 最关键的差异：Java 接口（interface）在 Python 里怎么实现

Java 教程里到处是 **lambda / 匿名类**，例如：

```java
// Java：匿名 EventHandler
new ElevationDetector(maxcheck, threshold, frame)
    .withHandler((s, d, increasing) -> { ... return Action.CONTINUE; });
```

**JPype 不支持** 把 Python 函数直接当 Java 接口用（不像 JavaScript/部分桥接层），
必须用 `@JImplements` + `@JOverride` 显式实现接口。

> **命名约定**：`@JOverride` 方法名（`init`、`eventOccurred`、`finish`、`resetState`、
> `handleStep`、`switchOccurred`、`eventIsEnabled` …）是 **Java 侧的方法名**，必须逐字照抄，
> **不能改成 snake_case**，否则 Java 侧调用时会抛 `NoSuchMethodError`。
> Python 侧的变量名、参数名则一律用 snake_case（PEP 8）。

通用模板：

```python
from jpype import JImplements, JOverride
from org.orekit.propagation.events.handlers import EventHandler

@JImplements(EventHandler)
class MyHandler:
    @JOverride
    def init(self, s0, t, detector):
        pass

    @JOverride
    def eventOccurred(self, s, detector, increasing):
        print("event at", s.getDate())
        return Action.CONTINUE   # 或 Action.STOP

    @JOverride
    def finish(self, s, detector):
        pass

    @JOverride
    def resetState(self, detector, s):
        return s

detector = ElevationDetector(...).withHandler(MyHandler())
```

### 重要细节：**default 方法也要一并实现**

Orekit 13.x 的很多接口把 `init`/`finish`/`resetState` 做成了 **default 方法**，
但 JPype 的代理对象在 Java 侧调用这些 default 方法时依然会转发到 Python，
如果 Python 类里没有对应方法，会报 `NoSuchMethodError` 一类的错。
**经验法则：接口里有几个方法（含 default），Python 里就全实现一遍。**

常用接口及其方法清单：

| Java 接口 | 必须实现的方法 |
|-----------|----------------|
| `OrekitFixedStepHandler` | `init(s0, t, step)`, `handleStep(state)`, `finish(state)` |
| `EventHandler` | `init(s0, t, detector)`, `eventOccurred(s, detector, increasing)`, `finish(s, detector)`, `resetState(detector, s)` |
| `AttitudeSwitchHandler` | `switchOccurred(preceding, following, s)` |
| `EnablingPredicate` | `eventIsEnabled(state, detector, g)` |

## 0.5 其他常见坑

1. **角度单位**：Orekit 所有角度 API 使用**弧度**。Java 教程里到处是 `FastMath.toRadians(7)`，
   Python 里同样用 `FastMath.toRadians(...)` 或 `math.radians(...)`。
2. **布尔值**：`true/false` → `True/False`。
3. **数字字面量**：`3.986004415e+14` → `3.986004415e14`；整数要加 `.0` 表示 double
   （如 `8000000.0`），否则可能匹配到错误的重载方法。
4. **静态方法/常量**：`Vector3D.dotProduct(a, b)`、`Constants.EIGEN5C_EARTH_MU` 原样可用。
5. **不要重复 `initVM()`**：一个 JVM 生命周期内只能调用一次。
6. **`PositionAngleType.MEAN` 这类枚举**：直接 `PositionAngleType.MEAN`。

## 0.6 验证安装

```python
import orekit_jpype
orekit_jpype.initVM()
from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()

from org.orekit.time import TimeScalesFactory, AbsoluteDate
utc = TimeScalesFactory.getUTC()
print(AbsoluteDate(2005, 12, 31, 23, 59, 50, utc))   # 2005-12-31T23:59:50.000Z
```

正常打印出日期即安装成功，可以进入 [第 1 章](./01-time.md)。
