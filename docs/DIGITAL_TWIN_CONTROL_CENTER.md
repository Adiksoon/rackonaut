# Rackonaut · Digital Twin w Control Center

Control Center wczytuje ten sam parametryczny model w Plan inspection, Live flight, Results i podglądach Service. Dane wizualne mają własny cykl zapisu i odczytu. Obowiązujące mapy SLAM, trasy, pozy inspekcyjne oraz decyzje Mission Manager, Collision Prevention, Safety i Recovery nadal korzystają z danych nawigacyjnych.

## Uruchomienie

Po przygotowaniu środowiska z [README](../README.md#start-here) uruchom z katalogu repozytorium:

```bash
scripts/robotics/build
read -rs RACKONAUT_SERVICE_CODE
export RACKONAUT_SERVICE_CODE
scripts/robotics/checkpoint live learned_warehouse:=true \
  http_port:=8772 mock_port:=8072 data_dir:=/ścieżka/do/danych
```

Otwórz [lokalny Control Center](http://127.0.0.1:8772/). Z istniejącym katalogiem danych aktywna wersja i jej model są odtwarzane po restarcie. W nowym katalogu użyj **Service → Warehouse Calibration**, aby wykonać mapowanie, zapisać lokalizacje, wrócić do doku i zatwierdzić trasę. **Save warehouse configuration** zapisuje wersję. Zamknij kalibrację i użyj **Warehouse Configuration**, aby sprawdzić integralność, obejrzeć model i aktywować konfigurację przy fizycznym doku. Odblokowanie Service, gotowość położenia, rezerwacja i budżet energii nadal warunkują odpowiednie działania.

## Ekrany

- **Plan inspection** rozdziela wybór, prognozę i start od sceny 3D. Kliknięcie znacznika aktualizuje tę samą listę co pole wyboru lokalizacji. Niebieskie znaczniki oznaczają wybrany zakres. Miejsca bez przypisania do półki mają oddzielną listę pod sceną.
- **Live flight** pokazuje orientację drona i ścieżki z aktualnej telemetrii. Kamera, cel, stan misji i energia są w panelu obok. Wspólna scena udostępnia rzut z góry i zapisane punkty LiDAR. Podczas właściwego mapowania Service przełącza scenę na strumień pomiarowy.
- **Results** przypisuje do modelu rzeczywiste wyniki Mock SAP oraz problemy biznesowe. Potwierdzona rozbieżność, uszkodzenie opakowania, blokada lub wycofanie produktu dają kolor czerwony. Sprawy wymagające weryfikacji są pomarańczowe. Zielony wymaga pozytywnego wyniku i braku wykrytych problemów. Niesprawdzone lokalizacje są szare. Kliknięcie otwiera dostępne dane i zdjęcia. Starszy raport zachowuje własną wersję magazynu po zmianie aktywnego wyboru.
- **Service** obejmuje Drone Management, Manual Control, Warehouse Calibration i Warehouse Configuration. Manual zachowuje W, A, S, D, R, F, Q, E i spację. Ekranowe przyciski używają przytrzymania i zwolnienia. Protection, token przeglądarki i watchdog korzystają z istniejącej ścieżki żądań. Dopuszczenie ręcznego startu w trybie nauczonym wymaga, aby zapisana wersja była zweryfikowana i gotowa przy doku. Zwykłe reguły zajętości, Safety i energii pozostają obowiązujące.
- **Diagnostics** zachowuje techniczną telemetrię i kontrolki symulatora. Globalny Emergency Stop i krytyczne ostrzeżenia są dostępne także z innych zakładek. W rozwiniętej chmurze przycisk Emergency Stop jest częścią pełnoekranowego panelu.

## Zapis wizualizacji i wydajność

Po zapisaniu pomiarów, zatwierdzeniu trasy i zapisaniu nowej wersji serwer zleca przygotowanie artefaktu. Podgląd starszej wersji lub wczytanie aktywnej konfiguracji uzupełnia brakujący artefakt na żądanie. Eksporter korzysta z kodu GOAL 26B. Obliczenia wykonuje pojedynczy proces pomocniczy o niższym priorytecie i z ograniczeniem liczby wątków obliczeniowych. Gotowy `visualization.json` jest zapisywany atomowo obok danych kalibracyjnych lub konfiguracji. Identyfikatory i skróty źródeł wiążą wizualizację z jej rewizją. Błąd renderowania lub brak modelu nie zmienia reguł gotowości robota.

Przeglądarka używa pojedynczego WebGL i współdzielonego generatora szablonów. Przełączanie kart i konfiguracji zwalnia zastąpione geometrie, a schowany widok zatrzymuje renderowanie. Odczyty gotowych artefaktów są buforowane w obrębie strony. Chronione zdjęcia kalibracyjne są dostępne w Service, a dowody z misji pochodzą z dotychczasowych kanałów wyników.

[Kontrakt HTTP wizualizacji](../contracts/http.md#control-center-warehouse-visualization) · [Algorytm GOAL 26B](ENHANCED_DIGITAL_TWIN.md) · [Three.js, renderowanie na żądanie](https://threejs.org/manual/en/rendering-on-demand.html) · [Python, zadania w tle](https://docs.python.org/3.10/library/concurrent.futures.html)

## Walidacja

Próby odbyły się w Ubuntu 22.04 pod WSL2, z ROS 2 Humble, Gazebo Fortress 6.16.0 i Chrome 158 sterowanym przez Playwright. Podczas prób ruchu działał jeden serwer Gazebo. Dwie osierocone instancje wcześniejszego GOAL 21 zostały tymczasowo wstrzymane, aby nie obciążały prób. Zmiany kodu ograniczają się do Control Center, pakowania istniejącej rekonstrukcji, kontraktu odczytu HTTP i dokumentacji.

| Próba | Wynik |
| --- | --- |
| Autonomiczna inspekcja GOAL 24 | **COMPLETE.** Konfiguracja `WH-E83B9581352A5C6DBC06694FE5E70FFA`, rewizja 2. Chrome wybrał na modelu A-01-01 i A-01-03. Stos zapisał po jednej nowej obserwacji dla obu miejsc i zakończył w fizycznym doku z rezerwacją Safety `RELEASED`. Pozostało 38,1% akumulatora. [Przebieg i obserwacje](digital-twin-control-evidence/live-proof.json) |
| Plan i Live | Stosunek panelu planu do mapy wyniósł około 25:75 przy szerokości okna 1600 px. Znacznik na mapie dwukrotnie zmienił zakres planu. W locie obserwowano kamerę, 306 różnych aktualizacji ekranowego położenia UAV oraz przejście na zapisany LiDAR i z powrotem. [Próba przeglądarki](digital-twin-control-evidence/offline-browser.json) · [Przebieg rzeczywisty](digital-twin-control-evidence/live-proof.json) |
| Wyniki biznesowe | A-01-01 otrzymała pomarańczowe oznaczenie etykiety wymagającej ręcznej weryfikacji. A-01-03 otrzymała czerwone oznaczenie brakującej palety. Osobna próba klasyfikacji objęła zieloną zgodność oraz czerwone uszkodzenie i wycofany produkt mimo zgodności samego inwentarza. [Wyniki misji](digital-twin-control-evidence/live-proof.json) |
| Ruch ręczny i zwykły powrót | Przeglądarka wywołała ruch we wszystkich ośmiu kierunkach. W, S, A i D sprawdzono na ekranowych przyciskach, a R, F, Q i E na klawiaturze. Zwolnienie dało zerowy wektor ruchu. Spacja dała zawis. Drugi lot zakończył się przyciskiem **Return to dock** i kontaktem fizycznym. [Pomiar żądań i dopuszczonego ruchu](digital-twin-control-evidence/manual-proof.json) |
| Watchdog, Emergency Stop, Safety, Recovery | Przerwanie dostarczania komend ruchu dało `LINK_LOST`, zerowe prędkości i nadal `RESERVED`. Emergency Stop z zakładki Diagnostics dał `ABORTED` i zachował rezerwacje D oraz A. Po osobnej zgodzie operatora Recovery osiągnęło `RECOVERY_COMPLETE`, fizyczny dok i Safety `RELEASED`. [Próba zabezpieczeń](digital-twin-control-evidence/manual-proof.json) |
| Przełączanie i historia | Przez Service aktywowano inną konfigurację, potwierdzono dopasowanie w doku i wyświetlono jej artefakt. Results wcześniejszego przebiegu zachowało rewizję używaną w misji. Następnie przywrócono sprawdzony GOAL 24. [Obie aktywacje i powiązanie misji](digital-twin-control-evidence/configuration-proof.json) |
| Zapis, restart serwera i integralność | Proces Control Center po restarcie udostępnił dokładnie ten sam zapis z tym samym ETag. Zmiana aktywnej wersji w odizolowanej kopii archiwum zachowała powiązanie starszej inspekcji. Porównano skróty wszystkich pierwotnych plików dwóch konfiguracji. [Próba restartu serwera i skróty](digital-twin-control-evidence/offline-archive-proof.json) |

Pomiędzy pierwszym ruchem a zadokowaniem w misji autonomicznej upłynęło około 179,8 s symulacji i 316,7 s czasu rzeczywistego. Średni RTF wyniósł 0,568. Wszystkie 302 zebrane w tym okresie próbki stanu odnotowały lokalizację `TRACKING`. W tej misji obowiązywały bazowe parametry nawigacji i zabezpieczeń. [Próbkowanie lotu](digital-twin-control-evidence/autonomous-runtime.json)

Przeszło 68 testów pakietów ROS, 6 testów rekonstrukcji, 7 testów kontraktu i Mock SAP oraz smoke test HTTP. Testy wizualizacji obejmują wygenerowanie i atomowy zapis, odczyt po restarcie, unieważnienie po zmianie rewizji oraz archiwalne powiązanie z misją.

### Wydajność przeglądarki i eksportu

W próbie Chrome z archiwum GOAL 24 scena używała pojedynczego płótna 1106×668. Obrót osiągnął średnio 23,8 odświeżenia sceny na sekundę. W dwusekundowej próbie bez interakcji naliczono pięć odświeżeń, a po przejściu do Service zero. Buforowana odpowiedź zawierała 901 101 bajtów. P95 czasu lokalnego odczytu w 24 próbach wyniósł 13,25 ms. Dopasowany ETag zwrócił 304. Przeglądarka sprawdziła też brak modelu nauczonej konfiguracji przy wymuszonej odpowiedzi 404. W takim przypadku pokazuje informację o braku powiązanego modelu. [Metryki Chrome](digital-twin-control-evidence/performance-proof.json)

W odizolowanej próbie zatwierdzonych danych GOAL 24 zapis konfiguracji wrócił po 0,175 s. Model o wielkości 982 205 bajtów pojawił się po 1,838 s bez żadnego żądania odczytu. Próba użyła rzeczywistego archiwum i testowych danych o stanie doku oraz uprawnieniach. Integralność zapisanego pakietu przeszła ponowną weryfikację. [Pomiar zapisu](digital-twin-control-evidence/offline-sealing-proof.json)

### Dodatkowa kalibracja

W pierwszej dodatkowej sesji zarejestrowano oba identyfikatory ArUco. Powrót został przerwany przez `LOCALIZATION_LOST` w górnym korytarzu. Safety zachowało rezerwacje. W próbie Recovery nie zostały spełnione warunki świeżego śledzenia i obwiedni lotu. Równoległa instancja X3 wystartowała około siedem sekund przed zatrzymaniem. Sam odstęp czasowy nie wskazuje przyczyny. Zachowano stan próby i zakończono tylko stos 26C. [Zapis przerwanej próby](digital-twin-control-evidence/first-calibration-attempt.json)

## Materiały

| Ekran | Materiał |
| --- | --- |
| Plan inspection | [Dwa miejsca wybrane na modelu](digital-twin-control-evidence/live-plan.png) · [Rzut z góry](digital-twin-control-evidence/live-plan-top.png) |
| Live flight | [Kamera, trasa, UAV i cel A-01-01](digital-twin-control-evidence/live-target.png) · [LiDAR](digital-twin-control-evidence/live-lidar.png) |
| Results | [Wyniki misji na modelu](digital-twin-control-evidence/live-results.png) · [Układ 1600 px](digital-twin-control-evidence/final-results-1600.png) · [układ 1366 px](digital-twin-control-evidence/final-results-1366.png) · [próba widoku](digital-twin-control-evidence/final-ui-proof.json) · [Starsza misja przy aktywnej innej konfiguracji](digital-twin-control-evidence/historical-with-alternate-active.png) |
| Service | [Drone Management i kalibracja](digital-twin-control-evidence/live-service.png) · [Podgląd innej konfiguracji](digital-twin-control-evidence/live-configuration.png) · [Ruch ręczny](digital-twin-control-evidence/manual-controls.png) |
| Diagnostics | [Emergency Stop i rezerwacje](digital-twin-control-evidence/live-diagnostics-emergency.png) · [Watchdog](digital-twin-control-evidence/manual-watchdog.png) · [Recovery](digital-twin-control-evidence/live-recovery.png) |
| Wideo | [Przyspieszony fragment rzeczywistej inspekcji, 31 s](digital-twin-control-evidence/control-center-flight.mp4) |

## Ograniczenia

Szablon obejmuje odcinki wyznaczone z pomiarów danej kalibracji. Lokalizacje bez jednoznacznej półki pozostają na liście. Raport historyczny wymaga jeszcze dostępnej wersji archiwum, z której korzystała misja. Model i zarejestrowana chmura są odczytywane w tej samej ramie, a dane wizualne pozostają niezależne od ocen bezpieczeństwa.
