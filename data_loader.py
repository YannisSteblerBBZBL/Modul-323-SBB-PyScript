import pandas as pd
import numpy as np
import os
import unicodedata
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

        # Normalisierte Stop-Namen (für robustes Matching, z.B. Umlaut/Unicode-Varianten)
        self._stops_name_norm: Optional[pd.Series] = None

        # Station/Plattform Mapping: parent_station -> [child stop_ids]
        self._parent_to_children: Dict[str, list] = {}
        # stop_id -> parent_station (oder "" wenn keiner)
        self._stop_to_parent: Dict[str, str] = {}
        
        print("Lade GTFS-Daten...")
        self._load_data()
        print("Daten erfolgreich geladen!")
    
    def _load_data(self):
        """Lädt alle GTFS-Dateien in Pandas DataFrames (speichereffizient und vektorisiert)"""
        # Stops (nur benötigte Spalten)
        self.stops = pd.read_csv(
            os.path.join(self.data_dir, "stops.txt"),
            usecols=['stop_id', 'stop_name', 'parent_station'],
            dtype={'stop_id': str, 'stop_name': str, 'parent_station': str}
        )
        # Normalisierte Namen cachen (casefold + Unicode Normalization)
        self._stops_name_norm = self.stops['stop_name'].map(self._normalize_name)
        # Cache: stop_id -> stop_name
        self.stop_id_to_name = dict(zip(self.stops['stop_id'], self.stops['stop_name']))

        # parent_station Mapping aufbauen (für Routing: Station -> alle Plattformen)
        # parent_station kann leer/NaN sein
        parent_series = self.stops['parent_station'].fillna('').astype(str)
        self._stop_to_parent = dict(zip(self.stops['stop_id'], parent_series))
        self._parent_to_children = {}
        for stop_id, parent in zip(self.stops['stop_id'], parent_series):
            parent = parent.strip()
            if parent:
                self._parent_to_children.setdefault(parent, []).append(stop_id)
        
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
        Findet stop_id basierend auf Stationsname (case-insensitive)
        Gibt nur zurück wenn exakt oder wenn Station mit Suchstring beginnt
        
        Args:
            stop_name: Name der Station
            
        Returns:
            stop_id oder None wenn nicht gefunden
        """
        stop_name_norm = self._normalize_name(stop_name)
        
        # Exakter Match
        exact_match = self.stops[self._stops_name_norm == stop_name_norm]
        if len(exact_match) > 0:
            return exact_match.iloc[0]['stop_id']
        
        # Stationen die mit dem Suchstring beginnen
        starts_with_match = self.stops[self._stops_name_norm.str.startswith(stop_name_norm, na=False)]
        if len(starts_with_match) > 0:
            return starts_with_match.iloc[0]['stop_id']
        
        return None
    
    def find_matching_stops(self, stop_name: str) -> list:
        """
        Findet alle Stationen die mit dem Suchstring beginnen oder exakt übereinstimmen
        
        Args:
            stop_name: Name der Station (oder Teil davon)
            
        Returns:
            Liste von Stationsnamen, sortiert (exakte Matches zuerst, dann alphabetisch)
        """
        stop_name_norm = self._normalize_name(stop_name)
        
        if not stop_name_norm:
            return []
        
        # Exakte Matches
        exact_matches = self.stops[self._stops_name_norm == stop_name_norm]['stop_name'].unique()
        
        # Stationen die mit dem Suchstring beginnen
        starts_with_matches = self.stops[self._stops_name_norm.str.startswith(stop_name_norm, na=False)]['stop_name'].unique()
        
        # Kombiniere und entferne Duplikate
        all_matches = list(set(list(exact_matches) + list(starts_with_matches)))
        
        # Sortiere: exakte Matches zuerst, dann alphabetisch
        all_matches.sort(key=lambda x: (
            0 if self._normalize_name(x) == stop_name_norm else 1,  # Exakte Matches zuerst
            self._normalize_name(x)  # Dann alphabetisch
        ))
        
        return all_matches
    
    def get_stop_name(self, stop_id: str) -> str:
        """Gibt den Haltestellennamen für eine stop_id zurück"""
        return self.stop_id_to_name.get(stop_id, "")
    
    def find_similar_stops(self, stop_name: str, max_results: int = 10) -> list:
        """
        Findet ähnliche Stationennamen basierend auf Teilstring-Matching
        
        Args:
            stop_name: Name der Station (oder Teil davon)
            max_results: Maximale Anzahl von Vorschlägen
            
        Returns:
            Liste von Stationsnamen, die ähnlich sind
        """
        stop_name_norm = self._normalize_name(stop_name)
        
        if not stop_name_norm:
            return []
        
        # Finde alle Stationen, die den Suchstring enthalten (auf normalisierten Namen)
        similar = self.stops[self._stops_name_norm.str.contains(stop_name_norm, na=False)]['stop_name'].unique()
        
        # Sortiere nach Relevanz (exakte Matches zuerst, dann alphabetisch)
        similar_list = list(similar)
        similar_list.sort(key=lambda x: (
            0 if self._normalize_name(x) == stop_name_norm else 1,  # Exakte Matches zuerst
            0 if self._normalize_name(x).startswith(stop_name_norm) else 1,  # Dann solche die damit beginnen
            self._normalize_name(x)  # Dann alphabetisch
        ))
        
        return similar_list[:max_results]

    def expand_station_stop_ids(self, stop_id: str) -> list:
        """
        Gibt alle stop_ids zurück, die zu einer Station gehören:
        - Wenn stop_id eine Plattform ist: parent_station + alle Geschwisterplattformen
        - Wenn stop_id eine Station ist: die Station + alle Plattformen (children)
        """
        if stop_id is None:
            return []
        stop_id = str(stop_id).strip()
        if not stop_id:
            return []

        parent = (self._stop_to_parent.get(stop_id, "") or "").strip()
        station_id = parent if parent else stop_id

        result = [station_id]
        children = self._parent_to_children.get(station_id, [])
        if children:
            result.extend(children)
        # Duplikate entfernen, Reihenfolge behalten
        seen = set()
        uniq = []
        for x in result:
            if x not in seen:
                seen.add(x)
                uniq.append(x)
        return uniq

    @staticmethod
    def _normalize_name(value: str) -> str:
        """
        Normalisiert Stationsnamen robust:
        - Unicode Normalization (NFKC) für kombinierte Zeichenvarianten
        - casefold für sprachspezifische Vergleiche
        - trim
        """
        if value is None:
            return ""
        s = str(value).strip()
        if not s:
            return ""
        return unicodedata.normalize("NFKC", s).casefold()