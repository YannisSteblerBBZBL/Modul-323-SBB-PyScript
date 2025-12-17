import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import os


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


class PyRouteCH:
    """Hauptklasse für die Routenberechnung"""
    
    def __init__(self, data_dir: str = "data"):
        """
        Initialisiert die Anwendung und lädt alle GTFS-Daten
        
        Args:
            data_dir: Verzeichnis mit den GTFS-Dateien
        """
        self.data_dir = data_dir
        self.stops: pd.DataFrame = None
        self.stop_times: pd.DataFrame = None
        self.trips: pd.DataFrame = None
        self.calendar: pd.DataFrame = None
        self.calendar_dates: pd.DataFrame = None
        self.routes: pd.DataFrame = None
        
        # Cache für Service-IDs pro Datum
        self.service_cache: Dict[str, set] = {}
        
        print("Lade GTFS-Daten...")
        self._load_data()
        print("Daten erfolgreich geladen!")
    
    def _load_data(self):
        """Lädt alle GTFS-Dateien in Pandas DataFrames (speichereffizient und vektorisiert)"""
        # Stops (nur benötigte Spalten)
        self.stops = pd.read_csv(
            os.path.join(self.data_dir, "stops.txt"),
            usecols=['stop_id', 'stop_name'],
            dtype={'stop_id': str, 'stop_name': str}
        )
        # Cache: stop_id -> stop_name
        self.stop_id_to_name: Dict[str, str] = dict(zip(self.stops['stop_id'], self.stops['stop_name']))
        
        # Stop Times - nur relevante Spalten laden für bessere Performance
        print("  Lade stop_times.txt (dies kann einige Zeit dauern)...")
        self.stop_times = pd.read_csv(
            os.path.join(self.data_dir, "stop_times.txt"),
            dtype={
                'trip_id': str,
                'stop_id': str,
                'arrival_time': str,
                'departure_time': str,
                'stop_sequence': np.int32
            },
            usecols=['trip_id', 'arrival_time', 'departure_time', 'stop_id', 'stop_sequence']
        )
        
        # Konvertiere Zeitwerte vektorisiert von HH:MM:SS zu Sekunden seit Mitternacht
        # Pandas unterstützt Stunden > 24 via to_timedelta
        arr_td = pd.to_timedelta(self.stop_times['arrival_time'], errors='coerce')
        dep_td = pd.to_timedelta(self.stop_times['departure_time'], errors='coerce')
        self.stop_times['arrival_time_sec'] = arr_td.dt.total_seconds().fillna(0).astype(np.int32)
        self.stop_times['departure_time_sec'] = dep_td.dt.total_seconds().fillna(0).astype(np.int32)
        
        # Trips
        self.trips = pd.read_csv(
            os.path.join(self.data_dir, "trips.txt"),
            dtype={'trip_id': str, 'route_id': str, 'service_id': str}
        )
        
        # Calendar
        self.calendar = pd.read_csv(
            os.path.join(self.data_dir, "calendar.txt"),
            dtype={'service_id': str}
        )
        # Konvertiere Datumsspalten
        self.calendar['start_date'] = pd.to_datetime(self.calendar['start_date'], format='%Y%m%d')
        self.calendar['end_date'] = pd.to_datetime(self.calendar['end_date'], format='%Y%m%d')
        
        # Calendar Dates
        print("  Lade calendar_dates.txt...")
        self.calendar_dates = pd.read_csv(
            os.path.join(self.data_dir, "calendar_dates.txt"),
            dtype={'service_id': str, 'date': str, 'exception_type': int}
        )
        self.calendar_dates['date'] = pd.to_datetime(self.calendar_dates['date'], format='%Y%m%d')
        
        # Routes
        self.routes = pd.read_csv(
            os.path.join(self.data_dir, "routes.txt"),
            dtype={'route_id': str, 'route_short_name': str, 'route_long_name': str}
        )
        
        # Erstelle Mapping von route_id zu route_name
        # Bevorzuge route_short_name, falls vorhanden, sonst route_long_name
        self.routes['route_name'] = self.routes['route_short_name'].fillna('')
        # Wenn route_short_name leer, verwende route_long_name
        mask = self.routes['route_name'] == ''
        self.routes.loc[mask, 'route_name'] = self.routes.loc[mask, 'route_long_name'].fillna('Unbekannt')
        self.routes['route_name'] = self.routes['route_name'].str.strip()
        
        # Merge route information into trips
        self.trips = self.trips.merge(
            self.routes[['route_id', 'route_name']],
            on='route_id',
            how='left'
        )
    
    @staticmethod
    def _time_to_seconds(time_str: str) -> int:
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
    def _seconds_to_time(seconds: int) -> str:
        """Konvertiert Sekunden seit Mitternacht zu HH:MM Format"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    
    def _get_weekday_name(self, date: datetime) -> str:
        """Gibt den Wochentag als String zurück (monday, tuesday, etc.)"""
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        return weekdays[date.weekday()]
    
    def _get_valid_services(self, date: datetime) -> set:
        """
        Bestimmt alle gültigen service_ids für ein gegebenes Datum
        
        Args:
            date: Reisedatum
            
        Returns:
            Set von gültigen service_ids
        """
        date_str = date.strftime('%Y%m%d')
        
        # Cache prüfen
        if date_str in self.service_cache:
            return self.service_cache[date_str]
        
        valid_services = set()
        weekday = self._get_weekday_name(date)
        
        # 1. Prüfe calendar.txt (reguläre Dienste)
        calendar_valid = self.calendar[
            (self.calendar['start_date'] <= date) &
            (self.calendar['end_date'] >= date) &
            (self.calendar[weekday] == 1)
        ]['service_id'].tolist()
        valid_services.update(calendar_valid)
        
        # 2. Prüfe calendar_dates.txt (Ausnahmen)
        # exception_type 1 = hinzugefügt, 2 = entfernt
        exceptions_add = self.calendar_dates[
            (self.calendar_dates['date'] == date) &
            (self.calendar_dates['exception_type'] == 1)
        ]['service_id'].tolist()
        exceptions_remove = self.calendar_dates[
            (self.calendar_dates['date'] == date) &
            (self.calendar_dates['exception_type'] == 2)
        ]['service_id'].tolist()
        
        valid_services.update(exceptions_add)
        valid_services.difference_update(exceptions_remove)
        
        # Cache speichern
        self.service_cache[date_str] = valid_services
        
        return valid_services
    
    def _find_stop_id(self, stop_name: str) -> Optional[str]:
        """
        Findet stop_id basierend auf Stationsname (case-insensitive, Teilstring-Match)
        
        Args:
            stop_name: Name der Station
            
        Returns:
            stop_id oder None wenn nicht gefunden
        """
        stop_name_lower = stop_name.lower().strip()
        
        # Exakter Match
        exact_match = self.stops[
            self.stops['stop_name'].str.lower() == stop_name_lower
        ]
        if len(exact_match) > 0:
            return exact_match.iloc[0]['stop_id']
        
        # Teilstring-Match
        partial_match = self.stops[
            self.stops['stop_name'].str.lower().str.contains(stop_name_lower, na=False)
        ]
        if len(partial_match) > 0:
            return partial_match.iloc[0]['stop_id']
        
        return None
    
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
        valid_services = self._get_valid_services(date)
        if not valid_services:
            return pd.DataFrame(columns=['trip_id', 'dep_stop', 'arr_stop', 'dep_time', 'arr_time', 'route_name'])
        valid_trips = self.trips[self.trips['service_id'].isin(valid_services)]
        
        # Merge mit stop_times (nur Trips dieses Datums)
        trip_stops = self.stop_times.merge(
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
                departure_stop_name=self.stop_id_to_name.get(dep_stop, ""),
                departure_time=dep_time,
                arrival_stop=arr_stop,
                arrival_stop_name=self.stop_id_to_name.get(arr_stop, ""),
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
        start_id = self._find_stop_id(start_name)
        end_id = self._find_stop_id(end_name)
        
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
    
    def format_route_output(
        self,
        route: List[RouteSegment],
        start_name: str,
        end_name: str,
        start_time: str
    ) -> str:
        """
        Formatiert die Route für die Konsolenausgabe
        
        Args:
            route: Liste von RouteSegment-Objekten
            start_name: Name der Startstation
            end_name: Name der Zielstation
            start_time: Startzeit im Format "HH:MM"
            
        Returns:
            Formatierter String für die Ausgabe
        """
        if not route:
            return "Keine Route gefunden."
        
        output = []
        output.append("=" * 50)
        output.append(" OptimalRoute.CH | Verbindung gefunden")
        output.append("=" * 50)
        
        # Start- und Zielpunkt
        start_time_formatted = self._seconds_to_time(route[0].departure_time)
        end_time_formatted = self._seconds_to_time(route[-1].arrival_time)
        
        output.append(f"Startpunkt: {start_name} ({start_time_formatted})")
        output.append(f"Zielpunkt:  {end_name} ({end_time_formatted})")
        
        # Gesamtreisezeit
        total_seconds = route[-1].arrival_time - route[0].departure_time
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        if hours > 0:
            time_str = f"{hours} Stunde{'n' if hours > 1 else ''}, {minutes} Minute{'n' if minutes != 1 else ''}"
        else:
            time_str = f"{minutes} Minute{'n' if minutes != 1 else ''}"
        
        output.append(f"GESAMTREISEZEIT: {time_str}")
        output.append("-" * 50)
        
            # Route-Segmente
        for i, segment in enumerate(route, 1):
            output.append(f"  {i}. FAHRT")
            output.append(f"     > Abfahrt: {self._seconds_to_time(segment.departure_time)}  | {segment.departure_stop_name}")
            output.append(f"     > Ankunft: {self._seconds_to_time(segment.arrival_time)}  | {segment.arrival_stop_name}")
            route_display = segment.route_name if segment.route_name else "Unbekannt"
            output.append(f"     > Linie:   {route_display}")
            
            # Umstieg-Information (außer beim letzten Segment)
            if i < len(route):
                wait_minutes = segment.wait_time // 60
                output.append("  ------------------------------------------------")
                output.append(f"  UMSTIEG: {segment.arrival_stop_name} ({wait_minutes} Minuten Wartezeit)")
                output.append("  ------------------------------------------------")
        
        output.append("=" * 50)
        
        return "\n".join(output)
    
    # ========== ERGÄNZENDE ANALYSEFUNKTIONEN ==========
    
    def fastest_direct_connection_per_hour(self) -> pd.DataFrame:
        """
        Findet die schnellste Direktverbindung pro Stunde
        
        Returns:
            DataFrame mit den schnellsten Direktverbindungen pro Stunde
        """
        # Merge stop_times mit trips und routes
        trip_info = self.stop_times.merge(
            self.trips[['trip_id', 'route_id']],
            on='trip_id',
            how='inner'
        ).merge(
            self.routes[['route_id', 'route_short_name']],
            on='route_id',
            how='left'
        )
        
        # Für jeden Trip: finde erste und letzte Station
        trip_segments = []
        for trip_id, trip_data in trip_info.groupby('trip_id'):
            trip_data = trip_data.sort_values('stop_sequence')
            if len(trip_data) < 2:
                continue
            
            first = trip_data.iloc[0]
            last = trip_data.iloc[-1]
            
            dep_time = first['departure_time_sec']
            arr_time = last['arrival_time_sec']
            duration = arr_time - dep_time
            
            # Stunde der Abfahrt
            dep_hour = dep_time // 3600
            
            trip_segments.append({
                'trip_id': trip_id,
                'departure_hour': dep_hour,
                'duration_seconds': duration,
                'route_name': first.get('route_short_name', '')
            })
        
        df_segments = pd.DataFrame(trip_segments)
        
        # Gruppiere nach Stunde und finde Minimum
        fastest = df_segments.groupby('departure_hour')['duration_seconds'].min().reset_index()
        fastest = fastest.merge(
            df_segments[['departure_hour', 'duration_seconds', 'route_name']],
            on=['departure_hour', 'duration_seconds'],
            how='left'
        )
        fastest['duration_minutes'] = fastest['duration_seconds'] // 60
        
        return fastest[['departure_hour', 'duration_minutes', 'route_name']].sort_values('departure_hour')
    
    def top_10_most_frequented_stops(self) -> pd.DataFrame:
        """
        Findet die Top 10 meistfrequentierten Haltestellen
        
        Returns:
            DataFrame mit den Top 10 Haltestellen
        """
        # Zähle Vorkommen jeder stop_id in stop_times
        stop_counts = self.stop_times['stop_id'].value_counts().head(10).reset_index()
        stop_counts.columns = ['stop_id', 'frequency']
        
        # Merge mit stops für Namen
        result = stop_counts.merge(
            self.stops[['stop_id', 'stop_name']],
            on='stop_id',
            how='left'
        )
        
        return result[['stop_name', 'frequency']].sort_values('frequency', ascending=False)
    
    def overnight_connections(self) -> pd.DataFrame:
        """
        Findet Übernacht-Verbindungen (Ankunft < Abfahrt)
        
        Returns:
            DataFrame mit Übernacht-Verbindungen
        """
        # Filtere stop_times wo arrival_time < departure_time (oder sehr große Werte)
        # Übernacht-Verbindungen haben oft arrival_time > 24*3600
        overnight = self.stop_times[
            (self.stop_times['arrival_time_sec'] < self.stop_times['departure_time_sec']) |
            (self.stop_times['arrival_time_sec'] >= 24 * 3600)
        ].copy()
        
        # Merge mit trips und stops für zusätzliche Informationen
        overnight = overnight.merge(
            self.trips[['trip_id', 'route_id']],
            on='trip_id',
            how='left'
        ).merge(
            self.routes[['route_id', 'route_short_name']],
            on='route_id',
            how='left'
        ).merge(
            self.stops[['stop_id', 'stop_name']],
            on='stop_id',
            how='left'
        )
        
        return overnight[['trip_id', 'stop_name', 'departure_time', 'arrival_time', 'route_short_name']].head(100)


def main():
    """Hauptfunktion der Konsolenapplikation"""
    print("=" * 50)
    print(" PyRouteCH - ÖV-Routenberechnung")
    print("=" * 50)
    print()
    
    # Initialisiere Anwendung
    router = PyRouteCH(data_dir="data")
    print()
    
    # Beispiel-Verwendung
    print("Beispiel-Routenberechnung:")
    print("-" * 50)
    
    # Beispiel 1: Basel SBB -> Zürich HB
    route = router.find_route(
        start_name="Basel SBB",
        end_name="Zürich HB",
        date="2025-12-15",
        time="08:00"
    )
    
    if route:
        print(router.format_route_output(route, "Basel SBB", "Zürich HB", "08:00"))
    else:
        print("Keine Route gefunden.")
    
    print("\n" + "=" * 50)
    print("Ergänzende Analysen:")
    print("=" * 50)
    
    # Analyse 1: Schnellste Direktverbindung pro Stunde
    print("\n1. Schnellste Direktverbindung pro Stunde:")
    fastest = router.fastest_direct_connection_per_hour()
    print(fastest.head(10).to_string(index=False))
    
    # Analyse 2: Top 10 Haltestellen
    print("\n2. Top 10 meistfrequentierten Haltestellen:")
    top_stops = router.top_10_most_frequented_stops()
    print(top_stops.to_string(index=False))
    
    # Analyse 3: Übernacht-Verbindungen
    print("\n3. Übernacht-Verbindungen (Beispiele):")
    overnight = router.overnight_connections()
    print(overnight.head(10).to_string(index=False))


if __name__ == "__main__":
    main()

