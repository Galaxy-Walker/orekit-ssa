# 第 1 章 时间系统（Time）

对应官方教程：
- Java 源码：`orekit-tutorials/src/main/java/org/orekit/tutorials/time/Time1.java`
- 官方文档：`src/site/markdown/tutorials/time.md` → https://www.orekit.org/site-orekit-tutorials-13.1/tutorials/time.html

## 1.1 要解决的问题

Orekit 的时间系统是整个库的地基：任何轨道、坐标、外推都离不开 `AbsoluteDate`。
本章用官方 `Time1` 的例子演示：

- 通过**时间尺度**（TimeScale，如 UTC、TAI）创建日期；
- 日期之间的**加减**（`shiftedBy`）；
- 同一个日期在**不同时间尺度**下的表示；
- 环绕**闰秒**打印，观察 UTC 分钟出现第 61 秒的罕见现象。

> 关键概念：`AbsoluteDate` 是**绝对时刻**（内部用秒数 + 偏移表示，与 2000-01-01T12:00:00 TAI 对齐），
> 它本身与时间尺度无关；**时间尺度只是"显示/解析"的参照系**。

## 1.2 官方 Java 源码（`Time1.java`，节选核心部分）

```java
// get the UTC and TAI time scales
final TimeScale utc = TimeScalesFactory.getUTC();
final TimeScale tai = TimeScalesFactory.getTAI();

// create a start date from its calendar components in UTC time scale
final AbsoluteDate start = new AbsoluteDate(2005, 12, 31, 23, 59, 50, utc);

// create an end date 20 seconds after the start date
final double duration = 20.0;
final AbsoluteDate end = start.shiftedBy(duration);

// output header line
System.out.println("        UTC date                  TAI date");

// loop from start to end using a half second step
// (a leap second was introduced this day, so the display should show
//  the rare case of an UTC minute with more than 60 seconds)
final double step = 0.5;
for (AbsoluteDate date = start; date.compareTo(end) < 0; date = date.shiftedBy(step)) {
    System.out.println(date.toString(utc) + "   " + date.toString(tai));
}
```

## 1.3 Python 等价实现

```python
import orekit_jpype
orekit_jpype.initVM()
from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()

from org.orekit.time import TimeScalesFactory, AbsoluteDate

utc = TimeScalesFactory.getUTC()
tai = TimeScalesFactory.getTAI()

start = AbsoluteDate(2005, 12, 31, 23, 59, 50, utc)
duration = 20.0
end = start.shiftedBy(duration)

print("        UTC date                  TAI date")
step = 0.5
date = start
while date.compareTo(end) < 0:
    print(date.toString(utc) + "   " + date.toString(tai))
    date = date.shiftedBy(step)
```

## 1.4 运行结果（节选）

```
        UTC date                  TAI date
2005-12-31T23:59:50.000Z   2006-01-01T00:00:28.000Z
2005-12-31T23:59:50.500Z   2006-01-01T00:00:28.500Z
...
2005-12-31T23:59:59.000Z   2006-01-01T00:00:37.000Z
2005-12-31T23:59:59.500Z   2006-01-01T00:00:37.500Z
2005-12-31T23:59:60.000Z   2006-01-01T00:00:38.000Z   <- UTC 第 60 秒（闰秒）！
2005-12-31T23:59:60.500Z   2006-01-01T00:00:38.500Z   <- 第 61 秒
2006-01-01T00:00:00.000Z   2006-01-01T00:00:39.000Z
```

可以看到：2006 年前那一刻插入了闰秒，UTC 的 `23:59:60` 正常出现，
而 TAI 时间不受影响、均匀推进（UTC 与 TAI 的差值从 32s 跳到 33s）。

## 1.5 Java → Python 对照说明

| Java | Python | 说明 |
|------|--------|------|
| `TimeScalesFactory.getUTC()` | 完全一样 | 时间尺度是**单例**，获取而非构造 |
| `new AbsoluteDate(...)` | `AbsoluteDate(...)` | 构造参数逐字一致 |
| `date.shiftedBy(d)` | 完全一样 | 返回新日期（`AbsoluteDate` 不可变） |
| `date.compareTo(end) < 0` | 完全一样 | 比较用 `compareTo`（不能直接 `<` 比较对象） |
| `for (date=start; ...; date=...)` | `while` 循环 | 语法差异，无逻辑差异 |

## 1.6 延伸：日期 ↔ Python 原生类型转换

`orekit_jpype.pyhelpers` 提供了与 Python `datetime` 互转的工具：

```python
from orekit_jpype.pyhelpers import absolutedate_to_datetime, datetime_to_absolutedate
from datetime import datetime, timezone

dt = absolutedate_to_datetime(start)          # AbsoluteDate -> datetime (UTC)
back = datetime_to_absolutedate(datetime(2005, 12, 31, 23, 59, 50, tzinfo=timezone.utc))
```

> 提示：用 `shiftedBy()` / `durationFrom()` 做时间运算，尽量避免在 Python 侧手动转秒，
> 以免丢失精度（Orekit 内部用 `TimeOffset` 表达高精度秒）。

## 1.7 练习

1. 把 `Time1` 改为打印 GPS 时间尺度（`getGPS()`），观察它与 TAI 的固定偏移（19 s）。
2. 用 `getUT1()` 打印 UT1，观察与 UTC 的差异（极移影响，通常毫秒级）。
3. 用 `datetime_to_absolutedate` 读入 Python 时间戳，转成 `AbsoluteDate` 后 `shiftedBy` 再转回。
