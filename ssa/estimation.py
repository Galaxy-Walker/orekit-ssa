"""笛卡尔 EKF：NumPy 线性代数，动力学和测站通过端口注入。

【重写练习脚手架】本文件的业务逻辑全部待实现，调用即抛 NotImplementedError。

- 规格来源：`tests/test_estimation.py`（不要修改它）
- 数学推导：`docs/architecture/stage-2-single-station-estimation.md` 第 3、4 节
- 实现顺序、提示阶梯与验收：`docs/learning/rewrite-estimation.md`

约定：历元是 `Epoch`，状态是 SI 单位 + 弧度，Java 对象不得出现在本文件。
"""

from dataclasses import dataclass

import numpy as np

from ssa.domain import CartesianPV, Epoch, InitialConditions, Matrix6, OrbitState, require_finite
from ssa.observations import GeometricRangeRateModel, RangeRateObservation
from ssa.propagation import EpochClock, LinearizedPropagatorFactory


def _matrix_tuple(matrix) -> Matrix6:
    return tuple(tuple(float(x) for x in row) for row in matrix)


@dataclass(frozen=True)
class StateEstimate:
    """同历元、同惯性系的 [r, v] 估计；协方差单位为对应状态单位的乘积。

    契约：
    - 协方差必须是 6×6、全部有限、对称、正定，否则抛 ValueError；
    - 构造后与传入对象脱钩：外部再改原矩阵（哪怕是 np.ndarray）不得影响本实例；
    - 内部以不可变 tuple of tuple 保存。
    """

    state: OrbitState
    covariance: Matrix6

    def __post_init__(self) -> None:
        raise NotImplementedError("StateEstimate: 校验不变量并转成不可变表示")


def diagonal_covariance(position_sigma_m: float, velocity_sigma_m_s: float) -> Matrix6:
    """位置 / 速度各三维独立的先验对角协方差。

    两项 σ 必须是正有限数（用 `require_finite(..., positive=True)`），否则 ValueError。
    """
    raise NotImplementedError("diagonal_covariance")


def white_acceleration_noise(dt_s: float, spectral_density_m2_s3: float) -> Matrix6:
    """惯性轴独立的连续白加速度、局部匀速近似下的离散过程噪声 Q。

    契约：dt_s 与谱密度有限且非负，否则 ValueError；返回 6×6 对称半正定矩阵，单位 m²；
    dt_s == 0 时返回全零矩阵。推导见阶段 2 文档第 4 节末尾。
    """
    raise NotImplementedError("white_acceleration_noise")


@dataclass(frozen=True)
class FilterUpdate:
    estimate: StateEstimate
    innovation: tuple[float, float]
    postfit_residual: tuple[float, float]
    normalized_innovation_squared: float


class ExtendedKalmanFilter:
    """序贯 EKF：状态 x=[r(m), v(m/s)]，预测走 LinearizedPropagatorFactory，时间差走 EpochClock。

    时间轴单向：不接受早于当前估计历元的观测或预测历元。
    """

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
        """校验 psd 有限非负，保存端口，并用 factory 的初始状态 + 传入协方差建立先验估计。"""
        raise NotImplementedError("ExtendedKalmanFilter.__init__")

    @property
    def estimate(self) -> StateEstimate:
        """当前（最新）估计。已给出，无需改写。"""
        return self._estimate

    def predict_to(self, epoch: Epoch) -> StateEstimate:
        """只推进状态与协方差，不消费观测。

        - 必须与当前估计历元的物理时间差（走 clock）做判断；
        - 同历元必须返回 `self.estimate` 本身（不得新建对象）；
        - 早于当前历元抛 ValueError，且不修改状态。
        """
        raise NotImplementedError("ExtendedKalmanFilter.predict_to")

    def process(self, observation: RangeRateObservation) -> FilterUpdate:
        """预测到观测历元，做一次测距 + 距离率联合更新。

        - 先校验卫星标识、测站标识、时间序，任一不符抛 ValueError；
        - 失败必须原子：`self.estimate` 保持调用前那个对象不变；
        - 返回先验创新 y、更新后用 h(x⁺) 重算的后验残差、NIS = yᵀ S⁻¹ y。
        """
        raise NotImplementedError("ExtendedKalmanFilter.process")
