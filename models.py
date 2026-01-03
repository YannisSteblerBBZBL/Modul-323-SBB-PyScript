from dataclasses import dataclass


@dataclass
class Connection:
    """Repräsentiert eine Verbindung zwischen zwei Haltestellen"""
    trip_id: str
    departure_stop: str
    arrival_stop: str
    departure_time: int  # Sekunden seit Mitternacht
    arrival_time: int    # Sekunden seit Mitternacht
    route_id: str
    route_name: str = ""
    departure_stop_name: str = ""
    arrival_stop_name: str = ""


@dataclass
class RouteSegment:
    """Repräsentiert ein Segment einer Route"""
    trip_id: str
    route_name: str
    departure_stop: str
    departure_stop_name: str
    departure_time: int
    arrival_stop: str
    arrival_stop_name: str
    arrival_time: int
    wait_time: int = 0  # Wartezeit vor dieser Fahrt
