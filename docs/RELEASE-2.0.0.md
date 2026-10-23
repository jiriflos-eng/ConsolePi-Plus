# Image ConsolePi+ 2.0.0 — sestavení a hardwarová přejímka

Aktuální revize image: **2.0.0-r3**, 22. 10. 2026. Verze aplikace: **2.0.0**. Cíl: Raspberry Pi 3 B/B+, arm64.

## Revize r3: úplná oprava prvotního HTTPS

Revize r3 obsahuje opravu firstboot skriptu, který před vystavením HTTPS
certifikátu počká na globální IPv4 rozhraní eth0. Zachovává opravený start
služeb z r2, klíčovou autentizaci i podmínky úspěšného Imager provisioningu.
Verze aplikace se nemění: **2.0.0**.

Regresní test spouští skutečný blok vystavení certifikátu s opožděně
přidělenou testovací IP a kontroluje IP SAN v hotovém X.509 certifikátu.
Druhý scénář ověřuje timeout bez vytvoření certifikátu a klíče. Oba běží
v dočasném adresáři; do distribučního obrazu žádné testovací klíče nevstupují.

Obraz je sestaven z čistého offline základu, bez kopírování provozní SD karty.
Validátor ověřuje povolené služby, prázdnou Ping DB, absentující identity,
firstboot pending, konfiguraci bootu a syntaxe SSH/firewall/systemd. Čerstvý
první start a reboot r3 prošly dne 23. 10. 2026; samostatný záznam je níže.
Starší výsledky opraveného r2 se evidují odděleně.

## Oprava prvního obrazu

První image 2.0.0 z 21. 10. 2026 měl po offline sestavení zakázané služby
SSH a webu. Při fyzickém testu RPi odpovídalo na ping, ale odmítalo TCP/22 a
TCP/443. Příčinou byl chybný závěrečný krok sestavení, nikoli SSH klíč uživatele.
Tento obraz je označený jako vadný a nemá se používat pro nové instalace.

Revize r2 ponechává SSH, nginx, web, port monitor, Ping Monitor a aktualizační
časovač povolené pro boot. Závislosti na generic firstboot se zachovávají;
služby se uvolní až po úspěšném ověření Imager nastavení. Nový validátor
kontroluje povolení každé jednotky zvlášť. Na kopii původního obrazu se jeho
kontrola prokazatelně zastavila na `ssh_enabled`; po opravě všechny kontroly
prošly. Tím se neoslabuje autentizace ani první provisioning.

## Původ a sestavení

Obraz vychází z dříve sanitizovaného a na RPi ověřeného generic image 1.9.1
(Debian/Raspberry Pi OS 13, arm64), nikoli z provozní SD karty. Do pracovní
kopie byl v odděleném Linux prostředí instalován zdrojový payload 2.0.0.
Nová závislost `fping` byla přidána z oficiálního APT repozitáře obrazu.
Boot firmware, jádro, rozložení oddílů a Imager provisioning pocházejí ze základu.

Při offline instalaci jsou restart/reload služeb odloženy a enable/disable
operace zapisuje skutečný systemctl v offline režimu. Migrace management
subnetu z běžícího NetworkManageru se vynechává: čistý základ už obsahuje
prázdnou generic politiku. Tyto úpravy se týkají jen dočasného instalačního
skriptu sestavení; distribuovaný instalátor zůstává beze změny.

Po instalaci byly odstraněny dočasné SSH/TLS/web identity, instalační zálohy,
logy, runtime soubory a data Ping Monitoru. Žurnál ext4 byl nově vytvořen a
souborový systém zrekonstruován pouze z alokovaných bloků; volné bloky se
nepřebírají. Čistý FAT boot oddíl a mezery mezi oddíly se zachovávají ze základu.

## Provedené kontroly

- zdrojové automatické testy, včetně Ping Monitoru (12 + 7 testů), CSV a CSRF;
- regresní test sanitizace SQLite/WAL/SHM a bezpečného zacházení se symlinky;
- `consolepi-validate-generic-image`: PASS v offline chrootu se skutečnými
  kontrolami souborů, účtů, SSH konfigurace, firewallu a systemd jednotek;
- negativní test původního obrazu (`ssh_enabled` FAIL), následný PASS po
  povolení všech požadovaných jednotek;
- samostatná kontrola jednotky `consolepi-ping.service` a přítomnosti `fping`;
- ext4 `e2fsck`: bez chyb po vyčištění;
- byte scan hotového obrazu: žádný úplný privátní klíč ve volných blocích;
  zbývající klíčové ukázky jsou výhradně ve veřejných vendor testech/příkladech;
- prázdný adresář Ping Monitoru, žádné cíle, historie, alarmy či pauzy;
- žádné SSH host/user klíče, webové heslo/secret, TLS identita ani machine-id
  konkrétního zařízení; generic provisioning zůstává `pending`;
- velikosti a SHA-256 raw obrazu, XZ i instalačních archivů v manifestu/checksums.

Veřejný soubor `IMAGE-VALIDATION.json` u vydání uvádí vazbu na zdrojový commit,
kontrolní součty a stav jednotlivých kontrol. Lokální pracovní kopie a provozní
data testovacího RPi nejsou součástí vydání.

## Fyzický test r2 · 22. 10. 2026

První boot opravené revize r2 na Raspberry Pi 3 úspěšně provedl Imager
provisioning. SSH s klíčem správce, nginx, web a Ping sběrač byly aktivní.
Čistá databáze měla sběr vypnutý, nula cílů a nula vzorků.

Při ověření HTTPS se ukázal závod prvního startu: certifikát vznikl dříve,
než NetworkManager přidělil Ethernetu IPv4, a neobsahoval IP SAN. Na testovacím
zařízení byl obnoven za běhu a HTTPS pak s plným ověřením názvu/IP vrátilo
úvodního průvodce. Zdrojový firstboot nově čeká na globální IPv4 rozhraní eth0
před vystavením certifikátu; regresní test pokrývá pozdější přidělení adresy
i timeout. Tato dodatečná oprava není obsažena v již vydaných immutable
souborech r2. Před stabilním vydáním je nutný nový build a jeho přejímka.

Po dokončení webového průvodce prošel i řízený reboot tohoto testovacího RPi.
Zůstal dokončený provisioning, statický síťový profil a HTTPS s plným ověřením
certifikátu. SSH, nginx, web a Ping služba byly po startu aktivní. Konfigurace
jednoho zařízení se nezměnila (ověřeno hashem), historie zůstala zachovaná a
po restartu přibyly nové sondy; zařízení přešlo do UP. Test proběhl na r2
s dodatečně opraveným certifikátem a aktualizovaným firstboot skriptem.

## Krátké provozní doměření · 22. 10. 2026

Na testovacím RPi3 s jedním zapnutým cílem během 35,1 s přibyly dvě sondy;
zařízení zůstalo UP. Sběrač spotřeboval průměrně 1,24 % jednoho CPU jádra a
16,4 MiB RSS. SSH, nginx, web i sběrač byly aktivní, HTTPS vracelo 200 bez
přesměrování do průvodce a statický profil zůstal zachovaný. SQLite
`PRAGMA quick_check` vrátilo `ok`. Teplota CPU byla přibližně 54,8 °C a firmware
vrátil `throttled=0x0`. Jde o krátké provozní měření jednoho cíle, nikoli
kapacitní ani dlouhodobý zátěžový test.

## Fyzická přejímka r3 · 23. 10. 2026

Uživatel potvrdil instalaci nového image r3 přes Imager. Na RPi3 byl ověřen
firstboot skript shodný s vydaným payloadem, dokončený provisioning, SSH přes
klíč správce a HTTPS s plným ověřením certifikátu. Nebylo potřeba obnovovat
certifikát ani měnit soubory systému. Síť při této přejímce používala DHCP.

Po řízeném restartu se změnilo boot ID, služby SSH/nginx/web/Ping byly aktivní,
web vrátil HTTP 200 přes ověřené HTTPS a průvodce se znovu neotevřel. Síťový
profil, nastavení tří monitorovaných zařízení (porovnáno hashem) i historie
zůstaly zachované. Přibyly nové sondy, heartbeat byl čerstvý a SQLite quick_check
vrátilo `ok`. Veřejné Ping API nevracelo adresy zařízení.

R3 je na základě této přejímky označená jako **stabilní** a alias latest vede
na `v2.0.0-r3`. Verze aplikace zůstává **2.0.0**. Dříve publikované image,
archivy, manifesty, SHA256SUMS ani původní IMAGE-VALIDATION.json se nemění:
ten zachycuje stav při sestavení. Následnou přejímku uvádí samostatný soubor
HARDWARE-ACCEPTANCE.json s vlastním SHA-256 u vydání.

## Rozsah a zbývající testy

Jde o přejímku instalace a restartu na Raspberry Pi 3. Není tím doložená
kapacita při dlouhodobé zátěži ani funkce připojené fyzické sériové konzole;
tyto provozní testy zůstávají samostatné. Starší fyzický test statické adresy
na opraveném r2 je výše; zde proběhl boot přes DHCP.
