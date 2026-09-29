"""传播端口及与后端无关的轨迹采样。"""

from collections.abc import Iterator
from math import ceil
from typing import Protocol

from ssa.domain import (
    Epoch, InitialConditions, LinearizedState, OrbitState, require_finite,
)


class Propagator(Protocol):
    """固定初值的状态查询；不因上一次查询而改变初值。

    状态始终使用初值的惯性系；不承诺同一实例可被多线程共享。
    """

    @property
    def initial_state(self) -> OrbitState: ...

    def propagate(self, epoch: Epoch) -> OrbitState:
        """按绝对 UTC 历元查询。"""
        ...

    def propagate_after(self, elapsed_s: float) -> OrbitState:
        """相对初始历元的物理秒数，可为负；不是相对上一次查询。"""
        ...


class PropagatorFactory(Protocol):
    def create(self, initial: InitialConditions) -> Propagator:
        """每次创建独立实例；后续滤波更新后可用新初值重建。"""
        ...


class LinearizedPropagator(Propagator, Protocol):
    """携带相对固定初值的笛卡尔状态转移矩阵。"""

    def propagate_with_transition(self, epoch: Epoch) -> LinearizedState: ...


class LinearizedPropagatorFactory(Protocol):
    def create_linearized(self, initial: InitialConditions) -> LinearizedPropagator: ...


class EpochClock(Protocol):
    def seconds_between(self, later: Epoch, earlier: Epoch) -> float:
        """有符号物理秒数，须正确处理 UTC 闰秒。"""
        ...


def sample_trajectory(
    propagator: Propagator,
    *,
    duration_s: float,
    step_s: float,
    start_offset_s: float = 0.0,
) -> Iterator[OrbitState]:
    """惰性、正向等间隔采样；含起点和终点，终点不整除时追加一次。

    start_offset_s 相对初始历元；零时长只输出一个状态。
    采样步长与数值积分器内部步长相互独立。
    """
    require_finite("duration_s", duration_s)
    require_finite("step_s", step_s, positive=True)
    require_finite("start_offset_s", start_offset_s)
    if duration_s < 0:
        raise ValueError("duration_s 不能为负")
    end = start_offset_s + duration_s
    require_finite("采样终点", end)
    intervals = duration_s / step_s
    require_finite("采样间隔数", intervals)
    for index in range(ceil(intervals)):
        offset = start_offset_s + index * step_s
        if offset < end:
            yield propagator.propagate_after(offset)
    yield propagator.propagate_after(end)
