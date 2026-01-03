import pandas as pd
import numpy as np
import os
from datetime import datetime
from typing import Dict, Optional


class GTFSDataLoader:
    """Klasse zum Laden und Verwalten von GTFS-Daten"""
    
    def __init__(self, data_dir: str = "data"):
        """
        Initialisiert den DataLoader und lädt alle GTFS-Daten
        
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
        
        # Cache: stop_id -> stop_name
        self.stop_id_to_name: Dict[str, str] = {}
        
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
        self.stop_id_to_name = dict(zip(self.stops['stop_id'], self.stops['stop_name']))
        
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
    
    def _get_weekday_name(self, date: datetime) -> str:
        """Gibt den Wochentag als String zurück (monday, tuesday, etc.)"""
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        return weekdays[date.weekday()]
    
    def get_valid_services(self, date: datetime) -> set:
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
    
    def find_stop_id(self, stop_name: str) -> Optional[str]:
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
    
    def get_stop_name(self, stop_id: str) -> str:
        """Gibt den Haltestellennamen für eine stop_id zurück"""
        return self.stop_id_to_name.get(stop_id, "")
