import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Tuple, Optional
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
        Baut alle gültigen Verbindungen (Connections) als DataFrame via Self-Join.
        
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
            return pd.DataFrame(columns=['trip_id', 'dep_stop', 'arr_stop', 'dep_time', 'arr_time', 'route_name'])
        valid_trips = self.data.trips[self.data.trips['service_id'].isin(valid_services)]
        
        # Merge mit stop_times (nur Trips dieses Datums)
        trip_stops = self.data.stop_times.merge(
            valid_trips[['trip_id', 'route_id', 'route_name']],
            on='trip_id',
            how='inner'
        )
        
        # Split in "current" (Abfahrtszeile) und "next" (Ankunft an nächster Haltestelle)
        curr = trip_stops[['trip_id', 'stop_sequence', 'stop_id', 'departure_time_sec', 'route_name']].rename(
            columns={
                'stop_id': 'dep_stop',
                'departure_time_sec': 'dep_time'
            }
        )
        # Filter früh nach Startzeit, um Datenmenge zu reduzieren
        curr = curr[curr['dep_time'] >= start_time_sec]
        
        nxt = trip_stops[['trip_id', 'stop_sequence', 'stop_id', 'arrival_time_sec']].rename(
            columns={
                'stop_id': 'arr_stop',
                'arrival_time_sec': 'arr_time'
            }
        ).copy()
        # Verschiebe Sequenz, damit stop_sequence übereinstimmt (dep i -> arr i+1)
        nxt['stop_sequence'] = (nxt['stop_sequence'] - 1).astype(np.int32)
        
        # Verbinde dep- mit arr-Zeilen
        conns = curr.merge(
            nxt,
            on=['trip_id', 'stop_sequence'],
            how='inner'
        )[['trip_id', 'dep_stop', 'arr_stop', 'dep_time', 'arr_time', 'route_name']]
        
        # Sortiere nach Abfahrtszeit
        conns = conns.sort_values('dep_time', kind='mergesort').reset_index(drop=True)
        return conns
    
    def _connection_scan_algorithm(
        self,
        connections: pd.DataFrame,
        start_stop: str,
        end_stop: str,
        start_time_sec: int
    ) -> Optional[List[RouteSegment]]:
        """
        Implementiert den Connection Scan Algorithm (CSA) für die Routenfindung
        
        Args:
            connections: Liste aller gültigen Connections, sortiert nach departure_time
            start_stop: stop_id des Startpunkts
            end_stop: stop_id des Zielpunkts
            start_time_sec: Startzeit in Sekunden seit Mitternacht
            
        Returns:
            Liste von RouteSegment-Objekten oder None wenn keine Route gefunden
        """
        # earliest_arrival[stop_id] = früheste Ankunftszeit an diesem Stop
        INF = 1 << 60
        earliest_arrival: Dict[str, int] = defaultdict(lambda: INF)
        earliest_arrival[start_stop] = start_time_sec
        
        # previous_connection[stop_id] = minimale Info zur Connection
        # gespeicherte Tuple: (trip_id, route_name, dep_stop, dep_time, arr_stop, arr_time)
        previous_connection: Dict[str, Tuple[str, str, str, int, str, int]] = {}
        
        # Scanne alle Connections in chronologischer Reihenfolge (DataFrame ist sortiert)
        it = connections.itertuples(index=False, name=None)  # yields tuples in column order
        for trip_id, dep_stop, arr_stop, dep_time, arr_time, route_name in it:
            # Prüfe Erreichbarkeit
            if earliest_arrival[dep_stop] <= dep_time:
                if arr_time < earliest_arrival[arr_stop]:
                    earliest_arrival[arr_stop] = int(arr_time)
                    previous_connection[arr_stop] = (trip_id, route_name or "", dep_stop, int(dep_time), arr_stop, int(arr_time))
        
        # Rekonstruiere Route rückwärts
        if earliest_arrival[end_stop] == INF:
            return None
        
        route_segments = []
        current_stop = end_stop
        
        # Sammle Connections in umgekehrter Reihenfolge
        connections_list: List[Tuple[str, str, str, int, str, int]] = []
        while current_stop != start_stop:
            if current_stop not in previous_connection:
                return None
            
            conn_tuple = previous_connection[current_stop]
            connections_list.append(conn_tuple)
            # conn_tuple = (trip_id, route_name, dep_stop, dep_time, arr_stop, arr_time)
            current_stop = conn_tuple[2]
        
        # Kehre um, damit wir vorwärts durchgehen können
        connections_list.reverse()
        
        # Erstelle Segmente mit korrekter Wartezeitberechnung
        for i, (trip_id, route_name, dep_stop, dep_time, arr_stop, arr_time) in enumerate(connections_list):
            # Wartezeit = Abfahrt dieser Connection - Ankunft der vorherigen Connection
            # am selben Stop (Umstiegsstop)
            wait_time = 0
            if i > 0:
                prev_arr_stop = connections_list[i - 1][4]
                prev_arr_time = connections_list[i - 1][5]
                # Sicherstellen, dass die Connection am selben Stop ankommt/abfährt
                if prev_arr_stop == dep_stop:
                    wait_time = max(0, dep_time - prev_arr_time)
            
            segment = RouteSegment(
                trip_id=trip_id,
                route_name=route_name,
                departure_stop=dep_stop,
                departure_stop_name=self.data.get_stop_name(dep_stop),
                departure_time=dep_time,
                arrival_stop=arr_stop,
                arrival_stop_name=self.data.get_stop_name(arr_stop),
                arrival_time=arr_time,
                wait_time=wait_time
            )
            route_segments.append(segment)
        
        return route_segments
    
    def find_route(
        self,
        start_name: str,
        end_name: str,
        date: str,
        time: str
    ) -> Optional[List[RouteSegment]]:
        """
        Hauptfunktion: Findet die schnellste Route zwischen zwei Stationen
        
        Args:
            start_name: Name der Startstation
            end_name: Name der Zielstation
            date: Reisedatum im Format "YYYY-MM-DD" oder "YYYYMMDD"
            time: Startzeit im Format "HH:MM"
            
        Returns:
            Liste von RouteSegment-Objekten oder None wenn keine Route gefunden
        """
        # Parse Datum
        try:
            if len(date) == 8:  # YYYYMMDD
                travel_date = datetime.strptime(date, '%Y%m%d')
            else:  # YYYY-MM-DD
                travel_date = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            print(f"Ungültiges Datumsformat: {date}")
            return None
        
        # Parse Zeit
        try:
            time_parts = time.split(':')
            start_time_sec = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60
        except (ValueError, IndexError):
            print(f"Ungültiges Zeitformat: {time}")
            return None
        
        # Map Stationsnamen zu stop_ids
        start_id = self.data.find_stop_id(start_name)
        end_id = self.data.find_stop_id(end_name)
        
        if start_id is None:
            print(f"Startstation '{start_name}' nicht gefunden!")
            return None
        
        if end_id is None:
            print(f"Zielstation '{end_name}' nicht gefunden!")
            return None
        
        if start_id == end_id:
            print("Start- und Zielstation sind identisch!")
            return None
        
        # Baue Connections für dieses Datum
        print(f"Baue Verbindungen für {travel_date.strftime('%Y-%m-%d')}...")
        connections = self._build_connections(travel_date, start_time_sec)
        print(f"  {len(connections)} Verbindungen gefunden")
        
        # Wende CSA an
        print("Berechne optimale Route...")
        route = self._connection_scan_algorithm(connections, start_id, end_id, start_time_sec)
        
        return route
