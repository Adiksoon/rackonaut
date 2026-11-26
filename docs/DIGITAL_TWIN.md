# GOAL 11 · Rackonaut Digital Twin

## Uruchomienie

Na Ubuntu 22.04 lub WSL2 z ROS 2 Humble i Gazebo Fortress uruchom z katalogu repozytorium:

```bash
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
LP_NUM_THREADS=4 ros2 launch rackonaut_control control.launch.py \
  adaptive_world:=true safety:=true safety_sensor:=laser
```

W [Control Center](http://127.0.0.1:8765) wybierz **3D Digital Twin**. Kliknij alejkę lub znaczniki A-01-01, A-01-02, A-01-03 i A-01-05. Włącz **Package quality** i **Adaptive inspection**, a potem **Start Inspection**. Podczas lotu **Follow** ustawia kamerę w pobliżu drona. Po lądowaniu kliknij A-01-02 w widoku 3D. Panel pokaże stan porównania, próby, zdjęcia, **Focus rack** i **Plan reinspection**. **2D Warehouse Map** wraca do dotychczasowej mapy i zachowuje ten sam zakres.

**Isometric**, **Top** i **Reset** zmieniają perspektywę. Przeciągnięcie obraca scenę, prawy przycisk przesuwa kamerę, a kółko przybliża. **Eco** zmniejsza rozdzielczość renderowania i upraszcza warstwę skanów. Profil `safety_sensor:=virtual` korzysta z wirtualnej obecności z odpowiednim podpisem. Moduły renderowania są instalowane z ROS workspace i ładowane z serwera lokalnego.

## Dane i geometria

Przeglądarka używa `/api/layout` i `/api/state` z istniejącego Control Center. Ten sam wybór w 2D, 3D i panelu planowania trafia do `/api/plan` i `/api/start`. Start i Abort mają dotychczasową obsługę ROS. Widok pobiera pozycję, wysokość i kwaternion z odometrii. Interpolacja mieści się między odebranymi próbkami. Po utracie danych ostatnia pozycja jest oznaczona jako nieaktualna. Trasa nominalna, ślad lotu, aktualny cel i korekty pochodzą z Mission Managera.

Dane sceny powstają podczas generowania SDF. Zawierają obrys hali, regały, przęsła, poziomy, położenie sygnalizatorów, oznakowanie i palety scenograficzne. Hala jest pokazana w przekroju bez dachu. Uproszczony dron i skanery korzystają z położeń ROS i kalibracji. W magazynie jest 11 funkcjonalnych miejsc. Półprzezroczysta osłona oznacza przęsło bez zweryfikowanej zajętości. Symbol palety pojawia się po odczycie `occupied`. Scena prezentacyjna pomija kartony i etykiety scenariuszy z tych miejsc.

Kolory sygnalizatorów śledzą potwierdzone stany Safety Managera. Kolorowe pola pokazują dostęp, przygotowanie, rezerwację, naruszenie i usterkę. Przerywana niebieska granica wyznacza ograniczone pole pomiarowe LiDAR. Punkty mają współrzędne z bieżących skanów oraz wysokość płaszczyzny skanowania. Czerwone punkty to powroty zaklasyfikowane przez Safety Manager. Pole na podłodze ma ograniczone pokrycie przestrzeni przy regałach i poza płaszczyzną pomiaru. Po utracie skanów punkty znikają.

Status porównania pochodzi z podsumowania backendu. W demonstracji lokalny fixture zwrócił `pending`, więc UI pokazał **Pending SAP comparison**. Jakość ma osobny status. Zdjęcia z oceny **Intact** lub **Damaged** pochodzą z istniejącego archiwum. **Uncertain** korzysta z lokalnego odczytu jakości powiązanego z obserwacją, a brak oceny ma status **Not assessed**. Wybór na modelu pokazuje szczegóły bieżącej misji. Wcześniejsze wyniki pozostają dostępne w istniejącej historii raportów. Kontrakt HTTP v1 backendu jest zgodny z GOAL 10.

## Wydajność i uruchomienie bez internetu

Three.js **0.182.0** udostępnia gotowe instancje siatek i sterowanie kamerą. Do instalacji UI wchodzą dwa moduły renderera, OrbitControls i licencja MIT. Powtarzalne belki, stojaki, półki i ładunki scenograficzne renderują się w grupach instancji. Widok korzysta z prostych siatek bez cieni. Rysowanie jest ograniczone do około 25 kl./s i zatrzymywane po przełączeniu na 2D lub ukryciu karty. Hala nie jest odtwarzana z obrazu kamery. [Three.js r182](https://github.com/mrdoob/three.js/tree/r182) · [OrbitControls](https://threejs.org/docs/#OrbitControls) · [Licencja](../ros2_ws/src/rackonaut_control/web/vendor/three-LICENSE.txt)

Pomiar wykonano na tej samej instancji świata adaptacyjnego i profilu laserowego, z zatrzymanym dronem na padzie i aktywną kartą Chrome. Gazebo używał llvmpipe z czterema wątkami, a Chrome WebGL2 przez ANGLE, Radeon 610M i D3D11. RTF obliczono z 41 próbek statystyk Gazebo w każdym widoku. Kamera i skaner A były mierzone przez ROS 2 w czasie rzeczywistym przez około 13,5 s.

| Aktywny widok | RTF Gazebo | Kamera | Skaner A |
| --- | ---: | ---: | ---: |
| 2D | 0,659 | 6,57 Hz | 2,64 Hz |
| 3D | 0,643 | 6,41 Hz | 2,57 Hz |

Różnica RTF w tej krótkiej próbie wyniosła około 2,5%. Pełne loty z 3D trwały 147,0 i 148,3 s. Zachowany przebieg GOAL 10 na tym samym zakresie trwał 147,0 s. Pomiar dotyczy tego hosta i ustawień. [Surowe próbki](digital-twin/performance) · [GOAL 10](ADAPTIVE_INSPECTION.md)

## Próby i materiały

25 listopada 2026 r. w Chrome wybrano aleję B i cztery miejsca na geometrii 3D. Po przełączeniu na 2D zakres pozostał zgodny. Właściwy lot uruchomiono z zakresu wybranego w 3D. Misja `INS-CONTROL-20261125-123749-2F4F697F` zakończyła się czterema odwiedzonymi lokalizacjami, ośmioma obserwacjami, odzyskaniem P001, dwoma zdjęciami rozdarcia P003, ręczną weryfikacją A-01-05 i potwierdzonym lądowaniem. W czasie lotu zsynchronizowano położenie, plan, przebytą trasę i korektę adaptacyjną. Po lądowaniu test w Chrome potwierdził **Pending SAP comparison**, otworzył rzeczywisty obraz uszkodzenia P003 i przygotował ponowne zlecenie dla A-01-02. [Dane misji i API](digital-twin/flight-run.json) · [Wyniki i zdjęcia](digital-twin/damage-details.png) · [Ten sam wybór w 2D](digital-twin/fallback-2d.png)

- [Cały magazyn](digital-twin/whole.png) · [Zbliżenie regału](digital-twin/rack-close.png) · [Widok z góry](digital-twin/top.png) · [Wybór zakresu](digital-twin/selected.png)
- [Inspekcja z odometrią](digital-twin/drone-inspection.png) · [Korekta adaptacyjna](digital-twin/following-correction.png) · [Nagranie rzeczywistego lotu](digital-twin/demo.mp4) · [Próbki odometrii, planu i śladu](digital-twin/flight-telemetry.json)
- [Przygotowanie stref](digital-twin/preparing.png) · [Powroty z wózka](digital-twin/laser-returns.png) · [Alarm naruszenia](digital-twin/intrusion.png) · [Stan po Abort](digital-twin/abort.png)
- [Utrata skanów](digital-twin/stale-scan.png) · [Nieaktualna odometria](digital-twin/stale-odometry.png) · [Powrót do 2D](digital-twin/return-to-2d.png) · [Próbki Safety Managera](digital-twin/safety.json)

W oddzielnej misji wózek przeciął zarezerwowany korytarz T, co wywołało w 3D alarm **Intrusion** i przerwało rzeczywisty lot. W próbie ręcznego Abort zatrzymano drona podczas korekty A-01-02. Pozostała rezerwacja A i T. Wstrzymanie mostka LaserScan wyczyściło nieaktualne punkty, a wstrzymanie mostka odometrii oznaczyło ostatnią pozycję. Po przełączeniu na 2D oba mostki wznowiono. Osobno sprawdzono profil `virtual`, **Eco** i automatyczny powrót do mapy po kontrolowanej utracie kontekstu WebGL. [Profil wirtualny](digital-twin/virtual.png) · [Powrót z niedostępnego WebGL](digital-twin/webgl-fallback.png)

Próby przeprowadzono z referencyjnym dronem i lokalnym fixture API. Na sprawdzonych gałęziach zdalnych brakowało modułów pozostałych uczestników. Wszystkie 22 testy robotyki i 4 grupy testów kontraktu przeszły. Zweryfikowano trzy uruchamiane światy SDF i zgodność bajt po bajcie ośmiu wcześniejszych światów z GOAL 10.
