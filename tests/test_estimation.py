"""阶段 2：几何/STM 独立差分、滤波解析解及端到端物理回归。"""

from dataclasses import replace
from math import dist, pi, radians
from pathlib import Path
import csv
import tempfile
import unittest

import numpy as np

from orbit_determination import run_experiment, write_csv
from ssa.domain import CartesianPV, Epoch, InitialConditions, InertialFrame, KeplerianElements, OrbitState
from ssa.estimation import ExtendedKalmanFilter, StateEstimate, diagonal_covariance, white_acceleration_noise
from ssa.observations import (
    GeometricRangeRateModel, GroundStation, MeasurementNoise, RangeRateObservation,
    simulate_observations,
)
from ssa.orekit import IntegratorConfig, OrekitPropagatorFactory, PropagationMethod, initialize_orekit
from ssa.orekit.backend import OrekitClock
from ssa.orekit.forces import ThirdBody, ThirdBodyGravity
from ssa.orekit.stations import OrekitStationGeometry


def initial_conditions():
    return InitialConditions(
        "test-sat", Epoch("2002-01-01T00:00:00Z"),
        KeplerianElements(7000000.0, 0.001, radians(55), radians(30), radians(45), radians(60)),
    )


class FixedGeometry:
    station = GroundStation("fixed", 0.0, 0.0)

    def pv_at(self, epoch, frame):
        return CartesianPV((6000000.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    def elevation(self, state):
        return pi / 2 if state.pv.position_m[0] > 6000000.0 else -pi / 2


class EstimationContractTests(unittest.TestCase):
    def setUp(self):
        self.state = OrbitState(
            "test-sat", Epoch("2002-01-01T00:00:00Z"), InertialFrame.GCRF,
            CartesianPV((7000000.0, 0.0, 0.0), (100.0, 0.0, 0.0)), 1000.0,
        )
        self.model = GeometricRangeRateModel(FixedGeometry())

    def test_measurement_jacobian_matches_independent_finite_differences(self):
        state = replace(self.state, pv=CartesianPV((7000000.0, 200000.0, 300000.0), (200.0, 7000.0, 50.0)))
        expected = np.asarray(self.model.predict(state).jacobian)
        x = np.array(state.pv.position_m + state.pv.velocity_m_s)
        actual = np.empty((2, 6))
        for j in range(6):
            step = 1.0 if j < 3 else 0.01
            measurements = []
            for sign in (1, -1):
                shifted = x.copy()
                shifted[j] += sign * step
                prediction = self.model.predict(replace(state, pv=CartesianPV(tuple(shifted[:3]), tuple(shifted[3:]))))
                measurements.append(np.array([prediction.range_m, prediction.range_rate_m_s]))
            actual[:, j] = (measurements[0] - measurements[1]) / (2 * step)
        np.testing.assert_allclose(actual, expected, rtol=1e-7, atol=1e-9)

    def test_known_scalar_kalman_solution_and_identity_validation(self):
        class Factory:
            def create_linearized(inner, initial):
                class Propagator:
                    initial_state = self.state
                return Propagator()

        class Clock:
            def seconds_between(inner, later, earlier):
                return 0.0 if later == earlier else -1.0

        initial = InitialConditions(self.state.spacecraft_id, self.state.epoch, self.state.pv)
        ekf = ExtendedKalmanFilter(initial, diagonal_covariance(10.0, 1.0), Factory(), self.model, Clock())
        observation = RangeRateObservation(
            "test-sat", "fixed", self.state.epoch, 1000020.0, 102.0, MeasurementNoise(5.0, 0.5),
        )
        before = ekf.estimate
        for invalid in (
            replace(observation, spacecraft_id="other"),
            replace(observation, station_id="other"),
            replace(observation, epoch=Epoch("2001-12-31T23:59:59Z")),
        ):
            with self.assertRaises(ValueError):
                ekf.process(invalid)
            self.assertIs(ekf.estimate, before)
        update = ekf.process(observation)
        self.assertAlmostEqual(update.estimate.state.pv.position_m[0], 7000016.0)
        self.assertAlmostEqual(update.estimate.state.pv.velocity_m_s[0], 101.6)
        self.assertAlmostEqual(update.estimate.covariance[0][0], 20.0)
        self.assertAlmostEqual(update.estimate.covariance[3][3], 0.2)
        self.assertAlmostEqual(update.estimate.covariance[1][1], 100.0)
        self.assertAlmostEqual(update.normalized_innovation_squared, 6.4)

    def test_covariance_and_configuration_validation(self):
        for matrix in (
            np.eye(5), np.full((6, 6), np.nan), -np.eye(6),
            np.eye(6) + np.diag([2.0] * 5, 1),
            np.ones((6, 6)),
        ):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                StateEstimate(self.state, matrix)
        mutable = np.eye(6)
        estimate = StateEstimate(self.state, mutable)
        mutable[0, 0] = 100.0
        self.assertEqual(estimate.covariance[0][0], 1.0)
        for kwargs in ({"latitude_rad": 2.0}, {"min_elevation_rad": -0.1}, {"longitude_rad": float("nan")}):
            with self.assertRaises(ValueError):
                replace(FixedGeometry.station, **kwargs)
        with self.assertRaises(ValueError):
            MeasurementNoise(0.0, 1.0)

    def test_visibility_seed_and_noise(self):
        hidden = replace(self.state, pv=CartesianPV((-7000000.0, 0.0, 0.0), (100.0, 0.0, 0.0)))
        states = [hidden, self.state, self.state]
        first = tuple(simulate_observations(states, self.model, seed=7))
        self.assertEqual(len(first), 2)
        self.assertEqual(first, tuple(simulate_observations(states, self.model, seed=7)))
        self.assertNotEqual(first, tuple(simulate_observations(states, self.model, seed=8)))
        self.assertNotEqual(first[0].range_m, 1000000.0)

    def test_continuous_white_acceleration_discretization(self):
        q = np.asarray(white_acceleration_noise(2.0, 3.0))
        self.assertEqual(q[0, 0], 8.0)
        self.assertEqual(q[0, 3], 6.0)
        self.assertEqual(q[3, 3], 6.0)
        self.assertGreater(np.linalg.eigvalsh(q).min(), 0.0)
        np.testing.assert_array_equal(white_acceleration_noise(0.0, 3.0), np.zeros((6, 6)))
        with self.assertRaises(ValueError):
            white_acceleration_noise(-1.0, 3.0)


class OrekitEstimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_orekit()

    def test_cartesian_stm_against_finite_differences_and_random_access(self):
        initial = initial_conditions()
        initial = replace(initial, orbit=OrekitPropagatorFactory().create(initial).initial_state.pv)
        for forces in ((), (ThirdBodyGravity(ThirdBody.MOON),)):
            with self.subTest(forces=forces):
                factory = OrekitPropagatorFactory(
                    method=PropagationMethod.NUMERICAL,
                    integrator=IntegratorConfig(position_tolerance_m=0.0001), forces=forces,
                )
                propagator = factory.create_linearized(initial)
                np.testing.assert_allclose(propagator.propagate_with_transition(initial.epoch).transition_matrix, np.eye(6), atol=1e-12)
                target = propagator.propagate_after(600.0).epoch
                expected = propagator.propagate_with_transition(target)
                x = np.array(initial.orbit.position_m + initial.orbit.velocity_m_s)
                actual = np.empty((6, 6))
                for j in range(6):
                    step = 1.0 if j < 3 else 0.001
                    states = []
                    for sign in (1, -1):
                        shifted = x.copy()
                        shifted[j] += sign * step
                        pv = CartesianPV(tuple(shifted[:3]), tuple(shifted[3:]))
                        state = factory.create(replace(initial, orbit=pv)).propagate(target)
                        states.append(np.array(state.pv.position_m + state.pv.velocity_m_s))
                    actual[:, j] = (states[0] - states[1]) / (2 * step)
                np.testing.assert_allclose(actual, expected.transition_matrix, rtol=2e-5, atol=1e-5)
                propagator.propagate_after(1200.0)
                propagator.propagate_after(-600.0)
                self.assertEqual(propagator.propagate_with_transition(target), expected)
        with self.assertRaises(ValueError):
            OrekitPropagatorFactory().create_linearized(initial)

    def test_station_rotation_elevation_and_range_rate_sign(self):
        initial = initial_conditions()
        truth = OrekitPropagatorFactory().create(initial)
        geometry = OrekitStationGeometry(GroundStation("equator", 0.0, 0.0))
        model = GeometricRangeRateModel(geometry)
        for frame in InertialFrame:
            local_truth = OrekitPropagatorFactory().create(replace(initial, frame=frame))
            state = local_truth.initial_state
            station = geometry.pv_at(state.epoch, frame)
            self.assertGreater(dist(station.velocity_m_s, (0.0, 0.0, 0.0)), 400.0)
            overhead = replace(state, pv=CartesianPV(tuple(x * 1.1 for x in station.position_m), state.pv.velocity_m_s))
            self.assertAlmostEqual(geometry.elevation(overhead), pi / 2, delta=1e-7)
            occulted = replace(state, pv=CartesianPV(tuple(-x for x in overhead.pv.position_m), state.pv.velocity_m_s))
            self.assertFalse(model.is_visible(occulted))
            before, after = local_truth.propagate_after(-0.1), local_truth.propagate_after(0.1)
            derivative = (model.predict(after).range_m - model.predict(before).range_m) / 0.2
            self.assertAlmostEqual(model.predict(state).range_rate_m_s, derivative, delta=0.001)
        before = geometry.pv_at(truth.propagate_after(-1.0).epoch, initial.frame)
        after = geometry.pv_at(truth.propagate_after(1.0).epoch, initial.frame)
        numerical_velocity = (np.array(after.position_m) - np.array(before.position_m)) / 2
        np.testing.assert_allclose(numerical_velocity, geometry.pv_at(initial.epoch, initial.frame).velocity_m_s, atol=1e-5)

    def test_prediction_gaps_and_physical_time(self):
        clock = OrekitClock()
        self.assertEqual(clock.seconds_between(Epoch("2017-01-01T00:00:00Z"), Epoch("2016-12-31T23:59:59Z")), 2.0)
        initial = initial_conditions()
        factory = OrekitPropagatorFactory(method=PropagationMethod.NUMERICAL)
        model = GeometricRangeRateModel(OrekitStationGeometry(GroundStation("s", 0.0, 0.0)))
        p = diagonal_covariance(100.0, 0.1)
        ekf = ExtendedKalmanFilter(initial, p, factory, model, clock, acceleration_psd_m2_s3=1e-6)
        before = ekf.estimate
        self.assertIs(ekf.predict_to(initial.epoch), before)
        propagated = factory.create_linearized(initial)
        epoch = propagated.propagate_after(600.0).epoch
        linearized = propagated.propagate_with_transition(epoch)
        phi = np.asarray(linearized.transition_matrix)
        expected = phi @ np.asarray(p) @ phi.T + np.asarray(white_acceleration_noise(600.0, 1e-6))
        result = ekf.predict_to(epoch)
        np.testing.assert_allclose(result.covariance, expected, atol=1e-7)
        self.assertLess(dist(result.state.pv.position_m, linearized.state.pv.position_m), 1e-6)
        with self.assertRaises(ValueError):
            ekf.predict_to(initial.epoch)
        self.assertIs(ekf.estimate, result)

    def test_end_to_end_convergence_covariance_and_csv(self):
        result = run_experiment()
        last = result.samples[-1]
        self.assertGreater(len(result.samples), 50)
        self.assertLess(last.position_error_m, 30.0)
        self.assertLess(last.velocity_error_m_s, 0.05)
        baseline = dist(last.open_loop.pv.position_m, last.truth.pv.position_m)
        self.assertLess(last.position_error_m, baseline / 20)
        noise = last.observation.noise
        residuals = np.array([s.update.postfit_residual for s in result.samples])
        rms = np.sqrt(np.mean(residuals ** 2, axis=0))
        self.assertLess(rms[0], 2 * noise.range_sigma_m)
        self.assertLess(rms[1], 2 * noise.range_rate_sigma_m_s)
        for sample in result.samples:
            p = np.asarray(sample.update.estimate.covariance)
            np.testing.assert_allclose(p, p.T, atol=1e-12)
            self.assertGreater(np.linalg.eigvalsh(p).min(), 0.0)
            self.assertGreaterEqual(sample.update.normalized_innovation_squared, 0.0)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temporary:
            output = Path(temporary.name)
        try:
            write_csv(result, output)
            with output.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), len(result.samples))
            self.assertAlmostEqual(float(rows[-1]["position_error_m"]), last.position_error_m)
        finally:
            output.unlink()

    def test_no_visible_observations_is_explicit(self):
        with self.assertRaisesRegex(ValueError, "没有.*可见"):
            run_experiment(duration_s=0.0)


if __name__ == "__main__":
    unittest.main()
