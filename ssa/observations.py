"""单站瞬时几何测距 / 距离率；不包含光行时、大气和钟差修正。"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from math import pi, sqrt
from random import Random
from typing import Protocol

from ssa.domain import CartesianPV, Epoch, InertialFrame, OrbitState, require_finite


@dataclass(frozen=True)
class GroundStation:
    station_id: str
    latitude_rad: float
    longitude_rad: float
    altitude_m: float = 0.0
    min_elevation_rad: float = 0.0

    def __post_init__(self) -> None:
        if not self.station_id.strip():
            raise ValueError("station_id 不能为空")
        if not -pi / 2 <= self.latitude_rad <= pi / 2:
            raise ValueError("纬度必须位于 [-π/2, π/2]")
        if not -pi <= self.longitude_rad <= pi:
            raise ValueError("经度必须位于 [-π, π]")
        if not 0 <= self.min_elevation_rad < pi / 2:
            raise ValueError("最小仰角必须位于 [0, π/2)")
        require_finite("altitude_m", self.altitude_m)


@dataclass(frozen=True)
class MeasurementNoise:
    range_sigma_m: float = 10.0
    range_rate_sigma_m_s: float = 0.1

    def __post_init__(self) -> None:
        require_finite("range_sigma_m", self.range_sigma_m, positive=True)
        require_finite("range_rate_sigma_m_s", self.range_rate_sigma_m_s, positive=True)


@dataclass(frozen=True)
class RangeRateObservation:
    spacecraft_id: str
    station_id: str
    epoch: Epoch
    range_m: float
    range_rate_m_s: float
    noise: MeasurementNoise = MeasurementNoise()

    def __post_init__(self) -> None:
        if not self.spacecraft_id.strip() or not self.station_id.strip():
            raise ValueError("观测必须携带卫星和测站标识")
        require_finite("range_m", self.range_m, positive=True)
        require_finite("range_rate_m_s", self.range_rate_m_s)


class StationGeometry(Protocol):
    @property
    def station(self) -> GroundStation: ...

    def pv_at(self, epoch: Epoch, frame: InertialFrame) -> CartesianPV: ...

    def elevation(self, state: OrbitState) -> float: ...


@dataclass(frozen=True)
class MeasurementPrediction:
    range_m: float
    range_rate_m_s: float
    jacobian: tuple[tuple[float, ...], tuple[float, ...]]


class GeometricRangeRateModel:
    def __init__(self, geometry: StationGeometry) -> None:
        self.geometry = geometry

    def predict(self, state: OrbitState) -> MeasurementPrediction:
        station = self.geometry.pv_at(state.epoch, state.frame)
        r = tuple(a - b for a, b in zip(state.pv.position_m, station.position_m))
        v = tuple(a - b for a, b in zip(state.pv.velocity_m_s, station.velocity_m_s))
        rho = sqrt(sum(x * x for x in r))
        if rho == 0:
            raise ValueError("卫星与测站位置重合，观测模型未定义")
        u = tuple(x / rho for x in r)
        rate = sum(a * b for a, b in zip(u, v))
        # 距离率对位置的导数必须保留视线方向变化项。
        rate_position = tuple((v[i] - rate * u[i]) / rho for i in range(3))
        return MeasurementPrediction(rho, rate, (u + (0.0, 0.0, 0.0), rate_position + u))

    def is_visible(self, state: OrbitState) -> bool:
        return self.geometry.elevation(state) >= self.geometry.station.min_elevation_rad


def simulate_observations(
    states: Iterable[OrbitState],
    model: GeometricRangeRateModel,
    *,
    noise: MeasurementNoise = MeasurementNoise(),
    seed: int = 42,
) -> Iterator[RangeRateObservation]:
    """仅在真值可见的采样点生成独立高斯噪声；正距离率表示远离。"""
    random = Random(seed)
    for state in states:
        if model.is_visible(state):
            prediction = model.predict(state)
            yield RangeRateObservation(
                state.spacecraft_id, model.geometry.station.station_id, state.epoch,
                prediction.range_m + random.gauss(0.0, noise.range_sigma_m),
                prediction.range_rate_m_s + random.gauss(0.0, noise.range_rate_sigma_m_s),
                noise,
            )
