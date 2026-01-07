class RouteSegment:
    def __init__(
        self,
        trip_id,
        route_name,
        departure_stop,
        departure_stop_name,
        departure_time,
        arrival_stop,
        arrival_stop_name,
        arrival_time,
        wait_time=0,
    ):
        self.trip_id = trip_id
        self.route_name = route_name
        self.departure_stop = departure_stop
        self.departure_stop_name = departure_stop_name
        self.departure_time = departure_time
        self.arrival_stop = arrival_stop
        self.arrival_stop_name = arrival_stop_name
        self.arrival_time = arrival_time
        self.wait_time = wait_time


