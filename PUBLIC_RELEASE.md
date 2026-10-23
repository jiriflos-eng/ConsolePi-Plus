# ConsolePi+ public release checklist

The public repository is [jiriflos-eng/ConsolePi-Plus](https://github.com/jiriflos-eng/ConsolePi-Plus),
licensed under [MIT](LICENSE). The current source version is **2.0.0**; the
stable image/archive release is **2.0.0 (image r3)**, tagged **v2.0.0-r3**.
Fresh installation, web setup and reboot acceptance passed on 23 October 2026. Use this
checklist for subsequent publication; repository creation and license selection
have already been completed.

## Source and confidential material

Create a clean source archive with `./tools/build-public-source.sh` and inspect
its contents before publishing. Never commit private signing/SSH keys, device
configuration, customer information, logs, transcripts or configured disk images.
The public signing key can be distributed; its private counterpart stays on the
release administrator's workstation. Build from a clean, reviewed checkout;
local untracked output must not enter a release archive.

## Release artifacts

Use title **ConsolePi+ vX.Y.Z** and prefix `ConsolePi-Plus-X.Y.Z-*`.
For 2.0.0 the stable release contains:

- `ConsolePi-Plus-2.0.0-r3-generic.img.xz`;
- `ConsolePi-Plus-2.0.0-install.tar.gz` and `ConsolePi-Plus-2.0.0-source.tar.gz`;
- per-archive SHA-256 files and `SHA256SUMS`;
- `ConsolePi-Plus-2.0.0-r3.rpi-imager-manifest` and the stable-name alias
  `ConsolePi-Plus.rpi-imager-manifest`;
- Imager icons and the image installation guide.

The manifest must reference the matching image URL, compressed/extracted sizes,
SHA-256 values and supported SSH customization. Check both the pinned URL and
`releases/latest/download/ConsolePi-Plus.rpi-imager-manifest` in Imager before
publication. A URL following latest can change version; use the pinned manifest
for reproducible deployment.

Generic images must be sanitized and validated before publication. Remove
administrator keys, device identity, web password, TLS private key, configured
networks, proxy/mirror settings, secrets and logs. Verify fresh first boot and
reboot with key-only SSH, the web wizard, and DHCP/static boot provisioning.
Publish only the sanitized image and its checksums. A prerelease must clearly
identify pending physical first-boot/reboot checks; promote it to stable only
after those checks pass. The latest-release manifest continues to resolve to
the previous stable release until promotion.

Ping sanitization stops `consolepi-ping.service`, empties its whole StateDirectory
(including SQLite/WAL/SHM, device targets and pause history), and verifies that
no data remains. Free ext4 blocks and the journal must also be scrubbed before
compression; logical file deletion alone is insufficient.

Signed `.cpiupdate` application packages are a separate distribution mechanism.
Do not imply that such a package exists for a release without publishing it;
2.0.0 release assets include the image, source and installer listed above.
See [build validation and hardware acceptance](docs/RELEASE-2.0.0.md).
Keep previously published release assets and tags immutable when only updating
repository documentation.

## Documentation and third-party notices

Update both READMEs, installation guides, security policy and release notes for
the new version. Keep historical release notes and separately versioned Discovery
client links accurate. Use repository-local, dated screenshots with explanatory
captions. Audit material must distinguish illustration from executed test evidence.
Retain upstream licenses and notices for Raspberry Pi OS/Debian and other
components; do not imply vendor endorsement.

The original image, archive, manifest and SHA256SUMS assets are immutable.
`IMAGE-VALIDATION.json` records build-time checks and their then-pending hardware
steps. The subsequent `HARDWARE-ACCEPTANCE.json` and its separate SHA-256 file
record completed installation acceptance without rewriting those build assets.
