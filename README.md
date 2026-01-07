# PyRouteCH

Kleines Python-Script zur **ÖV-Routenberechnung** auf Basis von **GTFS-Daten** (Ordner `data/`).

## Quickstart

### Voraussetzungen

- **Python 3.8+**
- GTFS-Dateien im Ordner `data/` (mindestens: `stops.txt`, `stop_times.txt`, `trips.txt`, `routes.txt`, `calendar.txt`, `calendar_dates.txt`)

### Installation

```bash
pip install -r requirements.txt
```

### Starten

```bash
python main.py
```

Danach im Terminal:
- **Startstation** eingeben (bei mehreren Treffern kannst du eine Nummer auswählen)
- **Endstation** eingeben
- **Datum** im Format `YYYY-MM-DD` (Enter = heute)
- **Zeit** im Format `HH:MM` (Enter = aktuelle Zeit)

Beenden: `Ctrl+C` oder bei „Weitere Route berechnen?“ mit `n`.

## Wichtige Dateien (kurz)

- `main.py`: Startpunkt (interaktive Konsole)
- `data_loader.py`: lädt GTFS aus `data/`
- `route_calculator.py`: berechnet die Route
- `formatter.py`: formatiert die Ausgabe

## Hinweise / Troubleshooting

- Erster Start kann **langsamer** sein, weil `stop_times.txt` sehr groß sein kann.
- „Keine Route gefunden“: Datum/Zeit prüfen und ob die Stationen im GTFS-Feed wirklich existieren.

---
Erstellt im Rahmen von **Modul 323**.

