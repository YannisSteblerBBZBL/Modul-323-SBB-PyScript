import pandas as pd
import numpy as np
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, DefaultDict
from collections import defaultdict

from models import RouteSegment
from data_loader import GTFSDataLoader


class RouteCalculator:
    """Klasse für die Routenberechnung mit dem Connection Scan Algorithm"""
    
    def __init__(self, data_loader: GTFSDataLoader):
        """
        Initialisiert den RouteCalculator
        
        Args:
            data_loader: GTFSDataLoader-Instanz mit geladenen Daten
        """
        self.data = data_loader
    
    @staticmethod
    def time_to_seconds(time_str: str) -> int:
        """
        Konvertiert GTFS-Zeitformat (HH:MM:SS) zu Sekunden seit Mitternacht
        
        Args:
            time_str: Zeitstring im Format "HH:MM:SS" oder "H:MM:SS"
            
        Returns:
            Sekunden seit Mitternacht
        """
        if pd.isna(time_str) or time_str == '':
            return 0
        
        try:
            parts = str(time_str).split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2]) if len(parts) > 2 else 0
            
            # GTFS erlaubt Zeiten > 24:00:00 für Übernacht-Verbindungen
            return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            return 0
    
    @staticmethod
    def seconds_to_time(seconds: int) -> str:
        """Konvertiert Sekunden seit Mitternacht zu HH:MM Format"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    
    def _build_connections(self, date: datetime, start_time_sec: int) -> pd.DataFrame:
        """
        Baut alle gültigen Verbindungen (Connections) als DataFrame.

        WICHTIG: Eine Connection ist nur der Übergang von stop_sequence i -> i+1 innerhalb eines Trips.
        Das reduziert die Datenmenge drastisch (kein O(n^2) Self-Join mehr).
        
        Args:
            date: Reisedatum
            start_time_sec: Startzeit in Sekunden seit Mitternacht
            
        Returns:
            DataFrame mit Spalten: trip_id, dep_stop, arr_stop, dep_time, arr_time, route_name
            sortiert nach dep_time
        """
        # Filtere trips nach gültigen services
        valid_services = self.data.get_valid_services(date)
        if not valid_services:
            print(f"  ⚠ Warnung: Keine gültigen Services für {date.strftime('%Y-%m-%d')} gefunden!")
            print(f"     Prüfen Sie, ob das Datum im Gültigkeitsbereich der GTFS-Daten liegt.")
            return pd.DataFrame(columns=['trip_id', 'dep_stop', 'arr_stop', 'dep_time', 'arr_time', 'route_name'])
        valid_trips = self.data.trips[self.data.trips['service_id'].isin(valid_services)]
        
        # Merge mit stop_times (nur Trips dieses Datums)
        trip_stops = self.data.stop_times.merge(
            valid_trips[['trip_id', 'route_id', 'route_name']],
            on='trip_id',
            how='inner'
        )
        
        # Filtere früh nach Startzeit für bessere Performance
        trip_stops = trip_stops[trip_stops['departure_time_sec'] >= start_time_sec].copy()
        
        if len(trip_stops) == 0:
            return pd.DataFrame(columns=['trip_id', 'dep_stop', 'arr_stop', 'dep_time', 'arr_time', 'route_name'])
        
        # Sortieren innerhalb Trip, dann "next stop" vektorisiert bauen
        trip_stops_sorted = trip_stops.sort_values(
            ['trip_id', 'stop_sequence'],
            kind='mergesort'
        ).reset_index(drop=True)

        # Nächste Haltestelle und deren Ankunftszeit innerhalb desselben Trips
        trip_stops_sorted['next_stop'] = trip_stops_sorted.groupby('trip_id')['stop_id'].shift(-1)
        trip_stops_sorted['next_arrival_time_sec'] = trip_stops_sorted.groupby('trip_id')['arrival_time_sec'].shift(-1)

        conns = trip_stops_sorted[trip_stops_sorted['next_stop'].notna()].copy()

        conns = conns.rename(columns={
            'stop_id': 'dep_stop',
            'departure_time_sec': 'dep_time',
            'next_stop': 'arr_stop',
            'next_arrival_time_sec': 'arr_time'
        })

        # Nur valide Zeitreihen (Ankunft nach Abfahrt)
        conns = conns[conns['arr_time'] > conns['dep_time']].copy()

        # route_name kann NaN sein
        conns['route_name'] = conns['route_name'].fillna('')

        conns = conns[['trip_id', 'dep_stop', 'arr_stop', 'dep_time', 'arr_time', 'route_name']]
        # arr_time ist wegen shift float; cast nach Filter
        conns['dep_time'] = conns['dep_time'].astype(np.int32)
        conns['arr_time'] = conns['arr_time'].astype(np.int32)

        # Sortiere nach Abfahrtszeit für CSA
        conns = conns.sort_values('dep_time', kind='mergesort').reset_index(drop=True)
        return conns
    
    @dataclass(frozen=True)
    class _Label:
        """Interner Pfad-Label für K-begrenzten CSA."""
        stop_id: str
        arrival_time: int
        prev: Optional["RouteCalculator._Label"]
        # Connection-Infos, die zu diesem Label geführt haben (prev -> stop_id)
        trip_id: Optional[str] = None
        route_name: str = ""
        dep_stop: Optional[str] = None
        dep_time: Optional[int] = None

    def _reconstruct_route_from_label(self, end_label: "RouteCalculator._Label") -> Optional[List[RouteSegment]]:
        """
        Rekonstruiert eine Route aus einer Label-Kette.
        """
        # Sammle Connections rückwärts
        connections_rev: List[Tuple[str, str, str, int, str, int]] = []
        visited = set()
        cur = end_label
        while cur.prev is not None:
            # Schutz gegen (unerwartete) Zyklen in der Pointer-Kette
            obj_id = id(cur)
            if obj_id in visited:
                return None
            visited.add(obj_id)

            if cur.trip_id is None or cur.dep_stop is None or cur.dep_time is None:
                return None

            connections_rev.append((
                cur.trip_id,
                cur.route_name or "",
                cur.dep_stop,
                int(cur.dep_time),
                cur.stop_id,
                int(cur.arrival_time),
            ))
            cur = cur.prev

        if not connections_rev:
            return None

        connections_list = list(reversed(connections_rev))

        # Optimiere Route: Fasse zusammenhängende Fahrten im selben Trip zusammen
        optimized_connections: List[Tuple[str, str, str, int, str, int]] = []
        current_trip, current_route, first_dep_stop, first_dep_time, last_arr_stop, last_arr_time = connections_list[0]

        for trip_id, route_name, dep_stop, dep_time, arr_stop, arr_time in connections_list[1:]:
            if (trip_id == current_trip and last_arr_stop == dep_stop and last_arr_time <= dep_time):
                last_arr_stop = arr_stop
                last_arr_time = arr_time
            else:
                optimized_connections.append((
                    current_trip, current_route,
                    first_dep_stop, first_dep_time,
                    last_arr_stop, last_arr_time
                ))
                current_trip = trip_id
                current_route = route_name
                first_dep_stop = dep_stop
                first_dep_time = dep_time
                last_arr_stop = arr_stop
                last_arr_time = arr_time

        optimized_connections.append((
            current_trip, current_route,
            first_dep_stop, first_dep_time,
            last_arr_stop, last_arr_time
        ))

        # RouteSegments erzeugen inkl. Wartezeiten
        route_segments: List[RouteSegment] = []
        for i, (trip_id, route_name, dep_stop, dep_time, arr_stop, arr_time) in enumerate(optimized_connections):
            wait_time = 0
            if i > 0:
                prev_arr_stop = optimized_connections[i - 1][4]
                prev_arr_time = optimized_connections[i - 1][5]
                if prev_arr_stop == dep_stop:
                    wait_time = max(0, dep_time - prev_arr_time)

            route_segments.append(RouteSegment(
                trip_id=trip_id,
                route_name=route_name,
                departure_stop=dep_stop,
                departure_stop_name=self.data.get_stop_name(dep_stop),
                departure_time=dep_time,
                arrival_stop=arr_stop,
                arrival_stop_name=self.data.get_stop_name(arr_stop),
                arrival_time=arr_time,
                wait_time=wait_time
            ))

        return route_segments
    
    def _find_multiple_routes(
        self,
        connections: pd.DataFrame,
        start_stop: str,
        end_stop: str,
        start_time_sec: int,
        max_routes: int = 3,
        start_stop_ids: Optional[List[str]] = None,
        end_stop_ids: Optional[set] = None
    ) -> List[List[RouteSegment]]:
        """
        Findet mehrere Routen zwischen Start und Ziel.

        Performance-Fokus:
        - Pro Stop werden nur die besten K Labels gehalten (statt Millionen Routen zu sammeln)
        - Kein Dict-Copy pro Pfad, sondern Pointer-Kette (Label.prev)
        - Early-Stop: sobald wir max_routes Ziel-Labels haben und dep_time > schlechteste Ziel-Ankunft
        
        Args:
            connections: DataFrame mit allen gültigen Connections
            start_stop: stop_id des Startpunkts
            end_stop: stop_id des Zielpunkts
            start_time_sec: Startzeit in Sekunden seit Mitternacht
            max_routes: Maximale Anzahl von Routen die zurückgegeben werden
            
        Returns:
            Liste von Routen (jede Route ist eine Liste von RouteSegment-Objekten)
        """
        # Pro Stop nur die besten K Labels nach arrival_time behalten
        max_labels_per_stop = max(8, max_routes * 3)

        labels_by_stop: DefaultDict[str, List[RouteCalculator._Label]] = defaultdict(list)

        effective_start_ids = start_stop_ids if start_stop_ids else [start_stop]
        effective_end_ids = end_stop_ids if end_stop_ids else {end_stop}

        for sid in effective_start_ids:
            start_label = RouteCalculator._Label(stop_id=sid, arrival_time=int(start_time_sec), prev=None)
            labels_by_stop[sid].append(start_label)

        def try_insert_label(stop_id: str, label: RouteCalculator._Label) -> bool:
            labels = labels_by_stop[stop_id]
            # Schnell-Pruning: wenn voll und nicht besser als schlechtester
            if len(labels) >= max_labels_per_stop and label.arrival_time >= labels[-1].arrival_time:
                return False

            # Duplikate vermeiden (sehr grob, reicht für K klein)
            for existing in labels:
                if (existing.arrival_time == label.arrival_time and
                    existing.trip_id == label.trip_id and
                    existing.dep_stop == label.dep_stop and
                    existing.dep_time == label.dep_time and
                    existing.prev is label.prev):
                    return False

            # Insert sortiert nach arrival_time (K klein -> linear ok)
            i = 0
            while i < len(labels) and labels[i].arrival_time <= label.arrival_time:
                i += 1
            labels.insert(i, label)

            if len(labels) > max_labels_per_stop:
                labels.pop()
            return True

        # Early-stop Schwelle für Ziel
        worst_end_arrival: Optional[int] = None

        def recompute_worst_end_arrival() -> Optional[int]:
            # Aggregiere Ziel-Labels über alle Plattformen/Station
            all_end = []
            for eid in effective_end_ids:
                all_end.extend(labels_by_stop.get(eid, []))
            if len(all_end) < max_routes:
                return None
            all_end.sort(key=lambda x: x.arrival_time)
            return all_end[max_routes - 1].arrival_time

        for row in connections.itertuples(index=False, name=None):
            trip_id, dep_stop, arr_stop, dep_time, arr_time, route_name = row
            dep_time_i = int(dep_time)
            arr_time_i = int(arr_time)

            # Early stop: wir haben genug Zielrouten und sind zeitlich dahinter
            if worst_end_arrival is not None and dep_time_i > worst_end_arrival:
                break

            if dep_stop not in labels_by_stop:
                continue

            dep_labels = labels_by_stop[dep_stop]
            # Labels sind nach arrival_time sortiert -> sobald > dep_time abbrechen
            for lab in dep_labels:
                if lab.arrival_time > dep_time_i:
                    break

                new_label = RouteCalculator._Label(
                    stop_id=arr_stop,
                    arrival_time=arr_time_i,
                    prev=lab,
                    trip_id=trip_id,
                    route_name=route_name or "",
                    dep_stop=dep_stop,
                    dep_time=dep_time_i,
                )

                inserted = try_insert_label(arr_stop, new_label)
                if inserted and arr_stop in effective_end_ids:
                    worst_end_arrival = recompute_worst_end_arrival()

        # Alle Ziel-Labels sammeln (über alle Plattformen)
        all_end_labels: List[RouteCalculator._Label] = []
        for eid in effective_end_ids:
            all_end_labels.extend(labels_by_stop.get(eid, []))
        if not all_end_labels:
            return []

        # Rekonstruiere die besten max_routes (nach Ankunftszeit)
        all_end_labels.sort(key=lambda x: x.arrival_time)
        routes: List[List[RouteSegment]] = []
        seen_hashes = set()
        for lab in all_end_labels[:max_routes]:
            route_segments = self._reconstruct_route_from_label(lab)
            if not route_segments:
                continue
            route_hash = tuple((seg.departure_stop, seg.arrival_stop, seg.departure_time, seg.arrival_time)
                               for seg in route_segments)
            if route_hash in seen_hashes:
                continue
            seen_hashes.add(route_hash)
            routes.append(route_segments)
            if len(routes) >= max_routes:
                break

        return routes
    
    def _connection_scan_algorithm(
        self,
        connections: pd.DataFrame,
        start_stop: str,
        end_stop: str,
        start_time_sec: int
    ) -> Optional[List[RouteSegment]]:
        """
        Implementiert den Connection Scan Algorithm (CSA) für die Routenfindung
        Findet die schnellste Route (nach Gesamtreisezeit)
        
        Args:
            connections: Liste aller gültigen Connections, sortiert nach departure_time
            start_stop: stop_id des Startpunkts
            end_stop: stop_id des Zielpunkts
            start_time_sec: Startzeit in Sekunden seit Mitternacht
            
        Returns:
            Liste von RouteSegment-Objekten oder None wenn keine Route gefunden
        """
        routes = self._find_multiple_routes(connections, start_stop, end_stop, start_time_sec, max_routes=1)
        if routes:
            return routes[0]
        return None
    
    def find_route(
        self,
        start_name: str,
        end_name: str,
        date: str,
        time: str,
        max_routes: int = 5
    ) -> List[List[RouteSegment]]:
        """
        Hauptfunktion: Findet die schnellsten Routen zwischen zwei Stationen
        
        Args:
            start_name: Name der Startstation
            end_name: Name der Zielstation
            date: Reisedatum im Format "YYYY-MM-DD" oder "YYYYMMDD"
            time: Startzeit im Format "HH:MM"
            
        Returns:
            Liste von Routen (jede Route ist eine Liste von RouteSegment-Objekten)
        """
        # Parse Datum
        try:
            if len(date) == 8:  # YYYYMMDD
                travel_date = datetime.strptime(date, '%Y%m%d')
            else:  # YYYY-MM-DD
                travel_date = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            print(f"Ungültiges Datumsformat: {date}")
            return []
        
        # Parse Zeit
        try:
            time_parts = time.split(':')
            start_time_sec = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60
        except (ValueError, IndexError):
            print(f"Ungültiges Zeitformat: {time}")
            return []
        
        # Map Stationsnamen zu stop_ids
        start_id = self.data.find_stop_id(start_name)
        end_id = self.data.find_stop_id(end_name)
        
        if start_id is None:
            print(f"Startstation '{start_name}' nicht gefunden!")
            return []
        
        if end_id is None:
            print(f"Zielstation '{end_name}' nicht gefunden!")
            return []
        
        if start_id == end_id:
            print("Start- und Zielstation sind identisch!")
            return []
        
        # Baue Connections für dieses Datum
        print(f"\nBaue Verbindungen für {travel_date.strftime('%Y-%m-%d')}...")
        connections = self._build_connections(travel_date, start_time_sec)
        print(f"  {len(connections)} Verbindungen gefunden")
        
        # Wende Multi-Route-Algorithmus an
        print("\nBerechne optimale Routen...")
        start_ids = self.data.expand_station_stop_ids(start_id)
        end_ids = set(self.data.expand_station_stop_ids(end_id))
        routes = self._find_multiple_routes(
            connections,
            start_id,
            end_id,
            start_time_sec,
            max_routes=max_routes,
            start_stop_ids=start_ids,
            end_stop_ids=end_ids
        )
        
        return routes
    
    def find_route_by_ids(
        self,
        start_id: str,
        end_id: str,
        start_name: str,
        end_name: str,
        date: str,
        time: str,
        max_routes: int = 5
    ) -> List[List[RouteSegment]]:
        """
        Findet Routen direkt mit stop_ids (umgeht Namenssuche)
        
        Args:
            start_id: stop_id der Startstation
            end_id: stop_id der Zielstation
            start_name: Name der Startstation (für Ausgabe)
            end_name: Name der Zielstation (für Ausgabe)
            date: Reisedatum im Format "YYYY-MM-DD" oder "YYYYMMDD"
            time: Startzeit im Format "HH:MM"
            
        Returns:
            Liste von Routen (jede Route ist eine Liste von RouteSegment-Objekten)
        """
        # Parse Datum
        try:
            if len(date) == 8:  # YYYYMMDD
                travel_date = datetime.strptime(date, '%Y%m%d')
            else:  # YYYY-MM-DD
                travel_date = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            print(f"Ungültiges Datumsformat: {date}")
            return []
        
        # Parse Zeit
        try:
            time_parts = time.split(':')
            start_time_sec = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60
        except (ValueError, IndexError):
            print(f"Ungültiges Zeitformat: {time}")
            return []
        
        if start_id == end_id:
            print("Start- und Zielstation sind identisch!")
            return []
        
        # Baue Connections für dieses Datum
        print(f"\nBaue Verbindungen für {travel_date.strftime('%Y-%m-%d')}...")
        connections = self._build_connections(travel_date, start_time_sec)
        print(f"  {len(connections)} Verbindungen gefunden")
        
        # Wende Multi-Route-Algorithmus an
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
            end_stop_ids=end_ids
        )
        
        return routes
