# 第 8 章 进阶专题（TLE / 轨道确定 / GNSS / CR3BP）

前面 7 章覆盖了官方教程的**入门到进阶**主干。本章给出一条可自行扩展的路线图，
并给出一个**已在本项目验证**的 TLE 外推示例。其余专题按官方源码文件路径对照。

## 8.1 TLE 两行根数与 SGP4 外推

对应官方源码：`orekit-tutorials/src/main/java/org/orekit/tutorials/conversion/TLEConversion.java`

```python
import orekit_jpype
orekit_jpype.initVM()
from orekit_jpype.pyhelpers import setup_orekit_data
setup_orekit_data()

from org.orekit.propagation.analytical.tle import TLE, TLEPropagator
from org.hipparchus.util import FastMath

tle1 = '1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9053'
tle2 = '2 25544  51.6416  60.7864 0005103  63.0613 297.2264 15.49027807375022'
tle = TLE(tle1, tle2)

prop = TLEPropagator.selectExtrapolator(tle)
st = prop.propagate(tle.getDate().shiftedBy(3600.0))
print('epoch :', tle.getDate())          # 2024-01-01T12:00:00.000Z
print('a(km) :', st.getOrbit().getA() / 1000.0)
print('i(deg):', FastMath.toDegrees(st.getOrbit().getI()))
```

输出：

```
epoch : 2024-01-01T12:00:00.000Z
a(km) : 6796.590570119854
i(deg): 51.636
```

> 用真实两行根数（NORAD）直接建传播器，是做**观测预报**最常用的入口。

## 8.2 进阶专题路线图（官方源码清单）

所有文件位于 `orekit-tutorials/src/main/java/org/orekit/tutorials/`：

### 轨道转换
| 专题 | 源码 | 说明 |
|------|------|------|
| 根数 ↔ 笛卡尔互相转换 | `conversion/PropagatorConversion.java` | 不同 `OrbitType`/传播器间转换 |
| TLE 转换 | `conversion/TLEConversion.java` | 两行根数 ↔ Orekit 轨道 |

### 其他传播器
| 专题 | 源码 | 说明 |
|------|------|------|
| DSST 半解析外推 | `propagation/DSSTPropagation.java` | 长期/短周期摄动 |
| 星历模式 | `propagation/EphemerisMode.java` | 内存中存储整段轨迹 |
| 场传播（Field） | `propagation/FieldPropagation.java` | 自动微分 / 误差传播 |
| 梯度计算 | `propagation/GradientComputation.java` | 灵敏度分析 |
| 旋转/非惯性系传播 | `propagation/PropagationInRotatingFrame.java` | |
| 协方差传播 | `propagation/CovariancePropagation.java` | 状态不确定度演化 |
| 地面轨迹绘制 | `propagation/GroundTrack.java`、`utils/NdmUtils.java` | gnuplot 出图 |

### 轨道确定（estimation）
| 专题 | 源码 |
|------|------|
| 数值轨道确定（批最小二乘） | `estimation/NumericalOrbitDetermination.java` |
| 序贯批最小二乘 | `estimation/SequentialBatchLeastSquares.java` |
| 卡尔曼滤波 | `estimation/KalmanNumericalOrbitDetermination.java`、`ExtendedSemianalyticalKalmanFilter.java` |
| 激光测距定轨 | `estimation/LaserRangingOrbitDetermination.java` |
| 机动估计 | `estimation/ManeuverEstimation.java` |
| 定轨性能测试 | `estimation/performance/PerformanceTesting.java` |

### GNSS 与大地测量
| 专题 | 源码 |
|------|------|
| DOP 计算 | `gnss/DOPComputation.java` |
| RINEX 观测文件读取 | `gnss/RinexObservationFile.java` |
| 固体潮位移 | `models/TidalDisplacements.java` |

### 天体力学 / 相对论效应 / CR3BP
| 专题 | 源码 |
|------|------|
| 木星借力飞行 | `propagation/JupiterSwingBy.java` |
| 圆限制性三体问题 | `propagation/cr3bp/PropagationInCR3BP.java` |
| Halo 轨道 | `propagation/cr3bp/EarthMoonHaloOrbit.java` |
| 不变流形转移 | `propagation/cr3bp/ManifoldTransfer.java` |
| 日-地多重打靶 | `propagation/cr3bp/SunEarthMultipleShooter.java` |

### 配置与实用工具
| 专题 | 源码 |
|------|------|
| 多数据上下文 | `data/Context.java`（官方文档 `tutorials/data-context.md`） |
| YAML 描述轨道/观测模型 | `yaml/TutorialBatchLSEstimator.java` 等 |
| 轨道机动控制（间接法） | `control/indirect/FixedBoundarySingleShooting.java` |

## 8.3 官方文档 → 源码对照

| 官方站点页面 | 源码 Markdown |
|--------------|---------------|
| tutorials/time.html | `src/site/markdown/tutorials/time.md` |
| tutorials/frames.html | `src/site/markdown/tutorials/frames.md` |
| tutorials/propagation.html | `src/site/markdown/tutorials/propagation.md` |
| tutorials/attitude.html | `src/site/markdown/tutorials/attitude.md` |
| tutorials/maneuvers.html | `src/site/markdown/tutorials/maneuvers.md` |
| tutorials/data-context.html | `src/site/markdown/tutorials/data-context.md` |
| tutorials/integration-in-other-languages.html | `src/site/markdown/tutorials/integration-in-other-languages.md` |

## 8.4 下一步建议

针对你的 **航天器观测规划**（spacecraft-observation-planning）项目，推荐学习路径：

1. 精读第 5 章（可见性），扩展为**多地面站 × 多圈**的可见窗口批量计算；
2. 用 `GroundTrack` 或 `VisibilityCircle` 做覆盖/被遮挡分析；
3. 用 TLE（8.1）接入真实卫星（如 ISS/Starlink）做预报；
4. 需要精度时再切 `NumericalPropagator` 加力模型（第 4 章）；
5. 规划机动 → 第 7 章；定轨反演 → estimation 包。
