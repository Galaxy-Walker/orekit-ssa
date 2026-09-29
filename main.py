"""阶段 1：组合初始条件、传播后端与轨迹采样。"""

import argparse
from math import radians

from ssa.domain import Epoch, InitialConditions, KeplerianElements
from ssa.orekit import OrekitPropagatorFactory, PropagationMethod, initialize_orekit
from ssa.orekit.forces import ThirdBody, ThirdBodyGravity
from ssa.propagation import sample_trajectory


def main() -> None:
    parser = argparse.ArgumentParser(description="单星轨道传播示例（SI 单位）")
    parser.add_argument("--method", choices=list(PropagationMethod), default="keplerian")
    parser.add_argument("--duration", type=float, default=86400.0, help="传播时长，秒")
    parser.add_argument("--step", type=float, default=21600.0, help="输出采样步长，秒")
    parser.add_argument("--data-dir", help="Orekit 参考数据目录，默认使用 orekitdata 包")
    parser.add_argument("--third-body", choices=["sun", "moon"], action="append", default=[])
    args = parser.parse_args()
    if args.third_body and args.method != "numerical":
        parser.error("--third-body 需要 --method numerical")

    initialize_orekit(args.data_dir)
    initial = InitialConditions(
        spacecraft_id="sat-001",
        epoch=Epoch("2002-01-01T00:00:00Z"),
        orbit=KeplerianElements(
            semi_major_axis_m=7000e3,
            eccentricity=0.001,
            inclination_rad=radians(15.0),
            argument_of_perigee_rad=radians(30.0),
            raan_rad=radians(45.0),
            anomaly_rad=radians(60.0),
        ),
    )
    factory = OrekitPropagatorFactory(
        method=PropagationMethod(args.method),
        forces=tuple(ThirdBodyGravity(ThirdBody(body.upper())) for body in args.third_body),
    )
    propagator = factory.create(initial)
    print(f"卫星：{initial.spacecraft_id}  传播器：{args.method}  坐标系：{initial.frame}")
    print("UTC                                    x [m]          y [m]          z [m]      |v| [m/s]")
    for state in sample_trajectory(propagator, duration_s=args.duration, step_s=args.step):
        x, y, z = state.pv.position_m
        speed = sum(v * v for v in state.pv.velocity_m_s) ** 0.5
        print(f"{state.epoch.utc}  {x:14.3f} {y:14.3f} {z:14.3f} {speed:12.3f}")


if __name__ == "__main__":
    main()
