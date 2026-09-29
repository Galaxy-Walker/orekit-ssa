"""Orekit 传播策略配置；仅包含纯 Python 值。"""

from dataclasses import dataclass
from enum import StrEnum

from ssa.domain import require_finite


class PropagationMethod(StrEnum):
    KEPLERIAN = "keplerian"
    NUMERICAL = "numerical"


@dataclass(frozen=True)
class IntegratorConfig:
    min_step_s: float = 0.001
    max_step_s: float = 300.0
    position_tolerance_m: float = 0.01

    def __post_init__(self) -> None:
        for name in ("min_step_s", "max_step_s", "position_tolerance_m"):
            require_finite(name, getattr(self, name), positive=True)
        if self.min_step_s > self.max_step_s:
            raise ValueError("min_step_s 不能大于 max_step_s")
