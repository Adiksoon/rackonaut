# Rackonaut · Integracja X3 z Full Robotics

**X3 zaliczył GOAL 21A i ukończył Teach-and-Repeat po pełnym restarcie.** Pełny lot kalibracyjny po korekcie rejestracji LiDAR uzyskał 29,09 mm RMSE w alejce. W poprzednim pełnym locie wynik wynosił 31,44 mm. Autonomiczne powtórzenie uzyskało 29,37 mm w tej samej strefie, zapisało dwie nowe obserwacje w Mock SAP i zakończyło się fizycznym dokowaniem. [Kwalifikacja SLAM](x3-full-robotics-evidence/x3-planar-teach-verification.json) · [Powtórzenie](x3-full-robotics-evidence/x3-planar-repeat-verification.json) · [Nagranie](x3-full-robotics-evidence/x3-autonomous-learned-route.mp4)

## Baza i audyt modułu Michała

Branch `integration/x3-full-robotics` rozpoczął się od GOAL 24, `e43ccf7c0525296f52308fdba7db53ef1810256b`. Zdalny HEAD `feature/drone` sprawdzony przed pracą to `6d6886080bd744023ed1e21b04d95a1a20bfb480`. Otwarty PR #7 dotyczył samodzielnego profilu. Siedem commitów pakietu `rackonaut_drone` przeniesiono przez `cherry-pick -x`, zachowując oryginalne metadane autora i odsyłacze do źródłowych SHA. [PR #7](https://github.com/Adiksoon/rackonaut/pull/7) · [Historia źródłowa](https://github.com/Adiksoon/rackonaut/commits/feature/drone/) · [Instrukcja modułu Michała](../ros2_ws/src/rackonaut_drone/README.md)

| Commity źródłowe | Zakres i dotychczasowy dowód |
| --- | --- |
| `ddf0db2` | Open Robotics X3 UAV, Gazebo Fuel rew. 4. Lot ręczny, limit i timeout komend, kamera i dwa rzeczywiste odczyty w magazynie. Sterowanie próbą korzystało z odometrii Gazebo. |
| `4b1ee18`, `58ca460` | Porównanie pojedynczego postoju i zatrzymania po naruszeniu strefy. Starszy stos `6e04fcf`, świat Safety i Fixture API. X3 uzyskał 1/1, raport HTTP 200 i zawis po Abort. |
| `1e3fdfc` | Inspekcja X3 11/11 w 233,0 s, osiem zapisów jakości, lądowanie i raport. Profil korzystał z Fixture API i pozy Gazebo. |
| `708c865` | Wariant kamery z szumem i zmienionym oświetleniem. Nadal 11/11, siedem czytelnych etykiet, wzrost przypadków weryfikacji z 2 do 4 i spadek zapisów jakości z 8 do 4. |
| `7e92578` | LiDAR 8 m i IMU. Lokalizacja shadow korzystała z fabrycznej mapy. W wybranych oknach zawisu, obrotu i tunelu X3 osiągnął odpowiednio 12,4, 13,4 i 3,7 mm RMSE. Gazebo pozostało źródłem pozy sterującej. |
| `6d68860` | Jednoczesna przerwa IMU i LiDAR-u. Estymator wykrył utratę sygnału po 0,445–0,537 s i wznowił śledzenie po 0,128–0,154 s od wznowienia mostka. Odometria sterowania nadal pochodziła z Gazebo. |

Wyniki modułu Michała potwierdzają pracę modelu i toru sensorycznego w starszej konfiguracji. GOAL 24 ma osobne warunki odbioru dla przetwarzania w locie, aktywnej lokalizacji, fizycznego doku i ponownego wykorzystania nauczonej mapy. [Dowody źródłowe Michała](../ros2_ws/src/rackonaut_drone/docs/evidence/) · [Kryteria pełnej trasy GOAL 21A](SLAM_FULL_ROUTE_VALIDATION.md)

## Model i interfejsy

X3 przygotowuje się lokalnie z przypiętej rewizji Fuel. Autorzy zasobów to Carlos Agüero i Cole Biesemeyer, Open Robotics, CC BY 4.0. Przygotowanie sprawdza SHA-256 SDF, tekstury i użytych siatek. W symulacji działa kontroler `MulticopterVelocityControl` i cztery modele silników ze źródłowymi kierunkami CCW, CCW, CW, CW. Kontroler używa komend body-frame do 0,6 m/s na oś i 0,5 rad/s w yaw. Układ regulacji prędkości wewnątrz pluginu korzysta z symulowanej prędkości bryły zgodnie z implementacją Fortress. Nawigacja i kontrola misji otrzymują wyłącznie pozycję z LiDAR–IMU. [Model X3 w Gazebo Fuel](https://app.gazebosim.org/OpenRobotics/fuel/models/X3%20UAV) · [Licencja CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) · [Kontroler Fortress](https://gazebosim.org/api/gazebo/6/classignition_1_1gazebo_1_1systems_1_1MulticopterVelocityControl.html)

| Właściwość | Referencja | X3 Fuel rew. 4 |
| --- | --- | --- |
| Masa całkowita SDF | 0,900 kg | 1,520 kg |
| Kolizyjny korpus | Prostopadłościan 0,36 × 0,24 × 0,10 m | Prostopadłościan 0,47 × 0,47 × 0,11 m |
| Kolizje wirników | Wirniki są wizualne | Cztery cylindry o r = 0,10 m, grubość 5 mm |
| Promień obwiedni kolizyjnej w poziomie | 0,216 m | 0,356 m |
| Wzmocnienie prędkości XYZ | 3 / 3 / 4 | 2,7 / 2,7 / 2,7 |
| Limit przyspieszenia kontrolera XYZ | 1 / 1 / 1,5 m/s² | 2 / 2 / 2 m/s² |
| Bezwładność głównego korpusu Ixx, Iyy, Izz | 0,020 / 0,020 / 0,035 kg·m² | 0,03476 / 0,070 / 0,0977 kg·m² |
| Każdy silnik w symulacji | Maks. 950 rad/s, stałe narastania i opadania 0,020 / 0,025 s | Maks. 800 rad/s, stałe 0,0125 / 0,025 s |
| Kamera RGB | 320 × 240, 10 Hz, HFOV 1,05 rad, przesunięcie (0,23, 0, 0) m | 320 × 240, 10 Hz, HFOV 1,05 rad, przesunięcie (0,27, 0, 0,04) m |
| LiDAR i IMU | 192 × 37, LiDAR nominalnie 6 Hz i 8 lub 16 m. IMU 50 Hz. | Te same charakterystyki i ekstrynsyki. LiDAR (0, 0, 0,09) m, IMU w początku bazy. |

Promień X3 obejmuje cylindry wirników z uwzględnieniem przesunięć ich osi. Dotychczasowy promień kontroli przeszkód 0,48 m obejmuje obie obwiednie. W typowym przekroju górnego tunelu wewnętrzna powierzchnia boczna jest 0,894 m od osi. Po odjęciu dopuszczalnego odchylenia środka 0,33 m i promienia kontroli pozostaje 0,084 m. Przejścia i zachowanie przy hamowaniu weryfikują oddzielne próby. Zachowano dotychczasowe progi Collision Prevention, Safety, Energy i Recovery. [Generowanie korytarzy](../ros2_ws/src/rackonaut_warehouse/scripts/generate.py) · [Kontrola przestrzeni przed dronem](../ros2_ws/src/rackonaut_avoidance/rackonaut_avoidance/planner.py)

| Granica | Integracja X3 |
| --- | --- |
| Komendy | Mission Manager publikuje `/rackonaut/drone/cmd_vel`. `velocity_guard` jest subskrybentem, przekazuje świeże komendy do osobnego wejścia X3 i zeruje je po wygaśnięciu źródła. `flight_enabled` trafia do włącznika napędu X3. |
| Pozycja i czas | `rackonaut_localization` publikuje `/rackonaut/drone/odom` i jedyny dynamiczny TF bazy. Jeden mostek Gazebo publikuje `/clock`. Pozycja Gazebo może trafić na `/rackonaut/validation/ground_truth` po włączeniu diagnostyki. |
| Sensory | Zachowano tematy, typy i znaczniki czasu. `sensor_frames` mapuje współosiowe ramki IMU i LiDAR-u do istniejących nazw ROS. Statyczny TF kamery odpowiada faktycznemu montażowi X3. Collision Prevention analizuje dane do 8 m również wtedy, gdy estymator pełnej trasy używa 16 m. |
| Dock i Energy | Energy akceptuje wyłącznie parę fizycznych kolizji doku i korpusu wybranego modelu. Zachowano odrębną weryfikację pozycji i aktualności. Oba profile korzystają z tego samego modelu zużycia energii demonstratora. |
| Konfiguracja nauczona | Zapis SLAM X3 i `sensors.json` noszą oznaczenie modelu. Control Center sprawdza model przed zapieczętowaniem, a lokalizator sprawdza go ponownie przy wczytaniu. Zapis referencyjny bez oznaczenia zachowuje zgodność z profilem referencyjnym. X3 wymaga własnej kalibracji. |
| Backend i panel | Te same usługi ROS i endpointy HTTP. Wybór modelu następuje na poziomie launchera. |

## Uruchomienie

Wymagania to ROS 2 Humble, Gazebo Fortress, systemowy Python 3.10 i zależności Rackonaut. Pierwsze przygotowanie X3 potrzebuje modelu Fuel w cache. Pozostałe zasoby stosu buduje dotychczasowy skrypt.

```bash
scripts/robotics/check
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
ign fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/X3%20UAV/4'
```

### Dron referencyjny

Dotychczasowe wywołanie bez parametru wybiera ten sam profil.

```bash
export RACKONAUT_ROS_DOMAIN_ID=226 RACKONAUT_GZ_PARTITION=rackonaut-reference-demo
scripts/robotics/checkpoint live drone_model:=reference \
  http_port:=24876 mock_port:=24886 data_dir:="$PWD/ros2_ws/log/reference-demo"
```

### X3 z diagnostyką i LiDAR-em 16 m

```bash
export RACKONAUT_ROS_DOMAIN_ID=227 RACKONAUT_GZ_PARTITION=rackonaut-x3-demo
scripts/robotics/checkpoint live drone_model:=x3 full_route_slam:=true \
  localization_diagnostics:=true http_port:=24976 mock_port:=24986 \
  data_dir:="$PWD/ros2_ws/log/x3-demo"
```

Zmienna `RACKONAUT_SERVICE_CODE` udostępnia Service. Tryb `mapping_only:=true` zaczyna od lokalizacji przy doku z pustą mapą, a `learned_warehouse:=true` włącza także zapis i użycie nauczonej konfiguracji. Przy ponownym uruchomieniu użyj katalogu danych tej samej konfiguracji X3. `x3_source:=/ścieżka/do/rewizji/4` pozwala wskazać katalog zawierający oryginalny `model.sdf` i `meshes/`. Launcher sprawdza sumy assetów przed uruchomieniem Gazebo. [Procedura Teach-and-Repeat](LEARNED_WAREHOUSE_AUTONOMY.md)

## Walidacja

Środowisko prób to Ubuntu 22.04.5 LTS w WSL2, ROS 2 Humble, Gazebo Fortress 6.16.0, Python 3.10.12 i llvmpipe. Uruchomienia używały osobnych domen, partycji Gazebo, portów i katalogów danych. Na hoście równolegle działały inne symulacje w oddzielnych partycjach. Porównawczy benchmark wydajności pominięto.

Pierwsze loty X3 potwierdziły RGB i CameraInfo o zgodnych stemplach, 50,00 Hz IMU i 6,02 Hz LiDAR-u. W jednej chmurze na postoju odnotowano 659 poprawnych powrotów powyżej 8 m i maksimum 15,922 m. Fizyczna para to `rackonaut_dock::body::dock_contact_surface_collision` oraz `rackonaut_x3::X3/base_link::X3/base_link_inertia_collision`. Zapis grafu ROS zawiera pojedyncze źródła odometrii, dynamicznego TF, komend i zegara. [Surowe podsumowanie manewrów, sensorów i doku](x3-full-robotics-evidence/x3-protected-flight.json)

W chronionym locie odnotowano 1,28 mm maksymalnego przemieszczenia w trzysekundowym zawisie po ustaleniu, obrót o 0,44 rad oraz stop po utracie żądań operatora. Od zaniku komunikacji do pierwszego zera na publicznym temacie minęło 0,565 s czasu ściennego. Od pierwszego zera przy 0,273 m/s do spadku poniżej 0,05 m/s X3 wzniósł się o 0,131 m w 1,00 s symulacji. Po ustawieniu kartonu w szybie Collision Prevention wydało komendę zera przy Z = 2,391 m. W ustalonym zawisie Z wynosiło 2,559 m, a odczyt potwierdzonej przestrzeni dla polecenia nadal wynosił 0,243 m. Po usunięciu testowej przeszkody dron wrócił do doku i Safety zwolniło rezerwację. [Przebieg A/B](x3-full-robotics-evidence/x3-protected-flight.json)

Emergency Stop zatrzymał lot z rezerwacją Safety. Recovery zatwierdzono osobnym żądaniem z aktualną propozycją. Dron fizycznie zadokował, Safety przeszło do `RELEASED`. Awaria samego transportu LiDAR-u i zatrzymanie samego lokalizatora przerwały misje i pozostawiły D oraz A w `RECOVERY`. Powtórna ocena po powrocie LiDAR-u zakończyła się dokowaniem. Recovery po zatrzymaniu lokalizatora odmówiło kontynuacji po utracie aktualnej pozy i pozostało zablokowane. W próbie naruszenia strefy pracownik Gazebo wszedł do A. Alarm `intrusion` i przejście do `ABORTED` odnotowano po 1,41 s, z utrzymaną rezerwacją D i A. Przy 6,70% baterii próba startu ręcznego zwróciła HTTP 409, a plan inspekcji wskazał za małą energię do startu. [Pomiary awarii i Recovery](x3-full-robotics-evidence/x3-safety-faults.json)

### Pełna trasa shadow

Bazowy lot X3 `INS-CONTROL-20261126-155151-E90175FD` używał produkcyjnego lokalizatora LiDAR–IMU z fabryczną mapą do sterowania. Równoległy estymator SLAM 16 m budował własną mapę ze skanów i IMU. Gazebo dostarczało wyłącznie niezależne próbki do oceny. Walidator zestawiał pozycje według czasu skanu we wspólnej ramie doku. Trasa miała 72,36 m, dwa potwierdzone postoje, fizyczne dokowanie i stan `RELEASED`. Wszystkie 1 040 odcinków między kolejnymi próbkami środka drona z Gazebo mieściły się w zarezerwowanej przestrzeni D–A. W Mock SAP zapisano zajęte A-01-01 z nieczytelną etykietą i puste A-01-03. [Obserwacje Mock SAP](x3-full-robotics-evidence/x3-fixed-route-observations.json) · [Graf ROS](x3-full-robotics-evidence/x3-ros-graph.txt)

| Odcinek | Próbki | RMSE | p95 | Maks. |
| --- | ---: | ---: | ---: | ---: |
| Szyb | 167 | 8,01 mm | 9,14 mm | 14,17 mm |
| Tunel | 580 | 20,23 mm | 27,10 mm | 30,55 mm |
| Alejka i zejście | 294 | **33,59 mm** | 40,96 mm | 47,70 mm |
| Cała trasa | 1 041 | 23,60 mm | 36,85 mm | 47,70 mm |

Dryf przy doku wyniósł 0,76 mm, częstotliwość estymaty 3,24 Hz w czasie rzeczywistym, a RTF 0,539. Najdłuższa przerwa między estymatami wyniosła 0,168 s czasu symulacji. Bramka GOAL 21A wymaga także RMSE ≤ 30 mm w każdej strefie. Wynik bazowy to **FAIL** ze względu na alejkę. [Metryki](x3-full-robotics-evidence/x3-shadow-initial-verification.json) · [Sparowane próbki](x3-full-robotics-evidence/x3-shadow-initial-trace.jsonl) · [Wykres](x3-full-robotics-evidence/x3-shadow-initial.png)

W danych z pierwszej próby średni błąd w alejce wyniósł −28,4 mm w osi X, −7,8 mm w Y i −15,5 mm w Z. Przed powtórką punkt kotwiczenia X3 przy fizycznym doku ustawiono na 0,059 m na podstawie geometrii SDF. Dolna ściana korpusu jest 0,055 m poniżej początku modelu, a górna płaszczyzna styku doku leży na 0,004 m. Korekta dotyczy pozy inicjalizacji i pozostawia wspólną przestrzeń lotu oraz progi jakości. Powtórka korzysta z chronionego sterowania ręcznego z tą samą rezerwacją D–A.

Lot ręczny `INS-CONTROL-20261126-155917-447209A7` po korekcie osiągnął oba stanowiska. RMSE w alejce wyniósł 20,08 mm w 346 próbkach. Próba zakończyła się **FAIL**, ponieważ po rozpoczęciu powrotu Mission Manager wycofał sterowanie z powodem `Onboard lidar stopped advancing`. Odbiór wymaga kompletnej trasy, aktualnych danych i fizycznego dokowania. [Zakres próby i próbki strefowe](x3-full-robotics-evidence/x3-shadow-protected-manual-stop.json)

Powtórka autonomiczna `INS-CONTROL-20261126-160615-2FAFCDA1` zaliczyła pełną trasę shadow po korekcie zakotwiczenia X3. Osiągnięto 72,42 m, potwierdzono oba postoje i zapis w Mock SAP, a styk doku pozostał aktywny przy `RELEASED`. [Powtórka w Mock SAP](x3-full-robotics-evidence/x3-fixed-route-verified-observations.json) · [Nagranie pełnej autonomicznej inspekcji na fabrycznej mapie](x3-full-robotics-evidence/x3-autonomous-fixed-route.mp4)

| Odcinek | Próbki | RMSE | p95 | Maks. |
| --- | ---: | ---: | ---: | ---: |
| Szyb | 168 | 2,90 mm | 3,80 mm | 4,64 mm |
| Tunel | 583 | 12,56 mm | 17,63 mm | 21,44 mm |
| Alejka i zejście | 298 | 24,08 mm | 32,21 mm | 41,24 mm |
| Cała trasa | 1 049 | **15,93 mm** | 28,98 mm | 41,24 mm |

Dryf końcowy wyniósł 0,89 mm. Częstotliwość estymaty wyniosła 3,33 Hz w czasie rzeczywistym przy RTF 0,553. Maksymalna luka trwała 0,168 s czasu symulacji. Żaden heartbeat estymatora z okna lotu nie opuścił `TRACKING`. [Metryki](x3-full-robotics-evidence/x3-shadow-verified-verification.json) · [Sparowane próbki](x3-full-robotics-evidence/x3-shadow-verified-trace.jsonl) · [Wykres](x3-full-robotics-evidence/x3-shadow-verified.png)

### Aktywny SLAM bez mapy fabrycznej

W próbach pełnej trasy z mapowaniem usunięto plik lokalizacyjny z katalogu odczytu przed uruchomieniem ROS. Na początku X3 wyznaczał pozycję przy doku, a mapę stanowiły wyłącznie pomiary LiDAR–IMU bieżącej sesji. Operacje na pliku objęły katalog instalacyjny tego worktree.

Lot `INS-CONTROL-20261126-162056-98D326AD` objął pełny korytarz i zapisał dwa stanowiska z rozpoznanymi znacznikami ArUco. W 1 287 dostępnych parach odczytów RMSE wyniósł 14,34 mm. Ostatnia poprawnie zestawiona estymata była na wysokości 0,105 m. W fazie przyziemienia estymator zgłosił rozbieżność predykcji inercyjnej i dopasowania skanu, a Mission Manager przerwał lot. Zatwierdzenie konfiguracji pozostało zablokowane do potwierdzenia fizycznego doku. [Telemetria błędu przy przyziemieniu](x3-full-robotics-evidence/x3-active-slam-touchdown-abort.json)

W następnej wersji adapter X3 zaczyna ograniczać zadaną prędkość opadania do 0,12 m/s, gdy ostatnia odebrana pozycja sterująca wskazuje kolumnę o promieniu 0,36 m i wysokości podejścia 0,45 m nad fizycznym dokiem. Obejmuje to chroniony powrót i końcowe zejście po nauczonej trasie. Mission Manager nadal ma wyłączność publikacji publicznych komend. Adapter korzysta z tej samej pozycji LiDAR–IMU, którą otrzymują Mission Manager i Energy. Progi kontaktu, świeżości i rezerwacji pozostają wspólne. W krótkim chronionym locie z `source: slam` po korekcie X3 fizycznie zadokował przy około 0,12 m/s w końcowej części zejścia. Plik lokalizacji fabrycznej pozostał dostępny podczas tej krótkiej próby dokowania. Węzeł zapisał wynik mapowania, a Safety zwolniło rezerwację. [Próba krótkiego dokowania](x3-full-robotics-evidence/x3-slam-dock-probe.json)

W pełnej powtórce po ograniczeniu zejścia, `INS-CONTROL-20261126-163349-49ACF3C0`, dron przeleciał 72,95 m bez fabrycznej mapy lokalizacyjnej. Wszystkie 1 304 odcinki między kolejnymi próbkami pozycji Gazebo mieściły się w przestrzeni D–A. Po fizycznym dokowaniu Safety przeszło do `RELEASED`, a sesja `CAL-087DC55861C24188844DB23C3B4601BF` zapisała 56 918 zmierzonych punktów, 181 klatek kluczowych i oba stanowiska. Oba identyfikatory rozpoznało ArUco, a obrazy sparowano z pozą SLAM. Graf potwierdził, że jedynym odbiorcą odniesienia Gazebo był niezależny walidator. [Stanowiska i synchronizacja zdjęć](x3-full-robotics-evidence/x3-taught-locations.json) · [Zdjęcie A-01-01](x3-full-robotics-evidence/x3-taught-a-01-01.jpg) · [Zdjęcie A-01-03](x3-full-robotics-evidence/x3-taught-a-01-03.jpg) · [Chmura PLY](x3-full-robotics-evidence/x3-active-slam-map.ply) · [Graf ROS](x3-full-robotics-evidence/x3-active-ros-graph.json) · [Kontrola pliku fabrycznego](x3-full-robotics-evidence/factory-map-availability.txt)

| Odcinek aktywnego SLAM | Próbki | RMSE | p95 | Maks. |
| --- | ---: | ---: | ---: | ---: |
| Szyb | 241 | 2,14 mm | 3,25 mm | 3,97 mm |
| Tunel | 704 | 21,03 mm | 35,42 mm | 38,41 mm |
| Alejka i zejście | 360 | **31,44 mm** | 41,76 mm | 44,74 mm |
| Cała trasa | 1 305 | 22,63 mm | 36,47 mm | 44,74 mm |

Dryf doku wyniósł 0,38 mm, częstotliwość estymaty 3,37 Hz w czasie rzeczywistym, a RTF 0,559. Najdłuższa luka między próbkami trwała 0,168 s czasu symulacji. Przy niezmienionych limitach GOAL 21A wynik bramki aktywnego SLAM to **FAIL**. RMSE w alejce przekroczył wartość 30 mm o 1,44 mm. [Metryki i warunki odbioru](x3-full-robotics-evidence/x3-active-slam-verification.json) · [Sparowane próbki](x3-full-robotics-evidence/x3-active-slam-trace.jsonl) · [Wykres](x3-full-robotics-evidence/x3-active-slam.png)

### Przyczyna błędu w alejce i korekta SLAM

W poprzednim pełnym aktywnym locie średni błąd w alejce wynosił +9,53 mm w osi X, +16,82 mm w Y i −23,09 mm w Z. W zarchiwizowanej podmapie alejki 4,67% z 55 138 wokseli zawierało obserwacje z niezgodnymi płaszczyznami. Rejestracja przesuwała punkt podparcia w stronę środka wszystkich punktów w wokselu, zachowując normalną najstarszej obserwacji. Na krawędzi regału punkt podparcia mógł w ten sposób opuścić płaszczyznę, do której należała jego normalna. Dopasowanie punkt–płaszczyzna wykorzystywało wynik jako cel następnego skanu. [Pomiary i odtworzenie skanów](x3-full-robotics-evidence/slam-plane-diagnosis.json)

Korekta uwzględnia przy uśrednianiu obserwacje zgodne z płaszczyzną najstarszego punktu. Przesunięcie punktu podparcia przebiega wyłącznie stycznie do tej płaszczyzny, także przy odczycie zapieczętowanej mapy. Test jednostkowy sprawdza woksel z odwróconą normalną tej samej powierzchni, prostopadłą ścianą i równoległą płaszczyzną o innym odsunięciu. [Kod SLAM](../ros2_ws/src/rackonaut_localization/rackonaut_localization/slam.py) · [Test regresji](../ros2_ws/src/rackonaut_localization/test/test_localization.py)

Na identycznym zapisie LiDAR–IMU X3 z dolotu, obu stanowisk i początku powrotu RMSE w alejce zmalał z 22,59 do 21,24 mm, a p95 z 32,66 do 31,09 mm. Maksimum wzrosło z 37,94 do 39,71 mm. Uśrednianie zgodnych obserwacji bez zachowania odsunięcia płaszczyzny dało RMSE 22,81 mm. Każdy wariant miał te same 849 sparowanych próbek. Rozbieżność zmierzono względem odometrii Gazebo po estymacji. [Metryki odtworzenia](x3-full-robotics-evidence/slam-plane-diagnosis.json)

Stabilne sortowanie leksykograficzne kluczy wokseli skraca przebudowę lokalnego celu przy zachowaniu kolejności grup i wyboru najstarszego punktu. W próbach na żywo watchdog zatrzymywał lot przy utracie aktualności pomiarów. W jednej z prób niezależny odbiornik zarejestrował w momencie zatrzymania 390 ms przerwy w zegarze Gazebo i 406 ms przerwy w strumieniu IMU z mostka. Kolejne komunikaty przesunęły się odpowiednio o jeden krok fizyki i jeden okres IMU. [Kod SLAM](../ros2_ws/src/rackonaut_localization/rackonaut_localization/slam.py) · [Próby diagnostyczne](x3-full-robotics-evidence/slam-plane-diagnosis.json)

### Bramka GOAL 21A po korekcie

W kwalifikacji `INS-CONTROL-20261126-171703-B9A9C124` X3 z pustą mapą pomiarową przeleciał 73,18 m, rozpoznał i zapisał A-01-01 oraz A-01-03, fizycznie zadokował i zwolnił rezerwację Safety. Wszystkie 1 432 odcinki sparowanej trajektorii mieściły się w zarezerwowanej przestrzeni D–A. Gazebo dostarczało ground truth wyłącznie do niezależnej walidacji. [Kontrola grafu ROS](x3-full-robotics-evidence/x3-planar-teach-ros-graph.json) · [Sparowane próbki](x3-full-robotics-evidence/x3-planar-teach-trace.jsonl) · [Zdjęcie A-01-01](x3-full-robotics-evidence/x3-planar-teach-a-01-01.jpg) · [Zdjęcie A-01-03](x3-full-robotics-evidence/x3-planar-teach-a-01-03.jpg)

| Odcinek aktywnego SLAM | Próbki | RMSE | p95 | Maks. |
| --- | ---: | ---: | ---: | ---: |
| Szyb | 239 | 1,35 mm | 2,42 mm | 3,01 mm |
| Tunel | 709 | 16,87 mm | 22,04 mm | 25,20 mm |
| Alejka i zejście | 485 | **29,09 mm** | 36,64 mm | 39,96 mm |
| Cała trasa | 1 433 | **20,67 mm** | 33,98 mm | 39,96 mm |

Wynik przy dotychczasowych progach to **PASS**. RTF wyniósł 0,601, średnia częstotliwość estymat 3,62 Hz czasu rzeczywistego, dryf po powrocie 0,48 mm, a najdłuższa luka 0,168 s symulacji. Wszystkie komunikaty stanu lokalizatora z lotu wskazywały `TRACKING`. Zapis obejmuje 197 klatek kluczowych i 58 405 zmierzonych punktów. [Metryki bramki](x3-full-robotics-evidence/x3-planar-teach-verification.json) · [Chmura pomiarowa PLY](x3-full-robotics-evidence/x3-planar-teach-map.ply)

Do kwalifikacji użyto renderowania GLX przez Mesa D3D12 na AMD Radeon 610M. Poprawkę zgodności kopiowania tekstur z Ogre Next zastosowano lokalnie do renderera testowego w osobnej przestrzeni montowań. Procesy testowe przypisano do 15 logicznych CPU. Model X3, świat, sensory i progi odbioru odpowiadały profilowi integracyjnemu. Dojazd i obrót przy stanowiskach wykonano jako osobne żądania przez chroniony interfejs ręczny. [Poprawka Ogre Next dla WSLg](https://github.com/OGRECave/ogre-next/pull/388)

### Teach-and-Repeat

Po zaliczeniu bramki C sprawdzono obwiednię i zatwierdzono 162 odcinki grafu. Konfigurację `WH-216C75B710D2AF0D46B298CEC6B92350` zapieczętowano i aktywowano w rewizji 2. Po pełnym restarcie Gazebo, ROS i Mock SAP ten sam katalog danych udostępnił źródło `learned_map`. Dyspozycja `INS-CONTROL-20261126-172401-E49D771D` użyła obu zapisanych identyfikatorów stanowisk i zatwierdzonego skrótu grafu. Plik lokalizacji fabrycznej był poza ścieżką odczytu podczas kalibracji i powtórzenia. [Manifest, zatwierdzenie i weryfikacja restartu](x3-full-robotics-evidence/x3-planar-teach-repeat-proof.json)

X3 zaliczył wszystkie 162 odcinki, przeleciał 73,45 m i zakończył misję w `COMPLETE` z fizycznym stykiem oraz Safety `RELEASED`. Wszystkie 1 284 odcinki sparowanej trajektorii Gazebo mieściły się w przestrzeni D–A. Mock SAP przyjął dwie nowe obserwacje z bieżącej misji. Kamera pokazała zajęte A-01-01 z nieczytelną etykietą i puste A-01-03. [Wpisy Mock SAP](x3-full-robotics-evidence/x3-planar-repeat-observations.json) · [Sparowane próbki](x3-full-robotics-evidence/x3-planar-repeat-trace.jsonl) · [Nagranie pełnego cyklu, 91 s](x3-full-robotics-evidence/x3-autonomous-learned-route.mp4)

Powtórzenie uzyskało 20,91 mm RMSE na całej trasie i 29,37 mm w alejce, gdzie p95 wyniósł 36,80 mm, a maksimum 43,85 mm. Dryf przy doku wyniósł 0,30 mm, częstotliwość 3,66 Hz i RTF 0,608. Najdłuższa przerwa wyniosła 0,168 s czasu symulacji. Wszystkie komunikaty stanu lokalizatora z lotu wskazywały `TRACKING`. [Metryki powtórzenia](x3-full-robotics-evidence/x3-planar-repeat-verification.json)

Osobna próba integralności wykazała, że rzeczywiste, poprawne archiwum z GOAL 24 przechodzi dla referencji i zostaje odrzucone dla X3. [Test zgodności archiwum](x3-full-robotics-evidence/archive-model-compatibility.json)

## Regresja i porównanie modeli

Dron referencyjny uruchomiono przez dotychczasowy launcher bez argumentu `drone_model`. Przeszedł scenariusz chronionego lotu i pełną inspekcję A-01-01/A-01-03 z fizycznym dokowaniem. Smoke potwierdził zegar, odometrię, ruch, kamerę, konwersję CV i sprzątnięcie grup procesów. Przeszło 67 testów ROS, 7 testów kontraktu i Mock SAP oraz próba HTTP. [Smoke referencji](x3-full-robotics-evidence/reference-smoke.txt) · [Chroniony manewr referencji](x3-full-robotics-evidence/reference-protected-flight.json)

Po korekcie SLAM przeszło 69 testów ROS, 7 testów backendu i próba HTTP.

Inspekcyjne porównanie używa tego samego świata `localization_showcase.sdf`, lokalizatora sterującego z fabryczną mapą, LiDAR-u 16 m, wirtualnej obecności Safety i Mock SAP. Część manewrowa używa tego samego żądania wznoszenia i przerwania łącza operatora. Czasy lotu i hamowania w tabeli są czasami symulacji. Do porównania pozy przy wejściu w `INSPECT` użyto najbliższej czasowo próbki Gazebo, bez przeliczania docelowych waypointów. Pojedyncze przebiegi stanowią charakterystykę sprawdzonych scenariuszy. [Dane obu modeli](x3-full-robotics-evidence/model-comparison.json)

| Pomiar | Referencja | X3 |
| --- | ---: | ---: |
| Przemieszczenie w ustalonym zawisie przez 3 s | poniżej 0,01 mm | 1,28 mm |
| Hamowanie pionowe od pierwszego zera do prędkości ≤ 0,05 m/s | 5,39 cm w 0,40 s | 13,13 cm w 1,00 s |
| Prędkość przy pierwszym zerze w próbie hamowania | 0,280 m/s | 0,273 m/s |
| RMSE pozycji lokalizatora sterującego, względem Gazebo | 7,81 mm | 7,39 mm |
| Odległość od waypointów A-01-01 i A-01-03 przy wejściu w `INSPECT` | 16,1 / 10,8 mm | 16,0 / 7,4 mm |
| Czas autonomicznego lotu | 156,96 s | 174,16 s |
| Modelowane zużycie energii | 55,71 p.p. | 60,64 p.p. |
| Obserwacje Mock SAP | 2/2. A-01-01 zajęte, etykieta nieczytelna. A-01-03 puste. | 2/2. A-01-01 zajęte, etykieta nieczytelna. A-01-03 puste. |
| Fizyczne dokowanie | W manewrze ręcznym i inspekcji | W manewrze ręcznym i inspekcji |
| Utrzymanie modelu | Własny prosty SDF i bezpośrednie mosty | Przypięte zasoby Fuel, przygotowanie SDF, adapter komend i ramek oraz dodatkowa kalibracja wysokości doku |
| Benchmark wydajności symulacji | Pominięty z powodu innych uruchomionych symulacji | Pominięty z tego samego powodu |

X3 przebył 72,42 m wobec 70,80 m referencji. Dłuższa droga i czas zwiększyły koszt w modelu energii demonstratora. Próby hamowania potwierdzają potrzebę oceny X3 jako oddzielnego profilu. Zmierzono jeden manewr w pionie i zachowanie przed blokadą szybu, z zachowaniem tych samych marginesów ochrony.

## Wyniki bramek

| Bramka i próba | Wynik | Zakres |
| --- | --- | --- |
| A · Start, ROS, TF, RGB, CameraInfo, LiDAR i IMU | **PASS** | Strumienie i ich ramki zgodne. Jeden zegar i jedno źródło odometrii sterowania. |
| A · Wznoszenie, obrót, zawis, zejście i styk doku | **PASS** | Manewry chronione i potwierdzona fizyczna para kolizji. |
| B · Chroniony lot, kolizje, operator, Safety i Energy | **PASS** | Zatrzymanie przed przeszkodą, watchdog, naruszenie strefy i blokada startu przy niewystarczającym budżecie. |
| B · Izolowana utrata LiDAR-u i utrata lokalizacji | **PASS** | W obu przypadkach przerwanie misji i zachowana rezerwacja. |
| B · Emergency Stop, chroniony powrót i zatwierdzony Recovery | **PASS** | Chroniony powrót i Recovery po Emergency Stop oraz ponownej ocenie po przerwie LiDAR-u zakończone stykiem doku. |
| B · Recovery po wymuszonym zatrzymaniu lokalizatora | **FAIL** | Warunki nadzoru zmieniły się podczas próby. Safety utrzymało D i A. |
| C · Autonomiczna inspekcja z fabryczną mapą LiDAR–IMU i pełny shadow | **PASS po korekcie** | Dwa wpisy w Mock SAP, fizyczny dok i zaliczone progi shadow. |
| C · Pomiarowa mapa 3D z pustej sesji | **PASS** | 58 405 punktów w PLY i dwa zapisane stanowiska po korekcie SLAM. Fabryczny plik lokalizacji był wyłączony podczas próby. |
| C · Bramka jakości pełnej trasy ze sterowaniem aktywnym SLAM | **PASS po korekcie** | RMSE 29,09 mm w alejce i 20,67 mm na trasie, 3,62 Hz, fizyczny dok, `RELEASED`. |
| D · Teach-and-Repeat po pełnym restarcie | **PASS** | Zatwierdzona i zapieczętowana konfiguracja X3, 162 odcinki, dwie nowe obserwacje w Mock SAP, fizyczny dok i `RELEASED`. |
| E · Regresja profilu referencyjnego | **PASS** | Smoke, chroniony lot i pełna inspekcja 2/2 z Mock SAP i fizycznym stykiem. |

## Ograniczenia i rekomendacja

**Do demonstracji konkursowej rekomendowana jest referencja.** W porównywalnym scenariuszu miała krótszą drogę hamowania i niższy modelowany koszt energii. Teach-and-Repeat przeszedł dla referencji w GOAL 24 i dla X3 w kampanii opisanej powyżej. [Dowody Teach-and-Repeat referencji](LEARNED_WAREHOUSE_AUTONOMY.md)

Aktualna integracja potwierdza dwie lokalizacje na stosie GOAL 24. Wynik 11/11 pozostaje historyczną próbą Michała. W kwalifikacji X3 zapas RMSE w alejce wyniósł 0,91 mm, a w autonomicznym powtórzeniu 0,63 mm. Przy wymuszonym zatrzymaniu lokalizatora Recovery odmówiło ruchu po utracie aktualnej pozycji. Oba nagrania pokazują pełne cykle od doku do doku, z obrazem kamery i telemetrią odtwarzanymi w około czterokrotnym przyspieszeniu. [Nagranie na mapie fabrycznej](x3-full-robotics-evidence/x3-autonomous-fixed-route.mp4) · [Nagranie na mapie nauczonej](x3-full-robotics-evidence/x3-autonomous-learned-route.mp4)
