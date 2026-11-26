# Service Center i inicjalizacja kalibracji

W profilu Full Robotics operator może przerwać inspekcję jednym kliknięciem **Start Calibration**. Mission Manager zatrzymuje kolejne odczyty, utrzymuje rezerwację i wraca do stacji istniejącą trasą energetyczną. Zarchiwizowany wynik `INTERRUPTED_FOR_CALIBRATION` zawiera przyczynę `CALIBRATION_REQUESTED` oraz dotychczasowe obserwacje. Po fizycznym dokowaniu Safety zwalnia rezerwację, Energy pozwala ładować akumulator, a Control Center udostępnia pusty szkic magazynu.

## Uruchomienie

Wykonaj [Quick Start](../README.md#start-here), a następnie ustaw kod i uruchom Full Robotics z katalogu repozytorium.

```bash
read -rsp 'Kod serwisowy: ' RACKONAUT_SERVICE_CODE
printf '\n'
export RACKONAUT_SERVICE_CODE
scripts/robotics/checkpoint live
```

Otwórz [Control Center](http://127.0.0.1:8765), wybierz **Service**, wpisz kod i naciśnij **Unlock**. Sesja domyślnie działa 15 minut. **Lock Service** odwołuje ją od razu. Pięć nieudanych prób w ciągu minuty czasowo blokuje ponowne odblokowanie. Serwer sprawdza dostęp do poleceń i danych Service przy każdym żądaniu. [Konfiguracja i HTTP](../ros2_ws/src/rackonaut_control/README.md#service-center)

## Przejścia

| Stan | Warunek i działanie |
|---|---|
| `PRODUCTION` | Dyspozycja zwykłych inspekcji zgodnie z dotychczasowymi warunkami. |
| `CALIBRATION_REQUESTED`, `STOPPING_INSPECTION` | Zapis szkicu i blokada nowych dyspozycji oraz kolejnych kalibracji. Przy aktywnej inspekcji Control Center przekazuje żądanie przypisane do bieżącego lotu. |
| `RETURNING_TO_DOCK`, `WAITING_FOR_DOCK` | Mission Manager sam prowadzi drona przy aktywnej rezerwacji i pod nadzorem lokalizacji, LiDAR-u, Obstacle Avoidance oraz Energy. Dron stabilnie stojący w stacji przechodzi bez lotu. |
| `PREPARING_CALIBRATION`, `CALIBRATION_READY` | Fizyczny przełącznik doku, stabilna odometria, świeże sensory i zwolniona rezerwacja pozwalają otworzyć szkic. |
| `CALIBRATION_BLOCKED`, `RECOVERY_REQUIRED` | Brak gotowości albo przerwanie powrotu. Recovery wymaga odrębnej autoryzacji operatora, a awaria w locie utrzymuje rezerwację. |

Wygaśnięcie sesji i **Lock Service** nie zmieniają ruchu. **Emergency stop** pozostaje dostępny z każdego widoku podczas lotu. **Cancel Calibration** odblokowuje produkcję po potwierdzonym dokowaniu. Inspekcja zachowuje stan końcowy, więc kolejny lot wymaga nowej dyspozycji. Restart Control Center blokuje odzyskany szkic do czasu sprawdzenia doku i anulowania przez operatora. [Przepływ ROS](../contracts/ros.md#warehouse-calibration-initialization)

## Workspace i zakres

Warehouse Calibration wyświetla obraz kamery, pozycję, prędkość, poziom baterii i stan kontaktu. Szkic ma własny identyfikator i czas rozpoczęcia, opcjonalną nazwę magazynu, zero lokalizacji i waypointów oraz pustą referencję mapy. Lokalizator produkcyjny nadal korzysta z referencyjnego `localization_map.json`. Krótki Business Demo i profil fixture wyświetlają informację o niedostępnej kalibracji.

GOAL 19 ma do dyspozycji odrębny szkic i zweryfikowany warunek gotowości. Pomiary mapy 3D, teleoperacja, rejestracja miejsc składowania i zapisywanie trasy pozostają niedostępne w tym etapie.

## Próby w Gazebo

Weryfikacja z 26 listopada 2026 r. używała Ubuntu 22.04.5 w WSL2, ROS 2 Humble, Gazebo Fortress 6.16.0, Chrome z Playwright oraz profilu Full Robotics z Mock SAP. Testy D i E używały osobnych instancji symulatora. [Zapis stanów ROS i HTTP](service-center-evidence/verification.json)

| Próba | Wynik |
|---|---|
| A · Dostęp | Błędny kod i bezpośrednie żądania bez sesji zwracały `401`. Poprawny kod odblokował panel, a ręczna blokada unieważniła poprzednią sesję. Pięć błędnych prób wywołało `429` przy kolejnej próbie. Wygaśnięcie sesji w locie nie przerwało powrotu. |
| B · Dron w doku | Fizyczny kontakt i świeże sensory pozwoliły utworzyć pusty szkic bez startu misji. Druga kalibracja i zwykła dyspozycja w trakcie procedury zwracały `409`. |
| C · Aktywna inspekcja | Misja `INS-CONTROL-20261126-091954-648D1A6C` zachowała obserwację A-01-01. Doszło do jednego startu, fizycznego dokowania i rozpoczęcia ładowania. Safety zwolnił strefy A i D, a panel osiągnął `CALIBRATION_READY` po około 122 s od pierwszego odczytu żądania. Próba odbyła się bez restartu Gazebo. |
| D · Przeszkoda | Po rozpoczęciu powrotu wstawiono fizyczny model `shaft_block`. Pokładowy LiDAR wykrył przeszkodę. Obstacle Avoidance wyhamował drona, zgłosił brak przejazdu i zakończył lot jako `ABORTED`. A i D pozostały zarezerwowane. |
| E · Naruszenie strefy | Model pracownika przeszedł do strefy A w trakcie opadania do stacji. Istniejący czujnik obecności oparty na pozycji pracownika w Gazebo zgłosił naruszenie. Lot zakończył się jako `ABORTED`, Safety zatrzymał rezerwację, a Service przeszedł w `RECOVERY_REQUIRED`. |
| F · Anulowanie | Anulowanie w locie, a następnie zablokowanie Service pozwoliły dokończyć powrót. Produkcja została odblokowana po potwierdzeniu fizycznego doku. Przerwana inspekcja zachowała stan końcowy. |
| G · Regresja | W tym samym uruchomieniu Gazebo zwykła misja `INS-CONTROL-20261126-092509-F263176B` wykonała odczyt A-01-01, wylądowała z `COMPLETE` i udostępniła raport HTML oraz porównanie Mock SAP. |

W próbie C zachowano pojedynczą obserwację. W tym przebiegu kamera nie wygenerowała osobnego pakietu zdjęć jakościowych. Kompilacja 10 pakietów ROS, 36 testów modułowych, 7 testów kontraktu API i test dymny API zakończyły się powodzeniem.

## Materiały

- [Zakładka Service](service-center-evidence/01-service-tab.png), [ekran kodu](service-center-evidence/02-service-access.png) i [odblokowany panel](service-center-evidence/03-service-unlocked.png).
- [Rozpoczęcie w trakcie inspekcji](service-center-evidence/04-start-during-inspection.png), [powrót](service-center-evidence/05-autonomous-return.png), [dokowanie](service-center-evidence/06-physical-dock.png) i [Warehouse Calibration](service-center-evidence/07-calibration-workspace.png).
- [Przyspieszony zapis z Chrome](service-center-evidence/calibration-from-active-flight.mp4).
