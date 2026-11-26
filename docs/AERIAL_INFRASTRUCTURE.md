# Rackonaut — wydzielona infrastruktura powietrzna

Profil `aerial` prowadzi drona z wnęki technicznej przy północno-zachodniej ścianie, pionowym szybem do tunelu na wysokości 6,70 m, a następnie przez monitorowane zejście do alejki A lub B. Naziemna strefa T może pozostać otwarta, gdy dron przelatuje ponad nią.

## Uruchomienie

W Ubuntu 22.04 lub WSL2 z ROS 2 Humble i Gazebo Fortress, z katalogu repozytorium:

```bash
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
LP_NUM_THREADS=4 ros2 launch rackonaut_control control.launch.py \
  aerial:=true safety:=true safety_sensor:=laser
```

Otwórz [Control Center](http://127.0.0.1:8765). W *Simulation Controls* wybierz *Enter transfer*, poczekaj, aż karta *Ground transfer* pokaże obecność, i zleć inspekcję B. Do krótszego pokazu wybierz `B-01-01` w trybie *Custom inspection*. W widoku 3D przyciski *Aerial infrastructure* i *Flight corridor* sterują widocznością konstrukcji i osi lotu. Etykiety *Descent A/B* ustawiają kamerę na odpowiednim zejściu. *Focus dock* kieruje kamerę na stację.

Do próby blokady użyj *Enter descent B* przed startem lub gdy dron leci do B. Zalecany profil laserowy rezerwuje strefę po otrzymaniu aktualnego skanu i potwierdzeniu świateł. Jeśli potrzebny jest krótszy pokaz dwóch odlotów, wybierz `A-01-01` i `B-01-01`, zaznacz inspekcję adaptacyjną i uruchom z `battery_initial:=74.0`. Opcja `safety_sensor:=virtual` wykorzystuje wirtualną obecność pracownika we wszystkich strefach. `gazebo_gui:=true` otwiera dodatkowo okno Gazebo.

## Geometria i lot

| Element | Geometria w układzie magazynu |
| --- | --- |
| Stacja D | `(-4,70; 10,30; 0,05) m`, wnęka wydzielona w zakresie X od −6,18 do −3,27 m i Y od 8,92 do 11,72 m |
| Szyb D | Pionowa oś do 6,70 m, stalowe słupy i przezroczyste panele boczne |
| Tunel | Od szybu do skrzyżowania na X = 2,10 m, następnie nad przednią częścią alejek. Osłona dolna na Z ≈ 6,10 m. Zewnętrzna szerokość około 1,90 m |
| Zejście A | `(5,10; 0,45) m`, zejście z 6,70 do 0,79 m |
| Zejście B | `(5,10; −5,55) m`, zejście z 6,70 do 0,79 m |

Generator tworzy dwa światy SDF i wspólną geometrię `aerial_layout.json`. Gazebo i Digital Twin używają tych samych współrzędnych ram, paneli, stacji i punktów zejścia. Oznaczenia posadzki, pomarańczowe ramy, strzałki oraz sygnalizator stacji pomagają odczytać trasę. Panele wykorzystują przezroczyste prostopadłościany z uproszczoną kolizją. Połączenia i wejścia są otwarte. Wirtualny model pracownika w Digital Twin odwzorowuje bieżącą pozycję modelu Gazebo. Pozycja drona w aplikacji pochodzi z odometrii ROS 2.

Planer i Mission Manager używają jednego grafu. Walidacja sprawdza pokrycie całej długości odcinka sumą dopuszczalnych przestrzeni. Półszerokość odcinka dla środka drona wynosi 0,33 m. Planer sprawdza także ruchy adaptacyjne i powrót z nich. Ten sam kontroler `cmd_vel` sprawdza odcinek od aktualnej odometrii do celu. Dron kończy wznoszenie przed ruchem poziomym i zatrzymuje się nad każdą bramą. Zejście wymaga ponownego odczytu aktualnego zezwolenia. Wyjście z alejki, zwykły powrót, powrót energetyczny i wznowienie używają tej samej sieci.

Korpus kolizyjny drona ma 0,36 × 0,24 × 0,10 m. Promień obrysu czterech wirników wynosi ok. 0,39 m w rzucie. Przy krawędzi dopuszczalnego pasa lotu ten obrys zostawia ok. 0,14 m bocznego odstępu od słupów i ok. 0,17 m od przezroczystych paneli. Spód tunelu jest ok. 0,38 m ponad regałami o wysokości 5,70 m. Porównanie obwiedni trójkątów odwzorowania stalowej hali z rzutem konstrukcji dało co najmniej ok. 0,66 m do najniższego elementu konstrukcji dachowej i ok. 0,75 m do geometrii najbliższej lampy. Są to odstępy w modelu.

## Dostęp i energia

Safety Manager rezerwuje D oraz każdą z wybranych alejek razem z jej zejściem przez całą misję. Przygotowanie włącza żółte światła, a pozwolenie na start wymaga potwierdzonych świateł czerwonych. Do zejścia potrzeba co najmniej 0,8 s bieżącego, wolnego pola oraz aktywnej rezerwacji i sygnału. W profilu laserowym GPU LiDAR A i B monitorują posadzkę w polach obejmujących podstawy zejść. Mają płaszczyznę skanowania na wysokości 0,115 m. GPU LiDAR T pozostaje widoczny dla operatora także poza zakresem rezerwacji. D używa jawnie oznaczonego wirtualnego czujnika obecności modelowanego pracownika. Naruszenie wymaganej strefy, utrata objętych rezerwacją danych lub Abort zatrzymują misję. Po przerwaniu w powietrzu strefy pozostają zarezerwowane do odzyskania drona.

Profil `protected_aerial_demo` modeluje inną efektywną pojemność baterii demonstracyjnej. Współczynniki zużycia na sekundę symulacji wynoszą 0,26 dla zawisu, 0,19 na m/s ruchu i 0,52 na m/s wznoszenia. Próg gotowości wynosi 88%, a rezerwa na powrót 8 punktów procentowych. Prognoza uwzględnia długość i wznoszenie na rzeczywistej trasie, czas inspekcji oraz osobny budżet prób adaptacyjnych. Zużycie w locie jest całkowane z odometrii. Dokowanie wymaga stabilnego kontaktu potwierdzonego z pozycji, prędkości i orientacji. Po doładowaniu Safety wydaje nowe pozwolenie. Drugi odlot zachowuje identyfikator inspekcji i listę ukończonych lokalizacji.

## Rzeczywiste próby w Gazebo

Próby wykonano 25 listopada 2026 r. w Gazebo Fortress i ROS 2 Humble na WSL2 z llvmpipe. Odczyty pochodzą z kamery drona, wyniki zapisywało istniejące API demonstracyjne, a ruch pracownika zachodził w świecie Gazebo. Czasy poniżej biegną od startu misji. Profil wirtualny zmienia źródło decyzji Safety, przy zachowaniu rzeczywistej fizyki, odometrii i kamery Gazebo.

| Próba | Wynik | Czas rzeczywisty i energia |
| --- | --- | --- |
| A. Inspekcja B-01-01 z pracownikiem pod tunelem | LiDAR pokazywał zajęte T. Dron zarezerwował D i B, zszedł po otrzymaniu zgody na B, zapisał obserwację i zbliżenie uszkodzenia, a następnie zadokował i rozpoczął ładowanie | 309,0 s rzeczywistego czasu, 175,5 s symulacji od startu do lądowania. 99,6% → 37,6%, następnie stacja potwierdziła ładowanie do 88,2% |
| B. Pracownik wchodzi do zejścia B | LiDAR B wykrył przeszkodę. Abort na Z = 6,70 m przed rozpoczęciem zejścia. Po usunięciu pracownika system nadal utrzymywał D i B w trybie odzyskiwania | Około 298 ms od wykrycia przez algorytm LiDAR do potwierdzenia ROS Abort |
| C. Powrót, ładowanie i wznowienie | Wirtualna obecność, inspekcja adaptacyjna. Dron ukończył A-01-01, wrócił przy 44,0% przez tunel, doładował się i dokończył B-01-01 po drugim zezwoleniu w ramach tego samego zlecenia | 357,0 s. Pierwszy odlot 73,9% → 18,3%. Osiągnięcie 88,1% po 12,24 s symulacji od zadokowania. Drugi odlot 89,3% → 27,2% |
| A → B w jednym odlocie | Wirtualna obecność. Przejście przez oba zejścia i powrót po inspekcji B-02-01. Po zmianie punktu obserwacji kamera odczytała etykietę A-01-01 | 247,9 s rzeczywistego czasu, 245,1 s symulacji. 99,8% → 14,1% |
| Dodatkowe naruszenie A | Pracownik przeszedł z T do zarezerwowanej A podczas przelotu A → B. LiDAR A uruchomił Abort, a rezerwacje zostały w trybie odzyskiwania | Około 266 ms od wykrycia przez algorytm LiDAR do potwierdzenia ROS Abort |

Pozycja XY w szybie startowym mieściła się w rozdzielczości zapisu odometrii 1 mm względem środka szybu. Zakres Z w fazie przelotu wyniósł 6,677–6,705 m. W próbie A dron minął pracownika o współrzędnych `(2,10; −2,00; 0,00) m` na pozycji `(2,103; −1,985; 6,697) m`. Bezpośredni pomiar pozycji modelu z Gazebo przy B-02-01 różnił się od zaokrąglonej pozycji ROS przekazywanej do Control Center o około 0,4 mm. Digital Twin w Chrome pokazywał bieżącą wysokość z tej samej odometrii z dokładnością wyświetlania do 1 cm. Podane czasy Abort opisują symulowane zdarzenia oprogramowania i potwierdzenie usługi ROS.

Zachowanie starszych profili zweryfikowano przeprowadzając 27 testów pakietów ROS i cztery testy kontraktu HTTP. Walidator SDFormat zaakceptował oba nowe światy. Wszystkie dziesięć wcześniejszych światów SDF porównano bajt po bajcie ze zbudowanym `e3a0d79`. [Zestawienie prób i zdarzenia Safety](aerial-evidence/runs.json) · [Odometria laserowej próby B](aerial-evidence/laser-b-worker.jsonl.gz) · [Odometria blokady B](aerial-evidence/laser-b-blocked.jsonl.gz) · [Odometria wznowienia](aerial-evidence/virtual-charge.jsonl.gz) · [Odometria przejścia A → B](aerial-evidence/virtual-a-b.jsonl.gz)

## Czas i wydajność

Dla B-01-01 plan lotu wydłużył się z 23,5 do 77,1 m, a prognoza samego lotu z 56,7 do 196,8 s symulacji. Przy modelach baterii przypisanych do swoich profili prognozy nominalne z inspekcją wynoszą odpowiednio 40,6 i 68,4 punktu procentowego, z oddzielnym budżetem adaptacyjnym. W rzeczywistym przebiegu laserowym nowego profilu pomiar zużycia wyniósł 62,0 punktu procentowego. Najdalsza lokalizacja B-02-01 ma zaplanowaną samodzielną trasę 82,7 m i wymaga na starcie 78,5% wraz z rezerwą. Potwierdzono jej osiągnięcie i powrót również w dłuższym locie z A opisanym powyżej.

Na postoju porównano 96 próbek czasu Gazebo na widok z wcześniejszym GOAL 12. Pomiar wykonano na tym samym hoście, z profilem laserowym i czterema wątkami llvmpipe. Współczynnik RTF to przyrost czasu symulacji podzielony przez przyrost czasu rzeczywistego.

| Widok | RTF GOAL 12 | RTF GOAL 13 | Kamera GOAL 13 | LiDAR A GOAL 13 |
| --- | ---: | ---: | ---: | ---: |
| 2D | 0,657 | 0,602 | 5,94 Hz | 2,40 Hz |
| 3D | 0,640 | 0,604 | 5,97 Hz | 2,41 Hz |

Współczynnik RTF był niższy o około 6–8%. W osobnym oknie próbkowania w locie z otwartym widokiem 3D wyniósł 0,591. Porównanie obejmuje krótkie okna z poszczególnych uruchomień i zależy od chwilowego obciążenia hosta. [Próbki na postoju](aerial-evidence/performance/) · [Próbki w locie](aerial-evidence/flight-performance.txt) · [Wyniki GOAL 12](ENERGY_MANAGEMENT.md)

## Materiały

- [Film z pełnego cyklu B, ok. 30 s po przyspieszeniu](aerial-evidence/demo.mp4)
- [Hala i infrastruktura w Gazebo](aerial-evidence/gazebo-overview.jpg) · [Dron w szybie](aerial-evidence/gazebo-shaft.jpg) · [Przelot nad korytarzem](aerial-evidence/gazebo-overhead.jpg) · [Widok z kamery drona w tunelu](aerial-evidence/drone-camera.jpg)
- [Mapa 2D](aerial-evidence/map-2d.png) · [Infrastruktura 3D](aerial-evidence/twin-infrastructure.png) · [Stacja](aerial-evidence/twin-dock.png) · [Dron nad pracownikiem](aerial-evidence/twin-overhead.png) · [Zejście do B](aerial-evidence/twin-descent-b.png)
- [Blokada zejścia](aerial-evidence/control-blocked.png) · [Ładowanie między odlotami](aerial-evidence/twin-charging.png) · [Porównanie pozycji z Gazebo](aerial-evidence/pose-comparison.json)

## Ograniczenia

Praca ludzi pod tunelem jest założeniem koncepcyjnym tego demonstratora. Węzły łączenia mają otwarte przejścia, a osłony są uproszczeniem wizualnym i kolizyjnym. Do zejścia system sprawdza dostępność pola przy posadzce. Pojedyncza płaszczyzna LiDAR wykrywa obiekty przecinające wiązkę w zasięgu skanera. Strefa D reaguje na jednego modelowanego pracownika. Pomiar przestrzeni od posadzki po tunel, skutki awarii napędu, odporność osłon na uderzenie, procedury odzyskiwania oraz dopuszczenie do pracy przy personelu wymagają odrębnego projektu i prób fizycznych.

Geometria kolizyjna korzysta z mechanizmów SDFormat obsługiwanych przez Fortress. Pola laserowe korzystają z istniejącej integracji GPU LiDAR i ROS 2 LaserScan. [Geometria SDFormat](https://sdformat.org/spec/1.8/geometry/) · [Sensory Gazebo Fortress](https://gazebosim.org/docs/fortress/sensors/)
