import csv
import os
from datetime import datetime


class GTFSDataLoader:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir

        # Stops
        self.stops = []  # list of dicts: stop_id, stop_name, parent_station
        self.stop_id_to_name = {}
        self._stop_to_parent = {}
        self._parent_to_children = {}

        # Stop times
        # dict trip_id -> list of tuples (stop_sequence, stop_id, arrival_sec, departure_sec)
        self.stop_times_by_trip = {}

        # Trips + routes
        self.trip_to_service = {}
        self.trip_to_route_name = {}
        self.service_cache = {}

        # Calendar
        # dict service_id -> dict(start_date,end_date, weekdays dict)
        self.calendar = {}
        # dict date_yyyymmdd -> list of (service_id, exception_type)
        self.calendar_dates = {}

        print("Lade GTFS-Daten...")
        self._load_data()
        print("Daten erfolgreich geladen!")

    def _load_data(self):
        self._load_stops()
        self._load_stop_times()
        self._load_routes_and_trips()
        self._load_calendar()
        self._load_calendar_dates()

    def _load_stops(self):
        path = os.path.join(self.data_dir, "stops.txt")
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stop_id = (row.get("stop_id") or "").strip()
                stop_name = (row.get("stop_name") or "").strip()
                parent_station = (row.get("parent_station") or "").strip()
                if not stop_id:
                    continue

                item = {
                    "stop_id": stop_id,
                    "stop_name": stop_name,
                    "parent_station": parent_station,
                }
                self.stops.append(item)
                self.stop_id_to_name[stop_id] = stop_name
                self._stop_to_parent[stop_id] = parent_station
                if parent_station:
                    children = self._parent_to_children.get(parent_station)
                    if children is None:
                        self._parent_to_children[parent_station] = [stop_id]
                    else:
                        children.append(stop_id)

    def _load_stop_times(self):
        print("  Lade stop_times.txt (dies kann einige Zeit dauern)...")
        path = os.path.join(self.data_dir, "stop_times.txt")
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trip_id = (row.get("trip_id") or "").strip()
                stop_id = (row.get("stop_id") or "").strip()
                if not trip_id or not stop_id:
                    continue

                seq_raw = (row.get("stop_sequence") or "").strip()
                try:
                    stop_sequence = int(seq_raw)
                except ValueError:
                    continue

                arrival_time = (row.get("arrival_time") or "").strip()
                departure_time = (row.get("departure_time") or "").strip()
                arrival_sec = self._parse_gtfs_time_to_seconds(arrival_time)
                departure_sec = self._parse_gtfs_time_to_seconds(departure_time)

                tup = (stop_sequence, stop_id, arrival_sec, departure_sec)
                lst = self.stop_times_by_trip.get(trip_id)
                if lst is None:
                    self.stop_times_by_trip[trip_id] = [tup]
                else:
                    lst.append(tup)

        # sort each trip by stop_sequence (imperative, no key=...)
        for trip_id in self.stop_times_by_trip:
            self.stop_times_by_trip[trip_id].sort()

    def _load_routes_and_trips(self):
        # routes: route_id -> route_name
        routes_path = os.path.join(self.data_dir, "routes.txt")
        route_id_to_name = {}
        with open(routes_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                route_id = (row.get("route_id") or "").strip()
                if not route_id:
                    continue
                short_name = (row.get("route_short_name") or "").strip()
                long_name = (row.get("route_long_name") or "").strip()
                name = short_name
                if not name:
                    name = long_name if long_name else "Unbekannt"
                route_id_to_name[route_id] = name.strip()

        trips_path = os.path.join(self.data_dir, "trips.txt")
        with open(trips_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trip_id = (row.get("trip_id") or "").strip()
                route_id = (row.get("route_id") or "").strip()
                service_id = (row.get("service_id") or "").strip()
                if not trip_id or not service_id:
                    continue
                self.trip_to_service[trip_id] = service_id
                self.trip_to_route_name[trip_id] = route_id_to_name.get(route_id, "")

    def _load_calendar(self):
        path = os.path.join(self.data_dir, "calendar.txt")
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                service_id = (row.get("service_id") or "").strip()
                if not service_id:
                    continue
                start_raw = (row.get("start_date") or "").strip()
                end_raw = (row.get("end_date") or "").strip()
                try:
                    start_date = datetime.strptime(start_raw, "%Y%m%d")
                    end_date = datetime.strptime(end_raw, "%Y%m%d")
                except ValueError:
                    continue

                weekdays = {
                    "monday": (row.get("monday") or "0").strip() == "1",
                    "tuesday": (row.get("tuesday") or "0").strip() == "1",
                    "wednesday": (row.get("wednesday") or "0").strip() == "1",
                    "thursday": (row.get("thursday") or "0").strip() == "1",
                    "friday": (row.get("friday") or "0").strip() == "1",
                    "saturday": (row.get("saturday") or "0").strip() == "1",
                    "sunday": (row.get("sunday") or "0").strip() == "1",
                }
                self.calendar[service_id] = {
                    "start_date": start_date,
                    "end_date": end_date,
                    "weekdays": weekdays,
                }

    def _load_calendar_dates(self):
        print("  Lade calendar_dates.txt...")
        path = os.path.join(self.data_dir, "calendar_dates.txt")
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                service_id = (row.get("service_id") or "").strip()
                date_raw = (row.get("date") or "").strip()
                exc_raw = (row.get("exception_type") or "").strip()
                if not service_id or not date_raw:
                    continue
                try:
                    exc_type = int(exc_raw)
                except ValueError:
                    continue
                lst = self.calendar_dates.get(date_raw)
                if lst is None:
                    self.calendar_dates[date_raw] = [(service_id, exc_type)]
                else:
                    lst.append((service_id, exc_type))

    def _get_weekday_name(self, date_obj):
        weekdays = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        return weekdays[date_obj.weekday()]

    def get_valid_services(self, date_obj):
        date_str = date_obj.strftime("%Y%m%d")
        cached = self.service_cache.get(date_str)
        if cached is not None:
            return cached

        valid = set()
        weekday = self._get_weekday_name(date_obj)

        for service_id in self.calendar:
            cal = self.calendar[service_id]
            if cal["start_date"] <= date_obj <= cal["end_date"]:
                if cal["weekdays"].get(weekday):
                    valid.add(service_id)

        exceptions = self.calendar_dates.get(date_str)
        if exceptions is not None:
            i = 0
            while i < len(exceptions):
                service_id, exc_type = exceptions[i]
                if exc_type == 1:
                    valid.add(service_id)
                elif exc_type == 2:
                    if service_id in valid:
                        valid.remove(service_id)
                i += 1

        self.service_cache[date_str] = valid
        return valid

    def find_stop_id(self, stop_name):
        needle = self._normalize_name(stop_name)
        if not needle:
            return None

        # exact
        i = 0
        while i < len(self.stops):
            s = self.stops[i]
            if self._normalize_name(s["stop_name"]) == needle:
                return s["stop_id"]
            i += 1

        # startswith
        i = 0
        while i < len(self.stops):
            s = self.stops[i]
            norm = self._normalize_name(s["stop_name"])
            if norm.startswith(needle):
                return s["stop_id"]
            i += 1

        return None

    def find_matching_stops(self, stop_name):
        needle = self._normalize_name(stop_name)
        if not needle:
            return []

        exact = []
        starts = []

        i = 0
        while i < len(self.stops):
            name = self.stops[i]["stop_name"]
            norm = self._normalize_name(name)
            if norm == needle:
                exact.append(name)
            elif norm.startswith(needle):
                starts.append(name)
            i += 1

        # unique (preserve order)
        result = []
        seen = set()

        i = 0
        while i < len(exact):
            n = exact[i]
            if n not in seen:
                seen.add(n)
                result.append(n)
            i += 1

        starts.sort()
        i = 0
        while i < len(starts):
            n = starts[i]
            if n not in seen:
                seen.add(n)
                result.append(n)
            i += 1

        return result

    def find_similar_stops(self, stop_name, max_results=10):
        needle = self._normalize_name(stop_name)
        if not needle:
            return []

        matches = []
        i = 0
        while i < len(self.stops):
            name = self.stops[i]["stop_name"]
            norm = self._normalize_name(name)
            if needle in norm:
                matches.append(name)
            i += 1

        matches.sort()

        # unique + limit
        result = []
        seen = set()
        i = 0
        while i < len(matches) and len(result) < max_results:
            n = matches[i]
            if n not in seen:
                seen.add(n)
                result.append(n)
            i += 1
        return result

    def get_stop_name(self, stop_id):
        return self.stop_id_to_name.get(stop_id, "")

    def expand_station_stop_ids(self, stop_id):
        if stop_id is None:
            return []
        stop_id = str(stop_id).strip()
        if not stop_id:
            return []

        parent = (self._stop_to_parent.get(stop_id) or "").strip()
        station_id = parent if parent else stop_id

        result = [station_id]
        children = self._parent_to_children.get(station_id)
        if children is not None:
            i = 0
            while i < len(children):
                result.append(children[i])
                i += 1

        uniq = []
        seen = set()
        i = 0
        while i < len(result):
            x = result[i]
            if x not in seen:
                seen.add(x)
                uniq.append(x)
            i += 1
        return uniq

    def _normalize_name(self, value):
        if value is None:
            return ""
        s = str(value).strip()
        if not s:
            return ""
        return s.casefold()

    def _parse_gtfs_time_to_seconds(self, value):
        # supports times beyond 24:00:00
        if value is None:
            return 0
        s = str(value).strip()
        if not s:
            return 0
        parts = s.split(":")
        if len(parts) < 2:
            return 0
        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2]) if len(parts) >= 3 and parts[2] != "" else 0
        except ValueError:
            return 0
        return hours * 3600 + minutes * 60 + seconds


