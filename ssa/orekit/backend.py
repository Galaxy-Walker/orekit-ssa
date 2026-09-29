"""领域模型与 Orekit 的唯一轨道转换边界。"""

from dataclasses import dataclass
from typing import Any

from ssa.domain import (
    CartesianPV, Epoch, InitialConditions, KeplerianElements, OrbitState,
    require_finite,
)
from ssa.orekit.config import IntegratorConfig, PropagationMethod
from ssa.orekit.forces import ForceModelFactory
from ssa.orekit.runtime import require_initialized
from ssa.propagation import Propagator


def _date(epoch: Epoch) -> Any:
    from org.orekit.time import AbsoluteDate, TimeScalesFactory

    return AbsoluteDate(epoch.utc, TimeScalesFactory.getUTC())


def _orbit(initial: InitialConditions) -> Any:
    from org.hipparchus.geometry.euclidean.threed import Vector3D
    from org.orekit.frames import FramesFactory
    from org.orekit.orbits import CartesianOrbit, KeplerianOrbit, PositionAngleType
    from org.orekit.utils import PVCoordinates

    frame = getattr(FramesFactory, f"get{initial.frame.value}")()
    date = _date(initial.epoch)
    mu = float(initial.mu_m3_s2)
    values = initial.orbit
    if isinstance(values, KeplerianElements):
        return KeplerianOrbit(
            float(values.semi_major_axis_m), float(values.eccentricity),
            float(values.inclination_rad), float(values.argument_of_perigee_rad),
            float(values.raan_rad), float(values.anomaly_rad),
            getattr(PositionAngleType, values.anomaly_type.value), frame, date, mu,
        )
    pv = PVCoordinates(
        Vector3D(*(float(v) for v in values.position_m)),
        Vector3D(*(float(v) for v in values.velocity_m_s)),
    )
    return CartesianOrbit(pv, frame, date, mu)


class _OrekitPropagator:
    def __init__(self, initial: InitialConditions, native: Any) -> None:
        self._initial = initial
        self._native = native
        self._reference_date = native.getInitialState().getDate()
        self._initial_state = self._to_state(native.getInitialState())

    @property
    def initial_state(self) -> OrbitState:
        return self._initial_state

    def _to_state(self, state: Any) -> OrbitState:
        from org.orekit.time import TimeScalesFactory

        pv = state.getPVCoordinates()
        position, velocity = pv.getPosition(), pv.getVelocity()
        utc = state.getDate().toStringWithoutUtcOffset(TimeScalesFactory.getUTC(), 9)
        return OrbitState(
            spacecraft_id=self._initial.spacecraft_id,
            epoch=Epoch(str(utc) + "Z"),
            frame=self._initial.frame,
            pv=CartesianPV(
                (float(position.getX()), float(position.getY()), float(position.getZ())),
                (float(velocity.getX()), float(velocity.getY()), float(velocity.getZ())),
            ),
            mass_kg=float(state.getMass()),
        )

    def _propagate_date(self, target: Any) -> OrbitState:
        # 显式指定起点，避免 Java 默认从上一次终点继续传播。
        return self._to_state(self._native.propagate(self._reference_date, target))

    def propagate(self, epoch: Epoch) -> OrbitState:
        return self._propagate_date(_date(epoch))

    def propagate_after(self, elapsed_s: float) -> OrbitState:
        require_finite("elapsed_s", elapsed_s)
        return self._propagate_date(self._reference_date.shiftedBy(float(elapsed_s)))


@dataclass(frozen=True)
class OrekitPropagatorFactory:
    method: PropagationMethod = PropagationMethod.KEPLERIAN
    integrator: IntegratorConfig = IntegratorConfig()
    forces: tuple[ForceModelFactory, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", PropagationMethod(self.method))
        object.__setattr__(self, "forces", tuple(self.forces))
        if self.method == PropagationMethod.KEPLERIAN and self.forces:
            raise ValueError("开普勒传播不支持摄动力，请选择 numerical")

    def create(self, initial: InitialConditions) -> Propagator:
        require_initialized()
        from org.orekit.propagation import SpacecraftState, ToleranceProvider
        from org.orekit.propagation.analytical import KeplerianPropagator
        from org.orekit.propagation.numerical import NumericalPropagator
        from org.orekit.orbits import OrbitType
        from org.hipparchus.ode.nonstiff import DormandPrince853Integrator

        orbit = _orbit(initial)
        state = SpacecraftState(orbit).withMass(float(initial.mass_kg))
        if self.method == PropagationMethod.KEPLERIAN:
            native = KeplerianPropagator(orbit)
            native.resetInitialState(state)
        else:
            config = self.integrator
            tolerances = ToleranceProvider.getDefaultToleranceProvider(
                float(config.position_tolerance_m)
            ).getTolerances(orbit, OrbitType.CARTESIAN)
            integrator = DormandPrince853Integrator(
                float(config.min_step_s), float(config.max_step_s),
                tolerances[0], tolerances[1],
            )
            native = NumericalPropagator(integrator)
            native.setOrbitType(OrbitType.CARTESIAN)
            native.setInitialState(state)
            # 默认中心引力由 Orekit 添加；这里只叠加独立摄动力。
            for force in self.forces:
                native.addForceModel(force.create(initial))
            native.setResetAtEnd(False)
        return _OrekitPropagator(initial, native)
