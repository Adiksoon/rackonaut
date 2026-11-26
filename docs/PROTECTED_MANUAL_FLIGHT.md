# Rackonaut Protected Manual Flight

Tryb ręczny korzysta z kamery drona, pokładowych pomiarów LiDAR-u i lokalizacji LiDAR–IMU. Operator wybiera kierunek ruchu. Mission Manager publikuje prędkość po sprawdzeniu aktualnych pomiarów, strefy lotu i budżetu powrotu. Sesja zajmuje ten sam zasób co automatyczna inspekcja.

## Uruchomienie

```bash
scripts/robotics/build
scripts/robotics/checkpoint live
```

Otwórz [Control Center](http://127.0.0.1:8765/), wybierz **Manual flight** i alejki do zarezerwowania, a następnie **Start and take off**. Safety przygotowuje strefy, a Mission Manager wykonuje pionowy start na 0,72 m. Sterowanie staje się aktywne po wejściu w stan `MANUAL_FLIGHT`.

| Wejście | Działanie |
|---|---|
| `W` / `S` | Przód / tył w układzie drona |
| `A` / `D` | Lewo / prawo w układzie drona |
| `R` / `F` | Wznoszenie / opadanie |
| `Q` / `E` | Obrót w lewo / prawo |
| Przyciski kierunku | Przytrzymaj, aby ruszyć, i zwolnij, aby zatrzymać |
| `Space` lub **Hold position** | Wyzerowanie żądania ruchu |
| **Return and end session** | Zatrzymanie, chroniony powrót i próba fizycznego dokowania |
| **Emergency stop** | Przerwanie lotu i zachowanie rezerwacji do rozstrzygnięcia przez Safety |

Suwak ustawia 20–100% polecenia. Maksima wynoszą 0,40 m/s w poziomie, 0,28 m/s w pionie i 0,40 rad/s dla obrotu. Panel wyświetla żądanie i dopuszczone prędkości oraz powód ograniczenia. Przekazywanie poleceń wymaga aktywnej karty Control Center. Przed zakończeniem sesji użyj **Return and end session**.

Widoki **2D Map**, **3D Model** i **3D Scan** korzystają z dotychczasowych warstw. W **3D Scan** działają filtr wysokości, powiększenie widoku i dostęp do Emergency Stop. Trajektoria oraz zarejestrowane punkty aktualizują się w trakcie lotu.

## Interfejsy i ochrona

- Lokalny `POST /api/manual/start` przyjmuje `aisles` i zwraca identyfikator sesji oraz jej token. Żądania `/api/manual/movement` i `/api/manual/return` używają tego tokenu, numeru sekwencji i czasu wysłania. Publiczny stan sesji pozostaje dostępny pod `GET /api/state`.
- Control Center przekazuje aktualne żądania przez `/rackonaut/manual/request`. Mission Manager weryfikuje identyfikator, kolejność i wiek komunikatu, a następnie używa istniejącego publishera `/rackonaut/drone/cmd_vel`. Rezerwacja jest wspólna ze ścieżką autonomiczną.
- Przeglądarka wysyła heartbeat co 120 ms. Mission Manager niezależnie zeruje prędkość po 550 ms od ostatniego ważnego komunikatu. Utrata fokusu, zwolnienie kontrolki i zamknięcie karty dodatkowo czyszczą żądanie w przeglądarce. Przerwanie komunikacji podczas startu wymaga obsługi przerwanej misji.
- Ochrona wykorzystuje przestrzenną obwiednię z istniejącego Collision Avoidance, sprawdzanie pokrycia wiązkami i drogę hamowania zależną od prędkości i wieku skanu. Dopuszczona prędkość maleje wraz z odległością do przeszkody, obszaru niezaobserwowanego lub granicy korytarza. Zejście przez bramę wymaga aktualnej zgody Safety. Przy obrocie sprawdzana jest cylindryczna obwiednia obejmująca wszystkie kąty drona.
- Po utracie Safety, aktualnej lokalizacji lub danych niezbędnych do lotu Mission Manager zeruje ruch i stosuje istniejący Abort oraz Recovery. Na malejącą rezerwę energii reaguje zatrzymaniem ruchu ręcznego i zweryfikowanym powrotem, o ile budżet go dopuszcza. Normalne zakończenie wymaga stabilnej pozycji i fizycznego kontaktu z dokiem. Safety weryfikuje to niezależnie.

[Kontrakt ROS](../contracts/ros.md#protected-manual-flight)

## Próby w Gazebo Fortress

Próby wykonano 26 listopada 2026 r. na ROS 2 Humble. Sterowanie prowadzono w Chrome i przez lokalny interfejs żądań operatora. Do niezależnej weryfikacji ruchu włączono `localization_diagnostics:=true` i zapisano odometrię referencyjną Gazebo oraz wyjście `cmd_vel`. W trakcie lotu ROS wykazał jednego publishera `cmd_vel`, w węźle `rackonaut_mission`.

| # | Scenariusz | Wynik |
| --- | --- | --- |
| 1 | Start i ręczny lot w wolnej przestrzeni | **PASS.** Rezerwacja D i A, chroniony start, ruch z kamery i klawiatury. |
| 2 | Wszystkie osie i obrót | **PASS.** Niezależna odometria potwierdziła ruch w obu kierunkach trzech osi oraz obrót w obu kierunkach. Przy dojeździe do granicy korytarza odnotowano stan ograniczenia prędkości. |
| 3 | Ściana z przodu | **PASS.** `BLOCKED`. Pozostało 0,141 m względem ochronnej obwiedni drona. |
| 4 | Przeszkoda boczna | **PASS.** `BLOCKED`. Pozostało 0,142 m względem obwiedni. |
| 5 | Przeszkody nad i pod dronem | **PASS.** `BLOCKED` w obu kierunkach, odpowiednio 0,195 i 0,185 m do obwiedni. |
| 6 | Przeszkoda wstawiona podczas wznoszenia | **PASS.** `BRAKING` i `BLOCKED` przy nadal utrzymywanym poleceniu wznoszenia. Minimalny odstęp obwiedni 0,105 m. |
| 7 | Zwolnienie klawisza | **PASS.** Pierwsze polecenie zerowe po 0,102 s w zarejestrowanej próbie wznoszenia. |
| 8 | Odcięcie komunikacji z Chrome podczas wznoszenia | **PASS.** `LINK_LOST`, polecenie zerowe po 0,513 s. Prędkość spadła poniżej 0,055 m/s po dalszych 0,611 s. Safety utrzymał rezerwację. |
| 9 | Utrata pokładowego LiDAR-u | **PASS.** Wstrzymanie mostka w locie dało `FAULT`, `ABORTED` i `RECOVERY_REQUIRED`. Po przywróceniu danych i akceptacji operatora potwierdzono kontakt z dokiem. |
| 10 | Utrata lokalizacji | **PASS.** Wstrzymanie osobnego lokalizatora dało `LOCALIZATION_LOST`, zatrzymanie i `RECOVERY_REQUIRED`. |
| 11 | Pracownik wszedł do zarezerwowanej A | **PASS.** Safety wywołał Abort i utrzymał rezerwację. Od zarejestrowania naruszenia do potwierdzenia Abort minęło 250 ms. |
| 12 | Emergency Stop w locie | **PASS.** `EMERGENCY_STOP` i `ABORTED`, zerowa prędkość zadana, zawis i zachowana rezerwacja. |
| 13 | Bateria poniżej progu startu | **PASS.** Przy 4,819% i progu 12,5% Control Center zwrócił HTTP 409. Dron pozostał w fizycznym kontakcie z dokiem. |
| 14 | Wzrost chmury w ręcznym locie | **PASS.** Mapa wzrosła z 3 630 wokseli po starcie do 6 396 w locie, a po dokowaniu do 6 599. |
| 15 | Start autonomii w trakcie ręcznego lotu | **PASS.** Żądanie z poprawnymi lokalizacjami otrzymało HTTP 409. |
| 16 | Bezpieczne zakończenie | **PASS.** Chroniony powrót, `COMPLETE`, `DOCKED`, fizyczny kontakt i `RELEASED`. |
| 17 | Regresja A-01-01 → A-01-03 | **PASS.** `INS-CONTROL-20261126-104028-58EE27F9` ukończyła oba przystanki, zapisała obie obserwacje i zwolniła strefy po dokowaniu. Wyniki zgodne z próbą GOAL 19. A-01-01 zajęte z nieczytelną etykietą, A-01-03 puste. |

W próbie 6 Gazebo potwierdziło przestawienie płyty o wymiarach 1,57 × 1,57 × 0,26 m nad dronem. Wysokość środka płyty wyniosła 1,417 m. Dron osiągał w tym czasie 0,277 m/s. Pierwsze polecenie zerowe wyszło 0,421 s po potwierdzeniu Gazebo i 0,714 s po wysłaniu polecenia przestawienia. Te znaczniki wyznaczają przedział czasu reakcji dla tej próby. Od pierwszego zera do prędkości poniżej 0,055 m/s dron przeleciał 0,054 m w 0,648 s czasu rzeczywistego, co odpowiadało 0,40 s czasu symulowanego. Największy dalszy wznios wyniósł 0,061 m. Minimalny odstęp 0,105 m wyliczono z rzeczywistej pozycji drona i położenia płyty, przy obwiedni rozciągającej się 0,17 m od środka drona w pionie. Wyniki dotyczą tej konfiguracji symulatora.

Aby powtórzyć próbę dynamiczną, uruchom profil z `localization_diagnostics:=true`, rozpocznij ręczny lot z rezerwacją A i wznoszenie na 100%. Gdy dron osiągnie ok. 0,83 m, przestaw istniejący model `avoidance_shaft_block` do pozycji (−4,7, 10,3, 1,417) m przez usługę Gazebo `/world/rackonaut/set_pose`. Rejestruj odometrię diagnostyczną i wyjście `cmd_vel`. Do powtórzenia prób utraty danych wstrzymaj osobno mostek `rackonaut_lidar_bridge` oraz proces `rackonaut_localization`, a następnie wznów pomiar i uruchom Recovery po sprawdzeniu warunków. Sprawdź blokadę startu przy `battery_initial:=5`.

Uruchomiono 51 testów ROS, 7 testów kontraktu oraz smoke HTTP. Wszystkie przeszły.

## Materiały

- [Ręczny lot i budowanie chmury](manual-flight-evidence/02-manual-command.png)
- [Pełny ekran 3D Scan z filtrem i Emergency Stop](manual-flight-evidence/04-fullscreen.png)
- [Zawis po utracie komunikacji z Chrome](manual-flight-evidence/03-link-drop.png)
- [Rzeczywiste hamowanie i zatrzymanie](manual-flight-evidence/06-braking.png)
- [Fizycznie potwierdzone dokowanie](manual-flight-evidence/05-docked.png)
- [Nagranie Control Center podczas ręcznego lotu z próbami przeszkód, 29 s](manual-flight-evidence/manual-flight.mp4)
- [Wyniki prób, odometria i zgodność z trasą autonomiczną](manual-flight-evidence/verification.json)
- [Próbki odometrii i `cmd_vel` podczas hamowania](manual-flight-evidence/dynamic-stop.jsonl)

## Zakres

- Walidacja dotyczy drona referencyjnego w Gazebo Fortress i ROS 2 Humble. Domyślna konfiguracja Full Robotics używa wirtualnego czujnika obecności pracowników. Ochrona ruchu korzysta z symulowanego pokładowego LiDAR-u.
- Przestrzeń dopuszczona do lotu wynika z geometrii szybu, tuneli i zarezerwowanych alejek. Okluzje, ograniczony zasięg i obszary bez potwierdzonych wiązek mogą ograniczyć ruch. Operator wybiera inny kierunek, gdy sterowanie zostaje zablokowane.
- Używaj Control Center na tym samym hoście. Sesja ręczna ma jednego właściciela i jej token pozostaje w pamięci karty. Po zamknięciu karty dron utrzymuje zawis, dopóki warunki pozwalają, a dotychczasowe procedury bezpieczeństwa pozostają aktywne.
