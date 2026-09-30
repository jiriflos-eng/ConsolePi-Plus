#!/usr/bin/env python3
"""Exercise boot imports without changing the host's network."""
import configparser
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "usr/local/lib"))
import consolepi_boot_network as network
import consolepi_imager_security as imager

STATIC = "MODE=static\nADDRESS=192.168.20.10/24\nGATEWAY=192.168.20.1\nDNS=192.168.20.1,1.1.1.1\n"


class BootNetworkTests(unittest.TestCase):
    def test_static_windows_text(self):
        profile = configparser.ConfigParser()
        profile.read_string(network.profile_text("\ufeff# My settings\r\n" + STATIC.replace("\n", "\r\n")))
        self.assertEqual(profile["connection"]["interface-name"], "eth0")
        self.assertEqual(profile["connection"]["id"], "Wired connection 1")
        self.assertEqual(profile["ipv4"]["method"], "manual")
        self.assertEqual(profile["ipv4"]["address1"], "192.168.20.10/24")
        self.assertEqual(profile["ipv4"]["gateway"], "192.168.20.1")
        self.assertEqual(profile["ipv4"]["dns"], "192.168.20.1;1.1.1.1;")

    def test_dhcp_template(self):
        profile = network.profile_text((ROOT / "usr/share/consolepi/consolepi-network.txt").read_text())
        self.assertIn("method=auto", profile)
        self.assertNotIn("192.168", profile)
        self.assertNotIn("dns=", profile)

    def test_isolated_network_and_netmask(self):
        profile = network.profile_text("MODE=static\nADDRESS=192.168.20.10/255.255.255.0\nGATEWAY=\nDNS=\n")
        self.assertIn("address1=192.168.20.10/24", profile)
        self.assertNotIn("gateway=", profile)
        self.assertNotIn("\ndns=", profile)

    def test_reject_bad_settings(self):
        for content in ("", "MODE=dhcp\nMODE=static", "MODE=dhcp\nTYPO=1", "MODE=static",
                        "MODE=automatic", "MODE=static\nADDRESS=$(touch /tmp/unsafe)/24",
                        STATIC.replace("/24", ""), STATIC.replace("/24", "/33"),
                        STATIC.replace("/24", "/0"),
                        STATIC.replace("192.168.20.10/24", "192.168.20.0/24"),
                        STATIC.replace("192.168.20.10/24", "192.168.20.255/24"),
                        STATIC.replace("192.168.20.10/24", "127.0.0.1/24"),
                        STATIC.replace("192.168.20.10/24", "224.0.0.1/24"),
                        STATIC.replace("GATEWAY=192.168.20.1", "GATEWAY=192.168.30.1"),
                        STATIC.replace("GATEWAY=192.168.20.1", "GATEWAY=192.168.20.10"),
                        STATIC.replace("GATEWAY=192.168.20.1", "GATEWAY=192.168.20.255"),
                        STATIC.replace("1.1.1.1", "not-an-ip"),
                        STATIC.replace("1.1.1.1", "1.1.1.1,")):
            with self.subTest(content=content), self.assertRaises(ValueError):
                network.profile_text(content)

    def test_import_once_recovery_and_dhcp(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(network.os, "sync", create=True):
            boot = Path(directory)
            profile = boot / "wired.nmconnection"
            profile.write_text("old settings")
            source = boot / network.NAME
            source.write_text(STATIC)
            self.assertTrue(network.apply(boot, profile))
            self.assertFalse(source.exists())
            self.assertTrue((boot / (network.NAME + ".applied")).exists())
            self.assertEqual(profile.stat().st_mode & 0o777, 0o600)
            profile.write_text("later web settings")
            self.assertFalse(network.apply(boot, profile))
            self.assertEqual(profile.read_text(), "later web settings")
            source.write_text("MODE=static\nADDRESS=bad")
            with self.assertRaises(ValueError):
                network.apply(boot, profile)
            self.assertTrue(source.exists())
            self.assertEqual(profile.read_text(), "later web settings")
            self.assertTrue((boot / (network.NAME + ".error")).exists())
            source.write_text("MODE=dhcp\n")
            self.assertTrue(network.apply(boot, profile))
            self.assertIn("method=auto", profile.read_text())
            self.assertFalse((boot / (network.NAME + ".error")).exists())

    def test_invalid_files_and_failed_write_preserve_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            boot = Path(directory)
            source = boot / network.NAME
            profile = boot / "wired.nmconnection"
            profile.write_text("unchanged")
            for data in (b"\xff", b"#" * 16385):
                source.write_bytes(data)
                with self.assertRaises(ValueError):
                    network.apply(boot, profile)
                self.assertEqual(profile.read_text(), "unchanged")
            source.unlink()
            source.symlink_to(profile)
            with self.assertRaises(OSError):
                network.apply(boot, profile)
            source.unlink()
            os.mkfifo(source)
            with self.assertRaises(ValueError):
                network.apply(boot, profile)
            source.unlink()
            source.write_text(STATIC)
            with patch.object(network.os, "replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    network.apply(boot, profile)
            self.assertEqual(profile.read_text(), "unchanged")
            self.assertTrue(source.exists())

    def test_sanitizer_removes_previous_network_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            boot = Path(directory)
            (boot / "config.txt").write_text("# firmware\n")
            (boot / "cmdline.txt").write_text("console=tty1 root=PARTUUID=1234\n")
            for suffix in ("", ".applied", ".error"):
                (boot / (network.NAME + suffix)).write_text(STATIC)
            imager.sanitize_boot_partition(boot)
            self.assertFalse(any(boot.glob("consolepi-network*")))


if __name__ == "__main__":
    unittest.main()
