# Rackonaut · Storage Location Teaching

Warehouse Calibration zapisuje miejsca, z których operator chce obejrzeć regał. Operator zatrzymuje drona w chronionym locie i wybiera **Register Storage Location**. Formularz pokazuje przechwycone zdjęcie, proponuje identyfikator odczytany przez istniejący detektor ArUco i pozwala wpisać własny. **Save location** zatwierdza pose i zdjęcie w bieżącym szkicu. Zapisany punkt oznacza pozycję inspekcyjną drona.

## Uruchomienie

Po konfiguracji opisanej w [Quick Start](../README.md#start-here) zbuduj pakiety i uruchom pełny profil z lokalizacją SLAM.

```bash
scripts/robotics/build
read -rsp 'Kod Service: ' RACKONAUT_SERVICE_CODE
printf '\n'
export RACKONAUT_SERVICE_CODE
scripts/robotics/checkpoint live mapping_only:=true full_route_slam:=true
```

Otwórz [Control Center](http://127.0.0.1:8765/). Wybierz **Service**, odblokuj panel, kliknij **Start Calibration** i **Open mapping flight**. Po potwierdzeniu pustej mapy i listy wybierz alejkę i **Start mapping flight**. Po zatrzymaniu drona przy regale zarejestruj miejsce. Kliknięcie wiersza lub markera na **3D Scan** centruje kamerę mapy i pokazuje zdjęcie. Lista pozwala zmienić ID, ponownie zarejestrować pozycję i zdjęcie albo usunąć wpis ze szkicu. Zastąpienie rekordu oraz usunięcie wymagają potwierdzenia. Po **Return and end session** i fizycznym dokowaniu w Service pojawiają się linki do PLY, wyniku z trajektorią i listy miejsc.

## Źródło danych i synchronizacja

Control Center buforuje nagłówki ROS kamery i odometrii sterowania z bieżącej sesji SLAM. Wybiera klatkę objętą dwiema próbkami odometrii. XYZ jest interpolowane liniowo, a quaternion metodą SLERP. Wektor kierunku odpowiada osi optycznej kamery, która w modelu referencyjnym wskazuje w kierunku osi +X kadłuba. W pliku zapisano dokładny czas ROS klatki oraz oddzielny czas odebrania jej przez Control Center w UTC. Identyfikatory z ArUco pochodzą z istniejącego słownika tabliczek lokalizacji. Czytelny kod palety i pozycje skonfigurowanych regałów nie uczestniczą w przypisaniu. [Format ROS](../contracts/ros.md) · [ROS Message Filters](https://docs.ros.org/en/humble/p/message_filters/doc/index.html) · [SciPy SLERP](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.Slerp.html)

| Bramka rejestracji | Warunek |
| --- | --- |
| Tryb | Autoryzowany Service, aktywny lot ręczny powiązany z bieżącą sesją `RECORDING`, `TRACKING` oraz świeże odczyty LiDAR i IMU. |
| Safety i Energy | Aktualna rezerwacja tej misji, świeże i wolne wymagane strefy z potwierdzoną sygnalizacją, zweryfikowany budżet Energy oraz stan ręcznego sterowania `HOLD`. |
| Czasy | Klatka odebrana w ostatnich 0,60 s i odometria w ostatnich 0,35 s czasu rzeczywistego. Dwie próbki otaczające klatkę oraz sąsiednie próbki historii muszą być oddalone o najwyżej 0,12 s czasu symulowanego. |
| Zawis | Co najmniej 0,38 s historii przed klatką aż do ostatniej dostępnej pozy. Prędkość liniowa do 0,065 m/s i kątowa do 0,10 rad/s, z rozrzutem pozycji do 0,035 m i orientacji do 0,075 rad w zbadanym oknie. |
| Potwierdzenie | Zdjęcie do przeglądu jest powiązane z sesją Service i ważne 60 s. Zapis ponownie sprawdza świeże wejście i zawis. Ruch od podglądu, utrata śledzenia, powrót, Recovery i Abort blokują zatwierdzenie. |

Wątek HTTP wykonuje interpolację, detekcję i zapis poza blokadą służącą sterowaniu. Krótka blokada dostarcza spójny widok stanu oraz kopię buforów. Trwająca transakcja opóźnia jedynie publikację końcowego wyniku mapowania. Mission Manager publikuje polecenia ruchu własnym procesem. Progi powyżej dotyczą akwizycji zdjęcia i pozy.

## Zapis sesji

```text
mapping/CAL-…/
  map.ply
  result.json
  locations.json
  locations/CAP-…/reference.jpg
```

`calibration-draft.json` wskazuje listę przez `locations_reference`. Manifest jest źródłem aktualnej listy miejsc. Łączy sesję kalibracji i mapowania z PLY i wynikiem zawierającym trajektorię. Rekord ma własne `LOC-…`, identyfikator podany przez operatora lub odczytany z ArUco, nazwę ramy, kamerę, pozycję, quaternion XYZW, kierunek optyczny, czas akwizycji, ocenę SLAM, błędy standardowe składowych pozycji i odstępy czasowe użytych próbek. Zawiera też opcjonalny opis, status `approved` i ścieżkę do pełnej nieanotowanej klatki z kamery. Obraz ma rozdzielczość wejścia z ROS i jest kodowany do JPEG przez istniejącą ścieżkę kamery Control Center.

Zdjęcie otrzymuje nową ścieżkę przy każdym ponownym zarejestrowaniu. Po zapisie zdjęcia lista jest publikowana atomowo przez podmianę pliku. Numer rewizji chroni równoległe edycje. Starsze pliki zdjęć pozostają na dysku do celów odzyskiwania. Zapisany wynik sesji pozostaje dostępny także po uruchomieniu nowej kalibracji. Przy restarcie niedokończony szkic pozostaje zablokowany do decyzji operatora przy doku. Data i foto kalibracyjne pozostają w lokalnym archiwum, a zwykła ścieżka obserwacji Mock SAP ma własny kontrakt. [API operacji Service](../contracts/http.md#local-storage-location-teaching)
