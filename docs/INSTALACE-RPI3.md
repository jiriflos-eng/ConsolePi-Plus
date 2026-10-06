# ConsolePi+ 1.9.1: čistá instalace na Raspberry Pi 3

Pro standardní zápis hotového ConsolePi+ použijte
[návod pro generic image a manifest Imageru](INSTALACE-IMAGE-RPI-IMAGER.txt).
Tento postup je alternativní instalace na čistý Raspberry Pi OS Lite (64-bit).
Výsledné zařízení má vlastní identitu, SSH hostitelské klíče, HTTPS certifikát
a webové heslo. Soukromý SSH klíč správce zůstává na jeho počítači.

## Co je potřeba

- Raspberry Pi 3 Model B/B+, stabilní zdroj a microSD alespoň 16 GB;
- Ethernet do management sítě s DHCP;
- Raspberry Pi Imager, SSH klient a vlastní veřejný klíč Ed25519;
- dostupné zdroje APT nebo odpovídající proxy pro bootstrap;
- [instalační archiv 1.9.1](https://github.com/jiriflos-eng/ConsolePi-Plus/releases/download/v1.9.1/ConsolePi-Plus-1.9.1-install.tar.gz)
  a jeho [SHA-256](https://github.com/jiriflos-eng/ConsolePi-Plus/releases/download/v1.9.1/ConsolePi-Plus-1.9.1-install.tar.gz.sha256).

## 1. Příprava OS a SSH

V Imageru vyberte Raspberry Pi 3 a Raspberry Pi OS Lite (64-bit). Nastavte
uživatele `consolepi`, jeho vlastní heslo a SSH pouze veřejným klíčem. To platí
pro čistý Raspberry Pi OS; generic image ConsolePi+ už účet obsahuje a přijímá
pouze SSH customizaci podle samostatného návodu.

Klíč vytvoříte na macOS/Linuxu:

```sh
ssh-keygen -t ed25519 -f "$HOME/.ssh/consolepi-admin" -C "consolepi-admin"
```

Do Imageru vložte celý obsah `.pub`. Pro Windows a podrobnosti viz
[český README](../README.cs.md#1-vytvoření-ssh-klíče).
Po zápisu a ověření spusťte RPi s Ethernetem. IP zjistěte v DHCP serveru nebo
pomocí [ConsolePi Plus Discovery](../README.cs.md#nalezení-consolepi-plus-v-lokální-síti).

## 2. Aktualizace základního systému

```sh
ssh -i "$HOME/.ssh/consolepi-admin" consolepi@IP_ADRESA_PI
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

Po restartu pokračujte. Bootstrap potřebuje aktuální systém a dostupné balíčky.

## 3. Ověření a přenos archivu

V adresáři se staženými soubory na macOS:

```sh
shasum -a 256 -c ConsolePi-Plus-1.9.1-install.tar.gz.sha256
scp -i "$HOME/.ssh/consolepi-admin" ConsolePi-Plus-1.9.1-install.tar.gz consolepi@IP_ADRESA_PI:~/
ssh -i "$HOME/.ssh/consolepi-admin" consolepi@IP_ADRESA_PI
```

Na Linuxu lze použít `sha256sum -c`; ve Windows `Get-FileHash -Algorithm SHA256`
a hodnotu porovnat s checksumem. Na RPi rozbalte archiv bez přebírání vlastníků:

```sh
install_dir="$HOME/consolepi-install"
mkdir -p "$install_dir"
tar --no-same-owner -xzf "$HOME/ConsolePi-Plus-1.9.1-install.tar.gz" -C "$install_dir"
cd "$install_dir"
./bootstrap-install.sh
```

Archiv obsahuje soubory přímo v kořenu, nikoli další adresář pojmenovaný podle
verze. Bootstrap spusťte bez `sudo`. Převezme síť z `eth0` jako první povolený
zdroj. Jinou management síť lze určit pomocí
`./bootstrap-install.sh --management-cidr 10.176.122.0/24`.

Při vlastním sestavení ze zdrojů použijte `./tools/build-install-bundle.sh`;
výstup pro VERSION 1.9.1 je `dist/ConsolePi-Plus-1.9.1-install.tar.gz`.

## 4. Dokončení ve webovém průvodci

Otevřete `https://IP_ADRESA_PI/`. U prvního lokálního HTTPS certifikátu ověřte
identitu zařízení a poté pokračujte průvodcem: nastavte webové heslo, název,
hostname, administrativní veřejný SSH klíč a případně rozšiřte kořenový oddíl.
Po dokončení se přihlaste tlačítkem **Admin**. Konzole začínají nepřiřazené;
připojte USB adaptéry a nastavte popisy a sériové parametry.

Průvodce regeneruje hostitelské klíče. Po zamýšlené změně identity nezávisle
ověřte nový fingerprint a teprve potom odstraňte starý známý záznam pomocí
`ssh-keygen -R IP_ADRESA_PI`.

## 5. Kontrola a běžná údržba

```sh
ssh -i "$HOME/.ssh/consolepi-admin" consolepi@IP_ADRESA_PI
cat /usr/share/consolepi/VERSION
sudo consolepi-diagnose
sudo systemctl status consolepi-web nginx ssh nftables consolepi-port-monitor --no-pager
```

Přiřazenou sériovou konzoli otevřete pomocí
`ssh -tt -p 2201 console@IP_ADRESA_PI` s metodou zvolenou v **Autentizace**.
Účet `console` má vynucenou sériovou relaci bez administrativního shellu a tunelů.

- **Síť**: povolené zdroje přístupu, proxy a ověřované APT repozitáře.
- **Systém → Údržba**: samostatné systémové aktualizace a podpisem ověřované
  aplikační balíčky `.cpiupdate`. Aplikace odmítá stejnou nebo nižší verzi.
- **Systém → Logování konzolových portů**: ponechte **Pouze události**, pokud
  se nesmí ukládat obsah terminálu. Režimy output/full v 1.9.1 zaznamenávají
  výstup přes picocom bez obsahové redakce; zařízení může vypsat tajemství.
- **Síť → SNMPv3**: volitelné `authPriv`, dostupné pouze z management allowlistu;
  viz [Zabbix](../zabbix/README.md).
- Zálohy a reset mění provozní konfiguraci; před použitím posuďte jejich dopad.

[Obrazový přehled](WEB-UI.md) vysvětluje jednotlivé panely.
[Bezpečnostní podklady](security/README.md) obsahují nevyhodnocené akceptační
testy; samotné screenshoty potvrzení testů nenahrazují.
