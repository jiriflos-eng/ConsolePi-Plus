"""Import data-only IPv4 settings before NetworkManager starts."""
import ipaddress
import os
from pathlib import Path
import stat
import sys
import tempfile

NAME = "consolepi-network.txt"
PROFILE = Path("/etc/NetworkManager/system-connections/Wired connection 1.nmconnection")


def unicast(value):
    address = ipaddress.IPv4Address(value)
    if address.is_unspecified or address.is_loopback or address.is_multicast or int(address) >= 0xf0000000:
        raise ValueError("Use a unicast IPv4 address")
    return address


def profile_text(text):
    values = {}
    for number, line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or key not in {"MODE", "ADDRESS", "GATEWAY", "DNS"}:
            raise ValueError(f"Invalid setting on line {number}")
        if key in values:
            raise ValueError(f"Duplicate setting: {key}")
        values[key] = value
    mode = values.get("MODE")
    if mode not in {"dhcp", "static"}:
        raise ValueError("MODE must be dhcp or static")
    ipv4 = "method=auto\n"
    if mode == "static":
        address = values.get("ADDRESS", "")
        if "/" not in address:
            raise ValueError("ADDRESS must include a prefix, e.g. 192.168.1.50/24")
        interface = ipaddress.IPv4Interface(address)
        unicast(str(interface.ip))
        if interface.network.prefixlen == 0:
            raise ValueError("ADDRESS prefix must be between 1 and 32")
        if interface.network.prefixlen < 31 and interface.ip in (
                interface.network.network_address, interface.network.broadcast_address):
            raise ValueError("ADDRESS must be a host address, not network or broadcast")
        ipv4 = f"method=manual\naddress1={interface}\n"
        gateway = values.get("GATEWAY", "")
        if gateway:
            gateway = unicast(gateway)
            if gateway == interface.ip or gateway not in interface.network:
                raise ValueError("GATEWAY must be another host in the ADDRESS subnet")
            if interface.network.prefixlen < 31 and gateway in (
                    interface.network.network_address, interface.network.broadcast_address):
                raise ValueError("GATEWAY must not be network or broadcast")
            ipv4 += f"gateway={gateway}\n"
        dns = values.get("DNS", "")
        if dns:
            servers = [str(unicast(item.strip())) for item in dns.split(",")]
            ipv4 += "dns=" + ";".join(servers) + ";\n"
        ipv4 += "ignore-auto-dns=true\n"
    return ("[connection]\nid=Wired connection 1\ntype=ethernet\n"
            "interface-name=eth0\nautoconnect=true\n\n[ethernet]\n\n[ipv4]\n"
            + ipv4 + "\n[ipv6]\nmethod=auto\naddr-gen-mode=default\n")


def atomic_write(path, content, mode=0o600):
    fd, temporary = tempfile.mkstemp(prefix=".consolepi-network-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            if mode is not None:
                os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply(boot, profile=PROFILE):
    source = boot / NAME
    error = boot / (NAME + ".error")
    if not source.exists() and not source.is_symlink():
        return False
    try:
        with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Configuration must be a regular file")
            data = stream.read(16385)
        if len(data) > 16384:
            raise ValueError("Configuration exceeds 16 KiB")
        content = profile_text(data.decode("utf-8-sig"))
        # Validate everything before replacing the existing profile. Replaying
        # this write after power loss is safe; consume the input only afterwards.
        atomic_write(profile, content)
        os.replace(source, boot / (NAME + ".applied"))
        error.unlink(missing_ok=True)
        os.sync()
        return True
    except (ValueError, OSError) as exc:
        try:
            atomic_write(error, "ConsolePi network configuration failed: " + str(exc)
                         + "\nCorrect consolepi-network.txt and reboot.\n", mode=None)
        except OSError:
            pass
        raise


def main():
    mount = Path("/etc/consolepi/imager-boot-mount").read_text().strip()
    boot = Path(mount)
    if not boot.is_absolute() or boot.parent != Path("/boot") or not boot.is_mount():
        raise ValueError("Invalid or unmounted ConsolePi firmware partition")
    if apply(boot):
        print("ConsolePi Ethernet configuration imported")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(f"ConsolePi boot network: {error}", file=sys.stderr)
        sys.exit(1)
