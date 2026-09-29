"""WGS84 测站与地球自转适配；返回值仅包含 Python 数据。"""

from ssa.domain import CartesianPV, Epoch, InertialFrame, OrbitState
from ssa.observations import GroundStation
from ssa.orekit.backend import _date
from ssa.orekit.runtime import require_initialized


class OrekitStationGeometry:
    def __init__(self, station: GroundStation) -> None:
        require_initialized()
        from org.orekit.bodies import GeodeticPoint
        from org.orekit.frames import FramesFactory, TopocentricFrame
        from org.orekit.models.earth import ReferenceEllipsoid
        from org.orekit.utils import IERSConventions

        self._station = station
        earth = ReferenceEllipsoid.getWgs84(
            FramesFactory.getITRF(IERSConventions.IERS_2010, True),
        )
        point = GeodeticPoint(
            float(station.latitude_rad), float(station.longitude_rad), float(station.altitude_m),
        )
        self._topocentric = TopocentricFrame(earth, point, station.station_id)

    @property
    def station(self) -> GroundStation:
        return self._station

    def pv_at(self, epoch: Epoch, frame: InertialFrame) -> CartesianPV:
        from org.orekit.frames import FramesFactory

        native_frame = getattr(FramesFactory, f"get{frame.value}")()
        pv = self._topocentric.getPVCoordinates(_date(epoch), native_frame)
        r, v = pv.getPosition(), pv.getVelocity()
        return CartesianPV(
            (float(r.getX()), float(r.getY()), float(r.getZ())),
            (float(v.getX()), float(v.getY()), float(v.getZ())),
        )

    def elevation(self, state: OrbitState) -> float:
        from org.hipparchus.geometry.euclidean.threed import Vector3D
        from org.orekit.frames import FramesFactory

        return float(self._topocentric.getElevation(
            Vector3D(*(float(x) for x in state.pv.position_m)),
            getattr(FramesFactory, f"get{state.frame.value}")(), _date(state.epoch),
        ))
