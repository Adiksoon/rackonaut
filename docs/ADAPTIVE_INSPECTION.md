# GOAL 10 · Adaptacyjna inspekcja Rackonaut

## Uruchomienie

Uruchom polecenia w katalogu repozytorium na Ubuntu 22.04 lub WSL2 z ROS 2 Humble i Gazebo Fortress.

```bash
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
LP_NUM_THREADS=4 ros2 launch rackonaut_control control.launch.py adaptive_world:=true safety:=true safety_sensor:=laser
```

W [Control Center](http://127.0.0.1:8765) wybierz **Custom inspection** i zaznacz A-01-01, A-01-02, A-01-03 oraz A-01-05. Pozostaw **Package quality** i włącz **Adaptive inspection**. Te same lokalizacje z wyłączoną opcją dają próbę porównawczą w tym samym świecie. Parametr `safety_sensor:=virtual` uruchamia ten sam scenariusz wizualny z wirtualnym profilem bezpieczeństwa. Panel podpisuje źródło informacji o obecności.

## Decyzje i historia

Mission Manager czeka na bieżący wynik z kamery przyjęty przez API. Przy nieczytelnej etykiecie zmienia odległość i przesuwa się w bok. Przy niepewnej zajętości zmienia perspektywę, a przy braku wyniku koryguje ustawienie kamery ruchem i obrotem drona. Wykryty defekt z zapisanym zdjęciem może uruchomić bliższe ujęcie. Poprawny wynik bez przesłanek do zbliżenia kończy wizytę. Dwie dodatkowe próby i budżet 36 s na lokalizację ograniczają ponawianie. Gdy zabraknie dostępnych podejść, system wskazuje ręczną weryfikację. Dotrzymanie budżetu obejmuje powrót do pozycji referencyjnej, a przekroczenie limitu podczas ruchu powoduje Abort.

Każda zapisana próba ma własny `observation_id` i znacznik czasu klatki. Próby mają wspólny `inspection_id`. W historii jest także miejsce na próbę bez odczytu, która nie tworzy zdarzenia HTTP. Zdjęcia zachowują powiązanie z konkretnym odczytem. Istniejące podsumowanie API nadal wybiera najnowszą obserwację dla każdej lokalizacji. Control Center pokazuje przyczynę, numer próby, ruch na mapie, wynik i lokalizacje do sprawdzenia. Przenośny raport HTML zawiera historię, identyfikatory i zdjęcia.

Profil magazynu dodaje zawieszoną tabliczkę przed etykietą w A-01-01. Kamera może zobaczyć znacznik obok tabliczki po zmianie perspektywy. A-01-02 zawiera rozdarty karton, A-01-03 jest puste, a w A-01-05 etykieta nie zawiera czytelnego markera. Reguły misji korzystają z wyniku obrazu i geometrii dopuszczalnych punktów. Identyfikatory lokalizacji służą do znalezienia geometrii i zapisania wyniku.

## Safety Manager

Plan rezerwuje z góry strefy przecinane przez trasę bazową i oba odcinki każdego przewidzianego ruchu dodatkowego. Dron wraca do pozycji referencyjnej przed ponowną korektą lub kontynuacją lotu. Dotychczasowy regulator pozostaje jedynym wydawcą komend prędkości. Utrata rezerwacji, brak aktualnej telemetrii i Abort zatrzymują ruch. Po zatrzymaniu w powietrzu rezerwacja pozostaje aktywna, a ponowne uruchomienie demonstracji wymaga przywrócenia drona na pad przez restart symulatora.

Trzy skanery mierzą obecność w ograniczonych polach A, B i T. W A pole przy podłodze ma współrzędne X 3,50–15,00 m i Y −1,56–1,60 m, a płaszczyzna pomiaru leży 0,115 m nad podłogą. Punkty dodatkowych ujęć w profilu laserowym mieszczą się w obrysie odpowiedniego pola z marginesem. Pomiar przy podłodze nie potwierdza wolnej przestrzeni na wysokości drona, poza polami (w tym na części drogi z padu) ani w cieniu przeszkody. Jest to mechanizm demonstracyjny w znanym otoczeniu symulacji.

## Wydajność

| Pomiar z WSL2, Gazebo Fortress i GPU LiDAR | RTF | Kamera | Skaner A |
| --- | ---: | ---: | ---: |
| GOAL 09, domyślne llvmpipe | 0,629 | 6,37 Hz | 2,52 Hz |
| Próba kontrolna GOAL 10, `LP_NUM_THREADS=4` | 0,660 | 6,56 Hz | 2,65 Hz |

RTF to iloraz przyrostów czasu symulowanego i rzeczywistego z 45 próbek Gazebo. Częstotliwości są mierzone za mostkiem ROS 2 i odniesione do czasu rzeczywistego. Wyniki pochodzą z oddzielnych prób. W 111 odczytach stanu podczas standardowego lotu maksymalny wiek skanów A/B/T wyniósł odpowiednio 409/402/414 ms przy progu 750 ms. Przyspieszenie llvmpipe ustawiono tylko dla procesu uruchomieniowego. Próba sprzętowa na WSL z D3D12 zakończyła się błędem OgreNext `GL3PlusTextureGpu::copyTo` przed działającym strumieniem. [Pomiar GOAL 09](../ros2_ws/src/rackonaut_safety/docs/SENSOR_SAFETY.md#wydajność) · [Pomiary GOAL 10](adaptive-evidence/performance)

## Próby demonstracyjne

Loty uruchomiono 25 listopada 2026 r. w Chrome przez Control Center. Obie próby porównawcze użyły tego samego świata, zakresu czterech miejsc, profilu laserowego, konfiguracji llvmpipe i włączonej oceny jakości.

| Wynik | Standardowa | Adaptacyjna |
| --- | ---: | ---: |
| Czas od startu misji do lądowania | 111,6 s | 147,0 s |
| Skontrolowane lokalizacje | 4 | 4 |
| Obserwacje przyjęte przez API | 4 | 8 |
| Dodatkowe próby | 0 | 4 |
| Odzyskane odczyty etykiet | 0 | 1 |
| Nierozwiązane problemy z odczytem | 2 | 1 |
| Zdjęcia rozdarcia P003 | 1 | 2 |

Powtórki i powroty do pozycji referencyjnej wydłużyły ten lot o 35,4 s. Dane potwierdzają osiem odrębnych zdarzeń ze znacznikami czasu, właściwe przypisanie zdjęć i wyświetlanie najnowszego odczytu w podsumowaniu API. W tej próbie lokalny fixture API zwracał `pending` dla porównania z oczekiwanym stanem magazynu. [Dane standardowe](adaptive-evidence/standard-run.json) · [Dane adaptacyjne](adaptive-evidence/adaptive-run.json) · [Przenośny raport](adaptive-evidence/inspection.html)

- **A-01-01.** Przy tabliczce stan początkowy to `occupied / unreadable`. Regulator przesunął drona o około 55 cm w bok i 18 cm w stronę regału oraz zmienił yaw o 13°. Kamera odczytała P001, a API zachowało również próbę początkową. [Nagranie](adaptive-evidence/recovery.mp4) · [Control Center po odzyskaniu odczytu](adaptive-evidence/recovered.png)
- **A-01-02.** Detektor rozdarcia uruchomił zbliżenie o 14 cm. Ocena obu ujęć dała `DAMAGED`. Każde zdjęcie ma własny identyfikator jakości i odwołanie do odrębnej obserwacji P003. Przy większych zbliżeniach znacznik lokalizacji albo fragment kartonu wypadał z kadru. [Pierwsze ujęcie](adaptive-evidence/damage-reference.png) · [Zbliżenie](adaptive-evidence/damage-closeup.png) · [Galeria w Control Center](adaptive-evidence/damage-in-control-center.png)
- **A-01-03.** Kamera potwierdziła pustą lokalizację przy pierwszej obserwacji. Dron przeszedł do następnego celu.
- **A-01-05.** Odczyty to kolejno `occupied / unreadable`, `uncertain / unknown` i `occupied / unreadable`. Rodzaj drugiej korekty zmienił się wraz z wynikiem. Po dwóch dodatkowych podejściach lokalizacja trafiła do ręcznej weryfikacji.
- **Rezerwacja i Abort.** W normalnym locie A i T były zarezerwowane podczas korekt i zwolnione po potwierdzonym lądowaniu. W osobnym locie operator przerwał misję podczas `REPOSITION` przy A-01-01. Safety Manager potwierdził `ABORTED` i przeszedł w `RECOVERY`. Dron utrzymał wysokość około 0,79 m, A i T pozostały zablokowane, a B była otwarta. Ponowny start zwrócił HTTP 409. [Stan Control Center po Abort](adaptive-evidence/abort.png) · [Odometria, rezerwacja i zdarzenia](adaptive-evidence/safety.json)
- **Profil wirtualny.** Jednolokalizacyjna próba A-01-01 odzyskała P001, zapisała dwie obserwacje i zakończyła się zwolnieniem A i T po 52,1 s oraz potwierdzonym lądowaniu. [Stan misji i Safety Managera](adaptive-evidence/virtual-run.json)

Próby wykorzystały referencyjnego drona, lokalny fixture API i Control Center z tego repozytorium. Na sprawdzonym repozytorium zdalnym brakowało osobnych gałęzi z modułami pozostałych uczestników. Walidacja SDF objęła oba nowe światy. Sześć wcześniejszych światów po ponownym wygenerowaniu miało identyczną zawartość. Przeszło też 21 testów robotyki i 4 grupy testów kontraktu.
