# Image ConsolePi+ 2.0.0 — kontrola předběžného vydání

Opravená revize image: **2.0.0-r2**, 22. 10. 2026. Verze aplikace: **2.0.0**. Cíl: Raspberry Pi 3 B/B+, arm64.

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

## Dosud neprovedeno pro tento nový obraz

Čerstvý zápis přes Raspberry Pi Imager, fyzický první boot, dokončení webového
průvodce a následný reboot na RPi 3. Dále dlouhodobý zátěžový test a fyzická
sériová konzole. Testy předchozího 1.9.1 obrazu ani testy modulu na běžícím
RPi tyto kroky pro nový obraz nenahrazují.

Proto je 2.0.0 označená jako **prerelease**; stabilní latest zůstává 1.9.1.
Pro test 2.0.0 použijte pevný manifest přiložený k vydání, nikoli latest URL.
Po úspěšné fyzické přejímce lze stejné vydání povýšit na stabilní.
