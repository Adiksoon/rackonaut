# Rackonaut · bezpieczeństwo na podstawie skanów laserowych

Profil dodaje trzy stacjonarne, poziome skanery GPU LiDAR w Gazebo Fortress. Mostek `ros_gz_bridge` przekazuje pomiary jako `sensor_msgs/msg/LaserScan` na `/rackonaut/safety/scan/a`, `/rackonaut/safety/scan/b` i `/rackonaut/safety/scan/t`. Obliczenia wykonują się na znanym montażu każdego skanera. W tym profilu Safety Manager subskrybuje pomiary oraz odometrię drona potrzebną do autoryzacji startu i potwierdzenia lądowania. Pozycje obiektów służą komponentowi Gazebo do ich przemieszczania. [Sensory Fortress](https://gazebosim.org/docs/fortress/sensors/) · [Mostek dla Humble](https://github.com/gazebosim/ros_gz/tree/humble/ros_gz_bridge)

Skan poziomy pozwala wykryć nieruchomą przeszkodę jeszcze przed startem. Pojedyncza kurtyna byłaby praktyczna do wykrywania przekroczenia wejścia. Kamera głębi pozwoliłaby monitorować większy przekrój wysokości, kosztem dodatkowego obrazu i przetwarzania. Na pokaz wybrano wbudowane skanery oraz przetwarzanie małej, uporządkowanej tablicy odległości na istniejącym stosie.

## Uruchomienie

Na Ubuntu 22.04/WSL2 z ROS 2 Humble, Fortress oraz zależnościami opisanymi w instrukcji Safety:

```bash
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
ros2 launch rackonaut_control control.launch.py safety:=true safety_sensor:=laser
```

Otwórz [Control Center](http://127.0.0.1:8765). Przerywane obrysy pokazują pola detekcji. Niebieskie linie i kropki to wybrane rzeczywiste wiązki z powrotem i ich końce. Pomarańczowe punkty to powroty spełniające regułę obecności. W sekcji **Warehouse Safety** widać wiek próbek, zajętość pola, stan sygnalizatorów i alarmy. Zielony sygnalizator oznacza dostęp dla ludzi do strefy bez rezerwacji. Pole może wtedy zawierać przeszkodę i blokować start drona.

**Simulation Controls** przemieszcza pracownika, wjeżdża wózkiem do A, pozostawia paletę w B i usuwa ją razem z wózkiem. Przycisk **Move outside** usuwa pracownika z pola. Przejazd wózka od parkingu do A odbywa się przed czołami regałów. Abort utrzymuje blokadę do restartu stosu.

Można dodać `laser_rviz:=true` i otworzyć trzy surowe skany w widoku z góry w RViz2. Stałe transformaty skanerów pochodzą z tego samego pliku kalibracji co świat. Jawny wariant wirtualny uruchamia się przez `safety:=true safety_sensor:=virtual`. Jest to także zachowanie dotychczasowego polecenia `safety:=true`. Utrata danych pomiarowych oznacza `STALE` lub `UNKNOWN` oraz blokadę wymaganej strefy.

## Geometria i detekcja

Każdy skaner emituje 512 próbek poziomych na skan, nominalnie 4 Hz w **czasie symulowanym**. Warstwa pomiarowa znajduje się 0,115 m nad podłogą. Geometria stref rezerwacji A, B i korytarza pozostaje taka sama jak w `demo-complete`. Skanery weryfikują poniższe pola wewnątrz tych stref.

| Skaner | Pole detekcji w układzie świata |
| --- | --- |
| A | X 3,50–15,00 m, Y −1,56–1,60 m. |
| B | X 3,50–11,00 m, Y −7,56–−4,40 m. |
| T | X 1,45–2,95 m, Y −7,50–1,05 m. |

Dla każdej skończonej odległości z ważnego skanu Safety Manager wylicza koniec wiązki w układzie mapy. Co najmniej trzy kolejne promienie z końcami w polu oznaczają obecność. Reguła stosuje się do każdego widocznego obiektu bez klasyfikacji i bez uczenia tła podczas pracy. Granica T omija obudowy skanerów alejek. Rzędy regałów, słupy i tablice znajdują się poza polami decyzji. Skan stary, z niewłaściwą ramką lub niewłaściwą geometrią nie odświeża stanu. Limit aktualności to 0,75 s czasu rzeczywistego dla każdego wymaganego pola. Na nieaktualnym skanie interfejs usuwa punkty, zamiast pokazywać ostatnie pomiary jako bieżące.

Model drona przelatuje nad płaszczyzną skanu. Kolumna startu i lądowania na polu pozostaje poza polem T, a pozwolenie na start i zwolnienie rezerwacji nadal wykorzystują odometrię i stan misji. Detekcja nie odejmuje drona ani obiektów na podstawie ich nazwy lub pozycji z symulatora.

Weryfikacja obejmuje wskazane tory ruchu i położenia obiektów. Skrajne części alejek, pole startowe, przestrzeń za regałami, obszar poza przerywanymi obrysami i obiekty nieprzecinające płaszczyzny są poza zakresem tego demonstratora. Przeszkoda bliższa może zasłonić dalszą. Trzy sąsiednie powroty dają ograniczoną czułość na wąskie obiekty i brzegi pola. Dla rzeczywistego magazynu potrzeba osobnej oceny ryzyka, walidacji pokrycia i niezależnych zabezpieczeń.

## Wydajność

Na tym samym hoście WSL2 z Ubuntu 22.04.5, ROS 2 Humble, Gazebo Fortress 6.16.0 i llvmpipe porównano rozgrzane, bezczynne stosy bez RViz2. Współczynnik to iloraz przyrostów czasu symulowanego i rzeczywistego między skrajnymi wartościami 45 próbek z Gazebo.

| Profil | Czas symulacji na sekundę rzeczywistą | Kamera pokładowa | Skaner A |
| --- | ---: | ---: | ---: |
| `demo-complete`, wariant wirtualny | 0,989 | 9,97 Hz | — |
| Profil laserowy | 0,629 | 6,37 Hz | 2,52 Hz |

Wariant laserowy spowalnia tę konfigurację o około 36%. Zmiana częstotliwości z 8 do 4 Hz oraz ograniczenie kamery podglądu do 3 Hz poprawiły obserwowaną przepustowość. Przed wydłużeniem postoju kamera wykryła uszkodzenie B-01-01 na żywo, ale do zapisu zdjęcia zabrakło stabilnych klatek. W profilu laserowym postój z oceną jakości wydłużono z 1,3 do 2,5 s. [Pomiary i surowe próbki](sensor-evidence/performance/summary.json) · [Dane pierwszego lotu B](sensor-evidence/telemetry/first-quality-flight.json)

## Próby w Gazebo

Próby wykonano 25 listopada 2026 r. za pomocą Control Center w Chrome oraz przez kontrolowane wstrzymanie rzeczywistego mostka skanów. Dane urządzeń pochodzą z symulatora.

| Próba | Wynik |
| --- | --- |
| Wolne pola | Trzy aktualne skany, zero zakwalifikowanych powrotów w polach, zielone światła. Po odstawieniu obiektów pola ponownie były wolne. [Mapa](sensor-evidence/01-clear-laser-fields.png) · [Dane](sensor-evidence/telemetry/all-cleared.json) |
| Nieruchomy pracownik przed startem | 29 zakwalifikowanych powrotów w próbce z A. Żądanie startu zostało odrzucone, a dron pozostał na polu. [Punkty](sensor-evidence/02-worker-laser-returns.png) · [Blokada](sensor-evidence/03-worker-start-blocked.png) |
| Wózek widłowy | Podczas wjazdu 35 powrotów w T, po zatrzymaniu 93 w A. [Kamera Gazebo](sensor-evidence/04-forklift-in-aisle.png) · [T](sensor-evidence/telemetry/forklift-transfer.json) · [A](sensor-evidence/telemetry/stationary-forklift.json) |
| Pozostawiona paleta | 77 powrotów w B po postoju. Po usunięciu z pola wrócił stan wolny. [Kamera Gazebo](sensor-evidence/05-pallet-in-aisle.png) · [Mapa powrotów](sensor-evidence/05-pallet-laser-returns.png) |
| Dron bez przeszkód | Przelot przez pole T i oględziny w B przebiegły przy świeżych skanach i zerze powrotów zakwalifikowanych jako przeszkoda. [Dron w B](sensor-evidence/06-drone-alone-in-field.png) · [Odometria i skany](sensor-evidence/telemetry/drone-alone-in-laser-field.json) |
| Utrata skanów na polu | Wstrzymanie mostka spowodowało `STALE`, `FAULT` i odmowę startu. Po wznowieniu skanów zlecenie pozostało odrzucone. [Utrata](sensor-evidence/telemetry/scan-fault.json) · [Przywrócenie](sensor-evidence/telemetry/scan-restored.json) |
| Utrata skanów w locie | W osobnej próbie wstrzymanie mostka wywołało Abort i pozostawiło A oraz T zarezerwowane po przywróceniu pomiarów. [Próba w locie](sensor-evidence/telemetry/scan-loss-in-flight.json) |
| Pracownik wchodzi podczas lotu | Pracownik wszedł do A. Powroty laserowe uruchomiły alarm i Abort. Dron pozostał w zawisie na 0,79 m, A i T pozostały zarezerwowane, a B otwarta. Próba następnego startu dostała HTTP 409. [Alarm](sensor-evidence/09-intrusion-laser-alarm.png) · [Dane i pozycja zawisu](sensor-evidence/telemetry/intrusion-abort.json) |
| Normalna inspekcja | `INS-CONTROL-20261125-112533-0CB026C0`, B z kontrolą jakości. Trzy potwierdzenia, zero pominiętych miejsc, jedno zdokumentowane uszkodzenie, lądowanie i zwolnienie B oraz T po 125,5 s. [Stan po lądowaniu](sensor-evidence/07-normal-landed-and-released.png) · [Raport HTML](sensor-evidence/inspection-b/index.html) |

W podglądzie i zrzutach stanu liczba powrotów oznacza liczbę punktów po ograniczeniu wizualizacji, z maksymalnie 96 punktami przeszkód na skan. Decyzja zapada na pełnej tablicy próbek. [LaserScan A z pracownikiem](sensor-evidence/telemetry/laser-worker-a.yaml) · [LaserScan wolnej B](sensor-evidence/telemetry/laser-clear-b.yaml)

W misji `INS-CONTROL-20261125-112744-C9C38F2F` od zakończenia analizy pierwszego skanu potwierdzającego przeszkodę do wysłania Abort minęło **76 ms**, a do odebrania `ABORTED` **276 ms**. To pomiar pojedynczej próby, bez czasu oczekiwania na następny skan i bez fizycznego hamowania drona. [Zdarzenia z czasami monotonicznymi](sensor-evidence/telemetry/safety-events.jsonl)

### Materiały

[11,75 s wejścia i alarmu w przeglądarce](sensor-evidence/laser-intrusion.mp4) · [Pracownik w Gazebo i potwierdzone zdarzenia](sensor-evidence/08-intrusion-gazebo.png) · [Surowe powroty w RViz2](sensor-evidence/10-rviz-live-returns.png)

### Następny etap

GOAL 10 powinien zweryfikować pokrycie z użyciem siatki pozycji i zasłoniętych obiektów oraz porównać wydajność na sprzętowym renderowaniu. Szczególnie istotne są brzegi pól, kolumna startowa, odcinek między polem T a początkiem A i B oraz pełna trasa 11 miejsc z włączoną kontrolą jakości.
