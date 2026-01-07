from dataclasses import dataclass


@dataclass
class RouteSegment:
    trip_id: str
    route_name: str
    departure_stop: str
    departure_stop_name: str
    departure_time: int
    arrival_stop: str
    arrival_stop_name: str
    arrival_time: int
    wait_time: int = 0
