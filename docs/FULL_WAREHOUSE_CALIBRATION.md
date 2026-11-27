# GOAL 28 — Pełna kalibracja magazynu Rackonaut

Kalibracja referencyjnego drona w wariancie `open-aisle` zarejestrowała **11 z 11 miejsc**, **94 194 punkty PLY** i **cztery zatwierdzone pętle od doku do doku**. Wszystkie sektory czterech odlotów sesji końcowej spełniły bramki GOAL 21A. Konfigurację `WH-D11FA03D45502B0ECE140FB6C611E072` odtworzono po pełnym restarcie z pliku archiwum i ułożono plan z czterema odlotami. [Archiwum do odtworzenia](full-warehouse-calibration-evidence/verified-survey/warehouse-configuration.tar.gz) · [Plan po restarcie](full-warehouse-calibration-evidence/verified-survey/restart-plan.json)

Punktem wyjścia był zaakceptowany wariant `open-aisle` z `dc9813c`, dołączony do `integration/full-system` przez fast-forward. Wyniki i implementacja są na `feature/full-warehouse-calibration`.

## Audyt i przewidywany czas

| Mechanizm | Stan przed GOAL 28 | Zakres rozszerzenia |
| --- | --- | --- |
| Warehouse Calibration i Mapping Session | Samo dokowanie zamyka zapis mapy i jednej trasy. | Powrót na ładowanie zapisuje odlot i checkpoint mapy. Następny odlot używa tej samej sesji i układu współrzędnych. Operator kończy kalibrację osobno przy doku. |
| SLAM 16 m | Do 240 klatek, usuwanie najstarszej. Dopasowanie wykorzystuje najwyżej 60 klatek w promieniu 12 m. | Odrębny tryb pełnej kalibracji zachowuje do 480 klatek z priorytetem pokrycia przestrzennego i kotwicą doku. Lokalne dopasowanie, progi, zasięg i układ sensorów zachowują swoje parametry. |
| Mapa PLY | Do 80 000 wokseli na siatce 0,16 m. | Pełny zapis pomiarowy do 160 000 wokseli i licznik odrzuconych prób. Pozostałe profile zachowują dotychczasowe limity. Widok przeglądarkowy otrzymuje do 80 000 punktów, a rekonstrukcja korzysta z pełnych danych. |
| Route Recorder i Route Review | 12 000 próbek po 5 Hz na zapis; jeden graf do 512 punktów. | Osobny dziennik i te same limity dla każdego odlotu. Trasy są zatwierdzane jako zbiór skierowanych pętli od doku do doku i dzielą jeden manifest miejsc. |
| Learned Route, Mission Manager i Energy | Jedna wykonywalna pętla na zlecenie. Pojemność i rezerwa są sprawdzane dla całej pętli. | Plan pokazuje odloty i budżety osobno. Wykonanie pozostaje na poziomie pojedynczej pętli. Kontynuacja kalibracji wymaga kolejnej dyspozycji operatora i nowej rezerwacji Safety. |
| Warehouse Configuration i czytniki | Format 1 z jednym dziennikiem. Czytnik NPZ ograniczał wejście do 40 MB danych nieskompresowanych. | Archiwum wieloetapowe wiąże indeks odlotów, wszystkie dzienniki i model 3D ze skrótami. Czytnik NPZ ma limit 55 MB wynikający z 480 klatek, najwyżej 4700 płaszczyzn na klatkę, XYZ i normalnych float32. Starsze konfiguracje zachowują dotychczasowy format. |

Poprzednia pętla pomiarowa D–A na około 71 m zużyła 66,2 p.p. symulowanego akumulatora. Przelot do B jest dłuższy o około 12 m w obie strony względem trasy do A przy tej samej wysokości i odległości w głąb alejki. Pierwszy szacunek dla całego magazynu to 4–6 odlotów, około 300–500 m sumy zmierzonych lotów i 20–35 min czasu symulacji wraz z ustawianiem kamery. Przy RTF 0,50–0,60 daje to około 35–70 min czasu rzeczywistego plus ładowanie. Próbki z GOAL 21A dawały około 180 klatek i 55 tys. wokseli na pętli D–A. Wspólne odcinki będą obserwowane ponownie, dlatego do pojemności mapy istotna jest liczba różnych pomiarów przestrzeni, a nie suma klatek z osobnych odlotów. [Zmierzone dane porównawcze GOAL 23](ROUTE_TEACHING.md#lot-demonstracyjny) · [Walidacja pełnego zasięgu](SLAM_FULL_ROUTE_VALIDATION.md)

## Metoda odbioru ustalona przed lotem

1. Uruchomić referencyjny model z `warehouse_variant:=open-aisle mapping_only:=true full_route_slam:=true` i pustym katalogiem danych. Niezależna walidacja porównuje pozycje względem odometrii Gazebo z interpolacją czasu. Pilot korzysta wyłącznie z pozy estymowanej, grafu dopuszczalnych korytarzy i obrazu z kamery. Odczytane znaczniki dają ID, a wizyjny obszar półki służy do wyboru kadru.
2. Dla każdej pętli sprawdzić dok, szyb, tunel, bramę, przednią i dalszą część alei. Pokrycie oznacza przejście przez te obszary i pomiar powierzchni regałów z dopuszczalnej przestrzeni, w rozbiciu na odloty i sektory. Strefa C nie zawiera funkcjonalnych miejsc.
3. Dla każdego zapisu sprawdzić ciągłość, dokładność i częstość w sekcjach D, tunel, brama A/B i alejka A/B. Warunki to 30 mm RMSE, 45 mm p95, 60 mm maksimum, 35 mm dryfu po powrocie, 3 Hz z czasu rzeczywistego, RTF co najmniej 0,45. Zgodność ramy między odlotami potwierdzić różnicą błędu doku i pokrywających się odcinków, a także ciągłością jednej mapy.
4. Dopiero po zamknięciu mapy porównać z niezależną geometrią zakres zmierzonych rzędów i niewidocznych powierzchni. Ocena modelu uwzględnia dane rzeczywiste z PLY i klatek kluczowych oraz porównanie z częściową rekonstrukcją GOAL 26B. Nieobserwowane części pozostają bez potwierdzenia.
5. Po zapisie przeładować cały stos, zweryfikować archiwum oraz fizyczny dok, sprawdzić TRACKING, rekonstrukcję, 11 odczytanych miejsc oraz osobne budżety tylko po skierowanych odcinkach z pomiaru.

## Uruchomienie

```bash
scripts/robotics/build
read -rsp 'Kod do panelu Service: ' RACKONAUT_SERVICE_CODE
printf '\n'
export RACKONAUT_SERVICE_CODE
scripts/robotics/checkpoint live warehouse_variant:=open-aisle mapping_only:=true \
  full_route_slam:=true learned_warehouse:=true localization_diagnostics:=true \
  data_dir:="/absolute/path/to/new-survey"
```

W **Service → Warehouse Calibration** wybierz pełną kalibrację. **Return and charge** kończy bieżący odlot przy fizycznym doku. **Continue mapping** ponownie otwiera kontrolowane mapowanie po naładowaniu i sprawdzeniu sensorów. **Finish full calibration** zapisuje główną mapę po potwierdzeniu jedenastu miejsc. Po przejrzeniu i zatwierdzeniu pętli **Save configuration** uruchamia rekonstrukcję z pomiarów i zapisuje model z manifestem.

## Pierwsza sesja próbna

Jedna sesja `CAL-C9FC968659CD435BA192096A97256E17` zebrała po trzecim powrocie 84 402 punkty PLY. Po przejściu z A do B punktowy checkpoint zachował wszystkie 62 508 wcześniejszych komórek. Przyjęto 571 klatek kluczowych. W zachowanych 480 po wyparciu nadmiarowych kadrów było 70 poz w alei A i 29 w B. Licznik odrzuconych wokseli pozostał zerowy. Nowy zasięg mapy obejmuje obie funkcjonalne alejki. [Checkpointy i zakres chmury](full-warehouse-calibration-evidence/checkpoint-coverage.json)

Bramka częstości w próbnej obserwacji A wyniosła 2,9724 Hz, poniżej wymaganych 3 Hz. Po powtórzeniu tej strefy drugi odlot osiągnął 3,2127 Hz w A. Trzeci osiągnął 3,1796 Hz w B, z błędem maksymalnym 19,106 mm w całym odlocie i dryfem 0,32 mm po powrocie. Pozostałe dane z pierwszych trzech lotów są w tabelach pomiarowych. [Wyniki odlotów i stref](full-warehouse-calibration-evidence/flight-metrics.json)

Po trzecim odlocie oryginalne zdjęcia miały A-01-01, B-01-01 i B-02-01. Interfejs pokazał listę brakujących miejsc i stan poprzednich odlotów. W trakcie sesji serwer odrzucił próbę zakończenia kalibracji oraz zwykłe zlecenie inspekcji. Obraz B-02-01 dekoduje znacznik, a użyteczność kadru powierzchni półki pozostaje w ocenie. [Postęp w Chrome](full-warehouse-calibration-evidence/calibration-progress-3.png) · [Blokada niepełnej kalibracji](full-warehouse-calibration-evidence/incomplete-guard.json) · [Niezależny odbiór odometrii Gazebo](full-warehouse-calibration-evidence/validation-topology.txt)

## Przerwany czwarty odlot pierwszej sesji

Pokładowa kamera dostarczyła dwa kolejne oryginalne zdjęcia i odczyty ArUco. Zdjęcie A-01-03 pokazało pustą półkę, a A-01-05 stanowisko z towarem. W sumie zarejestrowano obrazy pięciu miejsc. Niezależne ponowne dekodowanie zachowanych JPEG-ów potwierdziło ich identyfikatory. Ocena zajętości B-02-01 pozostała niepewna. [Zdjęcia, pozy i skróty SHA-256](full-warehouse-calibration-evidence/first-survey/photos.json)

O 09:18:09 UTC lokalizator zgłosił przerwę w danych IMU. Mission Manager przerwał lot, a Safety zachowało rezerwacje D i A. W momencie zatrzymania odnotowano 51,822% energii. Po ponownej ocenie lokalizator odzyskał `TRACKING`, a sygnalizacja potwierdziła rezerwacje. Procedura Recovery miała wówczas do dyspozycji 34,428%, przy prognozowanym koszcie powrotu 31,780% i rezerwie 8%. System utrzymał `RECOVERY_BLOCKED`. Przerwany odlot nie ma fizycznego dokowania ani zatwierdzonej pętli. Zachowano osobno ostatnią zapisaną chmurę z trzeciego odlotu. [Telemetria i warunki Recovery](full-warehouse-calibration-evidence/first-survey/sortie-04-recovery.json) · [Checkpoint PLY](full-warehouse-calibration-evidence/first-survey/checkpoint-03.ply) · [Trajektorie zweryfikowane przed przerwaniem](full-warehouse-calibration-evidence/first-survey/trajectories.png) · [Błędy pozycji](full-warehouse-calibration-evidence/first-survey/slam-error.png) · [Pokładowa kamera, próbkowanie co 2,5 s](full-warehouse-calibration-evidence/first-survey/camera-timelapse.mp4)

Przed zatrzymaniem rejestracja części skanów zajmowała do 171 ms. Odbiór IMU drona referencyjnego i dopasowanie LiDAR korzystały wtedy z jednego wykonawcy ROS 2. W pełnym profilu `open-aisle` oddzielono odbiór IMU przy użyciu mechanizmu z profilu X3. Czas nadejścia wiadomości jest zapisywany przed umieszczeniem jej w kolejce. Od tego czasu są liczone limity wieku próbek. W nowej sesji telemetria z czterech odlotów pokazała `TRACKING` w całym próbkowanym przebiegu.

## Zakończona sesja pomiarowa

Nowa sesja `CAL-40F4227CCAB2440CA0B9D91802A51805` rozpoczęła się z pustą chmurą. Jeden dziennik sesji wiąże cztery odloty i 11 zdjęć. Przebyto 335,11 m w około 29 min 34 s czasu rzeczywistego naliczonego w oknach lotów. Każdy powrót zakończył się po sygnale `gazebo_dock_switch`, a Safety zwolniło obszary. Przed dalszym startem akumulator doładowano do co najmniej 99,5% i uzyskano nową rezerwację. [Dziennik ładowania](full-warehouse-calibration-evidence/verified-survey/charge-cycles.jsonl) · [Dziennik Safety](full-warehouse-calibration-evidence/verified-survey/safety-events.jsonl) · [Postęp i fizyczne dokowanie w Chrome](full-warehouse-calibration-evidence/verified-survey/calibration-progress-11.png)

| Odlot | Obszar i miejsca | Droga | Energia na początku / przy zapisie dokowania | Próg planu z rezerwą 8% | RMSE / p95 / maks. / dryf (mm) | Hz / RTF |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | A, dolne cztery miejsca | 84,00 m | 99,78% / 18,13% | 98,66% | 13,20 / 26,41 / 40,88 / 0,57 | 3,317 / 0,551 |
| 2 | A, trzy górne miejsca | 84,16 m | 99,73% / 16,08% | 99,23% | 12,50 / 23,62 / 35,94 / 0,28 | 3,363 / 0,558 |
| 3 | B, wszystkie trzy miejsca | 86,58 m | 99,60% / 19,48% | 95,09% | 16,17 / 33,67 / 40,91 / 0,18 | 3,364 / 0,558 |
| 4 | A, A-01-08 | 80,36 m | 99,64% / 28,00% | 85,45% | 12,57 / 24,73 / 31,95 / 0,57 | 3,097 / 0,514 |

5 839 sparowanych estymat dało RMSE **13,71 mm**, p95 **26,67 mm** i maksimum **40,91 mm**. Średnio uzyskano **3,289 Hz** i **RTF 0,546**. Najwolniejszym sektorem był szyb D w czwartym odlocie z **3,033 Hz**. Najwyższe sektorowe RMSE wyniosło **28,15 mm** w bramie B. Walidator otrzymywał własny strumień odometrii Gazebo. Odbiorca IMU, źródło sterowania i wydawca poleceń pozostali rozdzieleni przez interfejsy ROS. [Metryki każdego sektora](full-warehouse-calibration-evidence/verified-survey/flight-metrics.json) · [Błąd pozycji](full-warehouse-calibration-evidence/verified-survey/slam-error.png) · [Porównanie trajektorii](full-warehouse-calibration-evidence/verified-survey/trajectories.png) · [Topologia ROS](full-warehouse-calibration-evidence/verified-survey/ros-topology.txt) · [Nagranie z pokładowej kamery, próbki co 2,5 s](full-warehouse-calibration-evidence/verified-survey/camera-timelapse.mp4)

Graf zawiera **496 skierowanych krawędzi**. Ograniczenia obwiedni, ciągłość danych, rezerwacje i prześwit sprawdzono z dzienników i grafu. Dwa odloty zaczynają graf od pierwszej świeżej pozycji po spóźnionej próbce sygnału stanu przed startem, przy fizycznym doku. Walidator zachował wskaźniki do oryginalnego dziennika. Ponowna inspekcja wymaga aktualnego sprawdzenia prześwitu. [Walidacja zatwierdzonych odlotów](full-warehouse-calibration-evidence/verified-survey/route-validation.json) · [Indeks odlotów](full-warehouse-calibration-evidence/verified-survey/sorties.json)

## Pokrycie i wydajność

Checkpointy zawierały kolejno 65 252, 71 076, 93 085 i **94 194** punkty. Chmura obejmuje zakres XYZ od `(-6,963, -12,361, -0,061)` do `(20,752, 12,381, 10,368)` m w ramie `rackonaut_odom`. Skróty stanu i pozycje w rejonie doku wiążą wszystkie odloty w jednej ramie. Każdy kolejny checkpoint zawierał wszystkie różne klucze wokseli odczytane z wcześniejszego PLY. Na granicy siatki zapis float32 może przypisać dwa punkty do jednego klucza. Licznik pomiarów odrzuconych przez limit 160 000 wokseli wyniósł zero.

Widok wykorzystuje do 80 000 rzeczywistych punktów. Z 910 przyjętych klatek kluczowych zapisano 480, w tym 190 z przestrzeni inspekcyjnej A. W opublikowanym NPZ z B pozostała klatka podejścia do bramy oraz zwroty z B widziane z sąsiednich pozycji. Wewnętrzne pozy B zostały wyparte mimo zachowanej chmury B. Wykryto przypadek, w którym brak powtórzonej klatki blisko nowej obserwacji powodował odrzucanie nowego obszaru. Reguła retencji może teraz zwolnić miejsce w gęściej próbkowanym obszarze. Regresję pokrywa test w dwóch rozłącznych regionach. Oryginalne NPZ zawiera pomiary zapisane podczas ukończonej kalibracji.

P95 czasu dopasowania z próbek Control Center wyniosło od 76 do 91 ms. Szczytowe zużycie pamięci wyniosło około 343 MiB dla lokalizatora, 297 MiB dla Control Center wraz z generowaniem modelu i 994 MiB dla Gazebo. Pomiar wykonano na Ubuntu 22.04 w WSL2, ROS 2 Humble i Gazebo Fortress z llvmpipe. [Checkpointy](full-warehouse-calibration-evidence/verified-survey/checkpoint-coverage.json) · [Pamięć procesów](full-warehouse-calibration-evidence/verified-survey/process-memory.txt) · [Plik PLY](full-warehouse-calibration-evidence/verified-survey/map.ply)

## Digital Twin

Rekonstrukcja przed porównaniem z SDF korzystała z obserwowanych płaszczyzn i słupów, pozy drona, parametrów kamery i zdjęć. Słownik ArUco zawiera identyfikatory A i B. Dwa rzędy mają po trzy zmierzone poziomy. W rzędzie zewnętrznym B widać dwa poziomy z zachowanymi pomiarami słupów po obu stronach. Model oznacza go jako częściowo obserwowany i pokazuje tylko wspierany zakres wysokości. Część końców rzędów i rząd scenograficzny pozostały poza zakresem widocznej rekonstrukcji.

| Rząd | Wymiary modelu (m) | Poziomy (m) | Zmierzona długość względem SDF | Przesunięcie środka w poprzek |
| --- | --- | --- | ---: | ---: |
| R01 | 15,19 × 1,18 × 5,55 | 0,429 / 2,475 / 4,520 | 77% | 4,9 cm |
| R02 | 15,73 × 1,17 × 5,54 | 0,420 / 2,467 / 4,514 | 80% | 2,2 cm |
| R03, częściowy | 10,12 × 1,20 × 3,46 | 2,453 / 4,545 | 51% | 7,1 cm |

W porównaniu z GOAL 26B wynik wzrósł z dwóch do trzech poprawnych rzędów, z jednego do dwóch odwzorowanych przebiegów alejek oraz z dwóch do 11 przypisanych stanowisk. Obydwa wcześniej rozpoznane rzędy miały około 9,56 i 9,92 m. Obecnie widać 15,19 i 15,73 m ich zmierzonego przebiegu. Osobne porównanie z SDF nie wykazało fałszywych rzędów. Błąd orientacji to około **0,035°**, odchylenie wykrytych powierzchni półek od najbliższej powierzchni referencyjnej wyniosło do **3,2 cm**, a wszystkie 11 projekcji trafiło we właściwy rząd, w odległości od **1,4 do 9,8 cm** od znaczników odniesienia. Poziom A-01-07 nie miał osobno potwierdzonej krawędzi półki. [Porównanie z SDF i GOAL 26B](full-warehouse-calibration-evidence/verified-survey/twin-validation.json) · [Model 3D](full-warehouse-calibration-evidence/verified-survey/digital-twin.json) · [Rzut chmury z obrysem modelu](full-warehouse-calibration-evidence/verified-survey/cloud-model-top.png)

## Stanowiska

W każdym oryginalnym JPEG-u dekodowanie potwierdziło ID miejsca. Odczyty przyporządkowano do zsynchronizowanych próbek LiDAR–IMU i zmierzonych węzłów trasy. Tabela podaje współrzędne drona, a nie pozycję półki. A-01-07 ma widoczny towar, choć automatyczna ocena zdjęcia zwróciła niepewność. A-01-05 pokazuje towar z nieczytelnym dodatkowym oznaczeniem palety. Oba znaczniki miejsc są czytelne. [Pełne dane, kwaterniony, czasy i SHA-256 JPEG-ów](full-warehouse-calibration-evidence/verified-survey/photos.json)

| Miejsce | Pozycja XYZ (m) | Yaw | Czas kamery (s) | Kadr | Rząd / poziom | Odlot / w planie |
| --- | --- | ---: | ---: | --- | --- | --- |
| A-01-01 | 5,098 · 0,451 · 0,833 | 87,7° | 126,2 | [42 px, towar](full-warehouse-calibration-evidence/verified-survey/photos/A-01-01.jpg) | R02 / 1 | 1 / tak |
| A-01-02 | 5,099 · 0,448 · 2,621 | 88,2° | 398,5 | [42 px, towar](full-warehouse-calibration-evidence/verified-survey/photos/A-01-02.jpg) | R02 / 2 | 2 / tak |
| A-01-03 | 7,961 · 0,449 · 0,803 | 87,8° | 144,5 | [42 px, puste](full-warehouse-calibration-evidence/verified-survey/photos/A-01-03.jpg) | R02 / 1 | 1 / tak |
| A-01-04 | 7,963 · 0,449 · 2,623 | 88,0° | 416,8 | [42 px, towar](full-warehouse-calibration-evidence/verified-survey/photos/A-01-04.jpg) | R02 / 2 | 2 / tak |
| A-01-05 | 10,838 · 0,449 · 0,762 | 87,9° | 163,2 | [42 px, towar](full-warehouse-calibration-evidence/verified-survey/photos/A-01-05.jpg) | R02 / 1 | 1 / tak |
| A-01-06 | 10,839 · 0,449 · 2,624 | 87,8° | 435,3 | [42 px, towar](full-warehouse-calibration-evidence/verified-survey/photos/A-01-06.jpg) | R02 / 2 | 2 / tak |
| A-01-07 | 13,358 · 0,448 · 0,861 | 87,7° | 181,2 | [41 px, automatycznie niepewne](full-warehouse-calibration-evidence/verified-survey/photos/A-01-07.jpg) | R02 / nieokreślony | 1 / tak |
| A-01-08 | 13,479 · 0,450 · 2,622 | 87,9° | 939,4 | [41 px, towar](full-warehouse-calibration-evidence/verified-survey/photos/A-01-08.jpg) | R02 / 2 | 4 / tak |
| B-01-01 | 5,100 · −5,551 · 0,843 | 88,1° | 680,2 | [42 px, towar](full-warehouse-calibration-evidence/verified-survey/photos/B-01-01.jpg) | R01 / 1 | 3 / tak |
| B-01-02 | 5,340 · −5,550 · 2,727 | 90,0° | 690,0 | [41 px, towar](full-warehouse-calibration-evidence/verified-survey/photos/B-01-02.jpg) | R01 / 2 | 3 / tak |
| B-02-01 | 8,192 · −5,550 · 1,041 | 87,8° | 709,4 | [42 px, puste](full-warehouse-calibration-evidence/verified-survey/photos/B-02-01.jpg) | R01 / 1 | 3 / tak |

## Restart i odtworzenie

Zatrzymano procesy Gazebo, ROS, Control Center i Mock SAP. Porty obu usług przestały nasłuchiwać. Na czystym katalogu danych rozpakowano archiwum, uruchomiono cały stos i z aktywnym fizycznym stykiem doku wybrano konfigurację `WH-D11FA03D45502B0ECE140FB6C611E072`. Weryfikacja 25 plików i konfiguracji przeszła. Lokalizator przeszedł do `TRACKING` ze źródłem `learned_map`. W Chrome sprawdzono 11 miejsc, trzy rzędy, chmurę i widok z 496 krawędziami trasy. [Konfiguracja w Chrome](full-warehouse-calibration-evidence/verified-survey/restart-configuration.png) · [Widok z trasą](full-warehouse-calibration-evidence/verified-survey/restart-twin-routes.png) · [Sprawdzenie przeglądarkowe](full-warehouse-calibration-evidence/verified-survey/restart-browser.json) · [Manifest](full-warehouse-calibration-evidence/verified-survey/manifest.json)

Pakiet zawiera surowy katalog `mapping` i odpowiadający mu `warehouse-configurations`. Rozpakuj pakiet do pustego katalogu i podaj go jako `data_dir` w poleceniu uruchomienia. Przy fizycznie zadokowanym dronie otwórz **Service → Warehouse Configuration**, wybierz powyższy identyfikator, sprawdź integralność i aktywuj magazyn. Plan z pełną listą miejsc pokazuje oddzielne budżety każdego odlotu. [Plan 11/11](full-warehouse-calibration-evidence/verified-survey/restart-plan.json)

Pierwsza próba uruchomienia jednej nauczonej pętli zatrzymała się przy doku. Proces misji porównał skrót całego grafu z treścią jednej pętli. Po poprawce dyspozycja przekazuje zatwierdzony graf i numer pętli, a proces misji sprawdza skrót przed wyborem odlotu i walidacją jego stanowisk. [Stan po odrzuceniu pierwszej dyspozycji](full-warehouse-calibration-evidence/verified-survey/restart-first-dispatch.json)

Po poprawce wykonano dwa ograniczone odtworzenia z odtworzonej konfiguracji. Dron wykrył B-02-01 jako puste oraz odczytał P008 w A-01-08. Obie obserwacje przyjął Mock SAP. W obu próbach lokalizacja pochodziła z `learned_map`, wszystkie sektory spełniły bramki GOAL 21A, a fizyczny dok pozwolił zwolnić rezerwacje. Pełna lista 11 miejsc została sprawdzona w planie. Próby w locie obejmowały dwa miejsca.

| Próba | Zapis kamery | Energia na doku | RMSE / p95 / maks. / dryf (mm) | Hz / RTF |
| --- | --- | ---: | ---: | ---: |
| B-02-01 | puste | 24,79% | 16,56 / 33,51 / 41,38 / 0,21 | 3,281 / 0,545 |
| A-01-08 | P008, czytelna etykieta | 32,67% | 13,08 / 26,12 / 36,00 / 0,21 | 3,303 / 0,548 |

W zapisie pomocniczego odczytu HTTP próby A jest 85,7 s przerwy. Niezależny strumień pozycji obejmuje ten odcinek, a największa przerwa między sparowanymi estymatami wyniosła 0,168 s czasu symulacji. Próba ze zmianą jednego bajtu pliku PLY na kopii odrzuciła pakiet w kontroli SHA-256. Końcowy build 11 pakietów oraz 82 testy ROS przeszły. [Odtworzenie A](full-warehouse-calibration-evidence/verified-survey/restart-probe-A-01-08.json) · [Odtworzenie B](full-warehouse-calibration-evidence/verified-survey/restart-probe-B-02-01.json) · [Metryki odtworzeń](full-warehouse-calibration-evidence/verified-survey/restart-replay-metrics.json) · [Próba integralności](full-warehouse-calibration-evidence/verified-survey/integrity-negative-test.json)
