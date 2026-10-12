# Journal Trade - Aplikacja Desktopowa

Aplikacja do prowadzenia dziennika transakcji giełdowych (trading journal). Działa w całości lokalnie na komputerze użytkownika - nie wymaga konta, zewnętrznego serwera ani połączenia z internetem (poza opcjonalną synchronizacją z brokerem).

Celem projektu jest pomoc traderowi w systematycznej analizie własnych wyników: zapisywaniu każdej transakcji (ceny, godzina, notatki, screenshot wykresu), przeglądaniu wyników w formie kalendarza oraz wyciąganiu wniosków na podstawie statystyk.

---

## Najważniejsze funkcje

* **Dashboard** - podsumowanie dnia, tygodnia, miesiąca i całości, krzywa kapitału z 30 dni, animowany wskaźnik winrate, seria wygranych/przegranych, najlepszy i najgorszy trade.
* **Kalendarz** - widok miesięczny, w którym każdy dzień pokazuje liczbę transakcji i łączny zysk/stratę (kolor zielony/czerwony). 
* **Widok dnia** - lista wszystkich transakcji z danego dnia: godzina wejścia, entry/exit price, wielkość pozycji, tagi, notatki i zrzuty ekranu.
* **Zaawansowane statystyki** - wynik wg dnia tygodnia i godziny wejścia, profit factor, średni R:R, wartość oczekiwana (expectancy) oraz analiza skuteczności poszczególnych tagów/strategii.
* **Kalkulator ryzyka** - wylicza wielkość pozycji na podstawie kapitału, % ryzyka i stop lossa.
* **Trzy metody wprowadzania transakcji** - ręcznie, import pliku CSV/HTML oraz automatyczna synchronizacja przez API.
* **Eksport danych** - pełna kopia danych do pliku CSV.

## Technologie

* **Backend:** Python 3, Flask (REST API + szablony Jinja2), SQLite
* **Frontend:** HTML5, CSS3 (własny design system, animacje), JavaScript (ES6+), Chart.js
* **Integracje:** MetaTrader 5 (MetaTrader5), Binance Futures REST API (podpis HMAC-SHA256)
* **Inne:** Architektura wielowątkowa (synchronizacja w tle), Pillow

## Instalacja i uruchomienie

Wymagania: Windows 10/11, Python 3.10 lub nowszy.

1. Sklonuj repozytorium i zainstaluj zależności:

    pip install -r requirements.txt

2. (Opcjonalnie) Utwórz ikonę na pulpicie uruchamiając skrypt:

    python setup_shortcut.py

3. Uruchom aplikację:

    python app.py

Aplikacja automatycznie otworzy przeglądarkę pod adresem: http://127.0.0.1:5555

> Uwaga: Baza danych (SQLite) tworzy się i konfiguruje automatycznie przy pierwszym uruchomieniu w pliku data/trades.db.

## Metody wprowadzania danych

1. **Automatyczna synchronizacja API (MT5 / Binance):** Aplikacja może działać w tle i co wybraną liczbę minut pobierać nowe, zamknięte pozycje z użyciem kluczy API (tylko odczyt).
2. **Import plików CSV/HTML:** Obsługa raportów z MetaTrader 4/5 oraz plików CSV z innych brokerów (kolumny są mapowane automatycznie). Narzędzie zapobiega duplikatom podczas ponownego importu.
3. **Wprowadzanie ręczne:** Pełna kontrola nad każdym trade'm, z możliwością wklejenia screenshota bezpośrednio ze schowka (Ctrl+V).

## Struktura projektu

    aplikacja/
    ├── app.py                 # Serwer główny Flask, REST API, migracje bazy
    ├── importers.py           # Parsery plików i obsługa API (MT5, Binance)
    ├── setup_shortcut.py      # Automatyzacja tworzenia skrótów Windows
    ├── data/                  # Baza danych SQLite (generowana auto)
    ├── templates/             # Widoki HTML (Jinja2)
    └── static/                # CSS, JS, Chart.js, zapisane zrzuty ekranu

## Architektura i rozwiązania techniczne

* **Architektura lokalna:** Flask serwuje endpointy JSON, a frontend pobiera dane asynchronicznie (Fetch API) renderując wykresy.
* **Wydajność:** Główne statystyki i agregacje liczone są bezpośrednio po stronie silnika bazy danych (SQLite), co zapewnia płynność nawet przy ogromnej historii transakcji.
* **Bezpieczeństwo danych:** Aplikacja działa wyłącznie lokalnie (nasłuchuje na 127.0.0.1). Klucze API i historia transakcji nie opuszczają dysku komputera. Zapytania SQL są w pełni parametryzowane.
* **Rozwiązywanie konfliktów:** Unikalny indeks na kolumnie external_id wsparty instrukcją INSERT OR IGNORE gwarantuje całkowity brak duplikatów przy imporcie z wielu źródeł naraz.

## Możliwy dalszy rozwój

* Dodanie integracji z API Bybit, XTB i Interactive Brokers.
* Obsługa i rozdzielenie wielu portfeli/kont inwestycyjnych.
* Szyfrowanie wrażliwych kluczy API.
* Dystrybucja jako pojedynczy, niezależny plik .exe przy pomocy PyInstaller.

---
**Autor:** Wojciech Goch
