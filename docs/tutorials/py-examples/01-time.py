import orekit_jpype as orekit
# 启动 Java 虚拟机
orekit.initVM()

from orekit_jpype.pyhelpers import setup_orekit_data
# 从已经加载的 pip 包中加载 Orekit 数据
setup_orekit_data()

from org.orekit.time import TimeScalesFactory, AbsoluteDate

# 获取时间坐标
utc = TimeScalesFactory.getUTC()
tai = TimeScalesFactory.getTAI()

# 定义起始时间
# 注意：Java 构造函数重载太多，须用位置参数，禁用关键字参数，否则 JPype 会静默回退到无参构造 AbsoluteDate()，得到 2000-01-01T11:58:55.816）
start_time = AbsoluteDate(2005, 12, 31, 23, 59, 50.0, utc)
duration = 20.0
# 返回偏移后的时间
end_time = start_time.shiftedBy(duration)

print(f"start time:{start_time}\tend time:{end_time}")

step = 0.5

while start_time.compareTo(end_time) < 0:
    print(f"UTC date:{start_time.toString(utc)}\tTAI date:{start_time.toString(tai)}")
    start_time = start_time.shiftedBy(step)
