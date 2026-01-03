from data_loader import GTFSDataLoader
from route_calculator import RouteCalculator
from analyzer import RouteAnalyzer
from formatter import RouteFormatter


def main():
    """Hauptfunktion der Konsolenapplikation"""
    print("=" * 50)
    print(" PyRouteCH - ÖV-Routenberechnung")
    print("=" * 50)
    print()
    
    # Initialisiere Komponenten
    data_loader = GTFSDataLoader(data_dir="data")
    calculator = RouteCalculator(data_loader)
    analyzer = RouteAnalyzer(data_loader)
    formatter = RouteFormatter()
    
    print()
    
    # Beispiel-Verwendung
    print("Beispiel-Routenberechnung:")
    print("-" * 50)
    
    # Beispiel 1: Basel SBB -> Zürich HB
    route = calculator.find_route(
        start_name="Basel SBB",
        end_name="Zürich HB",
        date="2025-12-15",
        time="08:00"
    )
    
    if route:
        print(formatter.format_route_output(route, "Basel SBB", "Zürich HB", "08:00"))
    else:
        print("Keine Route gefunden.")
    
    print("\n" + "=" * 50)
    print("Ergänzende Analysen:")
    print("=" * 50)
    
    # Analyse 1: Schnellste Direktverbindung pro Stunde
    print("\n1. Schnellste Direktverbindung pro Stunde:")
    fastest = analyzer.fastest_direct_connection_per_hour()
    print(fastest.head(10).to_string(index=False))
    
    # Analyse 2: Top 10 Haltestellen
    print("\n2. Top 10 meistfrequentierten Haltestellen:")
    top_stops = analyzer.top_10_most_frequented_stops()
    print(top_stops.to_string(index=False))
    
    # Analyse 3: Übernacht-Verbindungen
    print("\n3. Übernacht-Verbindungen (Beispiele):")
    overnight = analyzer.overnight_connections()
    print(overnight.head(10).to_string(index=False))


if __name__ == "__main__":
    main()

