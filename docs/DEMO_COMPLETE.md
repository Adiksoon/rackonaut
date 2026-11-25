# Rackonaut · demonstrator finałowy

Punktem odniesienia jest tag `demo-complete`. Demonstrator korzysta z drona referencyjnego w Gazebo i rozszerzonego Mock API. Zakres funkcjonalny obejmuje osiem miejsc w A i trzy w B. Alejka C oraz dalsze miejsca na regałach budują scenografię. Wszystkie porównania w tym przebiegu mają status `pending`.

## Uruchomienie

Na Ubuntu 22.04 lub WSL2 z ROS 2 Humble, Gazebo Fortress i pakietami `libignition-msgs8-dev` oraz `libignition-transport11-dev`:

```bash
git clone --branch demo-complete https://github.com/Adiksoon/rackonaut.git rackonaut-demo
cd rackonaut-demo
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
ros2 launch rackonaut_control control.launch.py safety:=true
```

Otwórz [Control Center](http://127.0.0.1:8765). Testowany układ to 1920 × 1080. Poczekaj na drona na polu startowym, dostępny Mock API i aktywny czujnik. Wybierz **Full inventory**, pozostaw włączone **Package quality** i kliknij **Start Inspection**. W bezpiecznym przebiegu pracownik pozostaje poza strefami. Po lądowaniu **View damage photos** prowadzi do zdjęć, **Open HTML Report** otwiera raport, a **Plan reinspection** wybiera miejsca z wynikiem wymagającym sprawdzenia. Każde zlecenie otrzymuje osobny identyfikator.

Próbę naruszenia wykonaj jako osobny przebieg. Po starcie do A odczekaj, aż dron wleci do alejki, następnie wybierz **Warehouse Safety** i **Enter aisle A**. Po zademonstrowaniu alarmu oraz zawisu zatrzymaj cały launcher przez Ctrl+C i uruchom go ponownie, żeby zresetować drona referencyjnego. Dane własnych przebiegów są w `ros2_ws/log/ros/control`. [Procedura bezpieczeństwa](../ros2_ws/src/rackonaut_safety/README.md#presence-and-access)

## Potwierdzone przebiegi

Próby odbyły się 25 listopada 2026 r. na Ubuntu 22.04.5 WSL2, ROS 2 Humble i Gazebo Fortress 6.16.0 z llvmpipe. Obie misje uruchomiono z Control Center w Chrome 158. Dron poruszał się w symulatorze, a raporty powstały z klatek kamery i zdarzeń przyjętych przez API.

| Przebieg | Rezerwacja | Wynik | Raport |
| --- | --- | --- | --- |
| Full inventory · `INS-CONTROL-20261125-105021-9497A0AD` | A, B i korytarz z polem startowym | 180,6 s. 11 odwiedzonych i 11 potwierdzonych miejsc, 0 pominiętych, 3 uszkodzone opakowania, lądowanie i zwolnienie stref. | [HTML](demo-complete/normal/index.html) · [Dane ROS i API](demo-complete/normal/run.json) |
| Plan reinspection · `INS-CONTROL-20261125-105328-71DD2F58` | A i korytarz, z dostępną B | 75,7 s. Dwie nowe obserwacje. A-01-05 nadal miało nieczytelną etykietę, a A-01-07 niepewną zajętość. Lądowanie i zwolnienie stref. Oba raporty dostępne z historii. | [HTML](demo-complete/reinspection/index.html) · [Dane ROS i API](demo-complete/reinspection/run.json) |

Pełna trasa prowadziła z A do B przed regałami. Próbka odometrii w trakcie przejścia wskazywała X = 2,104 m, Y = −2,902 m i Z = 0,787 m. Strefy pozostały zarezerwowane podczas zejścia i zostały zwolnione po potwierdzeniu lądowania. Uszkodzenia z dokumentacją zdjęciową dotyczyły A-01-02, A-01-04 i B-01-01. Tryby wyboru alejki i pojedynczych miejsc, opcjonalna kontrola jakości, mapa, podgląd detekcji, liczniki i raporty korzystają z tego samego stosu. [Telemetria przejścia](demo-complete/telemetry/full-transfer.json) · [Potwierdzenia przy lądowaniu](demo-complete/telemetry/full-landing.json) · [Historia po ponownej inspekcji](demo-complete/reinspection/13-reinspection-history.png)

## Krótki audyt bezpieczeństwa i obsługi

| Próba | Wynik |
| --- | --- |
| Safety Manager niedostępny | Przy dronie na polu żądanie startu otrzymało HTTP 409. W locie watchdog Mission Managera zakończył misję przez Abort. Interfejs zachował informację o ostatniej znanej rezerwacji jako niezweryfikowaną. [Postój](demo-complete/telemetry/manager-offline-at-pad.json) · [Lot](demo-complete/telemetry/manager-offline-in-flight.json) |
| Start po Abort | Dron pozostawał nad polem, rezerwacja utrzymała się po przywróceniu Safety Managera, a kolejny start otrzymał HTTP 409. [Próba ponownego startu](demo-complete/telemetry/restart-after-abort.json) |
| Nieaktualna obecność | Wstrzymanie mostka pozycji dało `STALE` i zablokowało zlecenie. Przywrócenie próbek nie uruchomiło odrzuconej misji. [Wynik](demo-complete/telemetry/stale-presence.json) |
| Brak potwierdzeń świateł | Wersja wyjściowa blokowała start, ale wystawiała `OPEN` na mapie. Po poprawce strefy pokazują `FAULT` i start jest blokowany. [Przed zmianą](demo-complete/telemetry/light-fault-before.json) · [Po zmianie](demo-complete/telemetry/signal-ack-loss.json) |
| Brak potwierdzonego lądowania | W osobnym przebiegu z istniejącym `land:=false` misja osiągnęła `COMPLETE`, a dron zawisł 0,79 m nad polem. System utrzymał rezerwację A i korytarza oraz odrzucił następny start. [Wynik](demo-complete/telemetry/unconfirmed-touchdown.json) |
| Przejście między alejkami | W trakcie całej misji Full Inventory obowiązywała rezerwacja A, B i korytarza. Ponowna inspekcja w A utrzymała dostępność B. [Pełna rezerwacja](demo-complete/telemetry/full-reserved.json) · [Ponowna inspekcja](demo-complete/telemetry/reinspection-reserved.json) |

W Control Center doprecyzowano zakres Full Inventory, dodano bezpośredni odnośnik do zdjęć oraz ostrzegawczy wygląd wyniku po Abort. Sprawdzono w 1920 × 1080 widoczność Start i statusu stref, brak przewijania poziomego, nawigację do zdjęć oraz otwieranie obu raportów z historii. Przeszło 20 testów, smoke kontraktu HTTP i walidacja SDF.

Czujnik bezpieczeństwa wykorzystuje pozycję jednego modelowanego pracownika w znanych strefach. Zawis w trybie odzyskiwania i zachowanie sygnałów dotyczą demonstracji w Gazebo. Wdrożenie fizyczne wymaga osobnej oceny ryzyka, odpowiednich urządzeń i walidacji.

## Materiały do finału

**Normalna misja Full Inventory**

1. [Magazyn i zielone światła](demo-complete/normal/01-warehouse.jpg) · [Wybór 11 miejsc](demo-complete/normal/02-full-inventory.png)
2. [Odliczanie i przygotowanie stref](demo-complete/normal/03-preparation.png) · [Żółte światła w Gazebo](demo-complete/normal/03-amber.jpg) · [Czerwona rezerwacja obu alejek](demo-complete/normal/04-both-aisles-reserved.png) · [Czerwone światła w Gazebo](demo-complete/normal/04-red-both.jpg)
3. [Odczyt palety P003](demo-complete/normal/05-live-pallet-reading.png) · [Przejście korytarzem z A do B](demo-complete/normal/06-cross-aisle-transit.png) · [Inspekcja w B](demo-complete/normal/07-live-aisle-b.png)
4. [Zdjęcia trzech uszkodzeń](demo-complete/normal/10-damage-evidence.png) · [Zejście na pole startowe](demo-complete/normal/08-landing.png) · [Zwolnienie stref](demo-complete/normal/09-full-results.png) · [Zielone światła po lądowaniu](demo-complete/normal/09-green-after-landing.jpg)
5. [Raport HTML](demo-complete/normal/index.html) · [Zrzut raportu](demo-complete/normal/11-full-html-report.png) · [Plan ponownej inspekcji](demo-complete/reinspection/12-plan-reinspection.png) · [Raport ponownej inspekcji](demo-complete/reinspection/index.html)

**Osobna próba naruszenia z GOAL 07**

- [Pracownik w A i alarm w panelu](../ros2_ws/src/rackonaut_safety/docs/evidence/08-intrusion-gazebo-panel.png) · [Przerwana misja i utrzymana rezerwacja na mapie](../ros2_ws/src/rackonaut_safety/docs/evidence/09-intrusion-aborted.png)
- [Istniejące nagranie demonstracji bezpieczeństwa](../ros2_ws/src/rackonaut_safety/docs/evidence/warehouse-safety-demo.mp4) · [Zdarzenia i pomiar czasu reakcji z osobnej próby](../ros2_ws/src/rackonaut_safety/README.md#demonstration-results)

## Scalenie i gotowość zespołu

Na GitHubie otwarty jest [PR #1](https://github.com/Adiksoon/rackonaut/pull/1) z `integration/demo-baseline` (`7b1d190`) do `main` (`ade02aa`). Wspólnym przodkiem PR #1 i linii finałowej jest `demo-baseline` (`6d10e45`). PR #1 zawiera własny commit dokumentacyjny. Kolejne gałęzie tworzą jeden łańcuch zaczynający się od Warehouse, Perception i Mission, dalej Quality Inspection, Demo Readiness, Mission Control, Warehouse Safety i `integration/demo-complete`.

1. Po akceptacji Adriana scalić PR #1 metodą zachowującą wspólne commity. Starszy tag pozostaje punktem niezależnego odtworzenia.
2. Po akceptacji kodu z `integration/demo-complete` otworzyć lub scalić jeden PR tej gałęzi do aktualnego `main`. Przejrzeć wynik względem rzeczywistej bazy, ponowić smoke i lot end-to-end. Kolejne gałęzie funkcji są przodkami finałowej i nie wymagają osobnych merge. W kopii testowej sprawdzono połączenie linii finałowej z dokumentacją PR #1. Tag wskazuje commit faktycznie zweryfikowanego demonstratora.
3. Każdy moduł członka zespołu przyjąć osobnym PR po niezależnym teście kontraktu. Następnie powtórzyć lot z kombinacją przyjętych komponentów na jednym hoście i jednej instancji świata.

W repozytorium i PR-ach sprawdzonych 25 listopada 2026 r. brakuje opublikowanych modułów Michała, Vahida i Tharindu. Poniższe bramki stosujemy po udostępnieniu ich gałęzi lub PR-ów.

| Moduł | Odbiór i integracja |
| --- | --- |
| Michał · dron | Zweryfikować wersję Fortress, licencję, pozycję startową i zachowanie przy zerowej komendzie. Potwierdzić pojedyncze źródło `/clock`, zgodne RGB/CameraInfo, TF, odometrię i body-frame `cmd_vel`. Sprawdzić lądowanie i Abort z interlockiem przed zastąpieniem drona referencyjnego. [Kontrakt ROS](../contracts/ros.md) |
| Vahid · backend | Uzgodnić rozszerzony stan oczekiwany `B-01-01 → P021`, `B-01-02 → P022`, `B-02-01 → null`. Sprawdzić HTTP v1 dla A i B, idempotencję oraz izolację po `inspection_id` na dwóch zachowanych paczkach obserwacji. Podłączyć przez `mock:=false backend_url:=…`. Przejść próbę porównania do jego danych. [Rozszerzenie inwentarza](../test_data/control_inventory_extension.json) · [Kontrakt HTTP](../contracts/http.md) |
| Tharindu · dashboard | Zasilić dashboard podsumowaniami i rozbieżnościami z uzgodnionego backendu dla tych samych `inspection_id`. Sprawdzić oba zakresy, rozróżnienie `pending`, niepewności i miejsc poza zakresem oraz odnośniki do dowodów. Uzgodnić osobny kontrakt zdjęć jakości przed podłączeniem. [Przekazanie danych jakości](../ros2_ws/src/rackonaut_mission/docs/VERIFICATION.md#quality-evidence-handoff) |

Opublikowanie i odbiór tych trzech modułów są warunkiem integracji zespołowej. Demonstrator z modelem referencyjnym i Mock API jest samodzielnie odtwarzalny.
