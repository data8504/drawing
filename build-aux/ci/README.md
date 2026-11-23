# Native validation and releases

Every PR and push to `master` or `stable/1.0` runs a complete native Meson build,
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

For a stable release, merge reviewed changes through branch protection, update
Meson and AppStream version metadata in that PR, then push its version tag
(`v1.2.0`, for example). The tag must identify a commit in protected `master` or
`stable/1.0` history. Existing older tags such as `1.0.2` can be rebuilt by running
the workflow from the protected default branch and supplying `release_tag`.
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
A published release is only verified on retry, never replaced. Asset corrections
require a new version.

CI runs use read-only tokens and no project secrets. Only publication receives
`contents: write`. External PR code runs on GitHub-hosted runners. Required branch
checks should be the two stable `Native ubuntu-*` job names, without path filters
that could leave required checks pending. Protect both release branches and tags
without administrator or automation bypasses. A sole maintainer may merge their
own PR after checks; requiring someone else's GitHub approval would prevent this.

Before the first continuity release, compare its installed source and behavior
with the deployed distribution package. Rebuilding the same upstream version
establishes continuity; it does not establish that later development changes are
safe. Keep exhaustive comparison probes and host-specific evidence out of the
maintained suite. Retain focused regression tests where recurring coverage
justifies their maintenance cost.
