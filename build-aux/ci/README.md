# Native validation and releases

Every PR and push to `master` runs a complete native Meson build,
including translations and documentation, on Ubuntu 24.04 and 26.04. The jobs
run the registered tests, stage the installation, build a native Debian package,
install that package on the disposable runner, and open a fresh image under a
private X server/session bus with memory-backed settings. This checks package
layout, resources, schemas and window initialization. It does not replace manual
Wayland, image editing or tablet validation.

The packages retain Debian/Ubuntu's Python module location and the existing
application/desktop identity. Package-manager file triggers refresh desktop,
icon and GSettings caches. Installation does not alter user documents or
preferences. Install the package matching the distribution with
`sudo apt install ./drawing_<version>-1+ubuntu26.04_all.deb` (or the 24.04 package).
A rollback reinstalls the previously saved package, preserving user data.

## Release preparation checklist

Before tagging a stable release:

- Update the version and date consistently in Meson, AppStream and the Debian
  changelog, together with any compatibility metadata affected by the release.
- Describe observable changes in the AppStream release notes. Mention toolkit,
  API or control-flow details only when they affect compatibility or how someone
  uses the application. Add the release to the bundled `help/C/whats_new.page`.
- When application metadata or help changes, regenerate `po/drawing.pot` with
  `utils-bash/translations.sh src_pot` and `help/C/drawing.pot` with
  `utils-bash/translations.sh help_pot`. Review added and removed messages, the
  report address and identifiers that should not be translated.
- Review the README and AppStream screenshots whenever the release materially
  changes the interface or toolkit. If the existing images no longer represent
  the application, add optimized captures under `docs/screenshots/<version>/`,
  check them against their captions and update every consuming URL.
- Run the full Meson build and test suite and validate the AppStream metadata.
  Explain any intentionally deferred release surface in the release pull request.

For a stable release, merge reviewed changes through branch protection, update
Meson and AppStream version metadata in that PR, then push its version tag
(`v1.2.0`, for example). The tag must identify a commit in protected `master`
history. To publish an older, unpublished tag in that history, run the workflow
from `master` and supply `release_tag`.
Release dispatch from other branches fails before building or publication.
This retains the tag's source unchanged and uses the current reviewed build
infrastructure. A blank dispatch runs CI only. Never move an existing tag.

Enable repository release immutability before releasing. Only after both native
builds and installed-package smoke tests pass does the publication job create a
draft, upload all packages, deterministic source archive, build manifests and
SHA256SUMS, download and verify every asset, and publish it as latest. Publication
locks the assets and tag and GitHub generates a release attestation. Release
notes and the latest designation remain editable. A failed upload leaves an
unpublished draft; a retry verifies existing bytes and fills missing assets.
Use `gh release verify 1.0.2` (with the corresponding tag) for a published
release. Rebuilding its source with newer packaging tools can change package
bytes. Asset corrections require a new version.

CI runs use read-only tokens and no project secrets. Only publication receives
`contents: write`. External PR code runs on GitHub-hosted runners. Required branch
checks should be the two stable `Native ubuntu-*` job names, without path filters
that could leave required checks pending. Protect `master` and release tags
without administrator or automation bypasses. A sole maintainer may merge their
own PR after checks; requiring someone else's GitHub approval would prevent this.

Before the first continuity release, compare its installed source and behavior
with the deployed distribution package. Rebuilding the same upstream version
establishes continuity; it does not establish that later development changes are
safe. Keep exhaustive comparison probes and host-specific evidence out of the
maintained suite. Retain focused regression tests where recurring coverage
justifies their maintenance cost.

The publishing token needs `contents: write`, not repository administration.
Enable immutable releases in repository settings before the first publication.
The workflow verifies the published release's `immutable` flag and exact assets;
GitHub's administration-only policy endpoint is not accessible to GITHUB_TOKEN.

GTK4 pull requests and pushes to master build the GNOME 51 Flatpak manifest
with the pinned official builder and SDK container. The SDK runs raster and
metadata checks. The native jobs run the full GUI suite, real codec round
trips, and installed-window smoke. The Flatpak job uploads a validation
bundle. The release workflow publishes the native packages and source archive.

Native CI installs GTK3 and GTK4 introspection runtimes because protected release
dispatch may rebuild an older GTK3 tag. The package and installed smoke helpers
read the source's declared GTK API before loading GTK; GTK4 packages depend on
GTK 4.10 or newer, while old tags keep their GTK3 dependency. This is build-tool
support for existing releases, not a second application backend.
