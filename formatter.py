from typing import List
from models import RouteSegment


class RouteFormatter:
    """Klasse für die Formatierung der Routenausgabe"""
    
    @staticmethod
    def seconds_to_time(seconds: int) -> str:
        """Konvertiert Sekunden seit Mitternacht zu HH:MM Format"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours:02d}:{minutes:02d}"
    
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
        start_time_formatted = self.seconds_to_time(route[0].departure_time)
        end_time_formatted = self.seconds_to_time(route[-1].arrival_time)
        
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
            output.append(f"     > Abfahrt: {self.seconds_to_time(segment.departure_time)}  | {segment.departure_stop_name}")
            output.append(f"     > Ankunft: {self.seconds_to_time(segment.arrival_time)}  | {segment.arrival_stop_name}")
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
