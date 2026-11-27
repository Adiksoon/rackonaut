# Rackonaut · Storage Location Teaching

Warehouse Calibration zapisuje miejsca, z których operator chce obejrzeć regał. Operator zatrzymuje drona w chronionym locie i wybiera **Register Storage Location**. Formularz pokazuje przechwycone zdjęcie, proponuje identyfikator odczytany przez istniejący detektor ArUco i pozwala wpisać własny. **Save location** zatwierdza pozę i zdjęcie w bieżącym szkicu. Zapisany punkt oznacza pozycję inspekcyjną drona.

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

Zdjęcie otrzymuje nową ścieżkę przy każdym ponownym zarejestrowaniu. Po zapisie zdjęcia lista jest publikowana atomowo przez podmianę pliku. Numer rewizji chroni równoległe edycje. Starsze pliki zdjęć pozostają na dysku do celów odzyskiwania. Zapisany wynik sesji pozostaje dostępny także po uruchomieniu nowej kalibracji. Przy restarcie niedokończony szkic pozostaje zablokowany do decyzji operatora przy doku. Dane i zdjęcia kalibracyjne pozostają w lokalnym archiwum, a zwykła ścieżka obserwacji Mock SAP ma własny kontrakt. [API operacji Service](../contracts/http.md#local-storage-location-teaching)

## Walidacja w Gazebo i Chrome

Test wykorzystał commit `88e6ee1` na Ubuntu 22.04.5 w WSL2 z ROS 2 Humble, Gazebo Fortress 6.16.0 i OpenCV 4.5.4. Przyciski akwizycji, edycji, potwierdzeń i wyboru markera obsłużył Playwright w Chrome. Skrypt pilotował po zatwierdzonym korytarzu istniejącym chronionym API. Klatki JPEG zweryfikowano bajt w bajt po odtworzeniu surowych obrazów ROS. Pozycje i orientacje porównano z oddzielnym nagraniem odometrii Gazebo, interpolowanym do chwili akwizycji każdego zdjęcia. Odtworzenie z nagranej odometrii SLAM dało te same zapisane pozy. [Telemetria i czasy klatek](storage-location-teaching-evidence/verification.json) · [Graf ROS](storage-location-teaching-evidence/ros-graph.txt)

Lot `INS-CONTROL-20261126-131104-CE011A0B` pokonał **71,08 m** w **362,6 s** rzeczywistych (**203,5 s** symulowanych), zużył **67,76 p.p.** energii i zakończył się stykiem `gazebo_dock_switch` oraz Safety `RELEASED`. Plik `localization_map.json` znajdował się poza katalogiem odczytu od uruchomienia do potwierdzenia doku. Sesja zachowała **56 549 punktów PLY**, **421 próbek trajektorii** oraz dwa zatwierdzone miejsca. [Identyfikator i podsumowanie archiwum](storage-location-teaching-evidence/archived-survey.json) · [Brak pliku referencyjnego w locie](storage-location-teaching-evidence/map-absence.txt)

| Zapis | Czas klatki w Gazebo | Błąd pozycji | Błąd orientacji | Źródło ID |
| --- | ---: | ---: | ---: | --- |
| A-01-01 | 127,500 s | 23,02 mm | 0,125° | Operator |
| A-01-03 | 143,400 s | 29,93 mm | 0,123° | Operator |
| DEMO-NEW-22, wpis próbny | 127,000 s | 24,30 mm | 0,114° | Operator |

W głównym locie operator wprowadził identyfikatory. Detektor zaproponował ID na osobnej klatce testowej z czytelnym znacznikiem. Wpis próbny `DEMO-NEW-22` został utworzony przy rzeczywistym zdjęciu, zmienił ID i po potwierdzeniu został usunięty ze szkicu. Aktywną pozycję A-01-01 zarejestrowano ponownie po wyraźnym potwierdzeniu zastąpienia zdjęcia i pozy. [Wpis testowy przed edycją](storage-location-teaching-evidence/custom-before-edit.json) · [Jego klatka z kamery](storage-location-teaching-evidence/operator-id-test.jpg)

| Przypadek | Dowód |
| --- | --- |
| A · Pusta kalibracja | **PASS.** 0 miejsc i 0 punktów użytkownika przed startem. |
| B · Dwa miejsca | **PASS.** Dwa zapisy zatwierdzone w prawdziwym locie w Gazebo, z klatkami powiązanymi ze znacznikiem odometrii. |
| C · ID spoza katalogu | **PASS.** `DEMO-NEW-22` zapisano z pozą SLAM, źródłem `operator` i zdjęciem z tego samego lotu. |
| D · Aktualizacja | **PASS.** Zmiana ID zachowała rekord, pozycję i zdjęcie. Ponowna rejestracja po potwierdzeniu zachowała identyfikator rekordu i opublikowała nowy obraz. |
| E · Usunięcie | **PASS.** Przycisk usunięcia wymagał potwierdzenia, a wpis zniknął z listy szkicu. |
| F · Ruch i stare dane | **PASS.** Próba podczas rzeczywistego ruchu zwróciła HTTP 409. Test jednostkowy odrzucił starą klatkę i brak otaczających próbek pozy. |
| G · Utrata dostępu lub lokalizacji | **PASS.** W trakcie lotu bez autoryzacji cztery operacje zwróciły HTTP 401. Test bramki odrzucił stan `LOST`. |
| H · Collision Prevention | **PASS.** Przy żądanej prędkości bocznej 0,40 m/s LiDAR wymusił 0,00 m/s przed kartonem. Safety pozostało `RESERVED`. |
| I · Dok i archiwum | **PASS.** Fizyczne dokowanie i cztery typy artefaktów sesji dostępne po zapisie. Odczyt zdjęcia bez Service zwrócił HTTP 401. |
| J · Restart i nowy szkic | **PASS.** Ponowne uruchomienie na kopii tych samych danych zatrzymało niedokończoną pracę w `CALIBRATION_BLOCKED` bez dyspozycji. Po zamknięciu szkicu nowa kalibracja miała 0 miejsc, a wcześniejsze archiwum zachowało 2. |
| K · Zwykła inspekcja Mock SAP | **PASS.** Produkcyjna misja A-01-01 zakończyła się jako `COMPLETE` z fizycznym dokowaniem, zwolnieniem stref i zapisanym raportem. |

Pierwsza próba zwróciła uwagę na sygnał Safety używany wyłącznie do zgody na start. Rejestracja w locie sprawdza teraz aktualną rezerwację, stan wymaganych czujników i potwierdzoną sygnalizację. Pierwsza próba fizycznie wróciła do doku przez istniejący Recovery. Druga próba użyła skorygowanej bramki. Kompilacja 10 pakietów, 58 testów jednostkowych ROS, 7 testów backendu oraz testy dymne ROS i API zakończyły się powodzeniem.

Zwykła inspekcja `INS-CONTROL-20261126-132127-9ABDEF99` trwała **256,2 s**. Przed jej startem baza Mock SAP zawierała **0 obserwacji** po obu kalibracjach. Po inspekcji miała **1 obserwację A-01-01** z wynikiem `unreadable_label`, zgodnie z rzeczywistym odczytem Perception. Po zamknięciu szkicu zwykłym lotem sterował profil referencyjny. [Regresja i licznik obserwacji](storage-location-teaching-evidence/regression-result.json)

## Materiały

- [Pusta lista](storage-location-teaching-evidence/01-empty.png) · [Chroniony lot](storage-location-teaching-evidence/02-calibration-flight.png) · [Formularz rejestracji](storage-location-teaching-evidence/03-register.png) · [Zdjęcie referencyjne](storage-location-teaching-evidence/04-reference.png).
- [Dwa markery na pomiarowej mapie](storage-location-teaching-evidence/05-two-map-markers.png) · [Zdjęcie po kliknięciu markera przy aktywnym filtrze wnętrza](storage-location-teaching-evidence/06-map-selected-photo.png).
- [Dokowanie](storage-location-teaching-evidence/07-docked.png) · [Pliki zapisanej sesji w Service](storage-location-teaching-evidence/08-saved-session.png) · [Pusta kalibracja po restarcie](storage-location-teaching-evidence/09-new-empty-calibration.png).
- [Nagranie obsługi formularza MP4](storage-location-teaching-evidence/teaching-demo.mp4) wykonano w krótkim, oddzielnym locie przy doku. Materiały z A-01-01 i A-01-03 pochodzą z pełnej sesji.
- [Mapa PLY](storage-location-teaching-evidence/mapping/CAL-0E4AA36E84344679B1371C9267F60E61/map.ply) · [Wynik i trajektoria](storage-location-teaching-evidence/mapping/CAL-0E4AA36E84344679B1371C9267F60E61/result.json) · [Lista miejsc i odnośniki do zdjęć](storage-location-teaching-evidence/mapping/CAL-0E4AA36E84344679B1371C9267F60E61/locations.json).

Wynik obejmuje jeden symulowany magazyn i ręczne uczenie pojedynczych widoków. Pozycja zapisu zależy od jakości lokalnego SLAM. Odczyt ArUco wymaga czytelnej, odpowiednio wykadrowanej tabliczki.
