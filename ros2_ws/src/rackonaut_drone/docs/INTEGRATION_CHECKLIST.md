# Odbiór X3 z kontrolerem misji Rackonaut

Dwie odrębne próby w Gazebo. Najpierw dron referencyjny jako punkt odniesienia. Po przeglądzie PR #7 te same kroki z X3 w jednej konfiguracji porównawczej. [PR modułu X3](https://github.com/Adiksoon/rackonaut/pull/7)

## Konfiguracja próby

- Zapisz SHA kodu, rewizję modelu, wersje Ubuntu, ROS i Gazebo, profil świata i API oraz identyfikator każdej inspekcji. W finalnym porównaniu uruchom oba modele na tej samej rewizji stosu, z tym samym światem, Mock API, profilem bezpieczeństwa i ustawieniami renderowania.
- Daj próbie osobną domenę ROS, partycję Gazebo, porty i katalog wyników. Uruchom po jednym modelu i po jednym źródle `/clock`, odometrii, obrazu, transformacji oraz poleceń ruchu. W trybie misji jedynym nadawcą publicznego `/rackonaut/drone/cmd_vel` jest Mission Manager. Przy X3 jego polecenia przechodzą przez przekaźnik do prywatnego wejścia kontrolera X3. Sprawdź również drogę sygnału Abort od Safety Managera do Mission Managera.
- Dron stoi na padzie. Poczekaj, aż obraz, odometria, API, odczyt obecności i potwierdzenia sygnałów będą jednocześnie gotowe przez kilka sekund. Dla X3 sprawdź rozpoznanie pola startowego i tolerancji przyziemienia z jego odometrią przed wydaniem pierwszej komendy lotu.

Uruchomienie referencji w odizolowanej kopii tagu `demo-complete`:

```bash
export RACKONAUT_ROS_DOMAIN_ID=70
export RACKONAUT_GZ_PARTITION=rackonaut-x3-reference-acceptance
source scripts/robotics/activate.bash
LP_NUM_THREADS=4 ros2 launch rackonaut_control control.launch.py \
  safety:=true http_port:=18765 mock_port:=18000 \
  data_dir:="$PWD/ros2_ws/log/integration-trial-a"
```

W drugim uruchomieniu użyj osobnego katalogu `integration-trial-b`, domeny ROS 71 i partycji `rackonaut-x3-reference-intrusion`. Panel jest na [porcie 18765](http://127.0.0.1:18765/). Szczegóły przygotowania tagu są w [opisie demonstratora](../../../../docs/DEMO_COMPLETE.md).

## A · Jeden punkt, lądowanie i raport

1. Wybierz pojedynczą lokalizację `A-01-01`, wyłącz kontrolę jakości opakowania, pozostaw wirtualnego pracownika poza strefami i uruchom inspekcję.
2. Obserwuj postęp, obraz oraz rezerwację A i korytarza T. Potwierdź, że co najmniej jedna obserwacja z kamery dotarła do API dla tej misji i poprawnej lokalizacji.
3. Odbiór wymaga `COMPLETE`, potwierdzenia **1/1**, `landed=true`, `at_pad=true`, wydania raportu dla właściwego identyfikatora oraz zwolnienia stref. Otwórz HTML i zapisz końcowy stan oraz obserwację. Zatrzymaj launcher.

## B · Naruszenie strefy i Abort

1. Uruchom świeżą instancję i powtórz ten sam zakres lotu. Gdy dron znajdzie się w powietrzu wewnątrz zarezerwowanej strefy A, użyj **Warehouse Safety → Enter aisle A**. To polecenie porusza wyłącznie wirtualnym pracownikiem w Gazebo. Zapisz pozycję i stan strefy przy wyzwoleniu.
2. Odbiór wymaga alarmu `intrusion` dla A, stanu `ABORTED`, fazy Safety `RECOVERY` i powodu zatrzymania w panelu. Dron ma wyhamować i pozostać w zawisie. Rezerwacja A i T pozostaje aktywna, zezwolenie na lot jest wycofane, a nowy start podczas zawisu zwraca HTTP 409.
3. W odizolowanej próbie porównawczej zmierz pozycje przez trzy sekundy od pierwszej pełnej sekundy po wykryciu `ABORTED`. Do porównania przyjmij maksymalnie 0,25 m przemieszczenia poziomego i 0,15 m pionowego względem pierwszej próbki z tego okna. Zapisz próbki, zdarzenie Safety, komunikat w UI oraz wynik próby ponownego startu. Przy niepowodzeniu zapisz pierwsze odchylenie i przerwij próbę w symulatorze.

## Wyniki referencyjne

Testy z 26 listopada 2026 r. wykonano na Ubuntu 22.04.5 WSL2, ROS 2 Humble, Fortress 6.18.0 i Pythonie 3.10.12, na tagu `demo-complete` (`cc8f742`). Dwa loty odbyły się w oddzielnych sesjach z włączonym Safety i z Mock API.

| Scenariusz | Wynik |
| --- | --- |
| A · `INS-CONTROL-20261126-094924-2F2FA923` | **1/1**, odczyt `A-01-01 → P001`, **48,7 s**, lądowanie na padzie, zwolnione strefy, raport HTML z HTTP 200. |
| B · `INS-CONTROL-20261126-095110-8E152250` | Wykryte naruszenie A i T, `ABORTED` w **1,48 s** od polecenia ruchu pracownika, `RECOVERY`, utrzymana rezerwacja, ponowny start zablokowany HTTP 409. W 17 próbkach przez 3,04 s odchylenie wyniosło **0,003 m poziomo** i **0,001 m pionowo**. |

Control Center pokazał **Safety alert · Intrusion detected** i zdarzenia **Abort dispatched** oraz **Abort confirmed**. Pole `mission.status.detail` miało ogólny tekst „Stopped by the operator”. Przy porównaniu przyczyny Abort odczytać także alarm i historię Safety.

Pierwsza próba startu zakończyła się komunikatem „Drone odometry is stale or unknown.” Powtórzenie po trzech sekundach ciągłej gotowości zakończyło się poprawnie. Próba B w tej samej domenie dostała HTTP 409 przed utworzeniem misji. Po zamknięciu launchera wykryto pozostałe procesy wcześniejszej misji. Próba B przeszła w nowej domenie i partycji Gazebo. Zidentyfikowane procesy testowe zatrzymano.

[Wyniki i próbki telemetrii](evidence/x3-reference-acceptance.json)

## Porównanie X3 i drona referencyjnego na tym samym stosie

Cztery loty z 26 listopada 2026 r. używały tego samego kodu Control Center, Mission i Safety z `6e04fcf`, świata `safety_showcase.sdf`, wirtualnego czujnika obecności i profilu `fixture`. X3 używał modułu z `ddf0db2`. Próby odbyły się w osobnych domenach ROS 72–75 i partycjach Gazebo. Lokalny launcher testowy podstawiał proces X3 w miejsce procesu referencyjnego. Parametry Safety, tematy ROS i konfiguracja demonstratora pozostały zgodne z bazą.

| Model | Jeden punkt | Naruszenie strefy i Abort |
| --- | --- | --- |
| Dron referencyjny | `INS-CONTROL-20261126-102936-DC1E305E`, 1/1, lądowanie, raport, 49,2 s | `INS-CONTROL-20261126-103040-0CA0A218`, Abort po 1,29 s, zawis 0,003 m poziomo / 0,000 m pionowo, HTTP 409 |
| X3 UAV v4 | `INS-CONTROL-20261126-102710-4073AEDB`, 1/1, lądowanie, raport, 63,0 s | `INS-CONTROL-20261126-102829-92149FF6`, Abort po 1,28 s, zawis 0,015 m poziomo / 0,002 m pionowo, HTTP 409 |

Oba modele uzyskały odczyt `A-01-01 → P001`, po lądowaniu zwolniły rezerwację i wygenerowały raport HTML z HTTP 200. Po Abort oba pozostały w zawisie z aktywnym `RECOVERY`, utrzymaną rezerwacją A i T oraz zablokowanym startem. Czasy Abort w tabeli są liczone od polecenia ruchu wirtualnego pracownika do pierwszego odczytu `ABORTED` w panelowym API. Są to pojedyncze przebiegi każdego scenariusza.

Dla X3 Safety zarejestrował **Abort confirmed** 0,251 s po wykryciu naruszenia. Panel pokazał **Safety alert · Intrusion detected**. Podsumowanie misji miało ogólny komunikat **Stopped by the operator**, tak jak w próbie referencyjnej. Przyczynę odczytać z alarmu Safety.

Kontrola regresji na tym samym buildzie przeszła **7 testów kontraktu i Mock SAP** oraz **19 testów Control, Mission i Perception**. [Wyniki, identyfikatory i zdarzenia Safety](evidence/x3-mission-validation.json)
