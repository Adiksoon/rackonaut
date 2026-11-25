# Rackonaut — pokładowe wykrywanie i omijanie przeszkód

Profil `avoidance` dodaje do infrastruktury GOAL 13 przestrzenny LiDAR pokładowy, lokalne omijanie przeszkód w zarezerwowanej alejce, zatrzymanie w zablokowanym szybie lub tunelu i wizualizację pomiarów w Control Center. W próbie demonstracyjnej dron samodzielnie ominął karton podczas inspekcji i ponownie w drodze powrotnej, po czym zadokował.

## Uruchomienie

Na Ubuntu 22.04 lub WSL2 z ROS 2 Humble i Gazebo Fortress uruchom z katalogu repozytorium.

```bash
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
LP_NUM_THREADS=4 ros2 launch rackonaut_control control.launch.py \
  avoidance:=true safety:=true safety_sensor:=laser
```

W [Control Center](http://127.0.0.1:8765) włącz *3D Digital Twin* i *Onboard scan*. W *Simulation Controls* wybierz *Place carton in A*, a następnie zleć `A-01-01` i `A-01-03` w trybie *Custom inspection*. Włączenie *Adaptive inspection* pokazuje także odzyskanie etykiety przy pierwszej lokalizacji. Aby wstawić przeszkodę podczas ruchu, użyj przycisku po rozpoczęciu lotu w stronę `A-01-03`. Do osobnych prób służą przyciski *Block aisle A*, *Block tunnel*, *Block descent A* i *Block launch shaft*. Każdy przenosi rzeczywisty kolizyjny model w Gazebo. *Remove flight obstacle* odstawia aktywną przeszkodę. Po Abort uruchom świeżą instancję symulacji przed kolejnym zleceniem.

Profil laserowy korzysta ze stacjonarnych skanerów Safety Managera i pokładowej chmury. Dla szybszego pokazu na słabszym hoście `safety_sensor:=virtual` przełącza stacjonarną warstwę obecności na jawny model pracownika. Pokładowy LiDAR, fizyka Gazebo i detekcja przeszkód działają w obu trybach. Dron startuje osobno z modelu demonstracyjnego. Dwanaście wcześniejszych światów SDF oraz referencyjny model RGB porównano bajt po bajcie z wcześniejszą bazą.

## Sensor i lokalna nawigacja

- Przestrzenny GPU LiDAR Fortress publikuje uporządkowany `PointCloud2` o wymiarach 192 × 37, zasięgu 0,10–8,00 m, kącie 360° w azymucie i ±88° w pionie. Mocowanie jest 9 cm nad środkiem układu drona. Stały TF i pełny kwaternion odometrii wiążą odczyt z pozycją w chwili akwizycji. Margines synchronizacji wynosi 85 ms czasu symulacji. Profil zachowuje oddzielną kamerę RGB dla inspekcji.
- Algorytm `rackonaut_avoidance` sprawdza do 1,50 m aktualnego odcinka w kierunku ruchu. Sprawdza zwrot ruchu względem celu również przy locie bokiem, wstecz oraz pionowo. Próbkowany obrys ma promień 0,48 m i półwysokość 0,17 m. Skończone odległości wyznaczają rzeczywiste zakończenia wiązek. Jawny zwrot poza maksymalnym zasięgiem pozwala ocenić przestrzeń wewnątrz zasięgu. Pomiar wewnątrz minimalnego zasięgu, wartości niepoprawne i wychodzące poza pole pomiarowe pozostają zajęte albo nieznane. Zbiór trafień jest grupowany przestrzennie na potrzeby panelu.
- Uwaga i hamowanie zależą od odległości wzdłuż odcinka, prędkości, wieku pomiaru i przyjętego modelu hamowania. Po zatrzymaniu planer bada boczne i wyższe punkty. Przed każdym ruchem sprawdza cały krótki odcinek w oparciu o świeże odczyty, granice dopuszczalnej przestrzeni i aktualną rezerwację. Dalszą część obejścia ocenia z nowego punktu obserwacji. Pole manewru jest ograniczone do zarezerwowanych alejek. Zejście i szyb używają odcinków pionowych i zatrzymują ruch przy blokadzie.
- Mission Manager pozostaje jedynym publisherem `cmd_vel` w locie. Stany nawigacji są raportowane obok fazy zadania, a identyfikator inspekcji, dotychczasowe odczyty i historia prób pozostają w tym samym raporcie. Oczekiwanie ma limit 7 s, jedno obejście ma limit 48 s, a liczba obejść jednego odcinka jest ograniczona do dwóch. System może odłożyć lokalizację i przejść do następnej po pełnej weryfikacji jej krótkiego dojścia. Rozważa powrót przez istniejący graf, gdy cały dostępny wariant powrotu można potwierdzić z bieżącego pomiaru. Zablokowana droga bez takiego potwierdzenia wymaga odzyskania przez operatora.
- W czasie powrotu i ładowania zachowują się reguły GOAL 13. Przed bocznym ruchem sprawdzany jest koszt dodatkowego lotu, zawisu i wznoszenia oraz koszt powrotu z końca odcinka. Rezerwa wynosi 8 punktów procentowych. Trasa automatycznego powrotu podlega tej samej bieżącej ocenie LiDAR.
- Safety Manager ma pierwszeństwo przed lokalnym planowaniem. Naruszenie strefy, utrata aktualnej rezerwacji albo Abort kończą zadanie. Utrata danych pokładowych po 650 ms zamyka ruch i wymaga odzyskania. Kontroler utrzymuje dotychczasową rezerwację przy przerwaniu w powietrzu.

Most `ros_gz_bridge` i model GPU LiDAR z Fortress zostały wykorzystane bez nowego sterownika. Archiwalny PX4-Avoidance jest powiązany z innym stosem lotu. PX4 Collision Prevention ogranicza ruch przy przeszkodzie i wymaga integracji z kontrolerem PX4, a OctoMap rozwiązuje trwałą reprezentację mapy. Rackonaut ocenia ograniczony obszar na bieżąco i korzysta z istniejącej sieci korytarzy oraz kontrolera. [Gazebo Fortress](https://gazebosim.org/docs/fortress/sensors/) · [Most dla ROS Humble](https://github.com/gazebosim/ros_gz/tree/humble/ros_gz_bridge) · [PX4 Collision Prevention](https://docs.px4.io/v1.14/en/computer_vision/collision_prevention.html) · [PX4-Avoidance](https://github.com/PX4/PX4-Avoidance) · [OctoMap](https://github.com/OctoMap/octomap)

## Pomiar przy kartonie

W ciągłej próbie `INS-CONTROL-20261125-144417-83054495` karton 0,46 × 0,46 × 0,46 m stał w nominalnej linii lotu przy `(6,95, 0,45, 0,82) m`. Najniższa krawędź znajdowała się na 0,59 m, ponad płaszczyzną skanu infrastruktury na 0,115 m. Po przejściu do pierwszego obejścia dron odleciał w bok, przeszedł wzdłuż kartonu i wrócił na nominalną trasę. Przy powrocie ominął karton po drugiej stronie. Widok inwentaryzacji rozpoznał obie lokalizacje, w tym A-01-01 ponownie odczytane z pozycji adaptacyjnej.

| Wielkość | Dolot do A-01-03 | Powrót z A-01-03 |
| --- | ---: | ---: |
| Prędkość z odometrii na początku hamowania | 0,257 m/s | 0,257 m/s |
| Czas od decyzji o hamowaniu do odnotowania zatrzymania | 0,90 s | 0,80 s |
| Droga do zatrzymania | 0,085 m | 0,078 m |
| Od zatrzymania do wybrania pierwszego odcinka | 0,30 s | 0,30 s |
| Dodatkowa droga względem cięciwy między punktami detekcji i ponownego wejścia | 1,30 m | 1,29 m |
| Najmniejszy odstęp od konserwatywnego obrysu wirników | 0,182 m | 0,174 m |

Odstępy obliczono z 3093 niezależnych próbek pozycji modelu w Gazebo, wymiarów rzeczywistej kolizji kartonu i obwiedni wirników o promieniu 0,392 m. Pozycje obiektów były używane wyłącznie w tej weryfikacji. Misja trwała około 351 s czasu rzeczywistego na hoście z równolegle uruchamianymi krótkimi próbami. Bateria spadła z ok. 99,1% do 35,2%. [Dane Gazebo](avoidance-evidence/native-clearance.csv) · [Metoda i minimum](avoidance-evidence/clearance.json)

## Próby w Gazebo

Próby wykonano 25 listopada 2026 r. na WSL2 z ROS 2 Humble, Gazebo Fortress i llvmpipe. Tryb Safety w poszczególnych próbach jest zapisany w telemetrii. Odczyty pokładowego LiDAR-u w obu trybach pochodzą z geometrii i ruchu w Gazebo. Lokalizacje rozpoznawała kamera RGB, a obserwacje trafiały do demonstracyjnego API.

| Próba | Wynik |
| --- | --- |
| A. Lot bez przeszkody | `A-01-01` i `A-01-03` wykonane, dokowanie potwierdzone. Brak manewrów omijania. |
| B. Karton w alejce | Samodzielne hamowanie, ominięcie, powrót na trasę i dokończenie tej samej misji. |
| C. Pełna blokada alejki | Dron zatrzymał się przed szeroką zaporą na Z ≈ 0,79 m i zakończył ocenę stanem `RECOVERY_REQUIRED`. Ukończony wcześniej odczyt pozostał w raporcie. |
| D. Przeszkoda wstawiona podczas lotu | Drugi niezależny przebieg z wstawieniem kolizyjnego kartonu już w fazie `TRANSIT` do A-01-03. Dron ominął go po przeciwnej stronie niż w pierwszym dolocie próby B, dokończył te same dwie lokalizacje, ponownie ominął karton i zadokował. |
| E. Zablokowany tunel | Dron zatrzymał się wewnątrz tunelu na Z = 6,70 m. Po upływie okna oceny zgłosił konieczność odzyskania. |
| F. Przeszkoda pod dronem | Dron zahamował w zejściu A na Z ≈ 4,31 m. Pozycja XY pozostała na osi zejścia. |
| G. Rzeczywista utrata skanu | Wstrzymanie dedykowanego mostu DDS/Gazebo podczas wlotu do tunelu wywołało stan `FAULT`, zatrzymanie i zachowanie rezerwacji. |
| H. Priorytet Safety podczas omijania | Stacjonarny LiDAR A pokazywał wolne pole przy rozpoczęciu manewru. Po wejściu pracownika Safety Manager potwierdził ROS Abort po ok. 265 ms od detekcji. Po usunięciu pracownika rezerwacje D i A pozostały aktywne w `RECOVERY`. |
| I. Powrót po obejściu | Karton pozostał na trasie powrotnej. Dron ominął go ponownie, wrócił tunelem i zadokował. |
| Dodatkowa próba, przeszkoda nad dronem | Dron zatrzymał wznoszenie na ok. 2,44 m przy stałym XY. Skan potwierdził pełną pionową drogę powrotną do stacji. Dron zadokował i zakończył zadanie w `COMPLETE_WITH_MISSES`, kierując pominiętą lokalizację do ponownej weryfikacji. |

W parze prób A/B, przy takim samym zakresie inspekcji i konfiguracji pokładowej, dwa obejścia zwiększyły czas z 163,20 do 185,04 s symulacji, a zużycie baterii z 57,69 do 63,89 punktu procentowego. Różnica czasu rzeczywistego wyniosła 33,3 s w osobnych uruchomieniach z różnym obciążeniem hosta. Potwierdzono 31 testów pakietów ROS i cztery testy kontraktu HTTP oraz walidację dwóch nowych światów i nowego modelu drona. [Przebiegi, zdarzenia, czasy](avoidance-evidence/runs.json) · [Wykres rzeczywistych torów](avoidance-evidence/measured-bypass.png)

Próby A/B wykorzystywały skan pokładowy 8 Hz. Powtórzona pełna misja D z docelowym skanem 6 Hz trwała 185,48 s symulacji i 318,7 s rzeczywistego czasu. Dron podczas pierwszego hamowania przejechał 0,081 m. Od odbioru skanu wykorzystanego do hamowania do decyzji minęło 316 ms czasu rzeczywistego, prędkość spadła poniżej progu zatrzymania po kolejnych 0,70 s, a wybór pierwszego odcinka obejścia zajął 0,30 s. Łączne zużycie wyniosło 64,01 punktu procentowego. [Zapis próby D](avoidance-evidence/dynamic.jsonl.gz) · [Zatrzymanie przez Safety](avoidance-evidence/safety-abort.png)

## Wydajność

Porównano dwa widoki na tym samym hoście z czterema wątkami llvmpipe, na postoju przy aktywnych mostach i bez drugiej symulacji. Każde okno obejmuje 96 próbek czasu Gazebo. RTF jest stosunkiem czasu symulacji do czasu rzeczywistego.

| Profil i widok | RTF | RGB [Hz] | LiDAR A [Hz] | Pokładowy LiDAR [Hz] |
| --- | ---: | ---: | ---: | ---: |
| GOAL 13 · 2D | 0,602 | 5,94 | 2,40 | — |
| GOAL 14 · 2D | 0,410 | 4,16 | 2,07 | 2,47 |
| GOAL 13 · 3D | 0,604 | 5,97 | 2,41 | — |
| GOAL 14 · 3D | 0,406 | 4,05 | 2,05 | 2,47 |

RTF spadł o około 32–33%. Pod obciążeniem kilku jednoczesnych symulacji wcześniejsze ustawienia powodowały odrzucenie dwóch startów i jedno przerwanie z powodu wieku skanu stacjonarnego. Końcowy profil ma 6 Hz pokładowo i 5 Hz w stacjonarnych A/B w czasie symulacji. Limity wieku pomiarów wynoszą nadal 650 ms pokładowo i 750 ms dla stacjonarnych skanów. W tej konfiguracji stacjonarny LiDAR wykrył wejście pracownika w próbie H. [Pomiary GOAL 14](avoidance-evidence/performance/) · [Pomiary GOAL 13](aerial-evidence/performance/)

## Materiały

- [Film z rzeczywistego lotu i zablokowanego tunelu, 30 s](avoidance-evidence/demo.mp4)
- [LiDAR pokładowy w Digital Twin](avoidance-evidence/sensor-on-drone.png) · [Karton i dron w Gazebo](avoidance-evidence/aisle-carton-gazebo.jpg) · [Pełna blokada tunelu w Gazebo](avoidance-evidence/blocked-tunnel-gazebo.jpg)
- [Wykrycie i hamowanie w Control Center](avoidance-evidence/braking-control.png) · [Chmura pomiarowa z fazy hamowania](avoidance-evidence/measured-cloud.json) · [Odcinek obejścia w Digital Twin](avoidance-evidence/detour-twin.png)
- [Powrót na nominalną trasę](avoidance-evidence/rejoin-control.png) · [Dokończona misja z wstawieniem kartonu w locie](avoidance-evidence/dynamic-complete.png) · [Ślad odometrii obu obejść](avoidance-evidence/measured-bypass.png)

## Ograniczenia

Raycast próbkowany kątowo ma dwa wąskie niewidoczne stożki przy osiach pionowych. Przy 1,5 m odstęp między sąsiednimi warstwami pionowymi wynosi około 0,13 m. Przezroczyste, cienkie, słabo zwracające lub gwałtownie wstawione obiekty mogą pozostać niewykryte. Poza dopuszczonym kontaktem na stacji nieznana przestrzeń powoduje zatrzymanie albo ograniczenie prędkości i wymaga dalszej obserwacji. System jest demonstratorem o ograniczonej geometrii i uproszczonej dynamice. Podane odstępy i czasy dokumentują konkretne przejazdy w Gazebo.
