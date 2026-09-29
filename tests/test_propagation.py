"""核心契约与轨道物理回归；使用标准库 unittest，无额外依赖。"""

from dataclasses import replace
from math import dist, pi, radians, sqrt
import subprocess
import sys
import unittest

from ssa.domain import (
    CartesianPV, EARTH_MU, Epoch, InitialConditions, InertialFrame,
    KeplerianElements, OrbitState,
)
from ssa.orekit import (
    IntegratorConfig, OrekitPropagatorFactory, PropagationMethod, initialize_orekit,
)
from ssa.orekit.forces import ThirdBody, ThirdBodyGravity
from ssa.propagation import sample_trajectory


def initial_conditions() -> InitialConditions:
    return InitialConditions(
        spacecraft_id="test-sat",
        epoch=Epoch("2002-01-01T00:00:00Z"),
        orbit=KeplerianElements(
            7000000.0, 0.001, radians(15.0), radians(30.0), radians(45.0), radians(60.0),
        ),
        mass_kg=120.0,
    )


class ContractTests(unittest.TestCase):
    def test_import_and_missing_initialization_do_not_start_jvm(self):
        # 独立进程检验导入副作用，不受其他集成测试已启动 JVM 的影响。
        code = """
from ssa.orekit import OrekitPropagatorFactory
from ssa.domain import CartesianPV, Epoch, InitialConditions
import jpype
assert not jpype.isJVMStarted()
initial = InitialConditions('s', Epoch('2002-01-01T00:00:00Z'),
                            CartesianPV((7000000., 0., 0.), (0., 7500., 0.)))
try:
    OrekitPropagatorFactory().create(initial)
except RuntimeError:
    pass
else:
    raise AssertionError('应要求显式初始化')
assert not jpype.isJVMStarted()
"""
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_physical_configuration(self):
        initial = initial_conditions()
        for changes in ({"mass_kg": 0}, {"mu_m3_s2": float("nan")}, {"spacecraft_id": " "}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(initial, **changes)
        for changes in ({"eccentricity": 1.0}, {"inclination_rad": 180.0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(initial.orbit, **changes)
        with self.assertRaises(ValueError):
            IntegratorConfig(min_step_s=10.0, max_step_s=1.0)
        with self.assertRaises(ValueError):
            OrekitPropagatorFactory(forces=(ThirdBodyGravity(ThirdBody.MOON),))

    def test_sampling_contract_without_orekit(self):
        class RecordingPropagator:
            def __init__(self):
                self.offsets = []

            def propagate_after(self, elapsed_s):
                self.offsets.append(elapsed_s)
                return OrbitState(
                    "fake", Epoch("2002-01-01T00:00:00Z"), InertialFrame.GCRF,
                    CartesianPV((7000000.0, 0.0, 0.0), (0.0, 7500.0, 0.0)), 100.0,
                )

        for duration, step, expected in (
            (125.0, 60.0, [0.0, 60.0, 120.0, 125.0]),
            (120.0, 60.0, [0.0, 60.0, 120.0]),
            (0.0, 60.0, [0.0]),
            (0.3, 0.1, [0.0, 0.1, 0.2, 0.3]),
        ):
            with self.subTest(duration=duration, step=step):
                fake = RecordingPropagator()
                states = list(sample_trajectory(fake, duration_s=duration, step_s=step))
                self.assertEqual(fake.offsets, expected)
                self.assertEqual(len(states), len(expected))
        fake = RecordingPropagator()
        list(sample_trajectory(fake, duration_s=125.0, step_s=60.0, start_offset_s=-60.0))
        self.assertEqual(fake.offsets, [-60.0, 0.0, 60.0, 65.0])
        for duration, step in ((-1.0, 1.0), (1.0, 0.0), (1.0, float("nan"))):
            with self.subTest(duration=duration, step=step), self.assertRaises(ValueError):
                list(sample_trajectory(fake, duration_s=duration, step_s=step))


class OrekitPhysicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_orekit()

    def test_runtime_initialization_is_idempotent(self):
        from org.orekit.data import DataContext

        manager = DataContext.getDefault().getDataProvidersManager()
        count = manager.getProviders().size()
        root = initialize_orekit()
        self.assertEqual(initialize_orekit(root), root)
        self.assertEqual(manager.getProviders().size(), count)
        with self.assertRaises(RuntimeError):
            initialize_orekit(root.parent)

    def test_one_period_and_conserved_energy(self):
        initial = initial_conditions()
        propagator = OrekitPropagatorFactory().create(initial)
        period = 2 * pi * sqrt(initial.orbit.semi_major_axis_m ** 3 / EARTH_MU)
        first = propagator.initial_state
        final = propagator.propagate_after(period)
        self.assertLess(dist(first.pv.position_m, final.pv.position_m), 1e-6)
        self.assertLess(dist(first.pv.velocity_m_s, final.pv.velocity_m_s), 1e-8)
        expected_energy = -EARTH_MU / (2 * initial.orbit.semi_major_axis_m)
        for state in sample_trajectory(propagator, duration_s=86400.0, step_s=7200.0):
            radius = sqrt(sum(v * v for v in state.pv.position_m))
            speed_squared = sum(v * v for v in state.pv.velocity_m_s)
            energy = speed_squared / 2 - EARTH_MU / radius
            self.assertAlmostEqual(energy / expected_energy, 1.0, places=12)
            self.assertEqual(state.mass_kg, 120.0)

    def test_numerical_matches_analytical_two_body(self):
        initial = initial_conditions()
        analytical = OrekitPropagatorFactory().create(initial)
        numerical = OrekitPropagatorFactory(method=PropagationMethod.NUMERICAL).create(initial)
        for elapsed in (-600.0, 0.0, 3600.0, 86400.0):
            with self.subTest(elapsed=elapsed):
                a, n = analytical.propagate_after(elapsed), numerical.propagate_after(elapsed)
                self.assertLess(dist(a.pv.position_m, n.pv.position_m), 1.0)
                self.assertLess(dist(a.pv.velocity_m_s, n.pv.velocity_m_s), 0.002)
                self.assertEqual(a.epoch, n.epoch)
                self.assertEqual(n.mass_kg, 120.0)

    def test_random_access_and_absolute_epoch(self):
        for method in PropagationMethod:
            with self.subTest(method=method):
                propagator = OrekitPropagatorFactory(method=method).create(initial_conditions())
                first = propagator.propagate_after(100.123456789)
                propagator.propagate_after(7200.0)
                propagator.propagate_after(-100.0)
                repeated = propagator.propagate_after(100.123456789)
                absolute = propagator.propagate(first.epoch)
                self.assertEqual(first, repeated)
                self.assertEqual(first.epoch.utc, "2002-01-01T00:01:40.123456789Z")
                self.assertLess(dist(first.pv.position_m, absolute.pv.position_m), 1e-5)
                self.assertEqual(propagator.initial_state.epoch.utc, "2002-01-01T00:00:00.000000000Z")

    def test_cartesian_restart_for_future_filter_update(self):
        initial = initial_conditions()
        factory = OrekitPropagatorFactory()
        original = factory.create(initial)
        updated = original.propagate_after(600.0)
        restarted = factory.create(replace(initial, epoch=updated.epoch, orbit=updated.pv))
        expected = original.propagate_after(1200.0)
        actual = restarted.propagate_after(600.0)
        self.assertLess(dist(expected.pv.position_m, actual.pv.position_m), 1e-6)
        self.assertEqual(actual.spacecraft_id, initial.spacecraft_id)

    def test_circular_equatorial_orbit_and_frames(self):
        for frame in InertialFrame:
            for method in PropagationMethod:
                with self.subTest(frame=frame, method=method):
                    initial = replace(
                        initial_conditions(), frame=frame,
                        orbit=CartesianPV((7000000.0, 0.0, 0.0), (0.0, sqrt(EARTH_MU / 7000000.0), 0.0)),
                    )
                    final = OrekitPropagatorFactory(method=method).create(initial).propagate_after(3600.0)
                    self.assertEqual(final.frame, frame)
                    self.assertAlmostEqual(dist(final.pv.position_m, (0.0, 0.0, 0.0)), 7000000.0, delta=0.1)

    def test_utc_leap_second_uses_physical_seconds(self):
        initial = replace(initial_conditions(), epoch=Epoch("2016-12-31T23:59:59Z"))
        propagator = OrekitPropagatorFactory().create(initial)
        leap = propagator.propagate_after(1.0)
        self.assertEqual(leap.epoch.utc, "2016-12-31T23:59:60.000000000Z")
        self.assertEqual(propagator.propagate_after(2.0).epoch.utc, "2017-01-01T00:00:00.000000000Z")
        self.assertEqual(propagator.propagate(leap.epoch), leap)

    def test_force_plugin_changes_orbit_and_preserves_factory_isolation(self):
        initial = initial_conditions()
        baseline = OrekitPropagatorFactory(method=PropagationMethod.NUMERICAL).create(initial)
        factory = OrekitPropagatorFactory(
            method=PropagationMethod.NUMERICAL,
            forces=(ThirdBodyGravity(ThirdBody.MOON),),
        )
        first = factory.create(initial)
        other = factory.create(replace(initial, spacecraft_id="other-sat"))
        perturbed = first.propagate_after(3600.0)
        other.propagate_after(7200.0)
        self.assertEqual(first.propagate_after(3600.0), perturbed)
        self.assertEqual(other.initial_state.spacecraft_id, "other-sat")
        self.assertGreater(dist(perturbed.pv.position_m, baseline.propagate_after(3600.0).pv.position_m), 0.1)


if __name__ == "__main__":
    unittest.main()
