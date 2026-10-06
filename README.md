# ConsolePi+

Documentation for **ConsolePi+ 1.9.1** ([release](https://github.com/jiriflos-eng/ConsolePi-Plus/releases/tag/v1.9.1)).

![ConsolePi+ 1.9.1 administration overview](docs/screenshots/1.9.1/01-prehled.jpg)

Screenshots were captured on a test Raspberry Pi on 6 October 2026. Addresses
and settings shown are examples; the disconnected console has no USB adapter assigned.
See the [interface gallery](docs/WEB-UI.md) and [security assessment documents](docs/security/README.md).

ConsolePi+ turns a Raspberry Pi 3 into a secure, web-managed serial console
server for network equipment. Each attached USB serial adapter is mapped to an
SSH port (for example, `2201` to `2204`) and opens a Cisco-compatible serial
console at 9600 8N1 by default.

The web interface currently ships in Czech. The public documentation is
available in English here and in Czech in [README.cs.md](README.cs.md).

## Features

- SSH administration on port `22` and restricted serial-console sessions on
  ports `2201`–`2204`;
- stable USB adapter identification, port labels and serial settings;
- exclusive per-port locking, serial-session and connection logging;
- local password, SSH public-key, or RADIUS authentication for console ports;
- web setup wizard, network configuration, firewall access-source allowlist,
  optional SNMPv3, CDP/LLDP and health monitoring;
- local-network ConsolePi Plus discovery through mDNS/Bonjour, with a portable
  macOS, Windows and Linux command-line client;
- signed application updates and a first-boot workflow suitable for cloned or
  custom SD-card images.

## Ready-to-flash image with Raspberry Pi Imager

[ConsolePi+ 1.9.1 release](https://github.com/jiriflos-eng/ConsolePi-Plus/releases/tag/v1.9.1)
includes the generic image and [Imager manifest](https://github.com/jiriflos-eng/ConsolePi-Plus/releases/download/v1.9.1/ConsolePi-Plus-1.9.1.rpi-imager-manifest).
Open the downloaded manifest, or set its URL under Imager Settings → Content Repository → Edit.
For a repository URL that follows the latest release, use:

    https://github.com/jiriflos-eng/ConsolePi-Plus/releases/latest/download/ConsolePi-Plus.rpi-imager-manifest

The version-specific manifest above stays pinned to 1.9.1.
Select Raspberry Pi 3, ConsolePi+ 1.9.1 and the SD card, then enable key-only SSH with one Ed25519 public key.
For static Ethernet IPv4, edit `consolepi-network.txt` on the boot partition after flashing and before the first boot.
See [the installation guide](docs/INSTALACE-IMAGE-RPI-IMAGER.txt) for SSH-only customization and recovery.

## Quick installation on Raspberry Pi OS Lite

Download the matching installer first from
[ConsolePi-Plus-1.9.1-install.tar.gz](https://github.com/jiriflos-eng/ConsolePi-Plus/releases/download/v1.9.1/ConsolePi-Plus-1.9.1-install.tar.gz).
Its [SHA-256 checksum](https://github.com/jiriflos-eng/ConsolePi-Plus/releases/download/v1.9.1/ConsolePi-Plus-1.9.1-install.tar.gz.sha256) is
published alongside it.

1. Use Raspberry Pi Imager to write **Raspberry Pi OS Lite (64-bit)** to the
   SD card. Configure an administrator named `consolepi`, enable SSH with
   public-key authentication, and use DHCP for the initial network connection.
   The separate generic ConsolePi+ image must instead follow its key-only guide.
   Its first-boot wizard requires an IPv4 management CIDR. Only TCP
   22/80/443 are temporarily reachable before that allow-list is committed.
2. Boot the Pi, connect Ethernet, then use **ConsolePi Plus Discovery** as the
   first step to find its local IP address. Build the portable client from
   [tools/consolepi-discover](tools/consolepi-discover) with the command in
   [Find ConsolePi Plus on the local network](#find-consolepi-on-the-local-network).
3. Update the base operating system:

       ssh -i "$HOME/.ssh/consolepi-admin" consolepi@PI_ADDRESS
       sudo apt update
       sudo apt full-upgrade -y
       sudo reboot

4. Copy the release bundle to the `consolepi` home directory:

       scp -i "$HOME/.ssh/consolepi-admin" ConsolePi-Plus-1.9.1-install.tar.gz consolepi@PI_ADDRESS:~/

5. Log in again and run the bootstrap installer:

       install_dir="$HOME/consolepi-install"
       mkdir -p "$install_dir"
       tar --no-same-owner -xzf "$HOME/ConsolePi-Plus-1.9.1-install.tar.gz" -C "$install_dir"
       cd "$install_dir"
       ./bootstrap-install.sh

6. Open `https://PI_ADDRESS/` and complete the first-boot wizard. It sets the
   web password, device identity, host keys and administrative SSH access.

For a detailed Czech clean-install guide, see
[docs/INSTALACE-RPI3.md](docs/INSTALACE-RPI3.md). For a compressed custom SD
image, see [docs/INSTALACE-IMAGE-RPI-IMAGER.txt](docs/INSTALACE-IMAGE-RPI-IMAGER.txt).

## APT repositories after installation

ConsolePi+ uses the official Debian and Raspberry Pi repositories by default.
For a network without direct Internet access, open **Network → APT repositories**
and switch to a local mirror. Enter separate HTTP/HTTPS base URLs for Debian,
Debian Security and Raspberry Pi; ConsolePi+ validates all three in an isolated
`apt-get update` before replacing the active configuration. The proxy setting is
independent and can be used with either source option. The initial bootstrap
still needs reachable package sources or a suitable proxy.

## SSH keys

Create an Ed25519 key pair on the administrator workstation:

    ssh-keygen -t ed25519 -f "$HOME/.ssh/consolepi-admin" -C "consolepi-admin"

Keep `consolepi-admin` private. The `.pub` file is safe to paste into Raspberry
Pi Imager or into the ConsolePi+ first-boot wizard. Windows PowerShell users
should first run `New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh"`,
then use the equivalent `ssh-keygen` command.

After an intentional reinstall or identity regeneration, independently verify
the new SSH host-key fingerprint. Only then remove the known old entry before reconnecting:

    ssh-keygen -R IP_RPI

## Find ConsolePi Plus on the local network

ConsolePi+ publishes a minimal `_consolepi._tcp.local` mDNS/Bonjour service.
The optional `consolepi-discover` client lists the IPv4 address, HTTPS URL and
SSH command without scanning the subnet. It works on macOS, Windows and Linux
from a single Go source tree in `tools/consolepi-discover`.

The separately distributed Discovery client remains available in the
[ConsolePi+ v1.9.0 release](https://github.com/jiriflos-eng/ConsolePi-Plus/releases/tag/v1.9.0):
macOS (Apple Silicon and Intel), Windows x64, and Linux (x64 and ARM64).
The accompanying `consolepi-discover-v1.9.0.sha256` file verifies the downloads.
The macOS and Windows ZIP downloads contain a `ConsolePi Plus Discovery` folder and
a launcher for the bundled desktop application. On macOS, verify the checksum
before double-clicking `Spustit ConsolePi Plus Discovery.command`; on Windows use
`Spustit ConsolePi Plus Discovery.cmd` and follow SmartScreen if it appears.

The service is limited to the current Ethernet/VLAN segment. It deliberately
does not cross routers; use a known IP address or configure an mDNS reflector
when discovery is needed across routed networks.

mDNS discovery is not authentication. Before entering credentials, verify the
HTTPS certificate warning or the SSH host-key fingerprint as usual.

Build standalone clients with Go 1.22+:

    ./tools/build-consolepi-discover.sh

For development, run `go run . --timeout 5s` from `tools/consolepi-discover`.
The binary opens the local graphical page by default, bound only to
`127.0.0.1`, with refresh, HTTPS and SSH-copy controls. Use `--shell` for
terminal output or `--help` for all options.

## Zabbix monitoring

ConsolePi+ exports read-only SNMPv3 `authPriv` metrics. The ready-to-import
[Zabbix 7.4 template](zabbix/template_consolepi_snmpv3_7.4.yaml) monitors CPU,
temperature, memory, root filesystem, uptime, cached update and reboot state,
Ethernet link, required ConsolePi+ services, and the four serial-console ports.
See the [Zabbix setup guide](zabbix/README.md). Add the Zabbix server or proxy
to **Síť → Povolené zdroje přístupu** before enabling SNMPv3; UDP/161 is never
open outside this allowlist.

## Development and release safety

A development checkout can contain local build output and confidential material.
Build release archives from a clean checkout and inspect them before publishing:

    ./tools/build-public-source.sh

The script creates a source archive that excludes local SSH keys, signing
private keys, release artifacts, disk images and macOS metadata. Review the
archive before publishing. The public signing key
`release-signing-private.pem.pub` may be published; the matching private key
must never leave the release administrator's secure workstation.

Read [PUBLIC_RELEASE.md](PUBLIC_RELEASE.md) before publishing. The project is
licensed under [MIT](LICENSE); retain upstream license notices.

## Security reporting

Please do not publish security-sensitive issues, credentials, device
configuration, serial transcripts or private keys. See
[SECURITY.md](SECURITY.md).

### Offline Ethernet configuration for generic images

The released 1.9.1 generic image includes `consolepi-network.txt` on the FAT boot
partition. After writing the card in Imager, edit it to set `MODE=static`,
`ADDRESS=192.168.1.50/24`, `GATEWAY=192.168.1.1` and
`DNS=192.168.1.1,1.1.1.1` (use your own network values). Gateway and DNS
may be empty for an isolated LAN. The default is `MODE=dhcp`.

Settings are imported before NetworkManager starts, then the file is renamed
to `.applied` so later web changes persist. Invalid input blocks network startup
and writes a `.error` file on the same partition. Fix the file offline and reboot.
See the [image installation guide](docs/INSTALACE-IMAGE-RPI-IMAGER.txt).
The published 1.9.0 generic-v16 image predates this feature and must be rebuilt;
copying the configuration file alone into that image does not enable it.

## Logging and security assessment

The default **events** mode stores no terminal transcript. In the 1.9.1 source,
`consolepi-session` uses the native `picocom --logfile` output recorder for both
**output** and **full** modes. Operator input is not separately recorded, but a
device can echo commands or return secrets in its output. The active session
path does not invoke the redaction writer; do not rely on the web's “redaction”
or “bidirectional” labels as guarantees. Use events mode when terminal contents
must not be stored. See [the security assessment](docs/security/README.md) for
source references, screenshot context and tests still requiring execution.
