# Rackonaut X3 UAV

Niezależny profil symulacyjny drona Michała na Ubuntu 22.04 lub WSL2, ROS 2 Humble, Gazebo Fortress i Pythonie 3.10. Profil uruchamia jeden model X3 z przednią kamerą RGB i obsługuje lot ręczny. [Zakres zadania](../../../docs/onboarding/MICHAL.md) · [Kontrakt ROS 2](../../../contracts/ros.md)

## Model i przygotowanie

Model **X3 UAV**, Open Robotics, publiczna rewizja **4** w Gazebo Fuel, autorzy w `model.config` Carlos Agüero i Cole Biesemeyer. Karta Fuel podaje **CC BY 4.0**. Pakiet weryfikuje SHA-256 modelu i używanych siatek oraz tekstury. Zasoby są pobierane do lokalnego cache. Przygotowany SDF 1.8 dodaje kamerę, kontroler prędkości i odometrię oraz rozwiązuje ścieżki do zasobów lokalnych. Konfiguracja silników bazuje na przykładzie Fortress wskazanym poniżej. Zachowano geometrię i masę X3, a kolory wirników zastępują odwołania do materiałów Gazebo Classic. [Metadane Fuel](https://fuel.gazebosim.org/1.0/OpenRobotics/models/X3%20UAV) · [Model rewizji 4](https://fuel.gazebosim.org/1.0/OpenRobotics/models/X3%20UAV/4/files/model.sdf) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) · [Przykład kontrolera Fortress](https://github.com/gazebosim/gz-sim/blob/0a33e9afb42054ed6a95e12be74be3700bf05d63/examples/worlds/multicopter_velocity_control.sdf)

Z katalogu głównego repozytorium w systemie plików WSL2:

```bash
scripts/robotics/check
source scripts/robotics/activate.bash
(cd ros2_ws && colcon build --packages-up-to rackonaut_drone)
source scripts/robotics/activate.bash

ign fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/X3%20UAV/4'
ros2 run rackonaut_drone prepare_model
ign sdf -k "$XDG_CACHE_HOME/rackonaut_drone/x3.sdf"
```

Domyślny katalog rewizji w cache Fortress to `~/.ignition/fuel/fuel.gazebosim.org/openrobotics/models/x3%20uav/4`. W razie niestandardowej lokalizacji podaj katalog rewizji przez `prepare_model --source`. Gotowy SDF i zasoby pozostają lokalne. Pobranie jest potrzebne tylko przy przygotowaniu modelu. Potem symulacja korzysta z lokalnych plików.

## Pełna inspekcja z X3

Osobny launcher modułu drona uruchamia X3, Control Center, magazyn z wirtualnym czujnikiem obecności i lokalne Mock API z 11 lokalizacjami. Przygotuj model zgodnie z instrukcją wyżej, zainstaluj zależności API przez `python3.10 scripts/api/setup.py` i uruchom:

```bash
source scripts/robotics/activate.bash
LP_NUM_THREADS=4 ros2 launch rackonaut_drone inventory.launch.py
```

Otwórz [Control Center](http://127.0.0.1:8765/). Poczekaj na gotowość drona, obrazu, API i stref. Wybierz **Full inventory**, pozostaw pracownika poza strefami i uruchom inspekcję. Po lądowaniu wybierz **Open report**. Profil używa scenariuszy Fixture API, w którym porównania inwentarza mogą pozostać w stanie `pending`.

Jeśli działa już inna instancja Rackonaut, ustaw osobną domenę i partycję przed aktywacją projektu i użyj osobnych portów. Przykład z odizolowanej próby:

```bash
export RACKONAUT_ROS_DOMAIN_ID=76 RACKONAUT_GZ_PARTITION=rackonaut-x3-full-inventory
source scripts/robotics/activate.bash
LP_NUM_THREADS=4 ros2 launch rackonaut_drone inventory.launch.py \
  http_port:=18765 mock_port:=18000 data_dir:="$PWD/ros2_ws/log/x3-full-trial"
```

Domyślny katalog raportów to `ros2_ws/log/ros/x3-inventory`. `gazebo_gui:=true` włącza okno Gazebo. Przez Ctrl+C zamkniesz profil. W trakcie misji komendy ruchu wysyła Mission Manager. Osobny launcher referencyjny Control Center jest dostępny według instrukcji w głównym README.

**Wynik próby pełnej inspekcji.** Na WSL2 Ubuntu 22.04.5, ROS 2 Humble i Gazebo Fortress 6.18.0 X3 potwierdził **11/11** lokalizacji bez pominięć w **233,0 s** z włączoną kontrolą jakości. Po ośmiu punktach w A przeleciał korytarzem do B, odwiedził trzy kolejne punkty, wylądował i zwolnił strefy A, B oraz T. W archiwum znalazło się osiem zapisów kontroli jakości, a raport HTML zwrócił HTTP 200. Identyfikator `INS-CONTROL-20261126-104105-66B6872F`. [Wynik i telemetria](docs/evidence/x3-full-inventory.json)

### Wariant trudniejszej kamery

`camera_profile:=challenging` dodaje do obrazu X3 szum Gaussa o odchyleniu standardowym `0.015` w skali znormalizowanej. Zmniejsza światło otoczenia i moc wybranych opraw oraz dodaje reflektor i bardziej połyskliwą etykietę w alejce B. Ustawienia służą do porównań symulacyjnych. Domyślne `camera_profile:=standard` uruchamia dotychczasowy model i świat.

```bash
source scripts/robotics/activate.bash
ros2 run rackonaut_drone prepare_model --camera-profile challenging
LP_NUM_THREADS=4 ros2 launch rackonaut_drone inventory.launch.py camera_profile:=challenging
```

Przy równoległych instancjach ustaw osobną domenę ROS, partycję, porty i `data_dir`, tak jak w przykładzie wyżej. Profil tworzy lokalną kopię świata w swoim `data_dir`. Kamera zachowuje tę samą kalibrację, rozdzielczość i temat ROS. Odometria, geometria kolizyjna i konfiguracja Safety pozostają takie jak w standardowym profilu.

W próbie z 26 listopada 2026 r. na WSL2 Ubuntu 22.04.5, ROS 2 Humble i Fortress 6.18.0 API potwierdziło **11/11** punktów w obu wariantach i **7** czytelnych etykiet palet. W trudniejszych warunkach liczba lokalizacji do ręcznej weryfikacji wzrosła z **2 do 4**, a liczba zapisów kontroli jakości spadła z **8 do 4**. Dwa puste miejsca (`A-01-03`, `B-02-01`) zmieniły wynik na niepewny. Odczyt zajętości w `A-01-05` także stał się niepewny. X3 wylądował, zwolnił strefy i wystawił raport. Identyfikator próby `INS-CONTROL-20261126-112516-4895F6CC`.

Na 20 surowych klatkach w obu ustawieniach z tego samego pola startowego średnia jasność centralnego obszaru spadła ze 101,2 do 84,4 w skali 0–255. Pojedyncze przebiegi porównują łączny wpływ zmian światła i szumu. Automatyczne ponawianie odczytów było wyłączone. [Dane porównawcze](docs/evidence/x3-camera-realism.json)

## Lokalizacja X3 w trybie shadow

Próba korzysta ze świata `localization_showcase.sdf` i istniejącej mapy statycznej Rackonaut. X3 startuje na znanej pozycji doku. Estymator działa w trybie `shadow`, a odometria Gazebo pozostaje źródłem pozycji drona. Walidator interpoluje pozycję Gazebo do znacznika czasu pomiaru i zapisuje porównania w `localization-validation.jsonl` w katalogu `data_dir`.

```bash
source scripts/robotics/activate.bash
ros2 run rackonaut_drone prepare_model --localization-shadow
LP_NUM_THREADS=4 ros2 launch rackonaut_drone localization.launch.py
```

Poczekaj na kalibrację na postoju przed rozpoczęciem sterowania z klawiatury. Estymatę i jej stan można odczytać w drugim aktywowanym terminalu z tematów `/rackonaut/localization/estimate` i `/rackonaut/localization/state`. W razie równoległego uruchomienia innego profilu ustaw inną domenę ROS i partycję Gazebo przed aktywacją.

Model ma IMU 50 Hz z tym samym szumem Gaussa i błędem stałym co profil referencyjny, oraz LiDAR 3D 192 × 37 przy nominalnych 6 Hz w czasie symulacji. IMU znajduje się w początku układu drona, a LiDAR 0,09 m wyżej. Adapter ROS nadaje pomiarom istniejące nazwy ramek kontraktu lokalizacji i zachowuje ich znaczniki czasu. Estymata trafia na osobny temat, więc domyślny profil inspekcji i źródło odometrii mają dotychczasową konfigurację.

Manewry z próby można odtworzyć bez teleop w drugim terminalu po aktywacji tej samej domeny ROS. Test unosi X3 nad dokiem, mierzy zawis i obrót 90°, leci przez szyb i górny tunel od wejścia do A do wejścia do B, po czym pozostawia drona w zawisie w symulacji. Kończy się zapisaniem okien pomiarowych i stanów w `traffic.json`. Po próbie zatrzymaj launcher.

```bash
python3 ros2_ws/src/rackonaut_drone/test/probe_shadow.py ros2_ws/log/x3-shadow-probe
```

**Wynik próby.** Ubuntu 22.04.5 WSL2, ROS 2 Humble, Fortress 6.18.0, Python 3.10.12. Walidator dopasował czasowo **723** próbek estymaty do odometrii Gazebo. Odbiornik zmierzył 50,00 Hz dla IMU i 6,02 Hz dla LiDAR-u w czasie symulacji. W trzech badanych oknach estymator raportował `TRACKING`.

| Etap | Próbki | RMSE 3D | p95 3D |
| --- | ---: | ---: | ---: |
| Zawis nad dokiem | 24 | 1,24 cm | 1,38 cm |
| Obrót 90° | 42 | 1,34 cm | 1,53 cm |
| Górny tunel A → B | 193 | 0,37 cm | 0,73 cm |

Próba obejmowała jedną trasę ze znaną mapą i poprawną inicjalizacją w doku. Walidator porównywał pozycje na znacznikach czasu skanu. [Pomiary i pozostałe etapy](docs/evidence/x3-shadow-localization.json)

### Zanik danych czujników w zawisie

W osobnej domenie ROS, podczas zawisu X3, dwukrotnie wstrzymano proces `x3_shadow_sensor_bridge` sygnałem `SIGSTOP` i wznowiono przez `SIGCONT`. Mostek przesyła razem dane IMU i LiDAR-u. Walidacja dotyczy jednoczesnej przerwy obu strumieni.

| Czas przerwy | Do stanu LOST | Od wznowienia do TRACKING | Komunikaty odometrii Gazebo podczas przerwy |
| ---: | ---: | ---: | ---: |
| 1,015 s | 0,445 s | 0,128 s | 18 |
| 3,007 s | 0,537 s | 0,154 s | 49 |

Estymator sygnalizował `IMU data stopped advancing`. Gazebo nadal publikowało pozycję dla próby lotu. Największa zmiana położenia względem początku przerwy do odzyskania śledzenia wyniosła 8,5 mm. Są to dwa kontrolowane pomiary na postoju w powietrzu, w trybie `shadow`. [Telemetria próby](docs/evidence/x3-shadow-dropout.json)

### Próba lotu sterowanego z IMU i LiDAR-u

W odizolowanej próbie integracyjnej launcher testowy z modułu X3 podstawia model i mostki X3 pod istniejący stos Control Center, Energy, Mission i Safety. Estymator jako jedyny publikuje `/rackonaut/drone/odom` oraz dynamiczny TF. Mostek Gazebo publikuje pozę osobno na `/rackonaut/validation/ground_truth` dla walidatora. Adapter doku mapuje nazwę kolizji korpusu X3 zgłoszoną przez fizyczny czujnik na nazwę obsługiwaną przez istniejący moduł energii.

```bash
export RACKONAUT_ROS_DOMAIN_ID=81 RACKONAUT_GZ_PARTITION=rackonaut-x3-active-81
source scripts/robotics/activate.bash
ros2 run rackonaut_drone prepare_model --localization-shadow
LP_NUM_THREADS=4 ros2 launch "$PWD/ros2_ws/src/rackonaut_drone/test/active_mission.launch.py" \
  localization:=sensor_based localization_diagnostics:=true safety:=true safety_sensor:=virtual \
  http_port:=18765 mock_port:=18000 data_dir:="$PWD/ros2_ws/log/x3-active-trial"
```

W [panelu testowym](http://127.0.0.1:18765/) przed startem sprawdź `TRACKING`, kontakt z dokiem i stan Safety. Ten launcher jest przeznaczony do porównawczej, bezokiennej próby na znanej mapie. Dla każdego przebiegu użyj osobnej domeny i katalogu danych. Scenariusze obejmują lot do jednego punktu i lądowanie, utratę IMU i LiDAR-u w pionowym wznoszeniu oraz pełną inspekcję z zakresem **Full inventory**.

W próbie utraty czujników wstrzymaj mostek publikujący IMU i LiDAR, gdy dron wznosi się, a walidator pokazuje wysokość ponad 0,75 m. Rejestruj stan misji, komendy prędkości i wysokość walidacyjną Gazebo. Po przerwaniu misji wznów mostek i sprawdź powrót do `TRACKING` oraz to, czy misja pozostaje w stanie `ABORTED`.

| Scenariusz | Wynik |
| --- | --- |
| Lot do `A-01-01` | `COMPLETE`, potwierdzono 1/1 stanowisko. Lądowanie z fizycznym kontaktem doku, zwolnienie stref i raport HTML (HTTP 200). |
| Przerwa IMU i LiDAR-u w czasie wznoszenia | `ABORTED` po 0,573 s. Sterownik wydał komendę zerową, a dron wzniósł się jeszcze o około 0,36 m przed ustabilizowaniem. Safety utrzymało strefy w `RECOVERY`. Śledzenie wróciło, a misja pozostała przerwana. |
| Pełna inspekcja 11 stanowisk | `ABORTED`, 7/11 stanowisk. Podejście do `A-01-03` zostało pominięte. Przy 17% baterii dron wylądował na doku. Autoładowanie przeszło do `CHARGING`, po czym misja zgłosiła `LOCALIZATION_LOST`. |
| Cztery pozostałe stanowiska | Potwierdzono `A-01-03` oraz `B-01-01`. W trakcie powrotu do doku estymator zgłosił `IMU data stopped advancing`, po czym misja została przerwana. |
| Przejście z `B-01-02` do `B-02-01` | Potwierdzono `B-01-02`. Moduł omijania zarejestrował przeszkodę 0,60 m od drona podczas przejścia. Misję przerwano po braku zweryfikowanego obejścia lub drogi powrotnej. |
| Bezpośrednia próba `B-02-01` z doku | `COMPLETE`, 1/1. Lądowanie z fizycznym kontaktem doku, zwolnienie stref i raport HTML (HTTP 200). |

Łącznie próby potwierdziły obserwacje dla wszystkich 11 stanowisk. Pełna misja z ładowaniem i automatycznym wznowieniem pozostaje kryterium odbioru. Przy pierwszym powrocie do doku kontroler przeszedł do `CHARGING` i po 36 ms zapisał `LOCALIZATION_LOST`. Ostatni odczyt panelu nadal pokazywał `TRACKING`. W późniejszym locie między stanowiskami w alei B sonda odebrała te same znaczniki czasu IMU przed adapterem i za nim. W próbie, w której estymator zapisał przerwę IMU, stanowisko pomiarowe rejestrowało komunikaty estymatora. Miejsce wystąpienia przerwy pozostaje nieustalone.

Stanowisko potwierdzone przez misję oznacza otrzymanie obserwacji z kamery i API. Status etykiety oraz rozpoznany identyfikator palety są zapisane osobno. [Pomiary i identyfikatory prób](docs/evidence/x3-active-flight.json)


## Sterowanie i obraz

Polecenia poniżej wykonuj w osobnych terminalach po aktywacji projektu z tym samym `RACKONAUT_ROS_DOMAIN_ID` i `RACKONAUT_GZ_PARTITION`. Jeśli działa już demonstrator, ustaw inną domenę i partycję **przed** aktywacją, np. `RACKONAUT_ROS_DOMAIN_ID=66` i `RACKONAUT_GZ_PARTITION=rackonaut-x3-local`. Uruchom tylko jednego wydawcę poleceń na temacie sterowania. Zakończ teleop przed uruchomieniem testu automatycznego.

```bash
source scripts/robotics/activate.bash
LP_NUM_THREADS=2 ros2 launch rackonaut_drone drone.launch.py
```

Domyślnie uruchamia się świat referencyjny `rackonaut` bez GUI, z odrębnym spawnem w `(0, 0, 0.12)` m, orientacja `(0, 0, 0)` rad. `gui:=true` otwiera okno Gazebo i wymaga działającego wyświetlania. Parametry `world_path`, `world_name`, `model_path` i `x/y/z/roll/pitch/yaw` pozwalają wskazać kompatybilny świat, przygotowany model i pozycję. Świat ma udostępniać usługę `/world/<nazwa>/create`. Zakończ launcher przez Ctrl+C.

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/rackonaut/drone/cmd_vel
ros2 run image_view image_view --ros-args -r image:=/rackonaut/camera/image_raw
```

Klawisze `t/b` sterują wysokością, `i/,` ruchem przód/tył, `j/l` obrotem, a `k` wysyła zerową prędkość. Przy zerze X3 wyhamowuje i pozostaje w zawisie. Przekaźnik przekazuje komendy z częstotliwością 10 Hz, zeruje je po upływie 0,5 s od ostatniej komendy na najbliższym cyklu i trzyma zero do następnego polecenia. Ograniczenia w symulatorze to 0,6 m/s na oś i 0,5 rad/s w yaw.

## Interfejsy

| ROS 2 | Gazebo / źródło | Weryfikacja |
| --- | --- | --- |
| `/rackonaut/drone/cmd_vel` | Przekaźnik `/rackonaut_drone/controller/cmd_vel` → `/rackonaut_x3/cmd_vel` | `Twist`, niezawodne QoS, +X w przód, +Y w lewo, +Z w górę, dodatni yaw wokół +Z |
| `/rackonaut/camera/image_raw`, `/rackonaut/camera/camera_info` | `/rackonaut_x3/rgb`, `/rackonaut_x3/camera_info` | `rgb8` 320 × 240 przy nominalnych 10 Hz czasu symulacji, wspólny stempel i `rackonaut_camera_optical_frame` |
| `/rackonaut/drone/odom`, `/tf` | `/rackonaut_x3/odom`, `/rackonaut_x3/tf` | Odometry i dynamiczny TF `rackonaut_odom` → `rackonaut_base_link` z symulatora, nominalnie 25 Hz |
| `/tf_static` | `x3_camera_tf` | Transformacja bazy do ramki optycznej. Kamera 0,27 m z przodu i 0,04 m powyżej bazy |
| `/clock` | `/world/<nazwa>/clock` | Jeden mostek zegara. Konsumenci z `use_sim_time:=true` |

Mostek w zweryfikowanym środowisku oferował niezawodne QoS. Odbiorniki obrazu, kalibracji, odometrii i zegara w teście używały `qos_profile_sensor_data`. Pozycja w odometrii i dynamicznym TF pochodzi z symulatora.

## Odtworzenie próby odbiorczej

1. Start w świecie referencyjnym zgodnie z poleceniem wyżej. W innym aktywowanym terminalu uruchom `python3 ros2_ws/src/rackonaut_drone/test/probe_x3.py ros2_ws/log/x3-motion`. Próba sprawdza ruch i zawis oraz zapisuje klatkę i wynik JSON. Po teście zatrzymaj ten launcher.
2. Zbuduj `rackonaut_warehouse` i `rackonaut_perception` przez `colcon build --packages-up-to rackonaut_warehouse rackonaut_perception` w `ros2_ws`, potem aktywuj projekt ponownie. Uruchom magazyn z osobnym spawnem przed regałem i przygotuj lokalne Mock API.

   ```bash
   LP_NUM_THREADS=2 ros2 launch rackonaut_drone drone.launch.py \
     world_path:="$(ros2 pkg prefix --share rackonaut_warehouse)/worlds/showcase.sdf" \
     x:=5.46 y:=0.45 yaw:=1.57079632679
   ```

   ```bash
   python3.10 scripts/api/setup.py
   .venv-backend/bin/python -m uvicorn backend.mock_api:app --host 127.0.0.1 --port 18001
   ```

3. Użyj tego samego identyfikatora w terminalach percepcji i odczytu wyników. Test w tej konfiguracji wznosi X3 przed regałem i utrzymuje go na dwóch wysokościach.

   ```bash
   ros2 run rackonaut_perception inspect --ros-args \
     -p use_sim_time:=true -p inspection_id:=INS-X3-REPRO-001 \
     -p backend_url:=http://127.0.0.1:18001
   ```

   ```bash
   python3 ros2_ws/src/rackonaut_drone/test/probe_x3.py ros2_ws/log/x3-warehouse --warehouse
   curl -fsS 'http://127.0.0.1:18001/api/observations?inspection_id=INS-X3-REPRO-001'
   ```

## Wyniki

Ubuntu 22.04.5 WSL2, ROS 2 Humble, Fortress **6.18.0**, Python **3.10.12**, llvmpipe i `ros_gz_bridge` 2.4.1. Bazą modułu był `6e04fcfa` z `origin/main`.

- **Referencja.** `scripts/robotics/smoke --reference` w czystej kopii tagu `demo-complete` (`cc8f742a38f6b81fab5a12217a2a47e5592015ad`) zaliczył zegar, odometrię, ruch, obraz i sprzątnięcie procesów. Pełna misja `INS-CONTROL-20261126-091714-C623F756` potwierdziła **11/11**, bez pominięć. Trwała **202,8 s**, dron wylądował, a raport HTML zawierał identyfikator misji i zwrócił HTTP 200. Użyto osobnej kopii WSL2 i oddzielnych portów.
- **X3 w świecie referencyjnym.** Ruch w górę 0,178 m, obrót 0,455 rad, ruch do przodu względem obróconego drona 0,184 m. Zmierzono 0,458 s od zakończenia nadawania w próbie do pierwszego zera; prędkość podczas sprawdzenia zawisu spadła poniżej 0,10 m/s. Osobna próba klawiatury potwierdziła wznoszenie po `t` o 0,190 m i zerową komendę po `k`. [Telemetria lotu](docs/evidence/motion.json) · [Próba klawiatury](docs/evidence/keyboard.json)
- **X3 w magazynie.** W próbie `INS-X3-20261126-092105` odczytano znaczniki na dwóch wysokościach. Percepcja przesłała rzeczywiste obserwacje z symulacji dla `A-01-01 → P001` oraz `A-01-02 → P003`. Obie dostały HTTP 201. [Dolna półka](docs/evidence/x3-shelf-marker-0.png) · [Górna półka](docs/evidence/x3-shelf-marker-1.png) · [Dane próby](docs/evidence/warehouse.json) · [Obserwacje API](docs/evidence/api-observations.json)
- **Regresja.** Przeszło 7 testów kontraktów i Mock SAP oraz 7 testów modułu Perception.

Pierwotny odbiór X3 obejmował sterowanie ręczne i tor kamery w symulacji. Pomiary autonomii i reakcji na utratę lokalizacji opisano w sekcji [próby lotu sterowanego z IMU i LiDAR-u](#próba-lotu-sterowanego-z-imu-i-lidar-u).
