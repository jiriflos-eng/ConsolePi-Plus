# Ping Monitor

Modul je v administraci pod `/ping`. Přepínač **Zapnout monitorování** je také přímo na hlavním přehledu. Po instalaci je sběr vypnutý. Vypnutí zachová zařízení a historii; běžící sonda se může dokončit, její výsledek se při vypnutém sběru nezapíše. Služba zůstává spuštěná a kontroluje přepínač jednou za sekundu, takže web nepotřebuje oprávnění pro systemctl.

## Rychlé nastavení od verze 2.0.0

1. Přihlaste se do administrace, zapněte Ping Monitor a otevřete jeho nastavení.
2. Zvolte **Přidat zařízení**, vyplňte název a IP/hostname. Pro začátek ponechte
   interval 30 s, timeout 1 s a jednu sondu. Otazník u každého pole vysvětlí význam.
3. Uložte zařízení. Přehled otevřete tlačítkem **Otevřít přehled**; dlaždice
   a TOP tabulky jsou na úvodním dashboardu pod Sériovými konzolemi.
4. Kliknutím na dlaždici otevřete historii. Zvolte časový rozsah; najetím myši
   zjistíte přesný čas a hodnotu. Grafy packet loss a jitteru mají gradient
   v barvě křivky. Nulová hodnota nemá pod osou žádnou výplň.
5. Vypnutí modulu zachová data a skryje veřejný přehled. Po zapnutí se evidovaná
   mezera ukáže žlutě; výpadek zařízení se odlišuje světle červenou.

Předběžný image 2.0.0 neobsahuje cíle, historii ani přístupové údaje. Sběr je
výchozí vypnutý. Sanitizace zastaví sběrač a odstraní celý obsah jeho datového
adresáře včetně SQLite WAL/SHM, incidentů a intervalů vypnutí. Nejde o postup
pro běžnou aktualizaci: ta provozní data zachovává.

## Instalace a aktualizace

Použijte standardní `install.sh` nebo podepsaný aktualizační balíček. Čistá instalace instaluje `fping`; offline aktualizace nové balíčky nestahuje. Na starších systémech se použije dostupný Linux `iputils-ping`, pokud fping chybí. Bez obou programů vzniká UNKNOWN s chybou, nikoliv DOWN. Pro doporučený režim na starším systému nainstalujte `fping` z repozitáře distribuce nebo z důvěryhodného offline balíčku.

Instalátor vytvoří `/var/lib/consolepi-ping` (0700, účet consolepi-web), provede migraci a zapne `consolepi-ping.service`. Schéma používá `PRAGMA user_version`; nepodporovanou novější verzi odmítne. Data nejsou v `/opt`, aktualizace je nepřepisuje. Nové webové soubory a jednotka jsou součástí instalačního i podepsaného aktualizačního payloadu. Podepisovací postup se nemění. Aktualizační builder nyní také vynechává pracovní outputs/downloads/dist-public, aby nebalil lokální prostředí testů.

Diagnostika na Raspberry Pi:

```sh
systemctl status consolepi-ping
journalctl -u consolepi-ping --since '-30 min'
systemctl show consolepi-ping -p MemoryCurrent -p CPUUsageNSec -p TasksCurrent
sudo du -h /var/lib/consolepi-ping
```

Účet služby je neprivilegovaný existující consolepi-web, má pouze síťovou capability CAP_NET_RAW a zapisuje do svého StateDirectory. Služba používá zámek souboru proti druhé instanci, 4 pracovní vlákna, Nice=10, CPUQuota=20%, MemoryMax=96M a TasksMax=24. Neslouží žádný nový port. Flask používá stávající cookie, autentizaci, HTTPS/nginx, first-boot gate a CSRF token. API mutace odmítá prázdný token. Příkazy jsou seznamy argumentů s oddělovačem `--`, bez shellu. Firewall, sériové konzole a SSH se nemění.

## Zařízení, limity a význam statistik

Adresa je IPv4, IPv6 bez scope ID nebo ASCII DNS hostname; IDN zadejte jako punycode. Interval 5–3600 s, timeout 0,1–5 s, 1–5 sond v cyklu. Cyklus musí vejít do intervalu. Fping spouští každou sondu zvlášť a ukládá její skutečný UTC čas zahájení a RTT, nikoli dopočítané časy ze souhrnu cyklu. Náhradní iputils-ping zaokrouhluje timeout nahoru na celou sekundu a výsledek `time<1` eviduje konzervativně jako 1 ms; pro přesnost pod 1 ms používejte fping. Bez překrytí stejného zařízení; rozpracované výsledky staré konfigurace se zahazují.

Nejvýše 128 konfigurací, zároveň nejvýše 8 sond/s a součet `probes × (timeout + 0,05) / interval` nejvýše 3. Tyto konzervativní meze omezují zatížení čtyř workerů při nedostupných cílech. Doporučený výchozí profil k přejímce: 32 zařízení, 30 sekund, jedna sonda, timeout 1 sekunda. Nejde o ověřenou kapacitu Raspberry Pi 3; hardwarová přejímka níže je stále nutná.

UP vyžaduje standardně dvě úspěšné sondy, DOWN tři ztracené sondy; prahy jsou nastavitelné. Incident začíná prvním neúspěchem potvrzené sekvence. RTT ≥ varovnému prahu nebo ztráty nad prahem v posledních 20 relevantních sondách znamenají DEGRADED při dostupnosti. Absolutní kritický RTT práh eviduje významné špičky; relativní detekce porovnává hodnotu s předchozí exponenciální baseline a varovným prahem.

Relevantní sondy pro packet loss a dostupnost: `ok`, `timeout`, `unreachable`. DNS, interní chyba a neprovedené měření mají RTT NULL a do jmenovatele nevstupují. Dostupnost je podíl úspěšných relevantních sond, nikoliv časově vážená SLA. Jitter je průměr absolutních rozdílů sousedních úspěšných RTT bez ztráty/neznámé mezery mezi nimi. Maximum v TOP je vždy skutečné maximum úspěšných sond. Doba posledního úspěchu je samostatný časový údaj. Statistiky za období zahrnují celé okrajové agregační intervaly (minuta do 30 dní, 5 minut do 90 dní, hodina pro delší rozsah).

Restart, vypnutí, pauza či změna konfigurace ukončí rozpracovaný incident jako `monitoring_gap`; UI uvede, že další stav je neznámý. Nejde o důkaz obnovení zařízení. Chybějící heartbeat nebo zastaralé měření znamená UNKNOWN. Po delší mezeře další zápis vloží `not_measured` marker; chybějící sběr není packet loss. Časy jsou UTC epochy, prohlížeč zobrazuje místní zónu.

## Historie a retence

SQLite používá WAL, busy_timeout=10 s a indexy. Zápisy výsledků všech dokončených cyklů i všech úrovní agregací probíhají v jedné transakci, obvykle jednou za sekundu. Úklid běží jednou za hodinu. SQLite uvolněné stránky znovu používá; pravidelný VACUUM se záměrně neprovádí kvůli SD kartě. Online zálohu vytvářejte SQLite backup API, nekopírujte pouze hlavní soubor během běhu bez WAL.

| Data | Retence |
|---|---|
| Jednotlivé sondy | 7 dní |
| Minutové agregace | 30 dní |
| Pětiminutové agregace | 90 dní |
| Hodinové a denní agregace | 730 dní |
| Uzavřené incidenty, změny alarmů a významné špičky | 730 dní |

Každá agregace obsahuje min/max s původními časy, součty RTT, počty úspěchů, ztrát a neznámých měření a jitter součty/počty. Po odstranění raw zůstane minimum a maximum každého uchovaného intervalu, **ne každý původní jednotlivý vzorek nebo každá menší špička**. Samostatná tabulka peaks uchovává všechny špičky splňující detekční práh po 730 dní.

Live graf používá nejvýše přibližně 600 bucketů. Rozsahy od 48 hodin používají podle šířky grafu 24–96 bucketů, každý nejvýše se dvěma skutečnými extrémy. Krátká historie čerpá raw, delší předagregované úrovně; měsíc a rok vycházejí z denních agregací. Při širším rozsahu se několik dní může sloučit do jednoho zobrazovaného intervalu; zachovají se jeho skutečná minima/maxima s původními časy a doplňková typická latence. Při přiblížení se zobrazí jemnější intervaly. Bucketování je ukotvené k UTC, první a poslední bucket mohou přesahovat požadovanou hranici. Pořadí extrémů je chronologické. Graf nepřipojuje intervaly se ztrátami, UNKNOWN či delším odstupem, ztráty a incidenty odlišuje podbarvením. Detail obsahuje RTT, packet loss a jitter; čas lze přiblížit a posunout. Canvas renderer je lokální, bez CDN a dalších závislostí. Tooltip ukazuje přesný čas zaznamenané sondy, nikoliv střed bucketu.

Alarmy RTT, ztrát a délky potvrzeného výpadku zapisují pouze změny stavu do tabulky alarms. Ta je odděleným zdrojem událostí pro budoucí doručovací adaptér (e-mail/Telegram/webhook); doručování v této verzi není implementováno. Údržba potlačuje nové alarmy do konce zvoleného okna (UI nabízí hodinu i plánované datum od/do; API `maintenance_start` a `maintenance_until` jsou UTC epochy). Stávající aktivní alarmy jsou během údržby skryté. Potvrzení incidentu nezastaví sběr.

## API a CSV

Všechny cesty vyžadují stávající přihlášení. Mutace vyžadují `X-CSRF-Token` se session tokenem (nebo formulářové `csrf`).

- GET `/ping/api/overview?period=3600`: zařízení, stavy, statistiky pro všechna TOP pořadí, velikost DB. Volitelně `group`.
- POST `/ping/api/settings`: JSON `{"enabled":true}` nebo false.
- POST `/ping/api/devices`: nové zařízení. POST `/ping/api/devices/ID`: částečná úprava; DELETE: odstranění včetně historie.
- GET `/ping/api/history/ID?period=172800`: omezená historická řada a incidenty; volitelně UTC `start`/`end`.
- GET `/ping/api/events?period=3600`: aktivní alarmy, otevřené incidenty, historie alarmů, incidenty a peaks (historické seznamy nejvýše 500 řádků).
- POST `/ping/api/incidents/ID/ack`: potvrzení incidentu.
- GET/POST `/ping/api/csv`: export nebo multipart import `file` (UTF-8, max. 256 KiB / 128 řádků). Import je atomický, přidává zařízení; neupravuje existující. Povinné sloupce `name,address`, volitelné odpovídají DEFAULTS v ping_monitor.py. Export chrání text před tabulkovými vzorci apostrofem.

## Ověření a přejímka Raspberry Pi 3

Lokálně:

```sh
python3 tests/ping_behavior.py
python3 tests/ping_web_behavior.py  # Flask a cryptography
sh tests/check.sh
```

Testy pokrývají maximum 450 ms z řady 8,9,10,450,12 včetně timestampu a retence, více špiček, vážené počty ztrát/UNKNOWN, UTC půlnoc a DST, migraci, stavovou hysterezi, validaci, omezený scheduler při 128 konfiguracích, ochranu argumentů subprocess, autentizaci, CSRF, CRUD, atomický CSV import a šablonu.

Na skutečném Pi 3 před produkcí ověřte 24 hodin doporučeného profilu včetně nedostupných cílů, DNS chyby, IPv6, více sond, restartu služby a rebootu. Měřte CPU/RSS, scheduler odstupy, růst DB a odezvu sériové konzole před/za běhu monitoringu. Ověřte přepínač a zachování DB po podepsané offline aktualizaci, čas extrému v ročním grafu a obnovu ze zálohy. Při restartu musí zůstat mezera UNKNOWN a nesmí vzniknout nový plošný DOWN. Akceptační cíl: RSS pod 96 MiB, průměrný CPU pod kvótou 20 % jednoho jádra, bez pozorovatelného zhoršení konzolí a bez opakovaných restartů služby. Tyto hardwarové výsledky nejsou v tomto prostředí ověřeny; lokální test není náhradou přejímky.


## Krátká hardwarová přejímka 21. 10. 2026

Ověřeno na Raspberry Pi 3 Model B Plus Rev 1.3, Debian 13 (arm64), ConsolePi+ 1.9.1. Nasazení bylo cíleným doplněním Ping Monitoru do instalované verze, nikoliv zkouškou nového podepsaného vydání. Původní web je na testovacím zařízení zálohován v `/var/backups/consolepi-ping-test/web-before-ping.tar.gz`.

- Všech 13 testů enginu a API prošlo přímo na Pi.
- Skutečné IPv4/IPv6 a gateway sondy: UP. Nedostupný testovací cíl: DOWN po třech ztrátách; DNS chyba: UNKNOWN. Cyklus tří sond ukládal tři jednotlivé odezvy.
- Ověřena pauza, vypnutí sběru bez nových raw vzorků, restart služby bez falešných incidentů, zachování skutečného maxima a jeho času v historickém API a SQLite integrity_check=ok.
- Zátěž: 32 konfigurací, interval 30 sekund, 45,1 sekund měření. Všechny konfigurace byly vzorkovány. Průměrná CPU spotřeba celé systemd služby včetně sond byla 4,23 % jednoho jádra; maximální RSS samotného Python sběrače 16 984 KiB (16,6 MiB), bez RSS krátce běžících fping procesů. Nejde o 24hodinový ani dlouhodobý retenční test.
- Web při této krátké zátěži neprokázal zpomalení: administrace 6,97 s před sběrem / 6,47 s při sběru, stránka Ping 1,45 / 1,38 s. Jsou to jednotlivá měření včetně stávajících systémových helperů, nikoliv statistický benchmark.
- Ověřeny skutečné HTTPS odpovědi přes nginx s validací místního certifikátu, chráněné API, CSRF odmítnutí a přepínač v hlavním dashboardu. Neotevřel se další port. SSH proces zůstal stejný, web/nginx/port-monitor/ssh zůstaly aktivní.
- Systém nemá aktivní paměťový cgroup řadič (`cgroup.controllers` neobsahuje memory). Deklarovaný MemoryMax se na tomto konkrétním systému nevynucuje. CPU kvóta je dostupná. Nastavení bootu se během testu neměnilo.
- Fyzické sériové zařízení nebylo připojeno, jeho skutečná odezva nebyla otestována. Reboot celého Pi, podepsaná offline aktualizace a dlouhodobá zátěž zůstávají k přejímce.

Dočasné zátěžové a poruchové konfigurace byly odstraněny. Sběr zůstal zapnutý pro localhost a výchozí bránu v intervalu 30 sekund. Podrobné lokální protokoly jsou v pracovním adresáři `outputs/ping-rpi3` a nejsou zahrnovány do vydání.


## Dlaždice a TOP přehled na úvodní stránce

Na úvodním dashboardu je pod sériovými konzolemi sekce Ping Monitor s ikonou, barevnými dlaždicemi a třemi TOP tabulkami (skutečné maximum RTT, počet incidentů, packet loss). Sekce se zobrazí pouze při zapnutém modulu; stav se kontroluje každých 15 sekund. Dlaždice otevírá `/ping/view/ID`, detail s grafy latence, ztrát a jitteru, volbou rozsahu, přiblížením a historií výpadků.

Tento přehled a detail jsou dle zadání dostupné i před přihlášením. Read-only API `/ping/public/summary` a `/ping/public/history/ID` funguje jen při zapnutém monitoru a nevrací adresy zařízení, popisy konfigurace, prahy ani chybové zprávy subprocessů. Při vypnutí summary vrátí pouze `enabled=false,devices=[]`, detail a historie vrací 404. Konfigurační API, zapnutí/vypnutí, import/export i potvrzování incidentů zůstávají autentizované a mutace chráněné CSRF. Public odpovědi se necachují. Přehledy používají skutečná data z SQLite; prázdné období či absence incidentů se zobrazí výslovně bez ukázkových hodnot.

Administrace `/ping` nyní obsahuje pouze konfiguraci zařízení, přepínač sběru, import/export a údržbu. Grafy, statistické žebříčky a historii zobrazuje úvodní dashboard a detail `/ping/view/ID`. Autentizovaný GET `/ping/api/devices` poskytuje lehký seznam konfigurací bez výpočtu historických statistik.

Historická API přijímají volitelné `buckets=1..1000` jako rozpočet zobrazovaných intervalů. Bez parametru platí od 48 hodin 96 intervalů, u kratších rozsahů 600. Velikost bucketu se zarovnává na uchovanou agregační úroveň. Redukce je pouze pro zobrazení: původní retenční agregace a významné špičky se nemění.

Grafy podbarvují evidované vypnutí sběru a pozastavení zařízení jemně žlutě, potvrzené výpadky světle červeně. Tooltip uvádí začátek a konec intervalu. Křivka nepřemosťuje vypnutý sběr. Intervaly se evidují od migrace databáze na verzi 2; starší neznámé mezery se zpětně neoznačují jako vypnutí. Vypnutí není ztracená sonda a neovlivňuje počty ztrát.
