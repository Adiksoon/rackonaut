# GOAL 26E — Final Control Center UX & Product Polish

Branch `feature/final-control-center-ux` · baza `15bce96` · implementacja `f50cfee` · język interfejsu English.

Control Center pokazuje stan lotu, skutki poleceń i warunki ich odblokowania w miejscu decyzji. Plan, Live flight i Manual Control używają tego samego Digital Twin. Results otwiera kolejkę spraw, dowody i zalecane działania. Service ma osobne sekcje zarządzania dronem, sterowania ręcznego, kalibracji i konfiguracji. Zachowano logo, raport i dziewięć oryginalnych ujęć z GOAL 26D. [Audyt przed zmianami](GUI_BLIND_AUDIT.md)

Zmiany obejmują frontend i warstwę Control Center odpowiedzialną za prezentację danych. Zatwierdzona trasa, parametry lokalizacji, rezerwacje i komendy są obsługiwane przez dotychczasowe moduły. Symulację i integrację oparto na ROS 2 Humble, Gazebo Fortress i Chrome z Playwright.

## Przed i po

| Ekran | GOAL 26D | GOAL 26E |
| --- | --- | --- |
| Plan inspection | [Przed](gui-blind-audit/01-plan.png) | [Zakres, bateria i plan dla wybranych miejsc](final-control-center-evidence/01-plan.png) |
| Live flight | [Przed](gui-blind-audit/02-live-flight.png) | [Faza, cel, śledzenie i zapas powrotu](final-control-center-evidence/02-live-flight.png) |
| Results | [Przed](gui-blind-audit/03-results.png) | [Realizacja planu i kolejka lokalizacji](final-control-center-evidence/03-results.png) |
| Results · dowody | [Przed](gui-blind-audit/04-results-evidence.png) | [A-01-02, oryginalne zdjęcie i zalecenie](final-control-center-evidence/04-results-evidence.png) |
| Service | [Przed](gui-blind-audit/05-service.png) | [Drone Management i podzakładki](final-control-center-evidence/05-service.png) |
| Manual Control | [Przed](gui-blind-audit/06-manual-control.png) | [Kamera, model i sterowanie w 1366 × 768](final-control-center-evidence/06-manual-control.png) |
| Warehouse Calibration | [Przed](gui-blind-audit/07-warehouse-calibration.png) | [Gotowość czujników, doku i następna akcja](final-control-center-evidence/07-warehouse-calibration.png) |
| Warehouse Configuration | [Przed](gui-blind-audit/08-warehouse-configuration.png) | [Aktywna i wybrana rewizja z integralnością](final-control-center-evidence/08-warehouse-configuration.png) |
| Diagnostics | [Przed](gui-blind-audit/09-diagnostics.png) | [Stan drona, bilans powrotu i rezerwacje](final-control-center-evidence/09-diagnostics.png) |

[Dialog przerwania inspekcji](final-control-center-evidence/calibration-interruption-dialog.png) · [Historyczny model po zmianie aktywnego magazynu](final-control-center-evidence/archive-map-correct.png) · [Nagranie przepływu Plan → Live → Results](final-control-center-evidence/operator-workflow.mp4)

## Uwagi pierwszego audytu i decyzje

| Ekran | Uwagi z audytu 26D | Rozwiązanie lub uzasadnienie |
| --- | --- | --- |
| Plan | Brak bieżącej baterii przy minimum startowym | Pokazano oba odczyty w panelu zakresu. Status obok przycisku wyjaśnia gotowość lub przyczynę blokady. |
| Plan | Niejasna półka, poziom i linia trasy | Pewne projekcje mają podświetlenie płaszczyzny przy punkcie na regale. Znaczniki niejednoznaczne pozostają osobno. Linia planu ma legendę i odpowiada trasie wybranych inspekcji. |
| Plan | Tryb przy starcie, drobna instrukcja, niejasne `Eco`, sugestia języka polskiego | Tryb jest widoczny w nagłówku i przy decyzji o starcie. Powiększono instrukcję i zastąpiono `Eco` przez `Low detail` z opisem. Zachowano angielski zgodnie z wymaganiem konkursowym. |
| Live | `Confirmed 0 / 2` nie opisuje fazy i potrzeby reakcji | Pokazano liczbę zapisanych obserwacji, dotarcie do miejsc, fazę i informację, kiedy operator powinien zareagować. |
| Live | Aktualna bateria dominuje nad prognozą powrotu | Obok bieżącego poziomu są prognoza przy doku, rezerwa i margines w punktach procentowych. Gdy pomiar lub budżet są niedostępne, UI pokazuje `Unavailable`. |
| Live | Kamera mapy i nakładanie etykiet; widoczność symulacji i stopu | `Follow` śledzi położenie z uwzględnieniem bliskiego aktywnego celu. Zwiększono odstęp znaczników. Tryb Simulation i Emergency stop pozostają widoczne podczas lotu. |
| Results | Wykonanie misji i pokrycie ewidencji łatwo pomylić | Są to osobne wskaźniki z odpowiednimi mianownikami. |
| Results | Mapa dominuje i utrudnia drogę do dowodu | Domyślnie przegląd spraw. Mapa jest dostępna osobnym przyciskiem i przez `Show on map`. Wynik historyczny wskazuje swoje archiwum. |
| Results | Historia opisana techniczną końcówką ID i niejednoznaczny tryb połączenia | Selektor ma datę, godzinę, magazyn, miejsca i stan. Pełny identyfikator jest w szczegółach. Stan symulowanego drona jest osobny. |
| Dowody | Licznik niepewnych odczytów zlewa się ze stanem dowodu i obsługą sprawy | `Reading needs review` opisuje odczyt. `Evidence reviewed` jest stanem dowodu. Akcja przeglądu zachowuje dotychczasowy stan biznesowy sprawy. |
| Dowody | Powielanie lokalizacji i brak kolejności zgłoszeń | Utworzono jedną pozycję na lokalizację z typami, priorytetem i liczbą przejrzanych dowodów. Kolejność korzysta z priorytetu i liczby ustaleń. |
| Dowody | Przyczyna uszkodzenia i opis ujęć giną | Powód i pierwotne zdjęcie są obok porównania oraz rekomendacji. Przełącznik otwiera rzeczywistą wersję z adnotacjami, ujęcia odróżnia czas i kolejność. |
| Dowody | Podsumowanie zabiera miejsce | Na desktopie wskaźniki są w jednym rzędzie, a obraz jest duży i dostępny w oryginalnej rozdzielczości. |
| Service | `Production` i `Simulation` mylą się; ostrzeżenie o przerwaniu pojawia się w spoczynku | Service używa `Inspection mode`, nagłówek oznacza środowisko. Dialog przerwania otwiera się tylko dla aktywnej inspekcji i wymienia skutki. |
| Service | `Storage locations —` przy aktywnej konfiguracji | Wskazano, gdzie odczytać liczbę nauczonych miejsc, a konfiguracja podaje liczbę po weryfikacji. |
| Service | Kafelki czujników dominują nad stanem misji | Stan i zakres znajdują się przed metrykami. Cztery podzakładki rozdzielają działania. |
| Manual | `ready`, `hold` i wyszarzony start równocześnie | Kokpit pokazuje `Manual flight · holding position` i `Airborne` zgodnie z rzeczywistą fazą. |
| Manual | Prześwit i przyczyna ograniczenia są schowane | Zweryfikowany prześwit i telemetria są przy kontrolerach. Powód ograniczenia, awarii lub utraty łącza jest widoczny przy kamerze. Kierunku najbliższej przeszkody nie wyprowadzano z samej skalarnej wartości prześwitu. |
| Manual | Dużo pustego miejsca na mapie i mała kamera | Mapa, kamera i sterowanie są równocześnie dostępne. `Focus camera` powiększa obraz, a `Follow` przybliża drona na mapie. |
| Calibration | `At pad`, `Waiting for dock` i `Unconfirmed` wyglądają jak sprzeczność | Checklist rozróżnia pozycję, fizyczny styk, Safety, świeżość czujników i pozycję zweryfikowaną. |
| Calibration | Niejasny skutek `Open mapping flight` | `Open mapping controls` otwiera widok. `Start mapping flight` jest osobną komendą. |
| Calibration | Kamera i ID dominują, brakuje przyczyn blokady | Aktualny krok i akcja są nad szczegółami. Stan mapy i doku wyjaśnia blokadę recenzji trasy. Zapis wymaga zaakceptowanej trasy. |
| Configuration | Ryzyko przerwania inspekcji przez przypadkową kalibrację | Akcja kalibracji jest w swojej sekcji, modal wymienia misję, powrót i zachowanie obserwacji. UI wiąże potwierdzenie z ID bieżącej misji. |
| Configuration | Niejasny magazyn aktywny, używany lub wybrany i blokada aktywacji | Niezależne pola określają aktywną rewizję, rewizję misji i wybór. Warunek aktywacji opisuje kontrolę integralności, stan doku i Safety. |
| Diagnostics | Relacja energii powrotu, dokończenia i rezerwy wymaga liczenia | Podano prognozę przy doku, rezerwę i margines obok odczytów technicznych. |
| Diagnostics | Prawidłowe rezerwacje wyglądają jak alarmy; `Clear` i `TRACKING` mają barwę ostrzeżenia | Rezerwacje są niebieskie, potwierdzona gotowość zielona, alert czerwony, brak danych szary. Tekst opisuje rezerwację i obecność niezależnie. |
| Diagnostics | Drobne dane i słabo widoczny tryb | Na górze jest zwięzły stan i działanie albo informacja o monitorowaniu. Techniczne panele nadal są dostępne. |

## Uruchomienie

Po standardowym przygotowaniu środowiska uruchom istniejący launcher z aktywnym archiwum nauczonego magazynu. [Instrukcje środowiska](../README.md#start-here) · [Use of learned warehouse configuration](DIGITAL_TWIN_CONTROL_CENTER.md)

```bash
scripts/robotics/checkpoint live learned_warehouse:=true data_dir:=/ścieżka/do/katalogu-danych
```

Domyślne porty to 8765 i 8000. Katalog danych wskazuje kontrolowaną kopię archiwum. Service używa istniejącego mechanizmu kodu dostępu. [Control Center](http://127.0.0.1:8765/)


## Walidacja interakcji

Próby wykonywał Playwright w Chrome 158.0.8127.88. Wyniki opisują działanie aplikacji i symulatora. Badanie użyteczności z operatorem pozostaje odrębnym etapem.

| Zadanie operatora | Wynik i podstawa |
| --- | --- |
| Wybrać dwie lokalizacje modelem 3D | Przełączono oba znaczniki, od zera do dwóch. Plan, lista i trasa aktualizowały się razem. |
| Ocenić baterię przed startem | 100% bieżącej baterii przy wymaganym minimum 80%. UI wskazał gotowość symulowanego startu. |
| Rozpoznać cel, fazę i postęp | W locie odczytano A-01-01, fazę i działanie automatyczne. Po poprawce odtworzony stan z lotu pokazuje 2/2 zapisane obserwacje. W osobnym teście kontrolowanym stan po dotarciu przed odczytem prawidłowo pokazuje 0/2 i `Reached · awaiting observation`. |
| Ocenić energię powrotu | W próbce z lotu ekran pokazał 71% aktualnie, 34% przy powrocie, rezerwę 8% i około +26 pp. |
| Znaleźć dowód A-01-02 | Otwarto archiwalny oryginał, przełączono adnotacje i z powrotem. Trzy ustalenia pozostały pod jedną lokalizacją. Po poprawkach wybór ustalenia zmienił jego rekomendację. |
| Zaplanować ponowną inspekcję | Z Results otwarto Plan z wybranym wyłącznie A-01-02. Test użył referencyjnego profilu biznesowego, w którym ta lokalizacja jest dostępna. |
| Rozpoznać skutek rozpoczęcia kalibracji w locie | Dialog zawierał dokładny identyfikator misji, zachowanie obserwacji, powrót i blokadę nowych startów. Anulowanie pozostawiło misję w locie. Przycisk Emergency stop był dostępny również w dialogu. Test jednostkowy potwierdził odrzucenie zgody dotyczącej innej misji. |
| Rozróżnić pozycję przy doku od kontaktu | Przerwana próba Recovery rzeczywiście osiągnęła `at_pad=true`, gdy `physical_dock=false`. Udane próby pokazały potwierdzony kontakt i zwolnione rezerwacje. Kreator przedstawia obie wartości oddzielnie. |
| Uruchomić chroniony tryb ręczny | Wystartowano z potwierdzonego doku, uzyskano rezerwację i odczytano stan `Manual flight · holding position`. |
| Rozpoznać ograniczenie ruchu | Rzeczywista komenda opuszczania przeszła w `LIMITED` z komunikatem `Reduced command within verified clearance` i odczytem prześwitu 0,326 m. Utrata przesyłania komend dała `LINK_LOST` i zero ruchu. |
| Aktywować zapisaną konfigurację | Zweryfikowano i aktywowano rewizję kończącą się `AC100C03`, poczekano na `TRACKING`, po czym przywrócono aktywną rewizję referencyjną. |
| Otworzyć historię po zmianie aktywnego magazynu | Misja `61439CAF` nadal otwierała model `E5E70FFA`, gdy aktywna konfiguracja miała końcówkę `AC100C03`. Po pełnym restarcie pojawiła się też nowa misja z zachowanym raportem i właściwą rewizją. |

[Próba konfiguracji i kalibracji](final-control-center-evidence/configuration-verification.json) · [Wyniki lotu](final-control-center-evidence/autonomous-regression.json) · [Restart i postęp](final-control-center-evidence/restart-and-progress.json) · [Raport biznesowy dostępny offline](final-control-center-evidence/offline-proof.json)

Układ sprawdzono w 1920 × 1080, 1600 × 900 i 1366 × 768 podczas aktywnego lotu ręcznego. Najniższa podstawowa akcja kokpitu, `Hold position`, kończyła się odpowiednio na 753, 753 i 755 px, a Emergency stop pozostawał w oknie. W 1024 × 720 i 390 × 844 nie wystąpił poziomy overflow w kokpicie. Małe okna wymagają pionowego przewijania. [Pomiary układu w locie](final-control-center-evidence/manual-followup-recovery.json)

## Regresja, Recovery i ograniczenia środowiska

- Panel odrzucił start autonomii podczas ręcznego lotu i start ręczny podczas autonomii. Zwolnienie klawisza, zmiana widoku i zdarzenie rozmycia fokusu przywróciły zerową dozwoloną komendę. Watchdog po przerwaniu ruchu HTTP utrzymał rezerwację i zwrócił zero ruchu. Chrome uruchomiony w ramach automatyzacji nie zgłosił zmiany aktywnego okna przy zmianie karty ani minimalizacji. Zdarzenie `blur` wywołano w przeglądarce, a reakcję zweryfikowano w rzeczywistym Mission Managerze.
- Emergency stop zatrzymał lot i zachował strefy D oraz A. Udana, osobno zatwierdzona próba Recovery w położeniu referencyjnym potwierdziła kontakt fizyczny i zwolniła rezerwacje. Po poprawkach ponowiono referencyjny test i sprawdzono, że historyczny alarm pozostaje zapisany, a UI pokazuje `Docked`. Odtworzenie rzeczywistego stanu `RECOVERY_BLOCKED` potwierdziło utrzymanie blokady startu oraz przejście do Recovery.
- Dwie wcześniejsze próby Recovery zakończyły się podtrzymaniem ochrony. W pierwszej po zmianie yaw system osiągnął pozycję przy doku, ale kontakt pozostał niepotwierdzony i wyczerpał się czas odcinka Recovery. W drugiej przy odsunięciu od środka doku nie było zweryfikowanego prześwitu pierwszego odcinka. Nie ustalono pełnej przyczyny kontaktu w pierwszym przypadku. Testy wznowiono przez restart własnej instancji Gazebo z kopią danych.
- Początkowy test przeglądarkowy zwracał błąd ścisłego selektora, ponieważ dopasował jednocześnie przycisk A-01-02 i znacznik 3D. Zawężono selektor do listy i potwierdzono przejście do planu.
- Pełna misja `INS-CONTROL-20261126-214430-08FAE03A` wykonała A-01-01 → A-01-03 przy jednej instancji Gazebo. Wynik `COMPLETE`, oba odczyty w raporcie, potwierdzony styk doku, status Safety `RELEASED` i pozostała bateria 40,13%. Lot z eksportem raportu trwał 318,1 s zegarowych. Po pełnym restarcie odczytano raport o tych samych bajtach i ten sam model przypisany do misji. Zweryfikowano skróty oryginalnych plików obu konfiguracji i raportu.
- Testy automatyczne obejmują 69 testów ROS i Control Center, siedem testów kontraktu i Mock SAP oraz smoke HTTP. Weryfikacje Playwright zakończonych przepływów nie wykazały błędów JavaScript.

[Próba sterowania i watchdog](final-control-center-evidence/manual-controls-verified.json) · [Ograniczone próby Recovery](final-control-center-evidence/recovery-limits.json) · [Udane Recovery](final-control-center-evidence/manual-reference-recovery.json) · [Ponowne Recovery i kokpit](final-control-center-evidence/manual-followup-recovery.json) · [Regresja starego alarmu](final-control-center-evidence/followup-verification.json) · [Blokada startu w Recovery](final-control-center-evidence/recovery-blocked-plan.png)

Kreator kalibracji przetestowano przy doku i w dialogu podczas lotu. Otwarcie panelu mapowania nie wysłało komendy startu. Do walidacji wyboru, podglądu i aktywacji użyto rzeczywistych, wcześniejszych kalibracji. Pełny lot mapujący pozostał poza zakresem tej walidacji. Prezentowane „sprawdzone miejsca” oznaczają zapisane obserwacje, także odczyt z rozpoznaną niepewnością. Wynik sprawy i przegląd dowodu są osobnymi stanami. Aplikacja nie wylicza niezależnego ETA dla aktualnego odczytu, gdy estymata nie wynika z telemetrii.

## Pomiary wydajności

W 674 próbkach końcowego lotu lokalizacja miała stan `TRACKING`. Średni współczynnik czasu rzeczywistego wyniósł 0,575 w oknie 180,52 s symulacji i 313,89 s zegarowych. W poprzednim GOAL 26C odpowiedni pomiar wynosił 0,568. Próby odbyły się na tej samej klasie środowiska, lecz przebieg renderowania i punkty próbkowania były różne.

Pomiary DevTools po rozgrzaniu przeglądarki wykazały 33 ms pracy wątku głównego w 3 s na Plan z modelem i 52 ms w 3 s na Diagnostics. Skrypt zliczający `drawElements` potwierdził 50 wywołań w 2,05 s z widocznym planem i zero na Diagnostics przy ukrytej scenie. Instrumentacja wykryła jeden kontekst WebGL. Metryka liczy wywołania rysowania.

[Próbkowanie lotu i RTF](final-control-center-evidence/flight-timing.json) · [Metryki Chrome](final-control-center-evidence/autonomous-regression.json) · [Ukryta scena](final-control-center-evidence/followup-verification.json) · [Pomiar GOAL 26C](DIGITAL_TWIN_CONTROL_CENTER.md#zapis-wizualizacji-i-wydajność)

Nagranie zestawia ekran Plan, przyspieszony zapis rzeczywistego lotu i ekran Results. Ujęcia Plan i Results pochodzą z finalnych widoków. Lot nagrano przed ostatnim dopracowaniem tekstu postępu. Finalny zrzut Live i Diagnostics odtworzono z rzeczywistego pomiaru tej samej misji. Na końcu klipu pokazano oddzielny, wcześniejszy wynik biznesowy A-01-02 z zapisanym zdjęciem. [Nagranie](final-control-center-evidence/operator-workflow.mp4)

## Porównanie ślepych audytów

GPT‑6.2 Astra otrzymała dziewięć początkowych ekranów w dziewięciu niezależnych rozmowach, każdorazowo z tekstem „GUI dla operatora. Oceń ten interfejs.”. W dziesiątej rozmowie otrzymała komplet tych obrazów i prośbę o ocenę spójności z perspektywy operatora. Po jednej iteracji korekt oceniono dziewięć aktualnych ekranów w kolejnych niezależnych sesjach. Dodatkowy przegląd konfiguracji dotyczył wyraźnego opisu działania `Plan with active warehouse`. Żadna z tych rozmów nie zawierała wcześniejszych ocen ani kontekstu projektu.

W GOAL 26D Astra zgłaszała trudne do przewidzenia przejście z inspekcji do kalibracji, niejasny bilans powrotu i mapę dominującą nad wynikami. Nowe opinie potwierdzają czytelniejszy podział działań, rozróżnienie realizacji planu i pokrycia rejestru, dostęp do dowodów obok stanu SAP oraz użyteczność odczytów baterii przy powrocie.

Pierwsza runda 26E wykryła konflikt między zapisanym alarmem Safety a bieżącą gotowością po Recovery. Status Safety celowo zachowuje wpis alarmu po zwolnieniu stref. Zmieniono interpretację w warstwie wyświetlania. Podczas Recovery panel wyświetla powód blokady, odsyła do dalszego działania i blokuje start. Po fizycznym dokowaniu i zwolnieniu rezerwacji panel pokazuje bieżący stan, a alarm zostaje w historii. Poprawiono też liczenie zapisanych obserwacji, wybór konkretnego ustalenia z dowodem oraz wskazanie konfiguracji używanej w planowaniu.

Uwagi pozostające po ponownej ocenie obejmują czytelność kolejności i kierunku trasy, większy priorytet prognozy energii w locie, jednoznaczne sformułowanie o weryfikacji prześwitu po poleceniu oraz dalsze uporządkowanie metryk technicznych. W kokpicie wyświetlany prześwit pochodzi z weryfikacji rzeczywistego polecenia. W utrzymaniu pozycji telemetria może nie zawierać takiej wartości, więc UI opisuje warunek pomiaru, a przeprowadzone próby potwierdzają ograniczenie ruchu i działanie watchdogu. Decyzję o zamknięciu rozbieżności pozostawiono poza zakresem operacji, które rozumie aktualny backend. Priorytety zachowują klasyfikację Mock SAP. Szczegółową kolejność ustaleń i ergonomię warto rozstrzygnąć z rzeczywistym operatorem.

### Pierwsza ocena 26E

<details>
<summary>Plan inspection</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/audit-initial/01-plan.png)

**Interfejs dobrze pokazuje, co operator wybrał do inspekcji, ale po przerwaniu misji daje sprzeczne wskazówki.** Na ekranie jednocześnie widać „Emergency stop active”, „Mission aborted” i „Ready for simulated takeoff”. Najbardziej widocznym przyciskiem nadal jest „Start inspection”. Ze zrzutu nie da się stwierdzić, czy można go nacisnąć, ale wygląda na aktywny.

| Priorytet | Co warto zmienić |
|---|---|
| **1. Jednoznaczny stan misji** | Przy aktywnym zatrzymaniu awaryjnym przycisk startu powinien być wyraźnie zablokowany. W miejscu komunikatu o gotowości pokaż przyczynę blokady. Baner powinien wskazywać najbliższy krok operatora zgodny z procedurą odzyskania drona. |
| **2. Czytelność mapy** | Widok izometryczny dobrze pokazuje konstrukcję regałów, ale ich dolna część wypada poza widoczny obszar. Dopasuj początkowy kadr do zaznaczonych miejsc. Jeśli cienka niebieska linia oznacza trasę, podpisz ją i zwiększ jej kontrast. |
| **3. Hierarchia informacji** | W nagłówku alarm ma podobną wagę wizualną jak „Mock SAP online”. Wyróżnij aktywne zatrzymanie awaryjne także ikoną i mocniejszym kontrastem. Powiększ drobne opisy parametrów w lewym panelu, szczególnie próg baterii wymagany do startu. |

**Warto zachować** podział na wybór lokalizacji po lewej i mapę po prawej. Identyczne oznaczenia `A-01-01` i `A-01-03` pozwalają szybko powiązać zaznaczenia z regałem. Liczba wybranych miejsc, szacowany czas i poziom baterii są zebrane tam, gdzie operator podejmuje decyzję o starcie.

Najpierw poprawiłbym ekran po przerwaniu misji. Operator powinien od razu widzieć, **co się stało, czy start jest możliwy i jaki krok ma teraz wykonać**.

</details>

<details>
<summary>Live flight</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/audit-initial/02-live-flight.png)

**Jako ekran nadzoru nad autonomiczną inspekcją ten interfejs dobrze pokazuje, gdzie jest dron. Trudniej z niego odczytać, czy inspekcja przebiega prawidłowo i czy operator powinien zareagować.** Na podstawie widocznego ekranu najważniejsze są trzy kwestie.

1. **Rozdzielić wizytę od wyniku inspekcji.** A-01-01 jest jednocześnie bieżącym celem i lokalizacją oznaczoną jako „Visited”, a system nadal czeka na prawidłową obserwację. Te stany mogą być spójne, jeśli dron dotarł na miejsce i próbuje odczytać etykietę. Wtedy komunikat „A-01-01 · na miejscu · oczekiwanie na odczyt” wyjaśnia sytuację jednym spojrzeniem. Jeśli celem misji są potwierdzone odczyty, warto pokazać ich liczbę obok liczby odwiedzonych lokalizacji.
2. **Nadać oczekiwaniu kontekst.** Ten sam status pojawia się w nagłówku i pod kamerą, ale żadne z tych miejsc nie podaje czasu oczekiwania ani kolejnego kroku automatu. Pod obrazem z kamery jest dobre miejsce na czas od rozpoczęcia próby i informację, co nastąpi dalej. Dzięki temu operator może odróżnić zwykły etap lotu od sytuacji wymagającej uwagi.
3. **Ułatwić ocenę na pierwszy rzut oka.** Mapa 3D zajmuje najwięcej miejsca, podczas gdy status misji i dane o powrocie są zapisane drobnym tekstem. Warto wzmocnić wizualnie bieżący etap i zapas baterii po powrocie. Etykieta „Above reserve +25.9 pp” wymaga powiązania z sąsiednimi polami. „Zapas po powrocie: ok. 26 p.p. ponad rezerwę” podaje znaczenie i zachowuje precyzję zbliżoną do pozostałych wskazań.

**Co działa dobrze:** kamera i model magazynu pokazują ten sam identyfikator A-01-01, więc operator może powiązać obraz z pozycją w przestrzeni. Przycisk zatrzymania awaryjnego wyróżnia się i łatwo go znaleźć. Tryb symulacji jest jawnie oznaczony.

**Pierwsza zmiana, którą bym wdrożył:** wykorzystać wiersz pod kamerą do pokazania celu, etapu odczytu i czasu jego trwania. To usuwa największą niejasność bez przebudowy ekranu.

</details>

<details>
<summary>Results</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/audit-initial/03-results.png)

**Ekran dobrze pokazuje wynik inspekcji, ale utrudnia operatorowi decyzję, co zrobić najpierw.** Widać, że sprawdzono obie zaplanowane lokalizacje, a w A-01-03 wykryto brak palety o wysokim priorytecie. Żeby ustalić, na czym opiera się to zgłoszenie i co trzeba zweryfikować, operator musi połączyć informacje z kilku miejsc.

**Co działa**

- Układ „lista lokalizacji → szczegóły” pozwala przeglądać zgłoszenia bez utraty kontekstu. Wybrana lokalizacja jest wyróżniona, a priorytety mają czytelne etykiety tekstowe.
- Rozdzielenie realizacji planu **2/2** i pokrycia magazynu **2/11** odpowiada na dwa różne pytania operatora. Warto to zachować.
- Zestawienie oczekiwanego produktu z obserwacją drona jasno wyjaśnia przyczynę zgłoszenia. Z tego samego widoku można otworzyć mapę lub zaplanować ponowną inspekcję.

**Co zmieniłbym w pierwszej kolejności**

1. **Rozdzielić wynik inspekcji od stanu weryfikacji.** Przy tej samej lokalizacji widać „Confirmed issue”, „0 of 1 reviewed” i „Evidence review pending”. Operator może odczytać pierwszy status jako potwierdzenie przez człowieka. Dwie jawne etykiety, np. „Wynik inspekcji — wykryto brak palety” oraz „Weryfikacja operatora — oczekuje”, usunęłyby tę dwuznaczność.
2. **Pokazać podstawę zgłoszenia obok czynności weryfikacyjnej.** Komunikat o braku zdjęcia zajmuje górę dużego, pustego pola, a odczyty kamery są zwinięte poniżej przycisku „Mark evidence reviewed”. Gdy zdjęcia brak, warto skrócić ten obszar i pokazać dostępny odczyt bezpośrednio przed przyciskiem. Operator mógłby sprawdzić materiał i od razu oznaczyć go jako przejrzany.
3. **Ułożyć szczegóły według kolejności pracy.** Nagłówek „A-01-03 · Brak palety” z priorytetem pozwoli od razu rozpoznać sprawę. Pod nim wystarczą oczekiwany stan, obserwacja i jedno zalecenie. Obecnie zalecenie sprawdzenia ruchów magazynowych i jednostki ładunkowej pojawia się dwukrotnie.
4. **Nadać większą wagę sprawom wymagającym uwagi.** Sześć jednakowych kart nadaje zerowej liczbie uszkodzeń tyle samo miejsca co wykrytej rozbieżności. Warto mocniej wyróżnić niezerowe liczniki problemów i zwiększyć rozmiar drobnego tekstu przy statusach weryfikacji.

Największy efekt dałoby przeprojektowanie panelu szczegółów. Dla A-01-03 operator powinien w jednym miejscu zobaczyć, **czego oczekiwał system, co zarejestrował dron i co pozostało do sprawdzenia**.

</details>

<details>
<summary>Results z dowodami</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/audit-initial/04-results-evidence.png)

Interfejs dobrze odpowiada na pytanie „co wykryto podczas inspekcji?”. Słabiej odpowiada na pytanie operatora „od czego zacząć i co mogę teraz zrobić?”. Największej poprawy wymaga przejście od listy usterek do oceny konkretnego znaleziska.

**Co działa dobrze**

- Podział na listę lokalizacji po lewej i szczegóły po prawej ułatwia orientację. Zaznaczenie wiersza i powtórzenie kodu **A-01-02** nad zdjęciem wyraźnie łączą oba panele.
- Osobne wskaźniki **3/3 wykonanych punktów planu** i **3/11 lokalizacji magazynu** przekazują ważną różnicę. Operator widzi, że inspekcja dobiegła końca i jaki obszar objęła.
- Zestawienie **„Expected in Mock SAP”** i **„Observed by drone”** obok zdjęcia pozwala od razu porównać oczekiwany produkt P002 z odczytanym P003.

**Co poprawiłbym w pierwszej kolejności**

1. **Umożliwić wybór konkretnego znaleziska.** A-01-02 ma trzy zgłoszenia. Panel pokazuje uszkodzenie opakowania, a obok niego rozbieżność kodów produktów. Nie widać, jak przejść do kolejnego zgłoszenia ani którego dotyczy zalecenie. Po rozwinięciu lokalizacji pokazałbym trzy osobne pozycje. Wybór jednej powinien wskazywać odpowiadające jej zdjęcie, status i zalecenie.
2. **Wyjaśnić relację między „Confirmed issue” a „0 of 3 reviewed”.** Operator może odczytać te komunikaty jako sprzeczne. Jeśli pierwszy status pochodzi z automatycznej detekcji, warto podpisać go „Wykryte przez system”, a stan pracy operatora pokazać osobno jako „Czeka na ocenę”. Jeśli problem faktycznie ktoś potwierdził, warto wskazać kto.
3. **Pokazać skutki trybu offline przy działaniach.** Informacja o niedostępności przeglądu jest drobna i oddalona od przycisku „Plan reinspection”, który wygląda na aktywny. Przy tej akcji warto jasno pokazać, czy ponowną inspekcję można zaplanować lokalnie, czy wymaga to połączenia.
4. **Nadać priorytetom znaczenie przy wyborze kolejności pracy.** Wszystkie trzy widoczne lokalizacje mają etykietę „High priority”. Jeśli taka klasyfikacja jest poprawna, krótki powód priorytetu albo informacja o wymaganym działaniu pomoże operatorowi zdecydować, którą lokalizację otworzyć pierwszą.

**Pierwsza zmiana do wdrożenia:** rozwinąć A-01-02 do trzech wybieralnych zgłoszeń i przy każdym pokazać stan oceny. To pozwoli operatorowi ustalić, co właśnie ogląda, czego dotyczy zalecenie i ile pracy pozostało. Ocena opiera się na pojedynczym zrzucie ekranu, więc dotyczy widocznych wskazówek, a zachowanie kontrolek po kliknięciu pozostaje niezweryfikowane.

</details>

<details>
<summary>Drone Management</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/audit-initial/05-service.png)

**Interfejs jest czytelny jako panel serwisowy, ale po przerwaniu misji nie odpowiada jasno na najważniejsze pytanie operatora: czy dron wymaga jeszcze interwencji?**

Największy problem widać na tym ekranie. Nagłówek pokazuje `Emergency stop active`, baner poleca `Verify and recover the drone`, a karta drona jednocześnie pokazuje `Docked`, `Physical dock contact confirmed` oraz `Safety: Released · Fresh sensors`. Te komunikaty mogą opisywać różne elementy systemu, lecz operator musi sam ustalić, czego dotyczy `Released` i co jeszcze wymaga sprawdzenia.

| Priorytet | Co warto zmienić |
|---|---|
| **Wysoki** | **Połączyć alarm z bieżącym stanem drona.** Baner powinien podawać znane fakty, np. „Misja przerwana. Zatrzymanie awaryjne aktywne. Kontakt ze stacją dokującą potwierdzony”. Jeśli procedura wymaga weryfikacji, obok powinno być przejście do jej szczegółów. |
| **Wysoki** | **Nazwać poszczególne zabezpieczenia.** Zastąpić ogólne `Safety: Released` nazwą konkretnej blokady i jej stanem. Aktywne zatrzymanie awaryjne powinno też wyraźniej odróżniać się od sąsiedniego wskaźnika `Mock SAP online`. |
| **Średni** | **Uporządkować kartę drona według pytań operatora.** `Docked` i potwierdzenie kontaktu ze stacją warto pokazać razem. `No active mission` oraz `Current mission: Idle` można scalić. Odzyskane miejsce przyda się na czas ostatniej aktualizacji danych, dziś określanych tylko jako `Fresh`. |
| **Niższy** | **Poprawić odczyt z dystansu.** Etykiety czujników są drobne, mimo że na ekranie pozostaje dużo miejsca. Warto powiększyć najważniejsze statusy i nadać im większą wagę wizualną niż długiemu identyfikatorowi mapy. |

Zachowałbym podział na stan drona i konfigurację magazynu, widoczne oznaczenie trybu `Simulation` oraz tekstowe opisy statusów, dzięki którym odczyt nie zależy wyłącznie od koloru. Pierwszą zmianą powinno być dopracowanie widoku po przerwaniu misji. Operator powinien w jednym miejscu zobaczyć, **co się wydarzyło, jaki stan potwierdził system i jaki krok pozostał do wykonania**.

</details>

<details>
<summary>Manual Control</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/audit-initial/06-manual-control.png)

**Interfejs jest czytelny, gdy dron utrzymuje pozycję. Największą słabością podczas manewru jest rozdzielenie obrazu z kamery, sterowania i informacji o prześwicie.** Operator patrzy na lewą stronę, żeby ocenić sytuację, a na prawą, żeby wydać polecenie i sprawdzić, czy system potwierdza bezpieczny odstęp.

**Co warto poprawić w pierwszej kolejności**

1. **Wyjaśnić zakres ochrony lotu.** Panel „Protected manual flight” pokazuje jednocześnie „Verified clearance: Unavailable”. Operator nie wie, czy system nadal ogranicza ruch w stronę przeszkody. Rezerwacja alejki A tego nie wyjaśnia. Przy sterowaniu powinien widnieć jednoznaczny komunikat o dostępnej ochronie i o tym, które ruchy są możliwe.
2. **Dopasować akcje do fazy lotu.** Dron ma status „Airborne” i wysokość 0,72 m, a panel nadal eksponuje „Start and take off”. Nawet jeśli przycisk jest nieaktywny, zajmuje najbardziej widoczne miejsce w grupie. Podczas lotu tę przestrzeń lepiej przeznaczyć na utrzymanie pozycji i powrót do doku. Warto zachować stałe położenie górnego „Emergency stop”.
3. **Dać więcej miejsca widokowi używanemu do manewru.** Kamera jest mała, a model magazynu zajmuje tylko część płótna mapy. „Focus camera” to dobry punkt wyjścia. Po powiększeniu obrazu operator powinien nadal widzieć wysokość, prędkość, stan ochrony i polecenie zatrzymania. Na mapie pomogłoby ciaśniejsze kadrowanie wokół drona i najbliższego regału.
4. **Poprawić czytelność przy tej rozdzielczości.** Na widoku 1366 × 768 dolna część panelu sterowania wychodzi poza kadr. Skróty klawiszowe i opisy parametrów są drobne. Zmniejszenie wysokości nagłówka i dwóch poziomów nawigacji pozwoliłoby powiększyć etykiety i zmieścić podstawowe sterowanie na ekranie.

**Warto zachować** zasadę „przytrzymaj, aby lecieć, puść, aby zatrzymać”, przestrzenny układ klawiszy ruchu oraz prognozę baterii po powrocie do doku. Ta ostatnia odpowiada bezpośrednio na pytanie operatora, z jakim zapasem dron wróci.

Ocena opiera się na pojedynczym zrzucie. Najważniejszy test z operatorem to sprawdzenie, czy przy komunikacie „Verified clearance: Unavailable” potrafi przed wykonaniem ruchu poprawnie powiedzieć, jakiej ochrony może oczekiwać od systemu.

</details>

<details>
<summary>Warehouse Calibration</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/audit-initial/07-warehouse-calibration.png)

**Interfejs dobrze pokazuje przebieg kalibracji, ale w chwili przerwania misji nie odpowiada jasno na najważniejsze pytanie operatora: co mam teraz zrobić?**

**Najwyższy priorytet ma obsługa przerwanej misji.** Na tym samym ekranie widać „Emergency stop active”, „Mission aborted” i „Calibration ready”. Warunki przy stacji dokującej mogą być spełnione mimo aktywnego zatrzymania awaryjnego. Pięć zielonych pól i dominujący przycisk „Open mapping controls” sugerują jednak, że operator może kontynuować procedurę. Status zatrzymania jest przy tym mniej widoczny niż przycisk. Sam zrzut nie pozwala ocenić, czy system blokuje start.

1. **Nadaj komunikatowi o przerwaniu misji konkretne działanie.** „Verify and recover the drone” nie mówi, gdzie zacząć. Jeśli obowiązuje procedura odzyskiwania, umieść w banerze przycisk „Otwórz procedurę odzyskiwania”. W karcie kalibracji doprecyzuj zakres gotowości, np. „Warunki przy stacji potwierdzone”. Jeżeli start jest zablokowany, pokaż to bezpośrednio przy sterowaniu.
2. **Wyeksponuj bieżące zadanie.** Największy nagłówek brzmi „Service”, choć operator pracuje nad mapowaniem magazynu. Nagłówek „Kalibracja magazynu” z podtytułem „Krok 2 z 7 · Mapowanie magazynu” szybciej orientowałby w zadaniu. „Service” jest już widoczne w nawigacji.
3. **Popraw czytelność krótkich informacji operacyjnych.** Etykiety kroków, opis działania przycisku i statusy w górnym pasku są drobne. Szczególnie warto powiększyć informację, że start wymaga osobnego polecenia. Tryb „Simulation” również zasługuje na wyraźniejsze oznaczenie, zwłaszcza jeśli operator korzysta też z wersji sterującej rzeczywistym dronem.

**Warto zachować** pasek siedmiu etapów, tekstowe wartości obok kolorów oraz osobne polecenie startu. W pierwszym teście z operatorem pokazałbym ten ekran bez objaśnień i zapytał: „W jakim stanie jest dron, czy możesz wystartować i co zrobisz teraz?”. Te trzy odpowiedzi pokażą, czy hierarchia komunikatów działa.

</details>

<details>
<summary>Warehouse Configuration</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/audit-initial/08-warehouse-configuration.png)

**Ekran jest czytelny jako panel konfiguracji, ale po przerwaniu misji operator musi sam ustalić, co zrobić dalej.** Dobrze widać wybraną rewizję, wynik kontroli integralności i zatwierdzenie trasy. Mniej jasne jest to, czy konfiguracja jest już gotowa do użycia i co wymaga teraz uwagi operatora.

1. **Najwyższy priorytet ma obsługa przerwanej misji.** Baner informuje o przerwaniu misji i zaleca sprawdzenie drona, a stan „Emergency stop active” znajduje się w rogu nagłówka obok informacji o symulacji i połączeniu z SAP. Warto pokazać stan zatrzymania również w banerze i dodać akcję „Otwórz diagnostykę drona”. Operator od razu zobaczy, od czego zacząć. Przyczynę przerwania należy podać tylko wtedy, gdy system ją potwierdził.

2. **Rozdziel wybór konfiguracji od gotowości do lotu.** Rewizja 2 jest opisana jako „Active warehouse”, choć system nadal czeka na dopasowanie mapy. Dwa komunikaty na dole karty powtarzają ten stan, ale nie wyjaśniają jego konsekwencji. Przy nazwie rewizji umieściłbym status „Wybrana · oczekiwanie na dopasowanie mapy” oraz krótką informację, czy oczekiwanie blokuje start i czy wymaga działania operatora.

3. **Nadaj ekranowi tytuł odpowiadający zadaniu.** Największy nagłówek to „Service”, choć operator pracuje w „Warehouse Configuration”. Użyłbym „Warehouse Configuration” jako tytułu strony, pozostawiając „Service” w nawigacji. Stan odblokowania i przycisk „Lock Service” warto zgrupować, bo obecnie leżą na przeciwnych krańcach ekranu.

4. **Popraw czytelność informacji, z których wynika decyzja.** Nazwa i identyfikator rewizji pojawiają się trzy razy, a informacja o oczekiwaniu na mapę ginie w drobnym tekście pod przyciskami. Zachowałbym porównanie rewizji aktywnej i wybranej, bo operator może przeglądać inną zapisaną konfigurację. Powiększyłbym natomiast tekst statusu i przeniósł go obok selektora. Obecny podział danych na dwie kolumny oraz jawne wyniki „Verified” i „Approved” warto zachować.

**Najpierw poprawiłbym baner po przerwaniu misji i status gotowości konfiguracji.** Te dwie zmiany pomogą operatorowi odpowiedzieć na najważniejsze pytania na tym ekranie: „Co mam teraz sprawdzić?” i „Czy mogę użyć tej rewizji do kolejnego lotu?”.

</details>

<details>
<summary>Diagnostics</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/audit-initial/09-diagnostics.png)

**Interfejs jest czytelny jako ekran diagnostyczny, ale podczas lotu operator musi sam złożyć obraz sytuacji z kilku kart.** Na pierwszy rzut oka wiadomo, że dron leci do punktu inspekcji. Trudniej ocenić, czy lot przebiega prawidłowo i czy coś wymaga uwagi.

**Co działa dobrze**

- Przycisk „Emergency stop” ma wyraźną etykietę, wyróżnia się kolorem i łatwo go znaleźć w prawym górnym rogu.
- Podział na energię, unikanie przeszkód i lokalizację ułatwia znalezienie szczegółów, gdy operator wie już, co chce sprawdzić.
- Panel energii podaje zapas względem wymaganej rezerwy. To bardziej przydatna informacja przy decyzji o kontynuowaniu lotu niż sam poziom baterii.

**Co poprawiłbym w pierwszej kolejności**

1. **Wykorzystać górną kartę do podsumowania sytuacji.** Obecnie powtarza komunikat „Flying to inspection location” widoczny już w nagłówku. Obok etapu lotu warto pokazać pozostały punkt `A-01-03`, stan trasy, zapas energii i ewentualny alert. Operator od razu zobaczy, czy ma powód, by zajrzeć niżej.
2. **Nadać kolorom i oznaczeniom jednoznaczne znaczenie.** Bursztynowa kropka towarzyszy zarówno „Clear”, jak i „TRACKING” oraz „Dock · Available”. Może więc sugerować ostrzeżenie przy zwykłej pracy. Podobnie kreska przy „Nearest obstacle on path” pozostawia dwie interpretacje. „Nie wykryto przeszkody” i „Brak danych ze skanu” powinny wyglądać inaczej, bo prowadzą do różnych decyzji.
3. **Wyjaśnić prognozy energii i powiększyć najważniejsze liczby.** Przy `37.8%` etykieta „Estimated energy to finish” nie rozstrzyga, czy chodzi o przewidywane zużycie, czy o stan baterii po zakończeniu. Jednoznaczna etykieta i wskazanie, dla którego scenariusza wyliczono `+25.8 pp`, oszczędzą operatorowi interpretowania modelu w trakcie lotu.
4. **Lepiej wykorzystać miejsce na ekranie.** Karta telemetrii zajmuje całą szerokość dla dwóch odczytów, a przy widocznej rozdzielczości 1600 × 900 szczegóły „Warehouse Safety” wypadają poniżej dolnej krawędzi. Skrócenie karty telemetrii pozwoliłoby pokazać stan stref bezpieczeństwa wyżej, bez dalszego zmniejszania już drobnego tekstu.

**Pierwszą zmianą byłaby przebudowa górnej karty.** Dałaby operatorowi szybki obraz lotu, zachowując obecne panele do diagnozowania przyczyn. Ocenę opieram na widoku symulacji w trakcie zwykłego lotu. Zachowanie interfejsu przy alarmie, utracie telemetrii i zatrzymaniu awaryjnym wymaga osobnego sprawdzenia.

</details>

<details>
<summary>Ocena spójności z kompletem zrzutów</summary>

**Aplikacja ma spójny przebieg inspekcji, ale traci spójność w momentach, gdy operator musi podjąć decyzję.** Łatwo przejść od planowania przez obserwację lotu do wyników. Trudniej jednoznacznie ustalić, czy po przerwaniu misji można wystartować, czy dron zakończył odczyt i czy wybrana mapa jest gotowa do użycia.

| Priorytet | Co widzi operator | Zalecana zmiana |
|---|---|---|
| **Krytyczny — gotowość do startu** | Na ekranie 1 jednocześnie widać `Emergency stop active`, polecenie odzyskania drona, `Ready for simulated takeoff` i wyróżniony przycisk `Start inspection`. Na ekranie 5 dron jest zadokowany, a pole `Safety` pokazuje `Released`, mimo że nagłówek nadal zgłasza aktywny stop. | Pokazać jeden wiążący komunikat o możliwości startu, używany także do sterowania dostępnością przycisku. Jeśli stop jest aktywny, podać blokadę i następną czynność. Po odzyskaniu drona oznaczyć przerwanie misji jako zdarzenie historyczne. |
| **Wysoki — postęp inspekcji** | Na ekranie 2 lokalizacja A-01-01 jest zarazem bieżącym celem i pozycją `Visited`, a dron czeka na poprawną obserwację. Licznik `1 of 2` można odczytać jako jeden ukończony odczyt. | Rozróżnić dotarcie, oczekiwanie na odczyt i zapisanie obserwacji. W locie i w wynikach tak samo liczyć ukończone odczyty. |
| **Wysoki — gotowość mapy** | Na ekranie 8 wybrana rewizja jest opisana jako aktywna, a równocześnie trwa oczekiwanie na dopasowanie mapy przy doku. Operator zna numer rewizji, lecz musi sam ocenić, czy można jej użyć do lotu. | Osobno pokazać wybraną konfigurację i jej gotowość do lotu. Przy oczekiwaniu na dopasowanie wskazać, czy wymaga ono działania operatora. |
| **Średni — wiarygodność wyniku** | Na ekranie 3 brak palety ma status `Confirmed issue`, choć przegląd dowodu nadal oczekuje, a zdjęcia nie zapisano. Na ekranie 4 raport offline zachowuje czytelne zestawienie stanu oczekiwanego i zaobserwowanego, lecz informacja o ograniczeniach przeglądu jest oddalona od działań. | Oznaczyć osobno wynik automatyczny, dostępny dowód i decyzję operatora. Informację o niedostępnej czynności pokazać przy jej kontrolce. |
| **Średni — zakres inspekcji** | Plan obejmuje wszystkie widoczne zarejestrowane lokalizacje, czyli dwie (ekran 1). Wyniki pokazują `Plan completed 2/2` i `Warehouse coverage 2/11` (ekran 3). Samo rozróżnienie jest wartościowe, ale pochodzenie liczby 11 pozostaje niejasne. | Nazwać źródło obu zbiorów, np. wskazać rewizję mapy przy planie oraz rejestr, z którego pochodzi całkowita liczba lokalizacji. |

**Warto zachować** stałą nawigację, oznaczenie symulacji i te same identyfikatory lokalizacji w planie, na mapie, w kamerze i w raporcie. Szczególnie dobrze działa widok wyników ze zdjęciem na ekranie 4. Operator może w jednym miejscu powiązać lokalizację, odczyt drona, oczekiwanie systemu magazynowego i zalecaną czynność. W locie podobną ciągłość zapewniają powtarzalne wskaźniki baterii i rezerwy na ekranach 2, 6 i 9.

**Pierwszą poprawką powinno być uzgodnienie komunikatów po zatrzymaniu awaryjnym.** Operator powinien z ekranu planowania dowiedzieć się, czy start jest możliwy i co ma zrobić dalej, bez przechodzenia do serwisu w celu interpretacji sprzecznych statusów. Ocena dotyczy dziewięciu zrzutów. Widać na nich konflikt komunikatów, ale skuteczność faktycznej blokady startu wymaga sprawdzenia w działającej aplikacji.

</details>

### Ponowna ocena po korektach

<details>
<summary>Plan inspection</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/01-plan.png)

**Operator ma jasną odpowiedź na pytanie „czy mogę wystartować?”, ale trudniej mu ocenić „czy dron poleci tam, gdzie chcę?”.** Na ekranie widać dwa wybrane miejsca, przewidywany czas około 4 minut i baterię 99% przy wymaganych 80%. Główny przycisk łatwo znaleźć. Najwięcej uwagi wymaga podgląd trasy przed startem.

| Priorytet | Co widać na ekranie | Co bym zmienił |
|---|---|---|
| Wysoki | Te same identyfikatory, `A-01-01` i `A-01-03`, pojawiają się na liście i na mapie. To ułatwia weryfikację celu. Cienka niebieska trasa częściowo zlewa się jednak z konstrukcją regału, a kierunek lotu i kolejność odwiedzin są trudne do odczytania. | Oznaczyć start i kierunek lotu. Dodać do obu miejsc numery kolejności, wspólne dla listy i mapy. |
| Wysoki | Tryb `Simulation` jest widoczny w nagłówku, a komunikat pod przyciskiem wspomina o symulowanym starcie. Sam przycisk `Start inspection` brzmi jak polecenie rzeczywiste. | W trybie symulacji nazwać przycisk `Start simulation`. Operator zobaczy skutek działania dokładnie tam, gdzie potwierdza decyzję. |
| Średni | `Aisle A 2` i `Rack row R02 2` wyglądają jak przyciski. Trudno odróżnić liczbę miejsc od części identyfikatora i zrozumieć relację między alejką, rzędem i miejscami. | Pokazać hierarchię „Alejka A → Rząd R02”, a liczbę zapisać osobno jako „2 miejsca”. Zachować pola wyboru przy konkretnych lokalizacjach. |
| Średni | Mapa jest duża, lecz podpisy narzędzi i legenda są drobne. Na pokazanym ekranie legenda przy dolnej krawędzi jest częściowo ucięta. | Umieścić legendę wewnątrz mapy i powiększyć podpisy potrzebne do odczytania trasy. |

Zachowałbym układ **wybór po lewej, weryfikacja na mapie po prawej** oraz zestawienie aktualnego i wymaganego poziomu baterii. Pierwszy test z operatorem można sprowadzić do jednego polecenia: „Przed naciśnięciem przycisku wskaż, skąd dron ruszy, które miejsce odwiedzi pierwsze i czy uruchamiasz symulację”. To sprawdzi czytelność ekranu w chwili decyzji.

</details>

<details>
<summary>Live flight</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/02-live-flight.png)

**Interfejs dobrze pokazuje przebieg inspekcji, ale utrudnia szybką ocenę powrotu do stacji.** Operator widzi, że dron wraca, obie obserwacje zostały zapisane, a celem jest „Dock”. Żeby odpowiedzieć na najważniejsze w tej chwili pytanie — „czy dron ma dość energii, żeby wrócić?” — musi jednak odczytać kilka drobnych pól u dołu panelu.

**Co działa**

- Kamera i mapa obok siebie pozwalają zestawić widok z drona z jego pozycją w magazynie. Identyczne oznaczenia `A-01-01` i `A-01-03` na mapie i liście ułatwiają powiązanie obserwacji z miejscem.
- Status „Returning to dock” jest widoczny zarówno w nagłówku, jak i pod kamerą. Dopisek „Autonomous flight · monitoring only” wyjaśnia rolę operatora.
- „Emergency stop” ma wyraźną etykietę i wyróżnia się na ciemnym pasku. To element, który warto zachować przy zmianach układu.

**Co poprawiłbym w pierwszej kolejności**

1. **Wyeksponować prognozę energii przy powrocie.** Skoro dron już wraca, warunkowe „At dock if returning now” brzmi jak opis alternatywnego scenariusza. Czytelniejszy komunikat to **„Przewidywany poziom baterii po powrocie: 34% · wymagane minimum: 8%”**. Warto też ujednolicić zaokrąglenia — z widocznych liczb wynika 26 punktów procentowych zapasu, a panel podaje 26,4.
2. **Ułatwić odnalezienie stacji na mapie.** W pokazanym kadrze łatwo rozpoznać regały, ale trudno od razu wskazać stację i prześledzić drogę powrotną. Pomogłyby podpis „Dock”, wyraźniejsza linia trasy oraz kadr obejmujący drona i cel podczas powrotu.
3. **Wzmocnić oznaczenie symulacji.** „Simulation” wygląda podobnie do sąsiednich znaczników statusu. Jeśli ten sam interfejs służy do rzeczywistych lotów, tryb powinien być rozpoznawalny na pierwszy rzut oka, także dla operatora skupionego na obrazie z kamery.
4. **Nadać paskowi postępu jednoznaczne znaczenie.** Pełny zielony pasek pod „Dock” i „2 of 2” można odczytać jako zakończenie lotu, choć dron wciąż wraca. Umieszczenie go bezpośrednio przy etykiecie „Zapisane obserwacje: 2/2” usunęłoby tę dwuznaczność.

Największą poprawę dałaby niewielka zmiana hierarchii pod kamerą. Pierwszy wiersz powinien łączyć **stan lotu, cel i prognozę baterii po dotarciu**. Wynik inspekcji może znaleźć się tuż niżej. Operator odczyta wtedy sytuację jednym spojrzeniem.

</details>

<details>
<summary>Results</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/03-results.png)

**Interfejs dobrze odpowiada na pytanie „co wymaga uwagi?”, ale słabiej prowadzi operatora przez weryfikację wyniku.** Na liście od razu widać dwa problemy, ich lokalizacje i priorytety. Po wybraniu A-01-03 operator może zestawić oczekiwanie SAP („Industrial junction box”) z odczytem drona („Empty location”). To najmocniejszy element ekranu.

W pierwszej kolejności poprawiłbym trzy rzeczy.

1. **Rozdziel odczyt drona od decyzji operatora.** Dla A-01-03 interfejs ogłasza „Missing pallet”, choć materiał czeka na weryfikację i nie zapisano zdjęcia. Lepiej pokazać „Podejrzenie braku palety”, a bezpośrednio pod nim odczyt, czas i informację o braku zdjęcia. Przycisk „Mark evidence reviewed” mówi tylko, że ktoś przejrzał materiał. Jeśli operator ma rozstrzygnąć sprawę, powinien móc zapisać wynik oceny, np. „Potwierdzam brak” albo „Wymaga ponownej inspekcji”.

2. **Zbierz informacje o wybranym problemie w jednym miejscu.** Po prawej „Missing pallet” pojawia się trzykrotnie, a status weryfikacji dwukrotnie. Jednocześnie pod komunikatem o braku zdjęcia zostaje duża pusta przestrzeń, a przycisk weryfikacji trafia niemal na dół ekranu. Jeden panel z kolejnością „oczekiwano → odczytano → dostępne dowody → decyzja” skróci drogę od zauważenia rozbieżności do działania. Zachowałbym obecną listę lokalizacji po lewej.

3. **Doprecyzuj zakres inspekcji w samych licznikach.** Sąsiadujące wartości „2 / 2” i „2 / 11” wymagają przeczytania drobnych podpisów, żeby zrozumieć, jak duża część pracy została wykonana. Prostszy komunikat to „Sprawdzono obie zaplanowane lokalizacje” oraz „Ta inspekcja objęła 2 z 11 lokalizacji magazynu”. Liczniki problemów można wtedy mocniej wyróżnić, a kategorie z wynikiem zero wizualnie wyciszyć.

**Największy zysk przyniesie przeprojektowanie panelu A-01-03.** Operator już widzi, którym miejscem zająć się najpierw. Teraz powinien móc równie szybko ocenić, na czym opiera się zgłoszenie i jaką decyzję zapisać. Ocena dotyczy widocznego ekranu.

</details>

<details>
<summary>Results z dowodami</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/04-results-evidence.png)

Ekran dobrze odpowiada na pytanie „co wykryto podczas inspekcji?”. Słabiej odpowiada na dwa pytania operatora: **„od czego zacząć?” i „co mogę zrobić teraz?”**. Układ podsumowanie → lista lokalizacji → dowód dla wybranego miejsca warto zachować.

**Co działa**

- Dla A-01-02 operator widzi obok zdjęcia zarówno produkt oczekiwany w SAP (P002), jak i odczytany przez drona (P003). Może sam sprawdzić, na czym polega rozbieżność.
- Rozdzielenie wykonania planu (3/3) od pokrycia magazynu (3/11) pokazuje, że inspekcja objęła wszystkie zaplanowane miejsca, choć stanowią one tylko część magazynu.
- Lista podaje liczbę ustaleń i postęp ich przeglądu dla każdej lokalizacji. Wybrana pozycja jest wyróżniona i ma ten sam identyfikator co panel szczegółów.

**Co poprawiłbym w pierwszej kolejności**

1. **Wyjaśnić dostępność działań offline.** Operator widzi „review actions unavailable offline”, „Evidence review pending” i aktywny przycisk „Plan reinspection”. Tekst pod nagłówkiem wyjaśnia, że plan można przygotować lokalnie, ale łatwo go przeoczyć. Przy przycisku dałbym komunikat „Plan zapiszesz lokalnie. Wysłanie wymaga połączenia”, a przy statusie dowodu wskazał, kiedy będzie można zatwierdzić ocenę.
2. **Ułatwić wybór następnej lokalizacji.** Wszystkie trzy pozycje mają etykietę „High priority”, więc sama etykieta nie pomaga ustalić kolejności. Jeśli obowiązuje reguła operacyjna, warto według niej sortować listę i pokazać powód pierwszeństwa. Jeśli priorytet jest równy, wystarczy wspólny nagłówek „Wysoki priorytet · 3 lokalizacje”.
3. **Powiązać zdjęcie z konkretnym ustaleniem.** Dla A-01-02 są trzy ustalenia. Gdy wybrane jest uszkodzenie opakowania, zdjęcie i zalecenie dotyczą uszkodzenia, ale sąsiednie porównanie P002/P003 wyjaśnia inną niezgodność. Wyraźniejsze zaznaczenie aktywnej zakładki i domyślne obrysowanie uszkodzenia na zdjęciu skróciłyby drogę od ustalenia do dowodu.
4. **Doprecyzować liczniki.** Karta pokazuje 2 rozbieżności magazynowe, a lista zawiera 5 ustaleń w 3 lokalizacjach. Te liczby mogą być poprawne, ale operator musi odgadnąć sposób liczenia. Każda karta powinna podawać jednostkę zgodną z danymi, np. „2 lokalizacje z rozbieżnością” albo „2 rozbieżności”.

Najpierw poprawiłbym komunikaty przy działaniach offline. To niewielka zmiana, która bezpośrednio odpowiada operatorowi, czy może zakończyć przegląd dowodu, zapisać plan ponownej inspekcji lub wysłać drona. Ocenę opieram na jednym zrzucie ekranu, więc dotyczy ona widoczności tych możliwości, a nie zachowania przycisków po kliknięciu.

</details>

<details>
<summary>Drone Management</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/05-service.png)

**Ekran dobrze sprawdza się jako przegląd serwisowy, ale operatorowi trudno na pierwszy rzut oka ustalić, co wymaga jego uwagi.** Widać, że dron jest zadokowany, nie wykonuje misji, a bateria ma 100%. Mniej wyraźne są informacje, które zmieniają interpretację całego ekranu — trwa symulacja, a dostęp serwisowy jest odblokowany.

| Priorytet | Obserwacja | Proponowana zmiana |
|---|---|---|
| Wysoki | „Simulation” w prawym górnym rogu wygląda podobnie do sąsiednich wskaźników. Przy szybkim spojrzeniu łatwo odczytać dane jako rzeczywistą telemetrię. | Umieścić stałe, wyróżnione oznaczenie „Tryb symulacji” przy nazwie aplikacji, widoczne również po zmianie zakładki. |
| Wysoki | „Service unlocked” znajduje się we właściwym miejscu, obok przycisku blokady, ale ma mały tekst i zieloną kropkę. Nie wiadomo też, co dokładnie blokuje „Lock Service”. | Nazwać zakres działania wprost, np. „Zablokuj sterowanie serwisowe”, jeśli właśnie to robi przycisk. Wyróżnić stan odblokowania proporcjonalnie do uprawnień, które daje. |
| Średni | „Drone Management” pojawia się trzy razy — w zakładce, tytule strony i nagłówku karty. Stan „Docked” ma mniejszą rangę wizualną niż powtórzony nagłówek. | W karcie użyć „Zadokowany” jako nagłówka, a „Brak aktywnej misji” zachować bezpośrednio pod nim. Powstanie jeden czytelny punkt startu. |
| Średni | Drobne etykiety „Fresh”, „Live” i „Tracking” wymagają uważnego czytania. Szczególnie niejednoznaczne jest „LiDAR match — Fresh” — mówi o aktualności, ale nie wyjaśnia jakości dopasowania. | Powiększyć etykiety. Jeżeli liczy się aktualność, pokazać czas od ostatniego pomiaru. Jeżeli liczy się jakość lokalizacji, nazwać ją osobno. |
| Niższy | W panelu magazynu najbardziej charakterystyczną wartością jest długi identyfikator mapy. Wiersz „Storage locations” odsyła do konfiguracji tekstem, który wygląda jak zwykła wartość. | Jeśli operator wybiera magazyn po nazwie, wyeksponować tę nazwę, a identyfikator mapy dać do skopiowania. Przejście do konfiguracji oznaczyć jednoznacznym linkiem. |

**Warto zachować** podział na stan drona i konfigurację magazynu, tekstowe opisy obok kolorów oraz rozróżnienie między statusem „Docked” a potwierdzeniem fizycznego kontaktu ze stacją. To ostatnie pozwala operatorowi sprawdzić, na czym opiera się wskazanie.

Najpierw poprawiłbym widoczność trybu symulacji i hierarchię informacji w lewej karcie. Ocena dotyczy widocznego stanu spoczynkowego. Do oceny obsługi sytuacji awaryjnej najbardziej miarodajny byłby ten sam ekran po utracie lokalizacji lub łączności.

</details>

<details>
<summary>Manual Control</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/06-manual-control.png)

Interfejs dobrze pokazuje, co robi dron, ale słabiej odpowiada na najważniejsze pytanie operatora: **czy mogę teraz bezpiecznie wykonać ruch i co się stanie po naciśnięciu sterowania?** Największy problem widać w prawym panelu. Nagłówek „Protected manual flight” sugeruje aktywną ochronę, pole „Verified clearance” pokazuje „Unavailable”, a przyciski ruchu wyglądają na dostępne.

| Priorytet | Co widać | Co warto zmienić |
|---|---|---|
| Wysoki | Operator musi sam zinterpretować „Unavailable”. Ze zrzutu nie wynika, czy kontroler zablokuje ruch, czy zweryfikuje go dopiero po wydaniu komendy. | Tuż nad przyciskami ruchu opisać faktyczne zachowanie kontrolera. Jeśli ruch jest zablokowany, pokazać przyczynę i oznaczyć niedostępne kierunki. Jeśli sprawdzenie następuje po naciśnięciu, jasno to zapowiedzieć i pokazać wynik przy danej komendzie. |
| Wysoki | Instrukcja „Release it to stop” znajduje się pod kamerą, daleko od sterowania. Obok siebie są też „Hold to move” i „Hold position”, co utrudnia rozróżnienie sposobu obsługi od stanu lotu. | Przy klawiszach umieścić jedną instrukcję: „Przytrzymaj, aby lecieć. Puść, aby zatrzymać drona”. Osobno pokazać bieżący stan lotu i funkcję spacji. |
| Średni | Przy rozdzielczości 1366 × 768 dolna część prawego panelu wychodzi poza ekran. Jednocześnie znaczną część widoku mapy zajmuje puste tło, a model regałów jest mały. | W domyślnym widoku lotu pokazać cały zestaw sterowania bez przewijania. Lepiej wykadrować mapę wokół drona i najbliższych regałów. |
| Średni | „Simulation” ma podobną wagę wizualną jak techniczny status „Mock SAP online”. | Wyraźniej oznaczyć tryb symulacji w stałym miejscu. Status integracji może pozostać mniej eksponowany. |

**Warto zachować** kamerę, mapę i sterowanie obok siebie. Operator może zestawić obraz z kamery z położeniem drona bez przełączania widoku. Przydatne są też stale widoczne zatrzymanie awaryjne w nagłówku oraz prognoza poziomu baterii po powrocie do doku.

Pierwszy test z operatorem przeprowadziłbym właśnie na pokazanym ekranie. Przed dotknięciem klawiatury poprosiłbym go o przewidzenie, co zrobi dron po przytrzymaniu **W** przy „Verified clearance: Unavailable” i co zrobi po puszczeniu klawisza. Porównanie odpowiedzi z rzeczywistym zachowaniem symulatora pokaże, czy panel wystarczająco jasno komunikuje zasady ruchu.

</details>

<details>
<summary>Warehouse Calibration</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/07-warehouse-calibration.png)

Operator widzi, że dron jest w stacji dokującej, przygotowanie zostało zakończone, a kolejnym krokiem jest mapowanie magazynu. **Największą zaletą interfejsu jest wyraźne oddzielenie otwarcia panelu od startu drona. Największą słabością jest sposób komunikowania gotowości.**

**Co działa dobrze**

- Wskaźnik etapów pokazuje, co już wykonano i gdzie operator jest teraz. Aktywny krok „Map warehouse” odpowiada głównemu przyciskowi „Open mapping controls”.
- Pięć kart pozwala szybko sprawdzić warunki przed mapowaniem. Każda podaje stan tekstem, więc operator może odczytać wynik również bez rozróżniania kolorów.
- Przycisk otwierający panel mapowania wyraźnie dominuje nad anulowaniem kalibracji. Sąsiadująca informacja, że start wymaga osobnego polecenia, pomaga przewidzieć skutek kliknięcia.

**Co zmieniłbym w pierwszej kolejności**

1. **Doprecyzować, do czego system jest gotowy.** Nagłówek pokazuje „Calibration in progress”, a panel „Calibration ready”. Operator musi sam ustalić, czy gotowa jest cała kalibracja, czy można rozpocząć mapowanie. Przy pokazanym stanie trafniejsza etykieta to **„Ready for mapping”**. Zdanie „The mapping result is empty” brzmi jak komunikat o problemie. Jeśli mapa ma powstać dopiero w tym kroku, czytelniejsze będzie „No map created yet”.
2. **Powiększyć tekst istotny dla decyzji.** Informacja o osobnej komendzie startu jest drobniejsza i mniej widoczna niż sam przycisk. Warto ją skrócić do **„Takeoff requires a separate command”** i umieścić bezpośrednio pod przyciskiem. Pierwsza część obecnej podpowiedzi tylko powtarza jego nazwę.
3. **Mocniej wyróżnić tryb symulacji.** „Simulation” wygląda podobnie do sąsiedniego wskaźnika „Mock SAP online”, choć określa kontekst pracy całego operatora. Stała, wyraźna etykieta trybu przy nazwie „Control Center” ułatwiłaby jego rozpoznanie jednym spojrzeniem.
4. **Lepiej wykorzystać tytuł panelu.** „Warehouse Calibration” pojawia się w zakładce, nagłówku strony i nagłówku karty. Tytuł karty **„Step 2 of 7 · Map warehouse”** skierowałby uwagę na bieżące zadanie i lepiej wykorzystał najbardziej widoczne miejsce w panelu.

Ocena dotyczy pokazanego ekranu. Przy teście z operatorem sprawdziłbym przede wszystkim, czy przed kliknięciem potrafi powiedzieć, **w jakim trybie pracuje, do czego dron jest gotowy i co dokładnie zrobi główny przycisk**.

</details>

<details>
<summary>Warehouse Configuration</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/08-configuration-before-action-label.png)

Najważniejszy problem jest przy aktywacji konfiguracji. **Wersja aktywna w stacji i wersja wybrana z listy mają tę samą nazwę i numer rewizji, ale różne identyfikatory** (`E5E70FFA` i `AC100C03`). Operator musi porównać dwa ciągi znaków, żeby zauważyć różnicę. Na ekranie służącym do zmiany konfiguracji ta informacja powinna być widoczna od razu.

| Priorytet | Co widać na ekranie | Proponowana zmiana |
|---|---|---|
| Wysoki | `Activate warehouse` i `Plan inspection` są obok siebie w kolejności pracy, choć wybrana konfiguracja różni się od aktywnej. Nie widać, której użyje planowanie. | Pokazać obok siebie „Aktywna w stacji” i „Wybrana do aktywacji”. Przy planowaniu wskazać konfigurację, której użyje system. |
| Wysoki | Pole potwierdzenia mówi ogólnie o „tej rewizji”. Wyjaśnienie, dlaczego przycisk aktywacji jest nieaktywny, znajduje się dopiero pod przyciskiem planowania. | Podać skutek bezpośrednio przy polu potwierdzenia, np. „Zastąp w stacji `E5E70FFA` konfiguracją `AC100C03`”. Zachować osobny krok aktywacji. |
| Średni | Tryb `Simulation` wygląda podobnie do sąsiednich wskaźników `Docked` i `Mock SAP online`. | Nadać trybowi symulacji wyraźne, stałe oznaczenie, zwłaszcza jeśli operator korzysta też z podobnego ekranu do pracy z rzeczywistym dronem. |
| Średni | Nazwa `Warehouse Configuration` pojawia się trzy razy, a etykiety parametrów i komunikaty pomocnicze są drobne. | Zachować tytuł strony, a kartę nazwać według jej funkcji, np. „Wybór i aktywacja konfiguracji”. Zwiększyć czytelność etykiet i wykorzystać część wolnej szerokości na porównanie konfiguracji. |

**Warto zachować** widoczny stan dokowania, informację o braku aktywnej misji oraz dostęp do kontroli integralności, podglądu Digital Twin i przeglądu trasy przed aktywacją. Te elementy pomagają operatorowi podjąć decyzję.

Pierwszy test z operatorem zrobiłbym na pokazanym ekranie. Przed kliknięciem powinien móc bez wahania odpowiedzieć na trzy pytania: „Co jest teraz aktywne?”, „Co zmieni aktywacja?” i „Której konfiguracji użyje planowanie, jeśli kliknę je teraz?”.

</details>

<details>
<summary>Diagnostics</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/09-diagnostics.png)

**Jako ekran diagnostyczny sprawdza się dobrze. Jako główny widok operatora wymaga zbyt dużo czytania.** Na pierwszy rzut oka widać, że dron wraca do stacji, trasa jest wolna, a bilans energii pozwala na powrót. Trudniej równie szybko ocenić, czy operator powinien zareagować.

1. **Wyeksponuj potrzebę interwencji.** Karta „Returning to dock” to właściwe miejsce na krótką ocenę sytuacji. Jeśli logika systemu ją potwierdza, komunikat mógłby brzmieć „Powrót do stacji · interwencja niewymagana”. Przy problemie w tym samym miejscu powinny pojawić się jego przyczyna i oczekiwana reakcja operatora.
2. **Uprość informację o energii.** Operator widzi 61,7%, 27,2%, 34%, 8% i +26,4 p.p. Najważniejszą zależność można podać wprost jako „Przewidywana bateria po powrocie do stacji: ok. 34% · wymagana rezerwa: 8%”. Obecne 34% i 8% wyglądają jak wartości dające 26 p.p. zapasu. Spójna precyzja wyświetlania oszczędzi operatorowi sprawdzania rachunku.
3. **Zwiększ czytelność najważniejszych pól.** Na tym zrzucie etykiety i jednostki są drobne, choć karta telemetrii ma dużo wolnego miejsca. Warto powiększyć stan lotu, wysokość i przewidywaną baterię po powrocie. Wektor kierunku lotu, błąd dopasowania mapy i liczba komórek mogą pozostać w zwartej sekcji technicznej.
4. **Doprecyzuj, co oznacza „Live”.** Nagłówek informuje o symulacji, a niżej pojawiają się „Live position” i „Presence feed live”. Przy szybkiej zmianie stanowiska łatwo odczytać „live” jako dane z fizycznego urządzenia. Stałe, wyraźne oznaczenie trybu oraz podpis „Pozycja w symulacji” rozwiązałyby tę niejednoznaczność.

Zachowałbym podział na podsystemy, tekstowe etykiety obok kolorowych wskaźników i osobne miejsce dla zatrzymania awaryjnego. **Pierwszą zmianą byłoby przeprojektowanie górnej karty tak, aby odpowiadała na trzy pytania operatora: co robi dron, czy bezpiecznie dokończy powrót i czy potrzebna jest reakcja.**

</details>

<details>
<summary>Warehouse Configuration z podpisaną akcją planowania</summary>

[Zrzut przekazany do oceny](final-control-center-evidence/08-warehouse-configuration.png)

**Operator może szybko sprawdzić, że dron jest zadokowany i żadna misja nie trwa. Trudniej odpowiedzieć na ważniejsze pytanie: której konfiguracji użyje następna inspekcja?** To główny problem tego ekranu.

1. **Pokaż obok siebie konfigurację aktywną i wybraną do aktywacji.** Obie nazywają się „Learned warehouse” i mają numer „Rev 2”. Różnią się dopiero końcowym identyfikatorem (`E5E70FFA` i `AC100C03`). Operator musi sam zauważyć tę różnicę w dwóch miejscach ekranu. Dwa wyraźnie podpisane bloki „Aktywna w stacji” i „Wybrana do aktywacji”, z wyróżnionymi identyfikatorami, ułatwiłyby sprawdzenie wyboru jednym spojrzeniem.
2. **Powiąż każdą akcję z konkretną konfiguracją.** „Plan with active warehouse” znajduje się pod szczegółami wybranej rewizji. Po zmianie wyboru na liście łatwo odnieść wrażenie, że przycisk zaplanuje inspekcję właśnie dla niej. Umieściłbym planowanie przy aktywnej konfiguracji, a pod wybraną zostawił akcję „Aktywuj AC100C03 w stacji”. Powód niedostępności tego przycisku warto umieścić bezpośrednio przy polu potwierdzenia. Obecnie instrukcję oddziela od pola jeszcze przycisk planowania.
3. **Wzmocnij widoczność trybu pracy.** „Simulation” ma podobną wagę wizualną jak „Docked” i „Mock SAP online”. Jeśli operator korzysta również z rzeczywistego systemu, tryb symulacji zasługuje na większe, stale widoczne oznaczenie w nagłówku.
4. **Popraw czytelność wierszy z danymi.** Na pokazanej rozdzielczości etykiety są drobne, a po prawej pozostaje sporo wolnego miejsca. Warto zwiększyć rozmiar etykiet i odstępy, a miejsce odzyskać przez usunięcie powtórzonego nagłówka „Warehouse Configuration”. Zachowałbym tekstowe statusy „Verified” i „Approved” — można je odczytać niezależnie od koloru.

**Pierwszy test z operatorem:** poproś go, żeby bez zmieniania ustawień wskazał, z której konfiguracji skorzysta „Plan with active warehouse”, a następnie pokazał, jak zaplanować inspekcję dla `AC100C03`. To sprawdzi, czy rozumie różnicę między wyborem zapisanej rewizji a jej aktywacją. Ocena opiera się na jednym zrzucie, więc przebieg po kliknięciu wymaga osobnej weryfikacji.

</details>
