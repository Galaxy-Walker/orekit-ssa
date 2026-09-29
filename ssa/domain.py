"""与轨道计算后端无关的数据契约；统一使用 SI 单位和弧度。"""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite, pi
import re

type Vector3 = tuple[float, float, float]
type Matrix6 = tuple[tuple[float, ...], ...]

EARTH_MU = 3.986004415e14  # EIGEN-5C 地球引力常数，m³/s²


def require_finite(name: str, value: float, *, positive: bool = False) -> None:
    if not isfinite(value) or (positive and value <= 0):
        raise ValueError(f"{name} 必须是{'正' if positive else ''}有限数")


class InertialFrame(StrEnum):
    GCRF = "GCRF"
    EME2000 = "EME2000"


class AnomalyType(StrEnum):
    MEAN = "MEAN"
    ECCENTRIC = "ECCENTRIC"
    TRUE = "TRUE"


@dataclass(frozen=True)
class Epoch:
    """UTC 历元，格式 YYYY-MM-DDTHH:MM:SS[.fffffffff]Z。

    保留闰秒表达能力；真实日期和闰秒有效性由时间后端解析。
    不用字符串排序或 Python datetime 进行时间差运算。
    """

    utc: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z", self.utc):
            raise ValueError("历元必须是以 Z 结尾的 UTC ISO 时间，最多 9 位小数")


@dataclass(frozen=True)
class CartesianPV:
    position_m: Vector3
    velocity_m_s: Vector3

    def __post_init__(self) -> None:
        for name in ("position_m", "velocity_m_s"):
            values = tuple(getattr(self, name))
            if len(values) != 3 or not all(isfinite(v) for v in values):
                raise ValueError(f"{name} 必须包含三个有限数")
            object.__setattr__(self, name, values)
        if all(v == 0 for v in self.position_m):
            raise ValueError("地心位置不能为零向量")


@dataclass(frozen=True)
class KeplerianElements:
    """阶段 1 的根数输入限定为椭圆轨道；输出统一为笛卡尔状态。"""

    semi_major_axis_m: float
    eccentricity: float
    inclination_rad: float
    argument_of_perigee_rad: float
    raan_rad: float
    anomaly_rad: float
    anomaly_type: AnomalyType = AnomalyType.MEAN

    def __post_init__(self) -> None:
        require_finite("semi_major_axis_m", self.semi_major_axis_m, positive=True)
        if not 0 <= self.eccentricity < 1:
            raise ValueError("椭圆轨道偏心率必须满足 0 <= e < 1")
        if not 0 <= self.inclination_rad <= pi:
            raise ValueError("倾角必须位于 [0, π] 弧度")
        for name in ("argument_of_perigee_rad", "raan_rad", "anomaly_rad"):
            require_finite(name, getattr(self, name))
        object.__setattr__(self, "anomaly_type", AnomalyType(self.anomaly_type))


@dataclass(frozen=True)
class InitialConditions:
    spacecraft_id: str
    epoch: Epoch
    orbit: KeplerianElements | CartesianPV
    frame: InertialFrame = InertialFrame.GCRF
    mu_m3_s2: float = EARTH_MU
    mass_kg: float = 1000.0

    def __post_init__(self) -> None:
        if not self.spacecraft_id.strip():
            raise ValueError("spacecraft_id 不能为空")
        if not isinstance(self.orbit, (KeplerianElements, CartesianPV)):
            raise TypeError("orbit 必须是 KeplerianElements 或 CartesianPV")
        object.__setattr__(self, "frame", InertialFrame(self.frame))
        require_finite("mu_m3_s2", self.mu_m3_s2, positive=True)
        require_finite("mass_kg", self.mass_kg, positive=True)


@dataclass(frozen=True)
class OrbitState:
    spacecraft_id: str
    epoch: Epoch
    frame: InertialFrame
    pv: CartesianPV
    mass_kg: float


@dataclass(frozen=True)
class LinearizedState:
    """阶段 2 扩展契约：Φ = ∂x(t)/∂x(t₀)，x=[r(m), v(m/s)]。

    矩阵的两端均使用传播器初始状态的惯性系；不包含过程噪声。
    阶段 1 的传播器不生成此对象，也不假设未知协方差为零。
    """

    state: OrbitState
    transition_matrix: Matrix6

    def __post_init__(self) -> None:
        matrix = tuple(tuple(row) for row in self.transition_matrix)
        if len(matrix) != 6 or any(len(row) != 6 for row in matrix):
            raise ValueError("状态转移矩阵必须为 6×6")
        if not all(isfinite(v) for row in matrix for v in row):
            raise ValueError("状态转移矩阵必须只包含有限数")
        object.__setattr__(self, "transition_matrix", matrix)
