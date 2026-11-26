# Rackonaut · Walidacja SLAM na pełnej trasie

Pierwszy pełny lot shadow ujawnił utratę lokalizacji bazowego SLAM w tunelu. Dotychczasowy lokalizator produkcyjny doprowadził drona do A-01-01 i A-01-03, po czym fizycznie zadokował. Wynik bramki SLAM dla tej próby to **FAIL**.

## Metoda i bramka jakości

Punktem odniesienia jest GOAL 21, commit `222c0d0d90d1bb91a9d6b2acd382dd0cb0e1ade6`. Pełny profil ROS 2 Humble i Gazebo Fortress uruchomiono z diagnostyką, a w oddzielnym węźle tryb `slam_shadow` z wyjściami pod `/rackonaut/slam_shadow/`. Walidator zestawił estymaty ze zinterpolowaną odometrią Gazebo przy znacznikach czasu skanów. Porównanie używa wspólnej ramy znanego doku. Nie stosowano dopasowania trajektorii po locie.

Progi przyjęte przed próbami to **RMSE ≤ 30 mm**, **p95 ≤ 45 mm**, **maksimum ≤ 60 mm**, **dryf po powrocie ≤ 35 mm**, **minimum 3 Hz w czasie rzeczywistym** i **RTF ≥ 0,45**. Korytarze mają roboczą połówkę przekroju 0,33 m wokół zatwierdzonej osi, a ogranicznik ręcznego lotu rezerwuje 0,06 m przy ich granicy. Błąd równy 60 mm może zużyć cały margines granicy. Dlatego ocena obejmuje także dostępność estymat w każdej strefie i rzeczywisty przebieg wewnątrz zatwierdzonej przestrzeni. Zakres rezerwacji i ustawienia Safety, Energy oraz Collision Prevention pozostają takie jak w profilu referencyjnym.

Log pozycji referencyjnej służy wyłącznie ocenie. Kandydat shadow subskrybuje pokładowe skany i IMU. Znane korytarze wyznaczają trasę produkcyjnego kontrolera i podział wyników na strefy.

## Bazowy pełny lot shadow

Lot `INS-CONTROL-20261126-112510-2D7DB5EC` miał **70,78 m** długości według próbkowanej trajektorii Gazebo, maksymalne oddalenie przestrzenne **16,30 m** i zakres wysokości **0,054–6,705 m**. Trwał **267,4 s** czasu rzeczywistego i **157,26 s** czasu symulacji, z **RTF 0,588**. Zużycie wyniosło **55,697 p.p.** energii. Zarejestrowano obie obserwacje, potwierdzono fizyczny kontakt z dokiem i przejście Safety do `RELEASED`.

| Strefa | Próbki SLAM / referencyjne | RMSE | p95 | Maksimum |
| --- | ---: | ---: | ---: | ---: |
| Szyb | 78 / 166 | 3,5 mm | 6,1 mm | 6,5 mm |
| Tunel | 230 / 511 | 122,2 mm | 64,2 mm | 1 619,8 mm |
| Alejka i zejście | 0 / 268 | brak | brak | brak |
| Cała trasa, dla dostępnych estymat | 308 / 945 | 105,7 mm | 53,7 mm | 1 619,8 mm |

Maksymalny błąd orientacji dostępnych estymat wyniósł 2,61°. Najdłuższa przerwa wyniosła 72,04 s czasu symulacji. Średnia dostępność na pełnym locie wyniosła 1,15 estymaty na sekundę czasu rzeczywistego. Dryf przy dokowaniu jest nieweryfikowalny z próby bazowej. Pierwotny stan lokalizatora nie publikował licznika klatek kluczowych. Ground truth pokazuje pełny lot, mimo luk w estymacji kandydata.

![Pełna trasa i błąd bazowego SLAM](slam-full-route-evidence/baseline-shadow.png)

[Telemetria próby](slam-full-route-evidence/baseline-verification.json) · [Estymaty shadow](slam-full-route-evidence/baseline-shadow.jsonl) · [Ślad odniesienia](slam-full-route-evidence/baseline-reference.jsonl)

## Analiza tunelu

Przed przerwą dopasowanie w osi tunelu zaczęło odchylać się od kolejnych obserwacji. Na próbce przy czasie symulowanym 615,196 s błąd przekroczył limit, a przy 618,352 s osiągnął 1,62 m, przede wszystkim w osi Y. Lokalne dopasowania nie dostarczały w tym obszarze wystarczająco stabilnych ograniczeń. Bazowa mapa używała krótkiego zasięgu dopasowania i ograniczonego okna ostatnich klatek. Próby porównawcze odtwarzają pakiety LiDAR i IMU z Gazebo przy zachowaniu czasów odbioru i porównują wynik osobno z zapisem walidacyjnym. [ROS Bag Humble](https://github.com/ros2/rosbag2/tree/humble/rosbag2_py) · [Metryka APE](https://github.com/MichaelGrupp/evo/wiki/Metrics)

Drugi pełny zapis z kontrolerem referencyjnym objął drogę powrotną i dokowanie. W odtworzeniu jego rozszerzona podmapa z korektą prędkości dała 944 estymaty. Uzyskała 34 mm RMSE, 66 mm p95 i 95 mm maksymalnego błędu. Lepsza dostępność estymat pozwala ocenić cały lot, a błędy nadal przekraczają bramkę. Porównania KISS-ICP i small_gicp na pierwszym zapisie również przekroczyły limity. [KISS-ICP](https://github.com/PRBonn/kiss-icp) · [small_gicp](https://github.com/koide3/small_gicp)

## Pełna trasa przez chroniony interfejs ręczny

Lot `INS-CONTROL-20261126-114028-6CDB8441` użył standardowych żądań Manual Flight i zatwierdzonych współrzędnych docelowych. Stan pozycji pochodził z lokalizatora referencyjnego. Dron pokonał **70,70 m**, oddalił się na **16,30 m**, utrzymał rezerwację i zapisał obraz kamerowy przy obu stanowiskach. Zakończenie potwierdził fizyczny styk doku i stan `RELEASED`. Czas wyniósł **329,3 s** przy **RTF 0,576**, a zużycie energii **64,032 p.p.** To sprawdzenie ścieżki sterowania dla przyszłej próby po przejściu bramki shadow. [A-01-01 z kamery](slam-full-route-evidence/reference-a-01-01.jpg) · [A-01-03 z kamery](slam-full-route-evidence/reference-a-01-03.jpg) · [Telemetria](slam-full-route-evidence/reference-manual.json)

## Profil pełnej trasy

Porównanie rzeczywistych zapisów wykazało, że dłuższe pomiary ujawniają odległe płaszczyzny poprzeczne do tunelu. W sześciu kontrolnych klatkach z Gazebo było od 451 do 583 powrotów powyżej 8 m, a największy zmierzony zasięg wyniósł 15,996 m. Profil `full_route_slam:=true` używa 16 m zasięgu w tym samym formacie 192 × 37. Estymator zachowuje do 240 klatek kluczowych i dopasowuje skan do maksymalnie 60 lokalnych klatek z promienia 12 m. W dopasowaniu wagi uwzględniają gęstość próbkowania, kąt padania wiązki i udział płaszczyzn w różnych kierunkach. Używa tych samych bramek obserwowalności i jakości estymaty. Ochrona ruchu nadal korzysta z dotychczasowego horyzontu obserwacji 8 m.

Odtworzenie pełnego zapisu 16 m przez tę implementację dało **944 estymaty** i wyniki **18,6 mm RMSE**, **25,6 mm p95**, **31,8 mm maksimum**, przy 173 zarejestrowanych klatkach kluczowych na końcu lotu. To próba z odtwarzania danych. Niezależna próba shadow na żywo stanowi bramkę dla sterowania.

### Niezależny lot shadow 16 m

Lot `INS-CONTROL-20261126-115445-100F3CAC` przez standardowy interfejs Manual Flight i lokalizację referencyjną pokonał **70,67 m** oraz oddalił się przestrzennie o **16,29 m**. Dron odwiedził oba stanowiska, wrócił przez tunel i zakończył lot potwierdzonym kontaktem oraz `RELEASED`. Zakres wysokości wyniósł **0,054–6,704 m**. Czas lotu to **335,1 s** rzeczywistych i **189,88 s** symulowanych, z **RTF 0,567**. Zużyto **64,198 p.p.** energii.

| Strefa | Próbki | RMSE | p95 | Maksimum |
| --- | ---: | ---: | ---: | ---: |
| Szyb | 225 | 7,3 mm | 11,3 mm | 12,3 mm |
| Tunel | 602 | 22,0 mm | 28,6 mm | 33,6 mm |
| Alejka i zejście | 316 | **33,5 mm** | 41,6 mm | 46,6 mm |
| Cała trasa | 1 143 | 24,0 mm | 37,4 mm | 46,6 mm |

Estymata shadow utrzymała **3,41 Hz** w czasie rzeczywistym. Najdłuższy odstęp wyniósł 0,168 s czasu symulacji, dryf przy doku 2,16 mm, a maksymalny błąd orientacji 0,257°. Estymator przyjął **181 klatek kluczowych** i zarejestrował **55 636 wokseli**. Czas dopasowania skanu wyniósł p95 **125,9 ms**. Z 372 próbek procesu zmierzono medianę **15,56% jednego rdzenia** i p95 **27,78%**. Najwyższe RSS wyniosło **185,35 MiB**. Gazebo w tym samym oknie zajmowało medianę **198,33% jednego rdzenia** i maksymalnie **864 MiB RSS**.

W alejce dominuje utrzymujące się przesunięcie w osi X, średnio −28,3 mm. **Bramka całościowa pozostaje niezaliczona**, ponieważ RMSE w tej strefie przekroczył lokalny próg 30 mm. Sterowanie pozostało na lokalizatorze referencyjnym. [Wykres](slam-full-route-evidence/extended-shadow.png) · [Pomiary](slam-full-route-evidence/extended-shadow-verification.json) · [Trajektorie](slam-full-route-evidence/extended-shadow-trace.jsonl)

## Regresja autonomicznej inspekcji na domyślnym profilu

Lot `INS-CONTROL-20261126-120343-DB9A5E1F` uruchomiono końcowym kodem profilu z domyślnym zasięgiem 8 m. Kontroler referencyjny przeszedł przez szyb, tunel i zejście, zapisał po jednej obserwacji A-01-01 i A-01-03 oraz zakończył w stanie `COMPLETE` z fizycznym kontaktem doku i Safety `RELEASED`. Trajektoria miała **70,76 m**. Lot trwał **290,0 s** z **RTF 0,539** i zużyciem **55,601 p.p.** energii. Wyniki odczytu etykiet zapisano zgodnie z raportem inspekcji. [Telemetria regresji](slam-full-route-evidence/default-autonomy-regression.json)

## Scenariusze

| # | Próba | Obecny stan |
| --- | --- | --- |
| 1 | Pełna trasa shadow | **FAIL.** Bazowy SLAM utracił estymaty w tunelu. Profil 16 m dał ciągłą estymatę na całej trasie, lecz przekroczył próg RMSE w alejce. |
| 2 | Pełna trasa sterowana SLAM | Oczekuje na przejście bramki shadow. |
| 3 | Niezależne powtórzenie pełnej trasy sterowanej SLAM | Oczekuje na przejście bramki shadow. |
| 4 | Powtarzalna geometria regałów | W shadow 16 m uzyskano 316 estymat w alejce. Lokalny RMSE wyniósł 33,5 mm przy progu 30 mm. |
| 5 | Powrót przez obserwowaną przestrzeń | Kontroler referencyjny wrócił i zadokował. Wymagany jest powrót z aktywnym SLAM. |
| 6 | Zmieniona geometria w alejce | Do wykonania po dopuszczeniu SLAM do pełnej trasy. |
| 7 | Mapa referencyjna fizycznie niedostępna | Do wykonania na pełnej trasie. |
| 8 | Zabezpieczenia w oddaleniu od doku | Do wykonania podczas pełnej trasy sterowanej SLAM. |
| 9 | Regresja produkcyjnej trasy autonomicznej | **PASS na domyślnym profilu po zmianach.** Dwie obserwacje, stan `COMPLETE`, potwierdzony dok i `RELEASED`. |
