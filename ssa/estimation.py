"""笛卡尔 EKF：NumPy 线性代数，动力学和测站通过端口注入。"""

from dataclasses import dataclass, replace

import numpy as np

from ssa.domain import CartesianPV, Epoch, InitialConditions, Matrix6, OrbitState, require_finite
from ssa.observations import GeometricRangeRateModel, RangeRateObservation
from ssa.propagation import EpochClock, LinearizedPropagatorFactory


def _matrix_tuple(matrix) -> Matrix6:
    return tuple(tuple(float(x) for x in row) for row in matrix)


@dataclass(frozen=True)
class StateEstimate:
    """同历元、同惯性系的 [r, v] 估计；协方差单位为对应状态单位的乘积。"""

    state: OrbitState
    covariance: Matrix6

    def __post_init__(self) -> None:
        p = np.asarray(self.covariance, dtype=float)
        if p.shape != (6, 6) or not np.isfinite(p).all() or np.any(np.diag(p) <= 0):
            raise ValueError("协方差必须为有限的 6×6 正定矩阵")
        # 按标准差归一化后检查，避免位置/速度单位尺度掩盖非对称或非正定。
        scale = np.sqrt(np.diag(p))
        correlation = p / np.outer(scale, scale)
        if not np.allclose(correlation, correlation.T, rtol=0.0, atol=1e-12):
            raise ValueError("协方差必须对称")
        try:
            np.linalg.cholesky(correlation)
        except np.linalg.LinAlgError as error:
            raise ValueError("协方差必须正定") from error
        object.__setattr__(self, "covariance", _matrix_tuple(p))


def diagonal_covariance(position_sigma_m: float, velocity_sigma_m_s: float) -> Matrix6:
    require_finite("position_sigma_m", position_sigma_m, positive=True)
    require_finite("velocity_sigma_m_s", velocity_sigma_m_s, positive=True)
    return _matrix_tuple(np.diag([position_sigma_m ** 2] * 3 + [velocity_sigma_m_s ** 2] * 3))


def white_acceleration_noise(dt_s: float, spectral_density_m2_s3: float) -> Matrix6:
    """惯性轴独立连续白加速度的局部匀速离散化；q 单位 m²/s³。"""
    for name, value in (("dt_s", dt_s), ("spectral_density_m2_s3", spectral_density_m2_s3)):
        require_finite(name, value)
        if value < 0:
            raise ValueError(f"{name} 不能为负")
    eye = np.eye(3) * spectral_density_m2_s3
    return _matrix_tuple(np.block([
        [eye * dt_s ** 3 / 3, eye * dt_s ** 2 / 2],
        [eye * dt_s ** 2 / 2, eye * dt_s],
    ]))


@dataclass(frozen=True)
class FilterUpdate:
    estimate: StateEstimate
    innovation: tuple[float, float]
    postfit_residual: tuple[float, float]
    normalized_innovation_squared: float


class ExtendedKalmanFilter:
    def __init__(
        self,
        initial: InitialConditions,
        covariance: Matrix6,
        factory: LinearizedPropagatorFactory,
        model: GeometricRangeRateModel,
        clock: EpochClock,
        *,
        acceleration_psd_m2_s3: float = 0.0,
    ) -> None:
        require_finite("acceleration_psd_m2_s3", acceleration_psd_m2_s3)
        if acceleration_psd_m2_s3 < 0:
            raise ValueError("过程噪声谱密度不能为负")
        self._initial = initial
        self._factory = factory
        self._model = model
        self._clock = clock
        self._q = acceleration_psd_m2_s3
        self._estimate = StateEstimate(factory.create_linearized(initial).initial_state, covariance)

    @property
    def estimate(self) -> StateEstimate:
        return self._estimate

    def _predict(self, epoch: Epoch) -> StateEstimate:
        current = self.estimate
        dt = self._clock.seconds_between(epoch, current.state.epoch)
        require_finite("预测时间差", dt)
        if dt < 0:
            raise ValueError("EKF 不接受早于当前估计的观测或预测历元")
        if dt == 0:
            return current
        initial = replace(
            self._initial, epoch=current.state.epoch, orbit=current.state.pv,
            mass_kg=current.state.mass_kg,
        )
        propagated = self._factory.create_linearized(initial).propagate_with_transition(epoch)
        phi = np.asarray(propagated.transition_matrix)
        p = phi @ np.asarray(current.covariance) @ phi.T
        p += np.asarray(white_acceleration_noise(dt, self._q))
        return StateEstimate(propagated.state, _matrix_tuple((p + p.T) / 2))

    def predict_to(self, epoch: Epoch) -> StateEstimate:
        """无观测时只推进状态和协方差。"""
        self._estimate = self._predict(epoch)
        return self.estimate

    def process(self, observation: RangeRateObservation) -> FilterUpdate:
        if observation.spacecraft_id != self.estimate.state.spacecraft_id:
            raise ValueError("观测卫星与估计状态不匹配")
        if observation.station_id != self._model.geometry.station.station_id:
            raise ValueError("观测测站与观测模型不匹配")
        predicted = self._predict(observation.epoch)
        measurement = self._model.predict(predicted.state)
        h = np.asarray(measurement.jacobian)
        p = np.asarray(predicted.covariance)
        r = np.diag([observation.noise.range_sigma_m ** 2, observation.noise.range_rate_sigma_m_s ** 2])
        innovation = np.array([
            observation.range_m - measurement.range_m,
            observation.range_rate_m_s - measurement.range_rate_m_s,
        ])
        s = h @ p @ h.T + r
        gain = np.linalg.solve(s, h @ p).T
        pv = predicted.state.pv
        x = np.array(pv.position_m + pv.velocity_m_s) + gain @ innovation
        state = replace(predicted.state, pv=CartesianPV(
            tuple(float(v) for v in x[:3]), tuple(float(v) for v in x[3:]),
        ))
        # Joseph 形式减轻大尺度差异和舍入造成的协方差非正定。
        a = np.eye(6) - gain @ h
        posterior = a @ p @ a.T + gain @ r @ gain.T
        estimate = StateEstimate(state, _matrix_tuple((posterior + posterior.T) / 2))
        postfit = self._model.predict(state)
        update = FilterUpdate(
            estimate, tuple(float(x) for x in innovation),
            (observation.range_m - postfit.range_m, observation.range_rate_m_s - postfit.range_rate_m_s),
            float(innovation @ np.linalg.solve(s, innovation)),
        )
        self._estimate = estimate
        return update
