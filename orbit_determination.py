"""阶段 2 组合根：单星 / 北京站的可复现仿真定轨实验。"""

import argparse
import csv
from dataclasses import dataclass, replace
from math import dist, radians, sqrt
from pathlib import Path

from ssa.domain import CartesianPV, Epoch, InitialConditions, KeplerianElements, OrbitState
from ssa.estimation import ExtendedKalmanFilter, FilterUpdate, diagonal_covariance
from ssa.observations import (
    GeometricRangeRateModel, GroundStation, MeasurementNoise, RangeRateObservation,
    simulate_observations,
)
from ssa.orekit import (
    OrekitClock, OrekitPropagatorFactory, OrekitStationGeometry, PropagationMethod,
    initialize_orekit,
)
from ssa.propagation import sample_trajectory


@dataclass(frozen=True)
class EstimationSample:
    observation: RangeRateObservation
    update: FilterUpdate
    truth: OrbitState
    open_loop: OrbitState

    @property
    def position_error_m(self) -> float:
        return dist(self.update.estimate.state.pv.position_m, self.truth.pv.position_m)

    @property
    def velocity_error_m_s(self) -> float:
        return dist(self.update.estimate.state.pv.velocity_m_s, self.truth.pv.velocity_m_s)


@dataclass(frozen=True)
class ExperimentResult:
    prior: OrbitState
    samples: tuple[EstimationSample, ...]


def run_experiment(
    *, duration_s: float = 86400.0, step_s: float = 30.0, seed: int = 42,
) -> ExperimentResult:
    """调用方先初始化 Orekit；先验历元选为首个可见采样点。"""
    initial = InitialConditions(
        "sat-001", Epoch("2002-01-01T00:00:00Z"),
        KeplerianElements(7000000.0, 0.001, radians(55.0), radians(30.0), radians(45.0), radians(60.0)),
    )
    truth = OrekitPropagatorFactory().create(initial)
    station = GroundStation("beijing", radians(39.9042), radians(116.4074), 50.0, radians(10.0))
    model = GeometricRangeRateModel(OrekitStationGeometry(station))
    observations = tuple(simulate_observations(
        sample_trajectory(truth, duration_s=duration_s, step_s=step_s),
        model, noise=MeasurementNoise(10.0, 0.1), seed=seed,
    ))
    if not observations:
        raise ValueError("当前时段没有高于 10° 的可见采样点，请增加 --duration 或减小 --step")

    first_truth = truth.propagate(observations[0].epoch)
    biased_pv = CartesianPV(
        tuple(x + d for x, d in zip(first_truth.pv.position_m, (100.0, -80.0, 60.0))),
        tuple(x + d for x, d in zip(first_truth.pv.velocity_m_s, (0.1, -0.08, 0.06))),
    )
    prior_initial = replace(initial, epoch=first_truth.epoch, orbit=biased_pv)
    factory = OrekitPropagatorFactory(method=PropagationMethod.NUMERICAL)
    ekf = ExtendedKalmanFilter(
        prior_initial, diagonal_covariance(200.0, 0.2), factory, model, OrekitClock(),
    )
    prior = ekf.estimate.state
    open_loop = factory.create(prior_initial)
    samples = tuple(
        EstimationSample(
            observation, ekf.process(observation), truth.propagate(observation.epoch),
            open_loop.propagate(observation.epoch),
        )
        for observation in observations
    )
    return ExperimentResult(prior, samples)


def write_csv(result: ExperimentResult, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "utc", "spacecraft_id", "station_id", "range_m", "range_rate_m_s",
            "position_error_m", "velocity_error_m_s", "open_loop_position_error_m",
            "position_sigma_rss_m", "velocity_sigma_rss_m_s",
            "innovation_range_m", "innovation_range_rate_m_s",
            "postfit_range_m", "postfit_range_rate_m_s", "nis",
        ])
        for sample in result.samples:
            obs, update = sample.observation, sample.update
            p = update.estimate.covariance
            writer.writerow([
                obs.epoch.utc, obs.spacecraft_id, obs.station_id, obs.range_m, obs.range_rate_m_s,
                sample.position_error_m, sample.velocity_error_m_s,
                dist(sample.open_loop.pv.position_m, sample.truth.pv.position_m),
                sqrt(sum(p[i][i] for i in range(3))), sqrt(sum(p[i][i] for i in range(3, 6))),
                *update.innovation, *update.postfit_residual, update.normalized_innovation_squared,
            ])


def main() -> None:
    parser = argparse.ArgumentParser(description="单星单站测距 / 距离率 EKF 仿真定轨")
    parser.add_argument("--duration", type=float, default=86400.0, help="真值仿真时长，秒")
    parser.add_argument("--step", type=float, default=30.0, help="观测采样步长，秒")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data-dir", help="Orekit 参考数据目录")
    parser.add_argument("--output", type=Path, help="逐观测诊断 CSV 路径")
    args = parser.parse_args()
    initialize_orekit(args.data_dir)
    try:
        result = run_experiment(duration_s=args.duration, step_s=args.step, seed=args.seed)
    except ValueError as error:
        parser.error(str(error))
    first, last = result.samples[0], result.samples[-1]
    prior_error = dist(result.prior.pv.position_m, first.truth.pv.position_m)
    baseline_error = dist(last.open_loop.pv.position_m, last.truth.pv.position_m)
    p = last.update.estimate.covariance
    print("单星单站 EKF：sat-001 / 北京站 / GCRF / 二体动力学")
    print(f"观测：{len(result.samples)} 组测距 + 距离率，随机种子：{args.seed}")
    print(f"观测时段：{first.observation.epoch.utc} → {last.observation.epoch.utc}")
    print(f"初始位置偏差：{prior_error:.3f} m")
    print(f"末次观测历元无更新位置误差：{baseline_error:.3f} m")
    print(f"末次更新位置误差：{last.position_error_m:.3f} m")
    print(f"末次更新速度误差：{last.velocity_error_m_s:.6f} m/s")
    print(f"末次位置标准差 RSS：{sqrt(sum(p[i][i] for i in range(3))):.3f} m")
    for index, unit in ((0, "m"), (1, "m/s")):
        rms = sqrt(sum(s.update.postfit_residual[index] ** 2 for s in result.samples) / len(result.samples))
        print(f"后验{'测距' if index == 0 else '距离率'}残差 RMS：{rms:.6f} {unit}")
    if args.output:
        write_csv(result, args.output)
        print(f"诊断已保存：{args.output}")


if __name__ == "__main__":
    main()
