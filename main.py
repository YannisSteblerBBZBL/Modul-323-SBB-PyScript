from datetime import datetime
from data_loader import GTFSDataLoader
from route_calculator import RouteCalculator
from formatter import RouteFormatter


def get_user_input(prompt: str, default: str = None) -> str:
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    else:
        while True:
            user_input = input(f"{prompt}: ").strip()
            if user_input:
                return user_input
            print("Bitte geben Sie einen Wert ein.")


def get_station_input(data_loader: GTFSDataLoader, prompt: str) -> tuple:
    while True:
        station_input = input(f"{prompt}: ").strip()
        if not station_input:
            print("Bitte geben Sie eine Station ein.")
            continue
        matching_stops = data_loader.find_matching_stops(station_input)
        if len(matching_stops) == 1:
            station_name = matching_stops[0]
            stop_id = data_loader.find_stop_id(station_name)
            print(f"✓ Station gefunden: {station_name}")
            return (station_name, stop_id)
        elif len(matching_stops) > 1:
            print("\nMehrere Stationen gefunden:")
            for i, stop in enumerate(matching_stops, 1):
                print(f"  {i}. {stop}")
            print()
            choice = (
                input(
                    "Bitte wählen Sie eine Station (Nummer eingeben oder 'n' für neue Eingabe): "
                )
                .strip()
                .lower()
            )
            if choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(matching_stops):
                    selected_station = matching_stops[choice_num - 1]
                    stop_id = data_loader.find_stop_id(selected_station)
                    print(f"✓ Station ausgewählt: {selected_station}")
                    return (selected_station, stop_id)
                else:
                    print("Ungültige Nummer. Bitte versuchen Sie es erneut.\n")
            elif choice == "n":
                continue
            else:
                print("Ungültige Eingabe. Bitte versuchen Sie es erneut.\n")
        else:
            print(f"✗ Station '{station_input}' nicht gefunden.")
            similar_stops = data_loader.find_similar_stops(
                station_input, max_results=10
            )
            if similar_stops:
                print("\nÄhnliche Stationen gefunden:")
                for i, stop in enumerate(similar_stops, 1):
                    print(f"  {i}. {stop}")
                print()
                choice = (
                    input(
                        "Möchten Sie eine dieser Stationen verwenden? (Nummer eingeben oder 'n' für neue Eingabe): "
                    )
                    .strip()
                    .lower()
                )
                if choice.isdigit():
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(similar_stops):
                        selected_station = similar_stops[choice_num - 1]
                        stop_id = data_loader.find_stop_id(selected_station)
                        print(f"✓ Station ausgewählt: {selected_station}")
                        return (selected_station, stop_id)
                    else:
                        print("Ungültige Nummer. Bitte versuchen Sie es erneut.\n")
                elif choice == "n":
                    continue
                else:
                    print("Ungültige Eingabe. Bitte versuchen Sie es erneut.\n")
            else:
                print(
                    "Keine ähnlichen Stationen gefunden. Bitte versuchen Sie es erneut.\n"
                )


def main():
    print("=" * 50)
    print(" PyRouteCH - ÖV-Routenberechnung")
    print("=" * 50)
    print()
    print("Initialisiere System...")
    data_loader = GTFSDataLoader(data_dir="data")
    calculator = RouteCalculator(data_loader)
    formatter = RouteFormatter()
    print()
    while True:
        print("=" * 50)
        print(" Routenberechnung")
        print("=" * 50)
        print()
        start_station, start_id = get_station_input(data_loader, "Startstation")
        print()
        end_station, end_id = get_station_input(data_loader, "Endstation")
        print()
        today = datetime.now().strftime("%Y-%m-%d")
        date = get_user_input("Reisedatum (YYYY-MM-DD)", today)
        current_time = datetime.now().strftime("%H:%M")
        time = get_user_input("Abfahrtszeit (HH:MM)", current_time)
        print()
        print("-" * 50)
        print(f"Berechne Route: {start_station} → {end_station}")
        print(f"Datum: {date}, Zeit: {time}")
        print("-" * 50)
        print()
        routes = calculator.find_route_by_ids(
            start_id=start_id,
            end_id=end_id,
            start_name=start_station,
            end_name=end_station,
            date=date,
            time=time,
        )
        if routes:
            print(
                formatter.format_route_output(routes, start_station, end_station)
            )
        else:
            print("=" * 50)
            print(" Keine Route gefunden")
            print("=" * 50)
            print()
            print("Mögliche Gründe:")
            print("- Die Stationen existieren nicht oder wurden falsch geschrieben")
            print("- Für das gewählte Datum und die Zeit gibt es keine Verbindung")
            print("- Die Stationen sind nicht miteinander verbunden")
            print()
        print()
        weiter = input("Weitere Route berechnen? (j/n): ").strip().lower()
        if weiter not in ["j", "ja", "y", "yes"]:
            break
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgramm beendet.")
    except Exception as e:
        print(f"\nFehler: {e}")
