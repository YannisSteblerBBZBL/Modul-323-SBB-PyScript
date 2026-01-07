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

## Dokumentation

### Wahl der imperativen Programmiersprache (Python) + funktionale Elemente (Recherche)

**Warum Python?**

- Python ist primär **imperativ** (Anweisungen/Schritte), unterstützt aber mehrere Paradigmen (u.a. objektorientiert & funktional).  
- Für dieses Projekt ist Python geeignet wegen **guter Datenverarbeitung** (z.B. `pandas`, `numpy`) und schneller Iteration in der Konsole.

**Unterstützte funktionale Elemente in Python (Auswahl)**

- **First-class Functions**: Funktionen sind Werte (können als Parameter übergeben/returned werden).
- **Lambda / Higher-Order Functions**: z.B. `sorted(..., key=lambda x: ...)`, `map`, `filter`.
- **Comprehensions & Generator Expressions**: kompakte Transformationen, z.B. `[... for ...]`, `{... for ...}`, `(... for ...)`.
- **(Im-)Mutability**: z.B. `tuple`, `frozenset`; sowie `@dataclass(frozen=True)` für unveränderliche Datenobjekte.

**Welche davon werden im Projekt konkret verwendet?**

- `data_loader.py`: Normalisierung via `Series.map(...)` und Sortierung mit `key=lambda ...`.
- `route_calculator.py`: `@dataclass(frozen=True)` für Labels (immutables Objekt), lokale Helferfunktionen, Sortierung via `key=lambda ...`, Generator-Expression für Route-Deduplizierung.
- Zusätzlich: deklarative Datenoperationen mit `pandas` (z.B. `merge`, `groupby(...).shift()`), wodurch viele Schleifen/Einzelschritte kompakter werden.

### Projektantrag

**Ausgangslage**

- GTFS-Daten liegen als Textdateien vor und enthalten Fahrpläne/Stops/Trips. Gesucht ist eine Verbindung zwischen zwei Stationen zu Datum/Zeit.

**Ziel**

- Eine Konsolen-Anwendung, die auf Basis der GTFS-Daten **eine oder mehrere** passende ÖV-Routen zwischen Start und Ziel berechnet und lesbar ausgibt.

**Abgrenzung**

- Keine GUI, kein Webservice, keine Live-API; nur GTFS-Dateien im Ordner `data/`.

**Anforderungen (Kurz)**

- **Muss**: Stationen eingeben, Datum/Zeit wählen (mit Defaults), Route berechnen, Ausgabe in der Konsole.
- **Kann**: mehrere Alternativen (Top-N), robustes Stationen-Matching (Teilstring/Mehrfachtreffer-Auswahl).
- **Nicht-funktional**: akzeptable Laufzeit auch bei großem `stop_times.txt` (Pruning/Begrenzung der Suche).

**Vorgehen / Meilensteine**

- Daten laden (GTFS) und validieren
- Routenberechnung implementieren
- Ausgabe formatieren
- Refactoring/Verbesserungen (Lesbarkeit/Performance) ohne Output-Änderung

### Output (V1.0 und V2.0)

**Vorgabe:** V1.0 und V2.0 sollen **denselben Output-Aufbau** (Header/Struktur) generieren; Unterschiede ergeben sich nur aus den eingegebenen Stationen/Datum/Zeit und den verfügbaren GTFS-Daten.

**Beispiel (gekürzt)**

```text
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
Reisedatum (YYYY-MM-DD) [2026-01-07]: 2026-01-07
Abfahrtszeit (HH:MM) [08:00]: 08:00

--------------------------------------------------
Berechne Route: Basel SBB → Zürich HB
Datum: 2026-01-07, Zeit: 08:00
--------------------------------------------------

Baue Verbindungen für 2026-01-07...
  12345 Verbindungen gefunden
Berechne optimale Routen...
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

### Fazit (funktionale Elemente & Refactoring)

**Welchen Nutzen bringen funktionale Elemente konkret?**

- **Kürzer & klarer** bei Transformationen/Sortierung (z.B. `sorted(..., key=...)`, Generator-Expressions).
- **Weniger Fehlerquellen** durch Immutability an kritischen Stellen (`@dataclass(frozen=True)` bei Labels).
- **Lesbarkeit**: Datenfluss wird „deklarativer“, besonders bei `pandas`-Operationen (Merge/GroupBy/Shift statt manueller Schleifen).

**Hat das Refactoring vereinfacht?**

- Ja: Logik ist stärker in **kleine, klar benannte Funktionen** aufgeteilt und nutzt mehr deklarative Operationen, wodurch weniger „Boilerplate“-Code nötig ist.

**Würden wir funktionale Elemente wieder verwenden?**

- Ja, vor allem für **Transformationen, Filter/Sortierung, Deduplizierung** und für **immutable Datenobjekte** in Algorithmen.

**Mögliche Anwendungsfälle im Betrieb**

- ETL/Reporting (CSV/DB → bereinigen → aggregieren)
- Log-Auswertung/Monitoring-Pipelines (filter/map/reduce-artige Schritte)
- Scheduling/Optimierung/Graph-Probleme, wo **immutable Labels/States** Debugging vereinfachen

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

