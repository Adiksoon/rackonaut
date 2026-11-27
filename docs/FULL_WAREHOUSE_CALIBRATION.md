# GOAL 28 — Pełna kalibracja magazynu Rackonaut

**Status roboczy.** Punktem wyjścia jest zaakceptowany wariant `open-aisle` z `dc9813c`. Branch integracyjny osiągnął tę rewizję przez fast-forward. Prace nad kalibracją są na `feature/full-warehouse-calibration`.

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
