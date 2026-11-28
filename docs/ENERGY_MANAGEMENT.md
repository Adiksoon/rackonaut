# GOAL 12 · Energia i autonomiczne dokowanie

## Uruchomienie

W Ubuntu 22.04 lub WSL2 z ROS 2 Humble i Gazebo Fortress uruchom z katalogu repozytorium:

```bash
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
LP_NUM_THREADS=4 ros2 launch rackonaut_control control.launch.py \
  energy:=true safety:=true safety_sensor:=laser battery_initial:=64.0 charge_rate:=6.0
```

W [Control Center](http://127.0.0.1:8765) wybierz **3D Digital Twin** lub **2D Warehouse Map**, a następnie **Custom inspection**. Zaznacz A-01-01, A-01-02, A-01-03 i A-01-05. Włącz **Package quality** i **Adaptive inspection**. Uruchom inspekcję, gdy panel potwierdzi odometrię, baterię i gotowość Safety Managera. Pole startowe jest jednocześnie stacją dokującą. W **Drone & Energy** widać przewidywany koszt i rzeczywiste zmiany symulowanej baterii. **Follow** ułatwia obserwowanie powrotu, a **Focus dock** przybliża stację.

`battery_initial` jest początkowym procentem przy uruchomieniu symulatora. `charge_rate` to przyrost w punktach procentowych na sekundę symulacji. Poziom zachowuje się pomiędzy zleceniami w uruchomionej instancji. Restart przywraca wartość startową. Przy konfiguracji demonstracyjnej rozpocznij misję po pojawieniu się gotowości, ponieważ na postoju model powoli zużywa energię. Profil `safety_sensor:=virtual` włącza pomiar obecności wirtualnej.

## Model i prognoza

Referencyjny model drona korzysta z pluginów sterowania wielowirnikowcem i odometrii. Dostępny w Fortress plugin LinearBattery oraz standardowy komunikat ROS 2 wykorzystano jako punkty odniesienia. Własny węzeł umożliwia powiązanie ładowania z warunkami kontaktu i stanem istniejącego Mission Managera bez zmiany pluginu napędowego. [LinearBattery Fortress](https://gazebosim.org/api/gazebo/6/classignition_1_1gazebo_1_1systems_1_1LinearBatteryPlugin.html) · [BatteryState Humble](https://docs.ros.org/en/humble/p/sensor_msgs/msg/BatteryState.html)

Energy Manager całkuje zużycie na podstawie różnic kolejnych znaczników czasu sim oraz zmierzonych prędkości. Domyślne stawki to 0,55 punktu procentowego na sekundę w powietrzu, 0,32 punktu na metr ruchu poziomego, 0,80 punktu na metr wzniesienia i 0,015 punktu na sekundę postoju. Model publikuje `/rackonaut/drone/battery` typu `sensor_msgs/msg/BatteryState`. Napięcie, temperatura, prąd i pojemność fizyczna są nieznane. Stan stacji i parametry modelu są publikowane w lokalnej telemetrii `/rackonaut/energy/state`. Węzeł zapisuje osiągnięte cykle do `charge-cycles.jsonl` w katalogu danych Control Center.

Plan pokazuje długość trasy, szacowany czas lotu i obserwacji, opcjonalny budżet adaptacyjny, koszt powrotu i rezerwę 8 punktów procentowych. Estymator wykorzystuje geometrię trasy oraz przyjęte prędkości i czasy stabilizacji. Serwer oraz Mission Manager sprawdzają możliwość dotarcia do pierwszego pozostałego celu i powrotu. W locie system porównuje dostępny poziom z kosztem kolejnej obserwacji i powrotu. Przy zbliżaniu się do chronionego budżetu powrotu może pozostawić niedokończoną bieżącą obserwację w kolejce. Prognozy służą temu demonstratorowi i nie mają gwarancji błędu.

## Dokowanie i kontynuacja

Mission Manager prowadzi drona do przodu alejki i korytarza tranzytowego, następnie nad środek stacji i do lądowania. Jest jedynym komponentem wydającym komendy prędkości. Stacja ma podświetlane oznaczenia i podstawę wizualną w Gazebo. Kontakt modelowany jest kinematycznie. Maksymalne odchylenie poziome to 9 cm, odchylenie Z to 2,2 cm, a odchylenie yaw to 0,065 rad. Dodatkowo system sprawdza prędkość liniową i kątową. Pozycja musi być utrzymana przez co najmniej 0,65 s symulacji. Sam proces ładowania zaczyna się po 1,45 s stabilnego kontaktu i przy odpowiednim stanie misji. Pierwsza konfiguracja demonstracyjna umożliwia rozpoczęcie lotu z częściowym naładowaniem. Zakończone zadanie może ładować się na stacji do 100%.

Ładowanie po powrocie przechodzi w gotowość przy wystarczającej energii na następny odcinek, powrót i rezerwę, oraz co najmniej 88% w tym profilu. W opisanym niżej profilu referencyjnym Safety Manager utrzymuje rezerwację przez oba loty i całe ładowanie. Każda zgoda zawiera numer odlotu. Drugi start wymaga świeżych danych, wolnych zarezerwowanych stref, potwierdzonych sygnałów oraz zgody dla drugiego odlotu. Alarm, brak danych lub Abort kończy zadanie procedurą odzyskania kontroli. Kontynuacja zachowuje ten sam identyfikator, historię obserwacji i zdjęć oraz kolejkę pozostałych celów. Raport HTML pokazuje zużycie i ukończone lokalizacje dla każdego lotu.

W profilu Full Robotics z fizycznym czujnikiem doku Safety utrzymuje rezerwację podczas powrotu. Po potwierdzeniu kontaktu, położenia i zwolnienia sterowania otwiera strefy na czas ładowania. Gdy bateria jest gotowa, ta sama inspekcja może zostać wznowiona dopiero po ponownej rezerwacji. Zajęta strefa wstrzymuje odlot. Sterownik wymaga nowej zgody dla kolejnego odlotu i potwierdzonych czerwonych sygnałów.

## Rzeczywiste próby

W Gazebo Fortress, ROS 2 Humble i lokalnym Chrome wykonano pełen lot laserowy `INS-CONTROL-20261125-125808-A2CDCFBA`. Cała misja trwała 241,4 s czasu rzeczywistego. Ładowanie do osiągnięcia progu gotowości zajęło około 13 s czasu symulacji od potwierdzenia dokowania. Próby telemetryczne podczas ładowania dały około 6,0 punktu procentowego na sekundę symulacji, zgodnie z nastawą.

| Część misji | Bateria początkowa | Bateria przy dokowaniu | Lokalizacje zakończone |
| --- | ---: | ---: | --- |
| Lot 1 | 63,4% | 14,7% | A-01-01, A-01-02, A-01-03 |
| Ładowanie i druga zgoda | 14,7% | 88,4% przy osiągnięciu gotowości | Rezerwacja A i T utrzymana |
| Lot 2 | 89,4% | 42,9% | Pozostałe A-01-05 |

Raport obejmuje obie części zadania, osiem obserwacji przyjętych przez API oraz zachowaną dokumentację jakości. Powrót rozpoczął się po zakończeniu A-01-03 przy około 29,4% baterii, gdy dostępna energia nie pokrywała prognozowanego kosztu A-01-05 i powrotu z zapasem. Podczas próbkowanych odcinków w powietrzu ładowanie było wyłączone. Dwa osobne zdarzenia `start_permitted` dotyczą tego samego identyfikatora i odlotów 1 oraz 2. [Raport HTML](energy-evidence/inspection.html) · [Dane inspekcji](energy-evidence/inspection.json) · [Chronologia i zgody](energy-evidence/cycle-telemetry.json) · [Komunikat BatteryState](energy-evidence/battery-state.yaml) · [Dziennik ładowania](energy-evidence/charge-cycles.jsonl)

Kolejne zlecenie A-01-01 rozpoczęło się z 93,5% zachowanej energii. Wykonało jedną obserwację i zakończyło się po 60,9 s oraz jednym locie. [Stan końcowy](energy-evidence/normal-mission.json) · [Plan w 2D](energy-evidence/plan-2d.png) · [Wynik w 2D](energy-evidence/normal.png)

[Nagranie ze skrótami między fazami](energy-evidence/demo.mp4) · [Plan w 3D](energy-evidence/plan-3d.png) · [Powrót](energy-evidence/return_to_dock.png) · [Dokowanie](energy-evidence/docking.png) · [Ładowanie](energy-evidence/charging.png) · [Wznowienie](energy-evidence/resuming.png) · [Zakończenie misji](energy-evidence/complete.png) · [Zestawienie dwóch odlotów](energy-evidence/report-energy.png)

Przy starcie z 5% w profilu wirtualnym Control Center blokował przycisk, a bezpośrednia prośba do lokalnego `/api/start` zwróciła HTTP 409 z wyliczonym minimum. Dron pozostał na stacji. [Blokada w 2D](energy-evidence/low-blocked.png) · [Odpowiedź serwera](energy-evidence/low.json) · [Stacja w Gazebo](energy-evidence/dock-gazebo.jpg) · [Stacja w Digital Twin](energy-evidence/dock-close.png)

W profilu wirtualnym osobny lot zakończył się dokowaniem i rzeczywistym wzrostem symulowanej baterii. Wejście pracownika w zarezerwowany obszar podczas ładowania wywołało `intrusion`, zakończyło zadanie przez Abort i zatrzymało ładowanie. Usunięcie pracownika nie spowodowało kolejnego startu. Udany drugi odlot potwierdzono w profilu laserowym. [Stacja podczas ładowania w Gazebo](energy-evidence/dock-charging-gazebo.jpg) · [Kontakt w 3D](energy-evidence/dock-contact.png) · [Blokada po alarmie](energy-evidence/obstacle-blocked.png) · [Dane Safety Managera](energy-evidence/obstacle.json)

W oddzielnej próbie ręczny Abort zatrzymał misję poza stacją na wysokości około 0,78 m. Próba potwierdziła brak ładowania, utrzymanie rezerwacji i przejście stacji w `FAULT` po wstrzymaniu mostka odometrii. Mostek przywrócono po pomiarze. [Abort w aplikacji](energy-evidence/manual-abort.png) · [Dane Abort i utraty odometrii](energy-evidence/manual-abort.json)

## Wydajność

Na tym samym hoście WSL2 profil laserowy używał llvmpipe z czterema wątkami. Zarejestrowano po 96 próbek Gazebo dla aktywnego widoku 2D i 3D, na postoju po misji. Kamera i skaner A były mierzone przez ROS 2.

| Aktywny widok | RTF Gazebo | Kamera | Skaner A |
| --- | ---: | ---: | ---: |
| 2D | 0,657 | 6,54 Hz | 2,62 Hz |
| 3D | 0,640 | 6,42 Hz | 2,58 Hz |

W GOAL 11 w podobnych warunkach uzyskano RTF 0,659 dla 2D i 0,643 dla 3D. Krótkie próby wskazują porównywalną wydajność; obejmują jeden host i odrębne uruchomienia, więc nie izolują kosztu samego Energy Managera. [Surowe pomiary](energy-evidence/performance) · [Wyniki GOAL 11](DIGITAL_TWIN.md)

## Zakres symulacji

Działanie zweryfikowano z referencyjnym dronem i lokalnym fixture API. W sprawdzonym repozytorium brakowało gałęzi modułów zespołu. Przeszło 26 testów robotyki i cztery grupy testów HTTP. Oba nowe światy przeszły walidację SDF, a osiem wcześniejszych światów jest identycznych bajt po bajcie z GOAL 11. Pola pomiaru zachowują ograniczenia GOAL 09. Wdrożenie w hali wymaga sprzętowego potwierdzenia kontaktu, niezależnych zabezpieczeń ładowania i budżetu powrotu zwalidowanego na konkretnym dronie i akumulatorze. Rezerwacja przez cały postój wydłuża wyłączenie przestrzeni dla operatorów.
