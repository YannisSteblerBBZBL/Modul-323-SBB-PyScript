from datetime import datetime

from models import RouteSegment


class _Label:
    def __init__(
        self,
        stop_id,
        arrival_time,
        prev,
        trip_id=None,
        route_name="",
        dep_stop=None,
        dep_time=None,
    ):
        self.stop_id = stop_id
        self.arrival_time = arrival_time
        self.prev = prev
        self.trip_id = trip_id
        self.route_name = route_name
        self.dep_stop = dep_stop
        self.dep_time = dep_time


class RouteCalculator:
    def __init__(self, data_loader):
        self.data = data_loader

    def _build_connections(self, date_obj, start_time_sec):
        valid_services = self.data.get_valid_services(date_obj)
        if not valid_services:
            print(
                f"  ⚠ Warnung: Keine gültigen Services für {date_obj.strftime('%Y-%m-%d')} gefunden!"
            )
            print(
                "     Prüfen Sie, ob das Datum im Gültigkeitsbereich der GTFS-Daten liegt."
            )
            return []

        # Build list of (dep_time, trip_id, dep_stop, arr_stop, arr_time, route_name)
        connections = []

        # iterate trips (imperative)
        for trip_id in self.data.trip_to_service:
            service_id = self.data.trip_to_service[trip_id]
            if service_id not in valid_services:
                continue

            stops = self.data.stop_times_by_trip.get(trip_id)
            if stops is None or len(stops) < 2:
                continue

            route_name = self.data.trip_to_route_name.get(trip_id, "") or ""

            i = 0
            while i < len(stops) - 1:
                # current stop -> next stop
                _seq, dep_stop, _arr_sec, dep_sec = stops[i]
                _seq2, arr_stop, arr_sec, _dep2 = stops[i + 1]

                if dep_sec >= start_time_sec and arr_sec > dep_sec:
                    # Put dep_time first so we can sort without key=
                    connections.append(
                        (int(dep_sec), trip_id, dep_stop, arr_stop, int(arr_sec), route_name)
                    )
                i += 1

        connections.sort()
        return connections

    def _reconstruct_route_from_label(self, end_label):
        connections_rev = []
        visited_ids = set()
        cur = end_label

        while cur.prev is not None:
            obj_id = id(cur)
            if obj_id in visited_ids:
                return None
            visited_ids.add(obj_id)

            if cur.trip_id is None or cur.dep_stop is None or cur.dep_time is None:
                return None

            connections_rev.append(
                (cur.trip_id, cur.route_name or "", cur.dep_stop, int(cur.dep_time), cur.stop_id, int(cur.arrival_time))
            )
            cur = cur.prev

        if not connections_rev:
            return None

        connections_rev.reverse()

        # merge consecutive connections on same trip
        optimized = []
        current_trip = connections_rev[0][0]
        current_route = connections_rev[0][1]
        first_dep_stop = connections_rev[0][2]
        first_dep_time = connections_rev[0][3]
        last_arr_stop = connections_rev[0][4]
        last_arr_time = connections_rev[0][5]

        i = 1
        while i < len(connections_rev):
            trip_id, route_name, dep_stop, dep_time, arr_stop, arr_time = connections_rev[i]
            if trip_id == current_trip and last_arr_stop == dep_stop and last_arr_time <= dep_time:
                last_arr_stop = arr_stop
                last_arr_time = arr_time
            else:
                optimized.append(
                    (
                        current_trip,
                        current_route,
                        first_dep_stop,
                        first_dep_time,
                        last_arr_stop,
                        last_arr_time,
                    )
                )
                current_trip = trip_id
                current_route = route_name
                first_dep_stop = dep_stop
                first_dep_time = dep_time
                last_arr_stop = arr_stop
                last_arr_time = arr_time
            i += 1

        optimized.append(
            (
                current_trip,
                current_route,
                first_dep_stop,
                first_dep_time,
                last_arr_stop,
                last_arr_time,
            )
        )

        # build RouteSegments
        segments = []
        idx = 0
        while idx < len(optimized):
            trip_id, route_name, dep_stop, dep_time, arr_stop, arr_time = optimized[idx]
            wait_time = 0
            if idx > 0:
                prev_arr_stop = optimized[idx - 1][4]
                prev_arr_time = optimized[idx - 1][5]
                if prev_arr_stop == dep_stop:
                    diff = dep_time - prev_arr_time
                    wait_time = diff if diff > 0 else 0

            segments.append(
                RouteSegment(
                    trip_id=trip_id,
                    route_name=route_name,
                    departure_stop=dep_stop,
                    departure_stop_name=self.data.get_stop_name(dep_stop),
                    departure_time=dep_time,
                    arrival_stop=arr_stop,
                    arrival_stop_name=self.data.get_stop_name(arr_stop),
                    arrival_time=arr_time,
                    wait_time=wait_time,
                )
            )
            idx += 1

        return segments

    def _try_insert_label(self, labels_by_stop, stop_id, label, max_labels_per_stop):
        labels = labels_by_stop.get(stop_id)
        if labels is None:
            labels_by_stop[stop_id] = [label]
            return True

        if len(labels) >= max_labels_per_stop and label.arrival_time >= labels[-1].arrival_time:
            return False

        # dedupe
        i = 0
        while i < len(labels):
            existing = labels[i]
            if (
                existing.arrival_time == label.arrival_time
                and existing.trip_id == label.trip_id
                and existing.dep_stop == label.dep_stop
                and existing.dep_time == label.dep_time
                and existing.prev is label.prev
            ):
                return False
            i += 1

        # insert sorted by arrival_time
        idx = 0
        while idx < len(labels) and labels[idx].arrival_time <= label.arrival_time:
            idx += 1
        labels.insert(idx, label)
        if len(labels) > max_labels_per_stop:
            labels.pop()
        return True

    def _recompute_worst_end_arrival(self, labels_by_stop, end_ids, max_routes):
        all_times = []
        for eid in end_ids:
            labels = labels_by_stop.get(eid)
            if labels is not None:
                i = 0
                while i < len(labels):
                    lab = labels[i]
                    all_times.append(lab.arrival_time)
                    i += 1

        if len(all_times) < max_routes:
            return None
        all_times.sort()
        return all_times[max_routes - 1]

    def _find_multiple_routes(
        self,
        connections,
        start_stop,
        end_stop,
        start_time_sec,
        max_routes=3,
        start_stop_ids=None,
        end_stop_ids=None,
    ):
        max_labels_per_stop = max(8, max_routes * 3)
        labels_by_stop = {}

        effective_start_ids = start_stop_ids if start_stop_ids is not None else [start_stop]
        effective_end_ids = end_stop_ids if end_stop_ids is not None else set([end_stop])

        i = 0
        while i < len(effective_start_ids):
            sid = effective_start_ids[i]
            start_label = _Label(stop_id=sid, arrival_time=int(start_time_sec), prev=None)
            labels = labels_by_stop.get(sid)
            if labels is None:
                labels_by_stop[sid] = [start_label]
            else:
                # insertion at end is fine: all start labels have same arrival_time
                labels.append(start_label)
            i += 1

        worst_end_arrival = None

        # Scan connections in dep_time order
        idx = 0
        while idx < len(connections):
            dep_time, trip_id, dep_stop, arr_stop, arr_time, route_name = connections[idx]

            if worst_end_arrival is not None and dep_time > worst_end_arrival:
                break

            dep_labels = labels_by_stop.get(dep_stop)
            if dep_labels is None:
                idx += 1
                continue

            # dep_labels are sorted by arrival_time
            j = 0
            while j < len(dep_labels):
                lab = dep_labels[j]
                if lab.arrival_time > dep_time:
                    break

                new_label = _Label(
                    stop_id=arr_stop,
                    arrival_time=int(arr_time),
                    prev=lab,
                    trip_id=trip_id,
                    route_name=route_name or "",
                    dep_stop=dep_stop,
                    dep_time=int(dep_time),
                )
                inserted = self._try_insert_label(
                    labels_by_stop, arr_stop, new_label, max_labels_per_stop
                )
                if inserted and arr_stop in effective_end_ids:
                    worst_end_arrival = self._recompute_worst_end_arrival(
                        labels_by_stop, effective_end_ids, max_routes
                    )

                j += 1

            idx += 1

        # Collect end labels
        end_labels = []
        for eid in effective_end_ids:
            labels = labels_by_stop.get(eid)
            if labels is not None:
                i = 0
                while i < len(labels):
                    end_labels.append(labels[i])
                    i += 1

        if not end_labels:
            return []

        # sort by arrival_time using tuples
        pairs = []
        i = 0
        while i < len(end_labels):
            lab = end_labels[i]
            pairs.append((lab.arrival_time, id(lab), lab))
            i += 1
        pairs.sort()

        routes = []
        seen_hashes = set()

        i = 0
        while i < len(pairs) and len(routes) < max_routes:
            lab = pairs[i][2]
            segs = self._reconstruct_route_from_label(lab)
            if segs is None:
                i += 1
                continue

            # route hash (imperative)
            route_hash_list = []
            j = 0
            while j < len(segs):
                seg = segs[j]
                route_hash_list.append(
                    (seg.departure_stop, seg.arrival_stop, seg.departure_time, seg.arrival_time)
                )
                j += 1
            route_hash = tuple(route_hash_list)
            if route_hash in seen_hashes:
                i += 1
                continue
            seen_hashes.add(route_hash)
            routes.append(segs)
            i += 1

        return routes

    def find_route_by_ids(
        self,
        start_id,
        end_id,
        start_name,
        end_name,
        date,
        time,
        max_routes=5,
    ):
        try:
            if len(date) == 8:
                travel_date = datetime.strptime(date, "%Y%m%d")
            else:
                travel_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            print(f"Ungültiges Datumsformat: {date}")
            return []

        try:
            parts = time.split(":")
            start_time_sec = int(parts[0]) * 3600 + int(parts[1]) * 60
        except (ValueError, IndexError):
            print(f"Ungültiges Zeitformat: {time}")
            return []

        if start_id == end_id:
            print("Start- und Zielstation sind identisch!")
            return []

        print(f"\nBaue Verbindungen für {travel_date.strftime('%Y-%m-%d')}...")
        connections = self._build_connections(travel_date, start_time_sec)
        print(f"  {len(connections)} Verbindungen gefunden")
        print("Berechne optimale Routen...")

        start_ids = self.data.expand_station_stop_ids(start_id)
        end_ids = set(self.data.expand_station_stop_ids(end_id))

        routes = self._find_multiple_routes(
            connections,
            start_id,
            end_id,
            start_time_sec,
            max_routes=max_routes,
            start_stop_ids=start_ids,
            end_stop_ids=end_ids,
        )
        return routes


