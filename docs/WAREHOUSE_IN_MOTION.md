# Magazyn w ruchu

Powtarzalny scenariusz Full Robotics z dronem X3. Gazebo przesuwa wózek z ładunkiem i zakrywa etykietę. Obraz dostarcza kamera X3, przeszkodę mierzy pokładowy LiDAR, a obserwacje porównuje Mock SAP. Scenariusz korzysta z istniejących interfejsów inspekcji. Polecenia ruchu drona nadal wydaje Mission Manager.

1. Podczas przelotu górnym korytarzem wózek z ładunkiem przecina przejazd pod bramką zniżania do alei A. Scenariusz czeka na pomiar zatrzymania przed wózkiem i dopiero wtedy odstawia wózek. X3 czeka na prześwit i kontynuuje zniżanie.
2. Przy dolocie osłona zasłania etykietę palety na `A-01-01`. Znacznik stanowiska pozostaje widoczny. Oczekiwany wynik to zajęte stanowisko z nieczytelną etykietą.
3. Na `A-01-02` kamera widzi paletę `P003`, podczas gdy Mock SAP oczekuje `P002`. Model palety pochodzi z istniejącego świata magazynu. Misję zamykają odczyt `A-01-03` i powrót do doku.

## Uruchomienie

W Ubuntu 22.04 lub WSL2 przygotuj środowisko według [README](../README.md#start-here). Z katalogu projektu uruchom:

```bash
scripts/robotics/warehouse-in-motion
```

Dodaj `--gui`, aby zobaczyć ruch wózka w oknie Gazebo, i `--keep-open`, aby przejrzeć Results po zakończeniu lotu. [Control Center](http://127.0.0.1:18770/) jest dostępny lokalnie, a Mock SAP działa na porcie 18005. Skrypt sam planuje i uruchamia inspekcję trzech stanowisk. Zmienne `RACKONAUT_SCENARIO_HTTP_PORT`, `RACKONAUT_SCENARIO_MOCK_PORT` i `RACKONAUT_SCENARIO_DOMAIN_ID` pozwalają wskazać wolne porty i domenę ROS. Do demonstracji wybierz jedną aktywną symulację. Ctrl+C kończy instancję scenariusza.

Katalog dowodów jest wypisywany przy starcie. Zawiera dziennik zdarzeń, log startu, a po zaliczeniu także `result.json`, `report.html` i trzy oryginalne PNG z kamery. Program wymaga pomiaru zatrzymania przed wózkiem, wznowienia zniżania po odjeździe wózka, oczekiwanych kategorii rozbieżności, trzech obserwacji, końcowego styku doku oraz stanu Safety `RELEASED`. Każde zdjęcie musi być powiązane z identyfikatorem, lokalizacją, znacznikiem czasu i zajętością obserwacji.

## Wynik wspólnego stosu (GOAL 27A)

Misja `INS-CONTROL-20261127-075753-B3666FCC` ukończyła trzy lokalizacje w 356,5 s. X3 zatrzymał się po przebyciu 0,094 m od wykrycia wózka pod bramką A i wznowił zniżanie po odjeździe wózka. Mock SAP poprawnie oznaczył nieczytelną etykietę, błędną i przestawioną paletę oraz puste miejsce z oczekiwaną paletą. Potwierdzono styk doku i zwolnienie stref. W Chrome widok Results wyświetlił oryginalne zdjęcia wszystkich trzech lokalizacji. [Wyniki audytu i dowody](FINAL_BRANCH_AUDIT.md#walidacja)

## Próba źródłowa

Misja `INS-CONTROL-20261126-211927-26746E94` potwierdziła wszystkie trzy stanowiska. Pod bramką A dron po wykryciu wózka przebył jeszcze 0,102 m, zanim się zatrzymał. Wznowił zniżanie po odjeździe wózka. Raport zwrócił HTTP 200 i rozróżnił zajęte stanowisko z nieczytelną etykietą, błędną paletę oraz brak oczekiwanej palety. Fizyczny styk w doku został potwierdzony, a Safety zwolniło strefy. [Dane próby](warehouse-in-motion-evidence.json)

Współbieżny demonstrator był wstrzymany podczas pomiaru i wznowiony po teście. We wcześniejszej próbie z aktywnym demonstratorem watchdog zatrzymał powrót po przerwie w danych LiDAR-u. Test opisuje symulację w WSL2 i wirtualny profil nadzoru stref.
