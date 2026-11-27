# GOAL 27A — Audyt końcowy branchy Rackonaut

Audyt z 27 listopada 2026 porównuje 48 branchy GitHuba z `integration/full-system` na `e960d6dc0a422a4597b7b5608f56ed3a53eb7c91`. Po `fetch` zweryfikowano historię, równoważność patchy i zgłoszenia zespołu. Lista zdalnych refów była identyczna z zapisem po publikacji GOAL 27. Siedem branchy wymagało sprawdzenia różnic. Wersje lokalne `main` (`ade02aa`) i `integration/x3-full-robotics` (`f4ca62f`) są przodkami swoich odpowiedników na GitHubie. Pozostałe lokalne branche wskazywały te same rewizje co odpowiadające im refy zdalne.

## Wkład zespołu

| Osoba | Potwierdzony wkład | Podstawa |
| --- | --- | --- |
| Adrian Zygarowski (`Adiksoon`) | Magazyn i showroom, percepcja, wspólna integracja, Control Center, Mock SAP i rekomendacje biznesowe. | `d9b1d3d`, `4d971fc`, `3c7c97b`, `f50cfee`; [odbiór GOAL 27](FULL_SYSTEM_INTEGRATION.md). |
| Michał (`michalczaplinski5`) | Dostarczył X3 z kamerą, mostami ROS 2 i integracją układów współrzędnych. Zgłosił także odbiór lotu X3 z lokalizacją LiDAR/IMU, trasy i cyklu ładowania. | [PR #7](https://github.com/Adiksoon/rackonaut/pull/7), [PR #9](https://github.com/Adiksoon/rackonaut/pull/9), merge `0953cbb` jego autorstwa i [odbiór X3](X3_FULL_ROBOTICS_INTEGRATION.md). Poszczególne commity z PR zachowują swoich autorów Git. |
| Vahid Abdullayev (`abzdullayezz`) | Niezależny importer CSV, walidacja, szablony, przykłady, dokumentacja i 54 testy importu. | `0efb6b0` z [PR #8](https://github.com/Adiksoon/rackonaut/pull/8) jest przodkiem integracji przez `3f42ff7`. Audyt dostępnych branchy, autorów i PR-ów nie wykazał innych prac przypisywalnych Vahidowi. |
| Tharindu | Rozważano pracę nad dashboardem na etapie podziału zadań. | Dostępne branche, commity i PR-y nie pozwoliły potwierdzić dostarczonego modułu. |

Git podaje `Codex` jako autora `28bdaf7`, `a2fd71c` i `32d4092`. Autorstwo konkretnej osoby dla tych commitów pozostaje niepotwierdzone. `568c313` zachowuje autora i wskazuje źródło Warehouse in Motion. `42e36df` zachowuje autora źródłowych testów X3, wskazuje rewizje źródłowe i dokumentuje ich adaptację. Rejestr zespołu jest w [TEAM_TASKS.md](TEAM_TASKS.md).

### feature/drone

Wszystkie siedem patchy z PR #7 jest obecnych. `git cherry -v e960d6d origin/feature/drone` oznacza wszystkie siedem jako równoważne, a wiadomości commitów zachowują pełne źródłowe SHA.

| Oryginał | Cherry-pick | Zakres |
| --- | --- | --- |
| `ddf0db2` | `17edc73` | Model i izolowana walidacja X3 |
| `4b1ee18` | `84ddcff` | Checklista integracji i próby Safety |
| `58ca460` | `e6b7f37` | Próby misji i zabezpieczeń X3 |
| `1e3fdfc` | `308e680` | Opcjonalny profil inspekcji X3 |
| `708c865` | `275ea1a` | Szum kamery i oświetlenie |
| `7e92578` | `a5ce0ba` | Próby lokalizacji w trybie obserwacyjnym LiDAR/IMU |
| `6d68860` | `d0257bb` | Utrata danych sensorów i odzyskanie śledzenia |

`codex/x3-full-robotics-acceptance` (`f06a38c`) i `feature/inventory-import` (`0efb6b0`) są przodkami integracji. Importer operuje na własnych wynikach walidacji CSV. Mock SAP i konfiguracja aktywnego magazynu mają własne ścieżki danych.

## Dwa dodatkowe commity X3

Porównano [`28bdaf7`](https://github.com/Adiksoon/rackonaut/commit/28bdaf766cc1a9a80b6f80e4c378346b4a3f2e7a) i [`a2fd71c`](https://github.com/Adiksoon/rackonaut/commit/a2fd71c3c4443af67be3dc9a5ad010e60150e3fa) względem `feature/drone` oraz wspólnego stosu.

| Element źródłowy | Stan wspólnej wersji i decyzja |
| --- | --- |
| Aktywna lokalizacja i normalizacja ramek w `28bdaf7`, osobny `localize_x3` w `a2fd71c` | Wspólny `rackonaut_localization` i profil X3 publikują zweryfikowaną odometrię z IMU i LiDAR-u. Niezależne uruchamianie i zestaw mostów powielałyby właściciela odometrii. Kod produkcyjny pozostaje wspólny. |
| Przetwarzanie IMU poza ciężkim dopasowaniem skanu | Wspólna lokalizacja ma oddzielny odbiornik, ograniczoną kolejkę, kontrolę ramki i kolejności oraz aktualność od czasu odbioru. Zaadaptowano test błędnej ramki, duplikatu, cofniętego stempla i przejścia w `LOST` po ustaniu postępu IMU. |
| Dokładne parowanie skanu z odometrią | Wspólny `Scanner` ma ograniczoną kolejkę skanów, dopuszcza spóźnioną odometrię o tym samym stemplu i zachowuje moment odbioru. Uzupełniono test o odzyskanie kolejnego skanu i przypadek, w którym pasująca odometria przyszła po wygaśnięciu skanu. |
| Ograniczenie napędu, watchdog, wyłączenie silników | Wspólna misja ogranicza translację przy doku, a profil X3 pilnuje świeżości komendy i gotowości mostu. Zaadaptowano test ograniczenia translacji i jawnej komendy zerowej. Istniejący test potwierdza wyłączenie dopiero po potwierdzonym styku doku. |
| Osobny `DockPower` i logika ładowania | Wspólne Energy, Safety i Mission weryfikują styk, gotowość ładowania, świeżą zgodę na kolejny wylot i wznowienie od nieukończonego zakresu. Zaadaptowano test blokady ponownego uzbrojenia przy nieaktualnej zgodzie lub braku gotowości ładowania. Zachowano jeden mechanizm sterowania napędem. |
| `plan_x3` i oddzielna trasa po ładowaniu | Wspólny planner wspiera pionowe zejście z wysokiej lokalizacji, a wspólna misja rozdziela wybrane podejścia na pionowe i poziome w granicach rezerwacji. Rozszerzono test do czterech przejść, 11 przystanków po wczytaniu pliku, zachowania widoków ponownej inspekcji oraz profilu standardowego. |
| Utrata IMU/LiDAR, nieświeża pozycja, powrót sensora | Wspólny stos wymaga aktualnej pozycji i sparowanego skanu, blokuje ruch przy utracie wymaganych danych, a misja zachowuje procedurę Safety przy przerwaniu. Skopiowano zapis osobnej próby utraty sensora. Aktualny audyt ponownie sprawdził wygasanie w testach automatycznych. |
| Skrypty `run_mission`, `serve_x3`, `prepare_model`, `sensor_frames` i launch testowy | Wspólny profil `checkpoint live drone_model:=x3` pokrywa przygotowanie symulatora, odometrii, misji i serwera. Osobne wejścia wiążą się ze starszą konfiguracją mostów, napędu i tras. Źródła historyczne pozostają dostępne na branchu. |
| Dokumentacja i dowody | Zachowano oba oryginalne pliki JSON z identycznymi blobami Git. [Aktywna lokalizacja](../ros2_ws/src/rackonaut_drone/docs/evidence/x3-active-flight.json) dokumentuje próby częściowe i 11 lokalizacji zebranych między próbami. [Pełna próba samodzielna](../ros2_ws/src/rackonaut_drone/docs/evidence/x3-full-mission-acceptance.json) dokumentuje ukończony lot, dok, ładowanie i osobną utratę danych. Wyniki wspólnego stosu mają osobne [dowody GOAL 27](FULL_SYSTEM_INTEGRATION.md). |

## Pozostałe rozbieżności

- `codex/control-center-operator-flow` (`d4c6d5d`) i `codex/control-center-reliability` (`6bc3b7f`). Uproszczone komunikaty lotu, mapa na żądanie, obsługa odłączenia kamery, komunikaty błędów i priorytety w Results mają odpowiedniki we wspólnym GUI. Wspólny Control Center również czyta surowy obraz i oddzielnie śledzi gotowość percepcji. Unikalne zmiany to pomiar opóźnień publikacji Safety, ostrzeżenie przy zatrzymaniu heartbeat, pojedynczy wątek OpenCV w Perception oraz przejście zegara timera Safety na `STEADY_TIME`. Pierwsze trzy są zmianami diagnostycznymi lub strojenia. Zmiana zegara wpływa na działanie zabezpieczeń przy pauzie symulacji i wymaga osobnego odbioru. Oba branche zachowano jako źródło tych różnic.
- `docs/local-contract-tests` (`83e46ed`). Instrukcje wykonania kontraktów w Ubuntu/WSL i PowerShell są w [README](../README.md#tests). Testy odpowiadają poleceniu z [GitHub Actions](../.github/workflows/contract-tests.yml).
- `integration/demo-baseline` (`7b1d190`). Zachowano branch historyczny. Aktualny [przewodnik integracji](INTEGRATION.md), [odbiór](FULL_SYSTEM_INTEGRATION.md) i [README](../README.md) opisują profile, polecenia uruchamiania i bramki. Starsze przypisania zadań i układ demonstratora ustąpiły zweryfikowanemu stanowi.
- `codex/warehouse-in-motion` (`32d4092`). Zaadaptowano opcjonalną demonstrację, opisaną poniżej.

## Warehouse in Motion

Z katalogu repozytorium przygotowanego według [README](../README.md#start-here):

```bash
scripts/robotics/warehouse-in-motion --keep-open
```

W [Control Center](http://127.0.0.1:18770/) wybierz **Results** po zakończeniu lotu. Opcja `--gui` uruchamia też Gazebo, a `--keep-open` zostawia stos uruchomiony po weryfikacji. Scenariusz korzysta ze wspólnego profilu `checkpoint live` z X3, osobnym ROS Domain ID, partycją Gazebo i lokalną instancją Mock SAP. Wywołuje istniejące `/api/plan` i `/api/start`. Usługi Gazebo dodają tylko dwa obiekty scenariusza. Wózek zmienia położenie w czterech krokach, a osłona zakrywa etykietę. Lot, odczyty, decyzje Safety, raport i zapis zdjęć pochodzą ze standardowych modułów.

[Dokumentacja scenariusza](WAREHOUSE_IN_MOTION.md) opisuje uruchamianie i historyczną próbę. Aktualna próba korzystała ze świata pokazowego, profilu X3 z LiDAR-em o zasięgu 8 m, lokalizacji względem znanej mapy i wirtualnego profilu stref Safety. LiDAR mierzył przeszkodę niezależnie od wirtualnego Safety. Wynik dotyczy wózka w bramce A i trzech lokalizacji w torze demonstracyjnym.

## Walidacja

Kompletna misja `INS-CONTROL-20261127-075753-B3666FCC` trwała 356,5 s od przyjęcia żądania startu do zweryfikowania wyniku. W fazie `AISLE_DESCENT` Collision Prevention zapisał `measured obstacle`. Od odbioru użytego skanu do wydania polecenia hamowania minęło 287 ms. Od wykrycia do ustabilizowanego zatrzymania minęło 1,3 s, a przesunięcie pozycji wyniosło 0,094 m. X3 zatrzymał się na Z = 2,241 m. Po odjeździe wózka i bez polecenia wznowienia kontynuował tę samą fazę do Z = 2,086 m. Pomiary pochodzą z tej próby Gazebo. [Dane zdarzeń i wynik misji](final-branch-audit-evidence/result.json).

| Lokalizacja | Obserwacja kamery i wynik Mock SAP | Dowody |
| --- | --- | --- |
| `A-01-01` | Zajęta, osłonięta etykieta. `UNREADABLE_LABEL`. | [Oryginał PNG](final-branch-audit-evidence/A-01-01-original.png) · [Results](final-branch-audit-evidence/results-A-01-01.png) |
| `A-01-02` | Kamera odczytała `P003`, a Mock SAP oczekiwał `P002`. `WRONG_PALLET`, `MISPLACED_PALLET`. | [Oryginał PNG](final-branch-audit-evidence/A-01-02-original.png) · [Results](final-branch-audit-evidence/results-A-01-02.png) |
| `A-01-03` | Pusta lokalizacja z oczekiwaną paletą. `MISSING_PALLET`. | [Oryginał PNG](final-branch-audit-evidence/A-01-03-original.png) · [Results](final-branch-audit-evidence/results-A-01-03.png) |

Raport zwrócił HTTP 200. Misja zakończyła się w `COMPLETE` z trzema potwierdzeniami, fizycznym stykiem doku i `Safety RELEASED`. W Chrome z Playwright wybrano trzy lokalizacje i sprawdzono, że ich oryginały załadowały się w Results (320 × 240 px). [Zrzut Results](final-branch-audit-evidence/results.png) · [Raport HTML](final-branch-audit-evidence/report.html) · [Wynik przeglądarkowy](final-branch-audit-evidence/browser.json).

| Polecenie | Wynik |
| --- | --- |
| `source scripts/robotics/activate.bash && /usr/bin/python3 -m pytest -q ros2_ws/src` | 82 testy zaliczone, w tym adaptacje czterech zestawów X3 |
| `.venv-backend/bin/python -m unittest discover -s tests -q` | 62 testy zaliczone |
| `.venv-backend/bin/python scripts/api/smoke.py` | API-01, API-02 i sprzątanie zaliczone |
| `bash -n scripts/robotics/warehouse-in-motion` i `python3 -m py_compile scripts/robotics/scenarios/warehouse_in_motion.py` | Obie kontrole składni zaliczone |

## Inwentarz branchy

„W historii” oznacza, że ostatni commit brancha był przodkiem `e960d6d` przed pracami 27A. Dla rozbieżnych gałęzi decyzje i sposób zachowania wkładu opisano wyżej.

| Branch na origin | Commit na początku audytu | Relacja do bazy |
| --- | --- | --- |
| `ci/contract-test-badge` | `6e01821` | W historii |
| `codex/control-center-operator-flow` | `d4c6d5d` | Rozbieżny |
| `codex/control-center-refresh` | `86682ea` | W historii |
| `codex/control-center-reliability` | `6bc3b7f` | Rozbieżny |
| `codex/warehouse-in-motion` | `32d4092` | Rozbieżny |
| `codex/x3-full-mission-acceptance` | `a2fd71c` | Rozbieżny |
| `codex/x3-full-robotics-acceptance` | `f06a38c` | W historii |
| `docs/local-contract-tests` | `83e46ed` | Rozbieżny |
| `docs/rackonaut-readme` | `4213d6e` | W historii |
| `feature/adaptive-inspection` | `39d5a86` | W historii |
| `feature/aerial-infrastructure` | `1818d64` | W historii |
| `feature/autonomous-recovery` | `dd854a4` | W historii |
| `feature/control-center-simplification` | `f759521` | W historii |
| `feature/demo-readiness` | `de57a33` | W historii |
| `feature/digital-twin` | `a014547` | W historii |
| `feature/digital-twin-control-center` | `15bce96` | W historii |
| `feature/drone` | `6d68860` | Rozbieżny |
| `feature/energy-management` | `e3a0d79` | W historii |
| `feature/engineering-showcase` | `44ea9e3` | W historii |
| `feature/enhanced-digital-twin` | `e417074` | W historii |
| `feature/final-control-center-ux` | `2a7d24a` | W historii |
| `feature/inventory-import` | `0efb6b0` | W historii |
| `feature/learned-warehouse-autonomy` | `e43ccf7` | W historii |
| `feature/measured-3d-map` | `de4677e` | W historii |
| `feature/measured-map-refinement` | `0fe5edc` | W historii |
| `feature/measured-warehouse-reconstruction` | `a30f8eb` | W historii |
| `feature/mission` | `6d10e45` | W historii |
| `feature/mission-control` | `b5e310d` | W historii |
| `feature/obstacle-avoidance` | `541948b` | W historii |
| `feature/perception` | `4d971fc` | W historii |
| `feature/protected-manual-flight` | `3745e74` | W historii |
| `feature/quality-inspection` | `593d51a` | W historii |
| `feature/route-teaching` | `c931e36` | W historii |
| `feature/sap-business-intelligence` | `3c7c97b` | W historii |
| `feature/sensor-localization` | `48f30c6` | W historii |
| `feature/sensor-safety` | `ca1fa1e` | W historii |
| `feature/service-center` | `de61082` | W historii |
| `feature/slam-full-route-validation` | `75c83d4` | W historii |
| `feature/storage-location-teaching` | `4d5a8a5` | W historii |
| `feature/unknown-warehouse-mapping` | `222c0d0` | W historii |
| `feature/warehouse` | `d9b1d3d` | W historii |
| `feature/warehouse-safety` | `2a60fa5` | W historii |
| `integration/competition-main` | `5e3696d` | W historii |
| `integration/demo-baseline` | `7b1d190` | Rozbieżny |
| `integration/demo-complete` | `cc8f742` | W historii |
| `integration/full-system` | `e960d6d` | W historii |
| `integration/x3-full-robotics` | `0953cbb` | W historii |
| `main` | `6e04fcf` | W historii |
