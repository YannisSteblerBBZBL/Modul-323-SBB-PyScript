import pandas as pd
from data_loader import GTFSDataLoader


class RouteAnalyzer:
    """Klasse für ergänzende Analysefunktionen"""
    
    def __init__(self, data_loader: GTFSDataLoader):
        """
        Initialisiert den Analyzer
        
        Args:
            data_loader: GTFSDataLoader-Instanz mit geladenen Daten
        """
        self.data = data_loader
    
    def fastest_direct_connection_per_hour(self) -> pd.DataFrame:
        """
        Findet die schnellste Direktverbindung pro Stunde
        
        Returns:
            DataFrame mit den schnellsten Direktverbindungen pro Stunde
        """
        # Merge stop_times mit trips und routes
        trip_info = self.data.stop_times.merge(
            self.data.trips[['trip_id', 'route_id']],
            on='trip_id',
            how='inner'
        ).merge(
            self.data.routes[['route_id', 'route_short_name']],
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
        stop_counts = self.data.stop_times['stop_id'].value_counts().head(10).reset_index()
        stop_counts.columns = ['stop_id', 'frequency']
        
        # Merge mit stops für Namen
        result = stop_counts.merge(
            self.data.stops[['stop_id', 'stop_name']],
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
        overnight = self.data.stop_times[
            (self.data.stop_times['arrival_time_sec'] < self.data.stop_times['departure_time_sec']) |
            (self.data.stop_times['arrival_time_sec'] >= 24 * 3600)
        ].copy()
        
        # Merge mit trips und stops für zusätzliche Informationen
        overnight = overnight.merge(
            self.data.trips[['trip_id', 'route_id']],
            on='trip_id',
            how='left'
        ).merge(
            self.data.routes[['route_id', 'route_short_name']],
            on='route_id',
            how='left'
        ).merge(
            self.data.stops[['stop_id', 'stop_name']],
            on='stop_id',
            how='left'
        )
        
        return overnight[['trip_id', 'stop_name', 'departure_time', 'arrival_time', 'route_short_name']].head(100)
