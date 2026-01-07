from typing import List
from models import RouteSegment


class RouteFormatter:
    @staticmethod
    def seconds_to_time(seconds: int) -> str:
        hours = seconds // 3600
        minutes = seconds % 3600 // 60
        return f"{hours:02d}:{minutes:02d}"

    def format_route_output(
        self,
        routes: List[List[RouteSegment]],
        start_name: str,
        end_name: str,
    ) -> str:
        if not routes:
            return "Keine Route gefunden."
        output = []
        for route_idx, route in enumerate(routes, 1):
            if route_idx > 1:
                output.append("")
                output.append("=" * 50)
            output.append("=" * 50)
            if len(routes) > 1:
                output.append(f" OptimalRoute.CH | Route {route_idx} von {len(routes)}")
            else:
                output.append(" OptimalRoute.CH | Verbindung gefunden")
            output.append("=" * 50)
            start_time_formatted = self.seconds_to_time(route[0].departure_time)
            end_time_formatted = self.seconds_to_time(route[-1].arrival_time)
            output.append(f"Startpunkt: {start_name} ({start_time_formatted})")
            output.append(f"Zielpunkt:  {end_name} ({end_time_formatted})")
            total_seconds = route[-1].arrival_time - route[0].departure_time
            hours = total_seconds // 3600
            minutes = total_seconds % 3600 // 60
            if hours > 0:
                time_str = f"{hours} Stunde{('n' if hours > 1 else '')}, {minutes} Minute{('n' if minutes != 1 else '')}"
            else:
                time_str = f"{minutes} Minute{('n' if minutes != 1 else '')}"
            output.append(f"GESAMTREISEZEIT: {time_str}")
            output.append("-" * 50)
            for i, segment in enumerate(route, 1):
                output.append(f"  {i}. FAHRT")
                output.append(
                    f"     > Abfahrt: {self.seconds_to_time(segment.departure_time)}  | {segment.departure_stop_name}"
                )
                output.append(
                    f"     > Ankunft: {self.seconds_to_time(segment.arrival_time)}  | {segment.arrival_stop_name}"
                )
                route_display = (
                    segment.route_name if segment.route_name else "Unbekannt"
                )
                output.append(f"     > Linie:   {route_display}")
                if i < len(route):
                    wait_minutes = segment.wait_time // 60
                    output.append("  ------------------------------------------------")
                    output.append(
                        f"  UMSTIEG: {segment.arrival_stop_name} ({wait_minutes} Minuten Wartezeit)"
                    )
                    output.append("  ------------------------------------------------")
            output.append("=" * 50)
        return "\n".join(output)
