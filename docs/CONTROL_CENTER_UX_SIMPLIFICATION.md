# Rackonaut Control Center · uproszczenie obsługi

Baza `feature/learned-warehouse-autonomy` z commita `e43ccf7`. Prace obejmują warstwę HTML, CSS i JavaScript Control Center. Implementacja korzysta z istniejących profili uruchomieniowych, danych Mock SAP, autoryzacji Service i poleceń sterowania.

## Audyt i hierarchia

| Użytkownik | Obserwacja w wersji bazowej | Decyzja w tej wersji |
| --- | --- | --- |
| Kierownik magazynu | Pierwszy ekran Results pokazywał podsumowanie przebiegu, a wyniki biznesowe były w zwiniętej sekcji. Z archiwalnym wynikiem ekran sugerował, że raporty dopiero się pojawią. | Results od razu pokazuje wybraną inspekcję, liczby, stany lokalizacji, listę spraw do rozstrzygnięcia i dowód dla pierwszego problemu. |
| Operator | Plan pokazywał lokalizacje świata referencyjnego, nawet gdy aktywny magazyn korzystał z zapisanej mapy. Start inspekcji nauczonej wymagał przejścia przez Service i ręcznej weryfikacji wybranej konfiguracji. | Wspólny Plan sprawdza profil, wybiera aktywną konfigurację i pobiera dozwoloną listę. Operator wybiera miejsca, widzi warunki gotowości i uruchamia lot. |
| Inżynier | Sterowanie ręczne zajmowało stałe miejsce w menu. Service równocześnie prezentował telemetrię, konfigurację, kalibrację i wybór pozycji do inspekcji. | Service prowadzi przez kalibrację, a dane techniczne są w rozwijanych szczegółach i osobnym Diagnostics. Sterowanie ręczne otwiera się z Service albo jako etap lotu kalibracyjnego. |

Ścieżka codzienna to **Plan inspection → Live flight → Results**. Plan pełni funkcję ekranu startowego. **Service** i **Diagnostics** mają wspólny obszar nawigacji po prawej. Interfejs pozostaje anglojęzyczny, tak jak wersja bazowa.

### Plan i lot

- W profilu referencyjnym pozostają wybór całego magazynu, alejek i poszczególnych miejsc. Profil nauczony wyświetla zweryfikowane lokalizacje z aktywnej konfiguracji, również jako znaczniki na planie odniesienia. Szczegóły rewizji i grafu są w Service.
- Wybór lokalizacji nauczonych korzysta z istniejącej sesji Service. Pierwsze odblokowanie w danej sesji nadal odbywa się w Service. Plan sam weryfikuje aktualną konfigurację po odblokowaniu. Backend ponownie pilnuje aktywności konfiguracji i gotowości drona na starcie lotu.
- Czas to prognoza modelu w czasie symulowanym, a próg baterii pochodzi z planu lotu. Krótki Business Demo bez aktywnego modelu Energy oznacza brak tych pomiarów.
- Live flight daje większą część szerokiego ekranu mapie. Obok są kamera, bieżący cel, postęp i bateria. Prognoza baterii po natychmiastowym powrocie pojawia się, kiedy dostępne są zweryfikowane dane. Warstwy mapy odróżniają model referencyjny, zapisany pomiar, akumulację pomiarów i krótkotrwałe bieżące zwroty LiDAR. Punkty, parametry dopasowania i opcje wyświetlania są dostępne na żądanie.

### Wyniki i dowody

- Każda lokalizacja ma etykietę tekstową. Dopasowanie, potwierdzona niezgodność, ręczna weryfikacja, niepewny pomiar i miejsce niesprawdzone mają różne znaczenia. Brak wiarygodnych danych ma także osobne oznaczenie awaryjne, jeśli backend nie rozpoznaje wyniku.
- O zajętości rozstrzyga pomiar, a o przypisaniu palety odczyt etykiety i porównanie z Mock SAP. Zajęta lokalizacja z nieczytelną etykietą jest sprawą do weryfikacji. Uszkodzenie opakowania ma oddzielne dowody i rekomendację.
- W szczegółach widać stan oczekiwany, stan zaobserwowany i działanie z istniejącego backendu. Jeśli zapisano obraz, można otworzyć zdjęcie z adnotacją i oryginał. Przy braku zdjęcia dostępny jest odczyt z kamery z czasem i identyfikatorem, jeśli powstał.
- Eksport otwiera zapisany raport HTML dla wybranej inspekcji, także po restarcie. Zespół może zapisać lub wydrukować ten raport w przeglądarce.

### Service, Diagnostics i Safety

Service pokazuje krok przygotowania, mapowania i rejestracji, powrotu, przeglądu trasy oraz zapisu i aktywacji. Zatwierdzenie trasy i aktywacja nadal wymagają osobnego potwierdzenia. Aktywacja odbywa się przy potwierdzonym doku. Parametry wykonanego lotu i odczyty sensorów można rozwinąć w kontekście operacji.

Diagnostics obejmuje telemetrię oraz stan lokalizacji, pomiarów, bezpieczeństwa i baterii, historię zdarzeń i kontrolki świata Gazebo. Alarm pojawia się w bieżącym widoku, a podczas pełnoekranowej mapy w samym panelu mapy. Emergency Stop jest w stałym nagłówku albo w pełnoekranowej mapie. Wyświetlenie awarii łącza nie chowa ostatnio dostępnego zatrzymania. Gdy połączenie z serwerem rzeczywiście nie działa, wysłanie polecenia przez interfejs zależy od przywrócenia łączności. Watchdog, zwolnienie klawisza i utrata fokusu nadal są obsługiwane przez dotychczasowy moduł manualny i Mission Manager.

## Metoda porównania

Audyt wersji bazowej użył rzeczywiście uruchomionego GOAL 24 z kopią zatwierdzonej konfiguracji i raportu z wcześniejszej inspekcji. Chrome otworzył Plan, Live, mapę 2D, model 3D, chmurę 3D, Results, Diagnostics, Manual flight, Service i zapisaną trasę. Prezentację alertów oraz proces kalibracji uzupełniła inspekcja istniejących reguł, formularzy i śladów lotów GOAL 24. W pomiarze geometrii przeglądarki stosowano te same dane i rozdzielczości 1366×768 i 1920×1080. Każdy wynik misji na zrzucie pochodzi z istniejącego raportu lub rzeczywistego przebiegu symulacji, zgodnie z podpisem.

Narzędzia użyte ponownie do testów przeglądarkowych to istniejące Playwright i przechwytywanie klatek Chrome. Stan wyników zawiera etykiety obok koloru. [Playwright](https://playwright.dev/docs/api/class-page#page-screenshot) · [Chrome DevTools](https://developer.chrome.com/docs/devtools/performance) · [W3C 1.4.1](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)

| Wskaźnik | Baza | Pierwsza wersja |
| --- | --- | --- |
| Przejścia od Planu do wysłania już dozwolonej inspekcji nauczonej, dwa domyślnie zaznaczone miejsca | 3 aktywacje UI: Service, sprawdzenie konfiguracji, start | 1 aktywacja UI po pobraniu planu: Start inspection. Pierwsze odblokowanie Service nadal wymaga kodu. |
| Dane techniczne stale widoczne w nagłówku chmury przy zapisanej mapie | 6 odczytów: ID, stan mapy, punkty zarejestrowane, punkty wyświetlane, lokalizacja z błędem, czas aktualizacji | 2 odczyty: źródło mapy i weryfikacja pozycji. Liczby punktów, czas i dopasowanie są w szczegółach. |
| Rozmiar renderu 2D w Live, laptop 1366×768 | 513×303 px, początek na y=307 | 831×470 px, początek na y=256 |
| Obraz kamery w Live obok 2D, laptop 1366×768 | 431×323 px | 399×299 px |
| Rozmiar renderu 2D w Live, monitor 1920×1080 | 513×303 px | 972×470 px |
| Obraz kamery w Live obok 2D, monitor 1920×1080 | 431×323 px | 472×354 px |
| Dostęp do liczb biznesowych po otwarciu Results | Dodatkowe rozwinięcie i czekanie na odczyt | Widoczne po załadowaniu danych bez dodatkowej akcji |
| Czas między wywołaniami `requestAnimationFrame`, Chrome headless i nieruchoma zapisana mapa 3D | mediana 4,2 ms, p95 4,4 ms na laptopowym viewporcie | mediana 4,2 ms, p95 4,3 ms na laptopowym viewporcie |

Krótki pomiar Chrome dotyczy planowania klatek przeglądarki na jednym hoście. Nie mierzy czasu GPU ani przepustowości Gazebo. Wynik służy jako kontrola wstępna. Mniejszy obraz kamery przy mapie 2D na laptopie to koszt większego pola nadzoru przestrzeni. Widok 3D Scan zachował szerokość obszaru mapy z bazowego trybu 3D, a część ustawień jest zwinięta.

## Weryfikacja

Środowisko prób to Ubuntu 22.04 pod WSL2, ROS 2 Humble, Gazebo Fortress 6.16.0 i Chrome przez Playwright. Przebiegi miały oddzielne domeny ROS, partycje Gazebo, porty i katalogi danych. Polecenia uruchomienia są w [README](../README.md#start-here). Zmiany przechodzą budowanie kolcon, 66 testów ROS, 7 testów kontraktu i Mock SAP oraz próbę HTTP z `scripts/api/smoke.py`.

| Obszar | Wynik i dowód |
| --- | --- |
| Plan referencyjny, start, Live i przełączanie 2D / model 3D | **PASS.** W Chrome wybrano A-01-01, A-01-02 i A-01-03. Podczas rzeczywistej inspekcji przełączono mapy. Po powrocie zapisano status `COMPLETE`. Misja `INS-CONTROL-20261126-160321-74392821`. [Dane próby](control-center-ux-evidence/business-proof.json) |
| Results, zdjęcia i eksport | **PASS.** 3 odczytane lokalizacje, 2 potwierdzone niezgodności inwentarza, 1 uszkodzone opakowanie i 1 wycofany produkt. Zdjęcie uszkodzenia i HTML raportu zwróciły HTTP 200. [Results](control-center-ux-evidence/results.png) · [dowód zdjęciowy](control-center-ux-evidence/evidence.png) |
| Nieautoryzowana kalibracja i utrata HTTP | **PASS.** Żądanie kalibracji bez sesji zwróciło 401. Zablokowanie pobierania stanu w przeglądarce pokazało alarm, a nawiązanie łączności przywróciło stan. [Dane próby](control-center-ux-evidence/business-proof.json) · [alert](control-center-ux-evidence/offline.png) |
| Kalibracja, rejestracja, fizyczny powrót | **PASS.** Sesja `CAL-623FDBCB5D9B4E838FAA93E1E3A01478` rozpoczęła się bez zapisanych miejsc. Zapisano zdjęcia z drona i pozycje A-01-01 oraz A-01-03. Po lądowaniu przełącznik doku potwierdził kontakt, Safety zwolniło strefy, mapa miała 55 775 punktów. [Początek](control-center-ux-evidence/calibration.png) · [rejestracja](control-center-ux-evidence/registration.png) |
| Przegląd trasy, zatwierdzenie, zapis, restart i aktywacja | **PASS.** Przegląd w locie odrzucono kodem 409. Po potwierdzonym doku zapisano konfigurację `WH-B6D7FBC50E70F2418C5532E6D8867192`. Po restarcie, weryfikacji integralności i kliknięciu Activate warehouse lokalizator dopasował pomiary do zapisanej mapy, a Plan udostępnił dwa zapisane miejsca. [Zatwierdzona trasa](control-center-ux-evidence/approved-route.png) |
| Pierwszy autonomiczny lot na nowej, właśnie nauczonej mapie | **ABORTED.** Po zapisaniu obserwacji A-01-01 sterownik zgłosił `LOCALIZATION_LOST` i utrzymał rezerwacje w stanie `RECOVERY`. Misja `INS-CONTROL-20261126-155858-ED9F2248`. Przyczyny utraty śledzenia nie ustalono w tej próbie. [Zapis próby](control-center-ux-evidence/calibration-proof.json) · [ekran przerwania](control-center-ux-evidence/localization-lost.png) |
| Ręczne sterowanie, przerwanie łącza operatora, pełny ekran i Emergency Stop | **PASS.** Klawisz ruchu podniósł drona, zwolnienie wyzerowało żądanie. Po utracie dostarczania komend watchdog zgłosił `LINK_LOST` i zadał zero przy zachowanej rezerwacji. Alarm HTTP i przycisk zatrzymania były widoczne w pełnym ekranie. Kliknięcie wywołało rzeczywisty Abort. Po ocenie i zatwierdzeniu Recovery potwierdzono kontakt z dokiem. [Telemetria](control-center-ux-evidence/safety-proof.json) |
| Wtargnięcie pracownika i Recovery | **PASS.** Przesunięto pracownika w Gazebo do A. Safety potwierdziło zajęcie strefy i utrzymało rezerwacje D i A po Abort. Po oczyszczeniu strefy operator ponownie zatwierdził powrót. Status `RECOVERY_COMPLETE`, kontakt `gazebo_dock_switch`. [Alarm](control-center-ux-evidence/intrusion.png) · [telemetria](control-center-ux-evidence/safety-proof.json) |
| Rozdzielczości demonstracyjne | **PASS.** W Chrome na 1366×768 i 1920×1080 otwarto główne widoki bez poziomego przepełnienia dokumentu i bez błędów JavaScript z tych przebiegów. |
| Próba porównawcza na zatwierdzonym archiwum GOAL 24 | **ABORTED w pierwszym przebiegu z dwiema lokalizacjami.** LiDAR przestał dostarczać aktualne pomiary w górnym korytarzu. Safety zachowało rezerwacje. [Zapis próby](control-center-ux-evidence/earlier-replay-proof.json) |
| Autonomiczna inspekcja nauczonego magazynu przez nowy Plan | **PASS w powtórzeniu z jednym miejscem na zatwierdzonym archiwum GOAL 24.** Chrome uruchomił A-01-03. Zapisano nową obserwację w Mock SAP. Dron osiągnął nauczoną pozycję oddaloną o 0.24 m od fabrycznej, zakończył w stanie `COMPLETE` i fizycznie zadokował. Safety zwolniło strefy. Misja `INS-CONTROL-20261126-161131-4C2582B8`. [Plan](control-center-ux-evidence/learned-plan.png) · [wyniki](control-center-ux-evidence/learned-results.png) · [dane próby](control-center-ux-evidence/learned-proof.json) |

Dodatkowa próba obrotu kamery miała 42 identyczne kroki wskaźnika i 16 000 wyświetlanych punktów na tej samej zapisanej mapie. Oba frontendowe warianty połączono z tym samym serwerem. Chrome zarejestrował około 522 i 535 wywołań rysowania WebGL na sekundę w 1366×768, a w 1920×1080 około 523 i 530. To licznik wywołań WebGL w krótkim ruchu, obejmujący wiele wywołań na klatkę. [Dane pomiaru](control-center-ux-evidence/render-proof.json)

## Materiały do przeglądu

| Ścieżka | Materiały |
| --- | --- |
| Start i planowanie | [Ekran startowy](control-center-ux-evidence/start.png) · [plan referencyjny](control-center-ux-evidence/plan.png) · [plan nauczony](control-center-ux-evidence/learned-plan.png) · [Plan w bazie](control-center-ux-evidence/before-plan.png) |
| Lot i mapa | [Aktywny lot](control-center-ux-evidence/live.png) · [model 3D podczas inspekcji](control-center-ux-evidence/map.png) · [zapisana chmura 3D](control-center-ux-evidence/measured-map.png) · [chmura w bazie](control-center-ux-evidence/before-measured-map.png) |
| Wyniki | [Podsumowanie](control-center-ux-evidence/results.png) · [potwierdzona niezgodność](control-center-ux-evidence/discrepancy.png) · [zdjęcia uszkodzenia](control-center-ux-evidence/evidence.png) · [Results w bazie](control-center-ux-evidence/before-results.png) |
| Service | [Service](control-center-ux-evidence/service.png) · [kalibracja](control-center-ux-evidence/calibration.png) · [rejestracja lokalizacji](control-center-ux-evidence/registration.png) · [zatwierdzona trasa](control-center-ux-evidence/approved-route.png) · [lot ręczny](control-center-ux-evidence/manual.png) |
| Diagnostyka i awarie | [Diagnostics](control-center-ux-evidence/diagnostics.png) · [Emergency Stop na pełnym ekranie](control-center-ux-evidence/fullscreen.png) · [Recovery po zatrzymaniu](control-center-ux-evidence/emergency.png) · [wtargnięcie](control-center-ux-evidence/intrusion.png) |
| Nagranie | [Plan → start → podgląd lotu → wyniki i zdjęcia, 29 s](control-center-ux-evidence/operator-workflow.mp4). Nagranie pochodzi z rzeczywistego Business Demo i jest przyspieszone. |

## Ograniczenia i dalszy przegląd

- W magazynie nauczonym wybór lokalizacji zależy od dotychczasowego uwierzytelnienia Service. Jeżeli operatorzy mają planować bez kodu, potrzebny jest uzgodniony dostęp tylko do odczytu zweryfikowanych lokalizacji aktywnej konfiguracji. Zapis, zatwierdzanie i aktywacja pozostają operacjami Service.
- Czasy są symulowane. Dla kilku uruchomień ze zmianą zakresu warto sprawdzić różnicę pomiędzy prognozą modelu a czasem zauważanym przez operatora.
- Próby środowiska nauczonego ujawniły przerwania odczytu lokalizacji i LiDAR-u. Osobna próba stabilności na hoście z jedną symulacją pozwoli ocenić ich powtarzalność. Wnioski z obecnych przebiegów dotyczą reakcji GUI i zabezpieczeń stosu.
