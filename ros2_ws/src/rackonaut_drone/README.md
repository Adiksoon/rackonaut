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

Zakres odbioru X3 to sterowanie ręczne i tor kamery w symulacji. Przed podłączeniem autonomii potrzebna jest wspólna próba z Adrianem obejmująca lądowanie oraz Abort z interlockiem.
