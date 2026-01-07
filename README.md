# PyRouteCH - ÖV-Routenberechnung

Ein Python-basiertes System zur Berechnung optimaler ÖV-Routen basierend auf GTFS-Daten (General Transit Feed Specification) der Schweizerischen Bundesbahnen (SBB).

## 📋 Inhaltsverzeichnis

- [Übersicht](#übersicht)
- [Projektstruktur](#projektstruktur)
- [Voraussetzungen](#voraussetzungen)
- [Installation](#installation)
- [Verwendung](#verwendung)
- [Skript-Dokumentation](#skript-dokumentation)
- [GTFS-Daten](#gtfs-daten)

## 🎯 Übersicht

Dieses Projekt implementiert einen **Connection Scan Algorithm (CSA)** zur Berechnung optimaler ÖV-Routen zwischen zwei Haltestellen. Es unterstützt:

- Routenberechnung zwischen beliebigen Stationen
- Berücksichtigung von Datum und Uhrzeit
- Umstiegsberechnung mit Wartezeiten
- Zusätzliche Analysefunktionen (schnellste Verbindungen, Top-Haltestellen, Übernacht-Verbindungen)

## 📁 Projektstruktur

```
Modul-323-SBB-PyScript/
├── main.py                 # Hauptskript - Einstiegspunkt der Anwendung
├── data_loader.py          # Lädt und verwaltet GTFS-Daten
├── route_calculator.py     # Implementiert den Connection Scan Algorithm
├── analyzer.py             # Zusätzliche Analysefunktionen
├── formatter.py            # Formatierung der Routenausgabe
├── models.py               # Datenmodelle (Connection, RouteSegment)
├── requirements.txt        # Python-Abhängigkeiten
└── data/                   # GTFS-Datenverzeichnis
    ├── agency.txt
    ├── calendar.txt
    ├── calendar_dates.txt
    ├── feed_info.txt
    ├── routes.txt
    ├── stop_times.txt
    ├── stops.txt
    ├── transfers.txt
    └── trips.txt
```

## 🔧 Voraussetzungen

- Python 3.8 oder höher
- GTFS-Daten im `data/` Verzeichnis

## 📦 Installation

1. **Repository klonen oder Projektordner öffnen**

2. **Python-Abhängigkeiten installieren:**

```bash
pip install -r requirements.txt
```

Dies installiert:
- `pandas` (>=2.0.0) - Datenverarbeitung und DataFrame-Operationen
- `numpy` (>=1.24.0) - Numerische Operationen

## 🚀 Verwendung

### Interaktive Routenberechnung

```bash
python main.py
```

Das Hauptskript startet eine interaktive Konsolenanwendung, die Sie durch die Routenberechnung führt:

1. **Startstation eingeben** - Name der Abfahrtsstation (z.B. "Basel SBB")
2. **Endstation eingeben** - Name der Zielstation (z.B. "Zürich HB")
3. **Reisedatum eingeben** - Format: YYYY-MM-DD (Standard: heutiges Datum, einfach Enter drücken)
4. **Abfahrtszeit eingeben** - Format: HH:MM (Standard: aktuelle Zeit, einfach Enter drücken)

Nach der Berechnung können Sie weitere Routen berechnen oder das Programm beenden.

**Beispiel-Interaktion:**
```
Startstation: Basel SBB
Endstation: Zürich HB
Reisedatum (YYYY-MM-DD) [2025-01-15]: 2025-12-15
Abfahrtszeit (HH:MM) [14:30]: 08:00
```

### Programmierung eigener Routenberechnungen

Falls Sie das System programmatisch nutzen möchten:

```python
from data_loader import GTFSDataLoader
from route_calculator import RouteCalculator
from formatter import RouteFormatter

# Initialisiere Komponenten
data_loader = GTFSDataLoader(data_dir="data")
calculator = RouteCalculator(data_loader)
formatter = RouteFormatter()

# Berechne Route
route = calculator.find_route(
    start_name="Bern",
    end_name="Genf",
    date="2025-12-15",  # Format: YYYY-MM-DD oder YYYYMMDD
    time="10:30"        # Format: HH:MM
)

# Formatiere Ausgabe
if route:
    print(formatter.format_route_output(route, "Bern", "Genf", "10:30"))
else:
    print("Keine Route gefunden.")
```

## 📚 Skript-Dokumentation

### `main.py`
**Hauptskript - Interaktive Konsolenanwendung**

- Initialisiert alle Komponenten (DataLoader, RouteCalculator, RouteFormatter)
- Bietet eine interaktive Benutzeroberfläche für Routenberechnungen
- Ermöglicht wiederholte Routenberechnungen in einer Sitzung
- Unterstützt Standardwerte für Datum (heute) und Zeit (jetzt)

**Funktionen:**
- `main()` - Hauptfunktion mit interaktiver Eingabeschleife
- `get_user_input(prompt, default)` - Hilfsfunktion für Benutzereingaben mit optionalen Standardwerten

**Interaktive Eingaben:**
- Startstation (Pflichtfeld)
- Endstation (Pflichtfeld)
- Reisedatum (optional, Standard: heutiges Datum)
- Abfahrtszeit (optional, Standard: aktuelle Zeit)

---

### `data_loader.py`
**Lädt und verwaltet GTFS-Daten**

Die Klasse `GTFSDataLoader` ist verantwortlich für:
- Laden aller GTFS-Dateien in Pandas DataFrames
- Effiziente Datenverarbeitung mit Caching
- Konvertierung von Zeitformaten (HH:MM:SS → Sekunden)
- Verwaltung von Service-IDs basierend auf Datum und Wochentag

**Hauptfunktionen:**
- `__init__(data_dir)` - Initialisiert den Loader und lädt alle Daten
- `get_valid_services(date)` - Bestimmt gültige Service-IDs für ein Datum
- `find_stop_id(stop_name)` - Findet stop_id basierend auf Stationsname (case-insensitive)
- `get_stop_name(stop_id)` - Gibt Haltestellennamen für eine stop_id zurück

**Geladene Daten:**
- `stops` - Haltestelleninformationen
- `stop_times` - Abfahrts- und Ankunftszeiten
- `trips` - Fahrteninformationen
- `routes` - Linieninformationen
- `calendar` - Reguläre Service-Zeiten
- `calendar_dates` - Ausnahmen (Feiertage, etc.)

---

### `route_calculator.py`
**Implementiert den Connection Scan Algorithm (CSA)**

Die Klasse `RouteCalculator` berechnet die optimale Route zwischen zwei Haltestellen.

**Hauptfunktionen:**
- `__init__(data_loader)` - Initialisiert den Calculator mit einem DataLoader
- `find_route(start_name, end_name, date, time)` - Hauptfunktion zur Routenberechnung
  - Findet die schnellste Route zwischen zwei Stationen
  - Berücksichtigt Datum und Startzeit
  - Gibt eine Liste von `RouteSegment`-Objekten zurück
- `_build_connections(date, start_time_sec)` - Baut alle gültigen Verbindungen für ein Datum
- `_connection_scan_algorithm(...)` - Implementiert den CSA-Algorithmus

**Algorithmus:**
Der Connection Scan Algorithm durchläuft alle Verbindungen chronologisch und findet die früheste Ankunftszeit an jedem Stop. Dies ermöglicht eine effiziente Berechnung der optimalen Route.

---

### `analyzer.py`
**Zusätzliche Analysefunktionen**

Die Klasse `RouteAnalyzer` bietet verschiedene Analysefunktionen für die GTFS-Daten.

**Hauptfunktionen:**
- `__init__(data_loader)` - Initialisiert den Analyzer mit einem DataLoader
- `fastest_direct_connection_per_hour()` - Findet die schnellste Direktverbindung pro Stunde
  - Gibt einen DataFrame mit Stunde, Dauer und Linie zurück
- `top_10_most_frequented_stops()` - Findet die Top 10 meistfrequentierten Haltestellen
  - Basierend auf der Anzahl der Abfahrten/Ankünfte
- `overnight_connections()` - Findet Übernacht-Verbindungen
  - Verbindungen, die über Mitternacht gehen (Ankunft < Abfahrt oder Zeit >= 24:00)

---

### `formatter.py`
**Formatierung der Routenausgabe**

Die Klasse `RouteFormatter` formatiert Routen für die Konsolenausgabe.

**Hauptfunktionen:**
- `format_route_output(route, start_name, end_name, start_time)` - Formatiert eine Route für die Ausgabe
  - Zeigt Start- und Zielpunkt mit Zeiten
  - Berechnet Gesamtreisezeit
  - Zeigt alle Route-Segmente mit Umstiegen und Wartezeiten
- `seconds_to_time(seconds)` - Konvertiert Sekunden seit Mitternacht zu HH:MM Format

**Ausgabeformat:**
```
==================================================
 OptimalRoute.CH | Verbindung gefunden
==================================================
Startpunkt: Basel SBB (08:00)
Zielpunkt:  Zürich HB (09:30)
GESAMTREISEZEIT: 1 Stunde, 30 Minuten
--------------------------------------------------
  1. FAHRT
     > Abfahrt: 08:00  | Basel SBB
     > Ankunft: 09:30  | Zürich HB
     > Linie:   IC 3
==================================================
```

---

### `models.py`
**Datenmodelle**

Definiert die Datenstrukturen für das Projekt.

**Klassen:**
- `Connection` - Repräsentiert eine Verbindung zwischen zwei Haltestellen
  - Enthält: trip_id, departure_stop, arrival_stop, Zeiten, route_id, route_name
- `RouteSegment` - Repräsentiert ein Segment einer Route
  - Enthält: trip_id, route_name, Abfahrts-/Ankunftsstop mit Namen, Zeiten, Wartezeit

---

## 📊 GTFS-Daten

Das Projekt benötigt GTFS-Daten im `data/` Verzeichnis. GTFS (General Transit Feed Specification) ist ein Standardformat für ÖV-Daten.

**Benötigte Dateien:**
- `stops.txt` - Haltestelleninformationen
- `stop_times.txt` - Abfahrts- und Ankunftszeiten (kann sehr groß sein)
- `trips.txt` - Fahrteninformationen
- `routes.txt` - Linieninformationen
- `calendar.txt` - Reguläre Service-Zeiten
- `calendar_dates.txt` - Ausnahmen (Feiertage, etc.)
- `agency.txt` - Verkehrsbetriebsinformationen
- `feed_info.txt` - Feed-Metadaten
- `transfers.txt` - Umstiegsinformationen (optional)

**Datenquelle:**
GTFS-Daten können von der SBB oder anderen ÖV-Anbietern bezogen werden. Stellen Sie sicher, dass alle erforderlichen Dateien im `data/` Verzeichnis vorhanden sind.

## 🔍 Beispiel-Ausgabe

```
==================================================
 PyRouteCH - ÖV-Routenberechnung
==================================================

Initialisiere System...
Lade GTFS-Daten...
  Lade stop_times.txt (dies kann einige Zeit dauern)...
  Lade calendar_dates.txt...
Daten erfolgreich geladen!

==================================================
 Routenberechnung
==================================================

Startstation: Basel SBB
Endstation: Zürich HB
Reisedatum (YYYY-MM-DD) [2025-01-15]: 2025-12-15
Abfahrtszeit (HH:MM) [14:30]: 08:00

--------------------------------------------------
Berechne Route: Basel SBB → Zürich HB
Datum: 2025-12-15, Zeit: 08:00
--------------------------------------------------

Baue Verbindungen für 2025-12-15...
  12345 Verbindungen gefunden
Berechne optimale Route...
==================================================
 OptimalRoute.CH | Verbindung gefunden
==================================================
Startpunkt: Basel SBB (08:00)
Zielpunkt:  Zürich HB (09:30)
GESAMTREISEZEIT: 1 Stunde, 30 Minuten
--------------------------------------------------
  1. FAHRT
     > Abfahrt: 08:00  | Basel SBB
     > Ankunft: 09:30  | Zürich HB
     > Linie:   IC 3
==================================================

Weitere Route berechnen? (j/n): 
```

## 📝 Hinweise

- Die Initialisierung des DataLoaders kann einige Zeit dauern, besonders beim Laden von `stop_times.txt` bei großen Datensätzen
- Die Routenberechnung verwendet den Connection Scan Algorithm, der für große Netzwerke effizient ist
- Stationennamen werden case-insensitive und mit Teilstring-Matching gesucht
- Das System unterstützt Übernacht-Verbindungen (Zeiten > 24:00)
- Bei Datum und Zeit können Sie einfach Enter drücken, um die Standardwerte (heute/aktuelle Zeit) zu verwenden
- Das Programm kann mit `Ctrl+C` jederzeit beendet werden

## 🐛 Fehlerbehebung

**Problem:** "Keine Route gefunden"
- Überprüfen Sie, ob die Stationsnamen korrekt sind
- Stellen Sie sicher, dass für das gewählte Datum Verbindungen verfügbar sind
- Prüfen Sie, ob die GTFS-Daten vollständig sind

**Problem:** "Startstation '...' nicht gefunden"
- Überprüfen Sie den Stationsnamen (Groß-/Kleinschreibung wird ignoriert)
- Verwenden Sie den vollständigen Namen (z.B. "Basel SBB" statt nur "Basel")

**Problem:** Langsame Performance
- Dies ist normal bei großen GTFS-Datensätzen
- Der DataLoader verwendet Caching für bessere Performance bei wiederholten Abfragen

## 📄 Lizenz

Dieses Projekt wurde im Rahmen von Modul 323 erstellt.

