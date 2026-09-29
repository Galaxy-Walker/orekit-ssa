"""数值传播的力模型插件；Java 类型严格局限在适配层。"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from ssa.domain import InitialConditions
from ssa.orekit.runtime import require_initialized


class ForceModelFactory(Protocol):
    def create(self, initial: InitialConditions) -> Any:
        """返回新的 Orekit ForceModel，禁止复用可变的 Java 力模型。

        initial 提供质量和引力常数等；中心引力由传播器自动添加，
        本接口用于摄动力。额外航天器参数可放在插件自身配置中。
        """
        ...


class ThirdBody(StrEnum):
    SUN = "SUN"
    MOON = "MOON"


@dataclass(frozen=True)
class ThirdBodyGravity:
    """内置插件示例：日/月第三体引力，依赖参考数据中的行星历表。"""

    body: ThirdBody

    def __post_init__(self) -> None:
        object.__setattr__(self, "body", ThirdBody(self.body))

    def create(self, initial: InitialConditions) -> Any:
        require_initialized()
        from org.orekit.bodies import CelestialBodyFactory
        from org.orekit.forces.gravity import ThirdBodyAttraction

        body = (
            CelestialBodyFactory.getSun()
            if self.body == ThirdBody.SUN
            else CelestialBodyFactory.getMoon()
        )
        return ThirdBodyAttraction(body)
