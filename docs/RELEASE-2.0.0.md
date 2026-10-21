# Image ConsolePi+ 2.0.0 — kontrola předběžného vydání

Datum sestavení: 21. 10. 2026. Cíl: Raspberry Pi 3 B/B+, arm64.

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

## Dosud neprovedeno pro tento nový obraz

Čerstvý zápis přes Raspberry Pi Imager, fyzický první boot, dokončení webového
průvodce a následný reboot na RPi 3. Dále dlouhodobý zátěžový test a fyzická
sériová konzole. Testy předchozího 1.9.1 obrazu ani testy modulu na běžícím
RPi tyto kroky pro nový obraz nenahrazují.

Proto je 2.0.0 označená jako **prerelease**; stabilní latest zůstává 1.9.1.
Pro test 2.0.0 použijte pevný manifest přiložený k vydání, nikoli latest URL.
Po úspěšné fyzické přejímce lze stejné vydání povýšit na stabilní.
