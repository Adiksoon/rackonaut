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

## Scenariusze

| # | Próba | Obecny stan |
| --- | --- | --- |
| 1 | Pełna trasa shadow | **FAIL.** Trasa fizycznie wykonana, bazowy SLAM przekroczył bramkę i utracił estymaty w tunelu. |
| 2 | Pełna trasa sterowana SLAM | Oczekuje na przejście bramki shadow. |
| 3 | Niezależne powtórzenie pełnej trasy sterowanej SLAM | Oczekuje na przejście bramki shadow. |
| 4 | Powtarzalna geometria regałów | Kontroler referencyjny przeleciał wzdłuż regałów. Brakuje ciągłych estymat bazowego SLAM w tej strefie. |
| 5 | Powrót przez obserwowaną przestrzeń | Kontroler referencyjny wrócił i zadokował. Wymagany jest powrót z aktywnym SLAM. |
| 6 | Zmieniona geometria w alejce | Do wykonania po dopuszczeniu SLAM do pełnej trasy. |
| 7 | Mapa referencyjna fizycznie niedostępna | Do wykonania na pełnej trasie. |
| 8 | Zabezpieczenia w oddaleniu od doku | Do wykonania podczas pełnej trasy sterowanej SLAM. |
| 9 | Regresja produkcyjnej trasy autonomicznej | **PASS w próbie bazowej.** Dwie obserwacje, stan `COMPLETE`, potwierdzony dok i `RELEASED`. |
