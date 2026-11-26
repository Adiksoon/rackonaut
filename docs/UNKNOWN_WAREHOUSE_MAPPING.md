# Rackonaut · Mapowanie nieznanego magazynu

Warehouse Calibration tworzy odrębną sesję SLAM. Operator wykonuje chroniony lot ręczny, obserwuje przyrost zmierzonej chmury i pobiera wynik po fizycznym dokowaniu. Zapis zawiera punkty PLY oraz estymowaną trajektorię w ramie `rackonaut_odom`.

## Uruchomienie

```bash
scripts/robotics/build
read -rs RACKONAUT_SERVICE_CODE
export RACKONAUT_SERVICE_CODE
scripts/robotics/checkpoint live mapping_only:=true
```

W osobnym terminalu lub w Chrome otwórz [Control Center](http://127.0.0.1:8765/). Wybierz **Service**, odblokuj panel podanym kodem, kliknij **Start Calibration**, a po potwierdzeniu doku i stanu **Calibration ready** przejdź do **Open mapping flight**. Widok Measured 3D Scan powinien pokazać identyfikator sesji, `SLAM · Tracking` i zero zarejestrowanych punktów. Wybierz zakres rezerwacji i **Start mapping flight**.

W czasie lotu używaj kontrolek GOAL 20. Przyciski **Return and end session** oraz **Emergency stop** korzystają z istniejących mechanizmów. Po kontakcie z dokiem i zwolnieniu rezerwacji panel Service udostępnia PLY i JSON. Zamknięcie kalibracji zachowuje zapis w katalogu danych, pod `mapping/<identyfikator>/`. Standardowy profil Full Robotics umożliwia rozpoczęcie kalibracji z produkcji i wznowienie dotychczasowej pracy po zamknięciu sesji.

## Audyt i wybór technologii

| Element | Zależność i rola |
| --- | --- |
| GOAL 15 | Produkcyjny lokalizator rejestruje skany do punktów i normalnych z `localization_map.json`. Znany dok podaje przybliżoną pozycję i orientację początkową. Predykcja wykorzystuje prędkość kątową i przyspieszenie właściwe z IMU. |
| GOAL 18 | Service zarządza dostępem i szkicem kalibracji oraz niezależnie czeka na stabilne położenie, fizyczny styk doku, sprawne sensory i zwolnienie rezerwacji przez Safety. |
| GOAL 19 i 19A | Renderer pokazuje zmierzoną chmurę, trajektorię, aktualność i jakość dopasowania. W trybie kalibracji widok lotu otwiera zmierzoną mapę z identyfikatorem sesji. |
| GOAL 20 | Mission Manager publikuje `cmd_vel` i ogranicza ruch na podstawie skanów, obwiedni, aktualności estymaty, Safety i Energy. Graf korytarzy, bramy i pozycja doku wyznaczają dopuszczalny obszar oraz drogę powrotu. |
| Safety i Energy | Safety zarządza rezerwacją, sygnałami i Recovery. Energia modeluje pobór i budżet powrotu. Potwierdzenie lądowania wykorzystuje rzeczywisty symulowany przełącznik kontaktowy. Domyślny nadzór obecności pracownika pozostaje wirtualną funkcją dotychczasowego Safety Managera. |

Gazebo Fortress publikuje uporządkowany `PointCloud2` 192 × 37 z koordynatami XYZ i czasem dla całej klatki, nominalnie 6 Hz. LiDAR ma pełny zakres azymutu i elewację ±88°. IMU dostarcza prędkość kątową i przyspieszenie nominalnie 50 Hz. Oba strumienie używają wspólnego czasu symulacji. Estymator używa kalibracji postoju oraz znanego przesunięcia LiDAR-u 0,09 m w osi Z.

| Rozwiązanie | Ocena w projekcie |
| --- | --- |
| KISS-ICP | Ma ścieżkę ROS 2 i lokalną odometrię LiDAR. Do wspólnej diagnozy IMU, bramek jakości i predykcji dla sterowania potrzebna byłaby dodatkowa integracja. [KISS-ICP](https://github.com/PRBonn/kiss-icp) |
| LIO-SAM | Opublikowano obsługę Humble. Ścieżka deskew oczekuje czasów pojedynczych punktów oraz numerów pierścieni lidaru mechanicznego. Pole czasu całej klatki i uporządkowana siatka symulatora wymagają osobnego adaptera i walidacji. [LIO-SAM ROS 2](https://github.com/TixiaoShan/LIO-SAM/tree/ros2) |
| FAST-LIO ROS 2 | Ścisła fuzja LiDAR–IMU i przyrostowa podmapa. Port poleca Humble, korzysta z zależności Livox i opisuje znaczenie czasu każdego punktu dla deskew. Koszt integracji wynika z dostosowania wejścia do pełnych klatek Fortress. [FAST-LIO ROS 2](https://github.com/Ericsii/FAST_LIO_ROS2) |
| small_gicp | Implementuje wydajne dopasowanie scan-to-map i jest kandydatem do dalszego profilowania. Fuzja, bramki jakości i praca z ramą projektu nadal pozostałyby po stronie Rackonaut. [small_gicp](https://github.com/koide3/small_gicp) |
| Rozwiązanie przyjęte | Wspólny solver point-to-plane ICP i istniejąca fuzja IMU z podmapą klatek LiDAR. Zachowuje format wejściowy i systemowe NumPy/SciPy. Ocenę oparto na niezależnej próbie shadow i bezpośredniej próbie sterowania. |

## Estymacja i granica zaufania

SLAM rozpoczyna od klatki LiDAR zarejestrowanej przy potwierdzonym doku. Z sąsiedztw pomiarowych wyznacza lokalne płaszczyzny. IMU przewiduje stan na moment kolejnego skanu, a dopasowanie do podmapy koryguje pozycję i orientację. Po spełnieniu bramek pokrycia, reszty dopasowania i obserwowalności estymator dopuszcza klatkę do akumulacji. Podmapa utrzymuje do 14 klatek kluczowych, z których wybiera obserwacje lokalne. Do widoku trafiają pozycje z własnych pomiarów, z ograniczeniem do jednego reprezentanta w wokselu 0,16 m.

Skan inicjalizacyjny buduje wewnętrzną podmapę do estymacji. Wynik użytkownika pozostaje pusty do rozpoczęcia rejestracji. W profilu `mapping_only:=true` nawet gotowość przy doku korzysta ze skanów i IMU. W standardowym profilu stan mapy produkcyjnej pozostaje osobnym obiektem. Strumienie map są oddzielne, a identyfikator i znacznik czasu blokują pakiety z poprzedniej sesji. Eksport zamraża dane po weryfikacji kontaktu i zwolnieniu rezerwacji.

Mission Manager sprawdza identyfikator i stan bieżącej sesji lokalizacji oraz nadal jest jedynym właścicielem `cmd_vel`. Bezpieczeństwo lotu wykorzystuje zatwierdzony model korytarzy i aktualny pokładowy LiDAR. Dane walidacyjne z Gazebo są przekazywane oddzielnie do `rackonaut_localization_validation`. Estymator i mapa używają pomiarów pokładowych oraz punktu startowego w doku.

Przed próbą ze sterowaniem przyjęto **RMSE ≤ 0,030 m**, **p95 ≤ 0,045 m**, **maksimum ≤ 0,060 m**, **dryf zamknięcia ≤ 0,035 m**, co najmniej **3 Hz** skorygowanych estymat w czasie rzeczywistym oraz **RTF ≥ 0,45** w nominalnym przebiegu. Progi błędu odniesiono do 0,06 m marginesu hamowania przy granicy korytarza i zmierzonego w GOAL 20 minimalnego odstępu 0,105 m od obwiedni. Pomiary odnoszą się do sprawdzonego zakresu lotu.

## Walidacja na żywo

Próby wykonano w Gazebo Fortress z ROS 2 Humble, WSL2 i renderowaniem programowym. W próbie shadow dotychczasowy lokalizator sterował dronem, a SLAM publikował estymatę do osobnego walidatora. Błąd policzono przez interpolację odometrii Gazebo do znaczników czasu LiDAR-u w uzgodnionej ramie doku. Nie stosowano dodatkowego dopasowania trajektorii. Dryf zamknięcia to różnica wektorów błędu na początku i końcu w rejonie doku.

| Próba | Próbki | RMSE | p95 | Maks. | Dryf przy doku |
| --- | ---: | ---: | ---: | ---: | ---: |
| Shadow, próbki w locie | 98 | 3,0 mm | 4,3 mm | 5,5 mm | — |
| Referencyjna hala, lot sterowany przez SLAM | 146 | 3,4 mm | 4,6 mm | 10,9 mm | 1,3 mm |
| Zmieniona geometria obok szybu | 80 | 4,0 mm | 5,6 mm | 7,3 mm | 1,1 mm |
| Start bez mapy referencyjnej i automatyczny powrót | 135 | 4,0 mm | 4,9 mm | 10,5 mm | 1,1 mm |
| Ponowna obserwacja szybu | 130 | 3,7 mm | 4,9 mm | 6,6 mm | 2,1 mm |

W głównej sesji mediana wyniosła **3,62 Hz** skorygowanych estymat w czasie rzeczywistym, **6,03 Hz** w czasie symulacji i **RTF 0,60** obliczone z ich ilorazu. Obliczenie dopasowania zajmowało p95 **10,65 ms** w próbkach stanu zebranych podczas lotu. Lokalizator w standardowym profilu podczas prób kalibracji zużywał medianę **12,3% jednego rdzenia**, p95 **13,6%**, z próbkowanym szczytem **198,4 MiB RSS**. Profil wyłącznie do mapowania uzyskał **9,85%**, **12,29%** i **79,9 MiB RSS**. Próbki zasobów procesu odczytywano z `/proc` co około 0,8 s. Przejściowo pracowały dwa izolowane stosy walidacyjne, a wyniki posegregowano według PID.

| # | Scenariusz | Wynik |
| --- | --- | --- |
| 1 | Pusta mapa sesji | **PASS.** Osobny identyfikator, zero punktów w HUD i HTTP 204. Kolejna sesja wystartowała od zera, pierwszy wynik nadal był dostępny. |
| 2 | Lokalizacja bez przygotowanej mapy | **PASS.** Start profilu `mapping_only`, lot i potwierdzone dokowanie przy fizycznie nieobecnym `localization_map.json` w instalacji. [Dowód próby](unknown-mapping-evidence/no-reference-proof.txt) |
| 3 | Akumulacja w ręcznym locie | **PASS.** Rozwój chmury od 0 do 6 317 wokseli w głównej sesji. |
| 4 | Ruch poziomy, pionowy i obrót | **PASS.** Klawiatura i aktywna estymata w obu osiach poziomych, podczas wznoszenia, opadania i obrotów. Zakres niezależnej odometrii Z w głównej próbie wyniósł 0,054–0,868 m, a w próbie powtórzenia dron dwa razy osiągnął ok. 1,04 m. |
| 5 | Powrót przez obserwowany obszar | **PASS.** Ponowne przejście przez ten sam odcinek szybu, zachowana rama lokalizacji i zweryfikowany kontakt z dokiem. |
| 6 | Dryf i błąd | **PASS.** W głównej próbie wszystkie progi błędu i dryfu zostały spełnione, jak w tabeli pomiarów. |
| 7 | Zgodność ponownego skanu | **PASS.** Dwa oddzielne skany po opuszczeniu i ponownym osiągnięciu wysokości 1,04 m, po 6 270 punktów. Dwukierunkowa mediana najbliższego sąsiada wyniosła 2 mm, p95 9 mm i 99,82% punktów w odległości poniżej 5 cm. Najdalsze pojedyncze dopasowanie wyniosło 0,299 m. |
| 8 | Zmieniona geometria | **PASS.** Przesunięto obiekt Gazebo przed inicjalizacją. Dla znanej walidacyjnie płaszczyzny X = −4,09 m w zadanym wycinku mapa zawierała 74 punkty z medianą X = −4,0912 m. Odpowiadający wycinek głównej mapy miał zero punktów. |
| 9 | Utrata LiDAR-u i IMU | **PASS.** W osobnych lotach wstrzymano mostek LiDAR i mostek IMU. Lokalne stany `LOST` dały odpowiednio brak aktualnego dopasowania i brak aktualnego IMU. Mission Manager przerwał lot i zachował rezerwację do Recovery. |
| 10 | Utrata estymaty | **PASS.** Wstrzymano lokalizator przy działających źródłach sensorowych. Mission Manager zgłosił `LOCALIZATION_LOST` i dopuścił powrót po przywróceniu estymacji oraz akceptacji Recovery. |
| 11 | Collision Prevention | **PASS.** Przy żądaniu lotu ku przesuniętemu obiektowi prędkość dopuszczona wyniosła zero i pojawił się `BLOCKED`. Estymator pozostał w `TRACKING`. |
| 12 | Emergency Stop i utrata komunikacji | **PASS.** Emergency Stop wywołał `ABORTED` z zachowaniem stref. Odcięcie żądań Chrome podczas ruchu wywołało `LINK_LOST` i wyzerowało ruch zadany. |
| 13 | Malejąca energia w locie | **PASS.** Start z początkowym poziomem 15,0%. Automatyczny `ENERGY_RETURN` przy 10,74%, zweryfikowane dokowanie i zapis 4 361 wokseli. |
| 14 | Bezpieczne zakończenie | **PASS.** `COMPLETE` i `RELEASED` po fizycznym kontakcie. PLY i JSON z trajektorią pobrano z Service, a konfiguracja produkcyjna wróciła po zamknięciu sesji. |
| 15 | Autonomiczna regresja | **PASS.** `INS-CONTROL-20261126-111243-CA57E000`, trasa A-01-01 → A-01-03, dwie zapisane obserwacje, fizyczny kontakt doku, `RELEASED`. Wynik zgodny z GOAL 20. |

Przeszły 52 testy ROS, 7 testów kontraktu i smoke HTTP. Moduły JavaScript przeszły sprawdzenie składni.

## Materiały

- [Pusta sesja po kalibracji](unknown-mapping-evidence/01-empty-map.png) · [Chmura podczas lotu](unknown-mapping-evidence/02-mapping-flight.png) · [Watchdog w zawisie](unknown-mapping-evidence/03-watchdog.png) · [Wynik po dokowaniu](unknown-mapping-evidence/04-result.png)
- [Nagranie rzeczywistej sesji w Gazebo, 42 s](unknown-mapping-evidence/mapping-flight.mp4) · [Mapa PLY](unknown-mapping-evidence/map.ply) · [Wynik i trajektoria](unknown-mapping-evidence/result.json)
- [Porównanie odometrii w ramie doku](unknown-mapping-evidence/trajectory-comparison.png) · [Zsynchronizowane próbki](unknown-mapping-evidence/trajectory-comparison.jsonl) · [Wyniki prób](unknown-mapping-evidence/verification.json)
- [Pierwszy niezależny skan](unknown-mapping-evidence/revisit-first.xyz32) · [Drugi niezależny skan](unknown-mapping-evidence/revisit-second.xyz32). Format to trzy wartości float32 little-endian na próbkę. [Mapa zmienionej sceny](unknown-mapping-evidence/changed-geometry.ply)
- [Graf walidacyjny ROS](unknown-mapping-evidence/ros-validation-boundary.txt) pokazuje mostek i walidator jako uczestników topicu ground truth. Lokalizator subskrybuje pomiary pokładowe, komendy sesji i stan doku.

## Ograniczenia

- Estymacja jest przyrostowa i lokalna. Globalna relokalizacja, korekta pętli oraz ponowne użycie wyeksportowanej mapy w sterowaniu pozostają poza zakresem.
- Wyniki walidacji obejmują chroniony rejon doku i szybu, w tym zmodyfikowaną geometrię w jego sąsiedztwie. Powtarzalne regały, zasłonięcia, uboga geometria i dłuższe trasy mogą zwiększyć dryf lub zatrzymać lot.
- Układ mapy zakłada położenie i orientację startową z instalacji doku. Obwiednie, strefy i trasy powrotu nadal wymagają osobnej konfiguracji bezpieczeństwa.
