# ConsolePi+ public release checklist

The public repository is [jiriflos-eng/ConsolePi-Plus](https://github.com/jiriflos-eng/ConsolePi-Plus),
licensed under [MIT](LICENSE). The current release is **1.9.1**. Use this
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
For 1.9.1 the release contains:

- `ConsolePi-Plus-1.9.1-generic.img.xz`;
- `ConsolePi-Plus-1.9.1-install.tar.gz` and `ConsolePi-Plus-1.9.1-source.tar.gz`;
- per-archive SHA-256 files and `SHA256SUMS`;
- `ConsolePi-Plus-1.9.1.rpi-imager-manifest` and the stable-name alias
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
Publish only the sanitized image and its checksums.

Signed `.cpiupdate` application packages are a separate distribution mechanism.
Do not imply that such a package exists for a release without publishing it;
1.9.1 assets currently include the image, source and installer listed above.
Keep previously published release assets and tags immutable when only updating
repository documentation.

## Documentation and third-party notices

Update both READMEs, installation guides, security policy and release notes for
the new version. Keep historical release notes and separately versioned Discovery
client links accurate. Use repository-local, dated screenshots with explanatory
captions. Audit material must distinguish illustration from executed test evidence.
Retain upstream licenses and notices for Raspberry Pi OS/Debian and other
components; do not imply vendor endorsement.
