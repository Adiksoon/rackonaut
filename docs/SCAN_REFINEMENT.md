# GOAL 19A · Czytelność widoku 3D Scan

Otwórz **Live flight → 3D Scan** w [Control Center](http://127.0.0.1:8765) uruchomionym w profilu Full Robotics. Na szerokim ekranie kamera i informacje o misji zajmują około 35% układu, a mapa około 65%. **Expand map** otwiera mapę na pełnym ekranie. W trakcie lotu **Emergency stop** jest dostępny w jego nagłówku i używa tej samej akcji, co przycisk w głównym interfejsie. **Esc** albo **Exit full screen** przywraca zwykły układ. [Uruchomienie Full Robotics](../README.md#b-full-robotics-demo)

## Wygląd i obsługa

- Punkty mają okrągły kształt i większy kontrast względem tła. **Point size** reguluje rozmiar w zakresie 60–180%. Rozmiar bazowy zależy od poziomu szczegółowości, a łagodna korekta zależy od odległości kamery.
- **Height filter** ma ustawienia **Full cloud**, **Warehouse interior** (0,30–5,90 m) i **Custom height**. Zakres wnętrza dobrano na podstawie zapisanego skanu referencyjnego. Odcina posadzkę oraz strefę sufitu i infrastruktury powyżej regałów. Panel pokazuje osobno punkty zarejestrowane i punkty widoczne po filtrze.
- **Isometric**, **Top** i **Side** dopasowują kadr do widocznej chmury. **Fit to cloud** zachowuje aktualny kierunek patrzenia, **Follow** utrzymuje drona w kadrze, a **Reset** przywraca widok izometryczny. Podczas wzrostu chmury kamera zmienia kadr płynnie. Ręczna obsługa wyłącza automatyczne dopasowanie do kolejnych pomiarów.
- Strzałka przy dronie pokazuje jego orientację. Trajektoria, Live LiDAR i czerwone znaczniki przeszkód mają odrębną paletę. Filtr Z dotyczy tylko renderowanej chmury mapy. Zapisane pomiary, bieżący skan i punkty zagrożeń zachowują odrębne bufory.
- Wiersz nad skanem pokazuje stan mapowania, liczbę punktów, stan lokalizacji i wiek ostatniej aktualizacji. Źródło danych, rozdzielczość, jakość dopasowania i ramę przeniesiono do **Map Details**.

## Porównanie zapisanej chmury

Oba widoki odtworzono w Chrome na tych samych 54 301 punktach z eksportu PLY GOAL 19. Zapisany skan jest oznaczony jako historyczny. Preset wnętrza wyświetlił 15 992 punkty, a zakres ręczny 0,8–2,5 m wyświetlił 4 552. Powrót do **Full cloud** przywrócił wszystkie 54 301 punktów. Sprawdzono również przełączanie ustawień kamery, liczbę wyświetlanych punktów, regulator i układ kontrolek przy szerokości 390 px.

| Wariant | Płótno przy oknie 1540 × 1100 px | FPS WebGL |
| --- | ---: | ---: |
| GOAL 19 · `de4677e` | ok. 511 × 553 px | 15,26 |
| GOAL 19A | ok. 929 × 735 px | 15,21 |

Wyniki pochodzą z dwóch około 12-sekundowych okien obrotu kamery w Chrome headless, na tym samym komputerze i w trybie High. Powierzchnia płótna wzrosła około 2,4 raza przy zbliżonym FPS. Pomiar dotyczył odtwarzanej chmury, a próbę działania na żywo wykonano osobno. [Zapis pomiarów](scan-refinement-evidence/verification.json)

## Krótka próba w Gazebo

W ROS 2 Humble i Gazebo Fortress misja `INS-CONTROL-20261126-101948-7EAD523C` przełączyła 3D Model, 2D Map i 3D Scan podczas wznoszenia. Zachowała ten sam identyfikator, jeden start, stan `TRACKING` i rezerwację Safety A oraz D. Licznik wzrósł z 1 129 do 2 519 punktów podczas wznoszenia. Po ustawieniu zakresu 50–52 m widok pokazał zero punktów mapy, a warstwa zagrożeń nadal wyświetlała 58 zarejestrowanych odbić od przeszkody w szybie. Naciśnięcie **Emergency stop** w pełnym ekranie zakończyło misję stanem `ABORTED` z komunikatem `Stopped by the operator`. Safety zachował rezerwację i przeszedł w `RECOVERY`.

Zbudowano 10 pakietów. Przeszło 46 testów ROS i 7 testów kontraktu HTTP. Zmiany wykonano w warstwie wizualizacji Control Center.

## Zrzuty

- [Widok przed zmianą](scan-refinement-evidence/01-before.png) · [Nowy widok izometryczny](scan-refinement-evidence/02-isometric.png)
- [Z góry](scan-refinement-evidence/03-top.png) · [Z boku](scan-refinement-evidence/04-side.png) · [Wnętrze bez sufitu](scan-refinement-evidence/05-interior.png)
- [Pełny ekran](scan-refinement-evidence/06-fullscreen.png) · [Przeszkoda i Emergency Stop na żywo](scan-refinement-evidence/07-live-hazard-fullscreen.png)
