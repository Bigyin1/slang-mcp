# Linux release artifacts

CI builds and tests the release executable on Ubuntu 24.04 x86-64 using Clang 23,
LLD and the Ubuntu GCC 14 C++ runtime. The downloadable archive contains the
server, license files and README, with a separate SHA-256 checksum. It targets
Ubuntu 24.04 x86-64 and compatible systems with the required glibc and libstdc++;
it is not a statically linked universal Linux binary.

The normal CI workflow builds the same archive and retains it as an Actions
artifact. The separate release workflow can be run manually for a test artifact;
when a GitHub Release is explicitly published, it checks out its tag, requires
that tag to match `v` plus the CMake project version, builds and tests the binary,
and attaches the archive and checksum to that release. Existing release assets
are not overwritten. No tag or release is created by these workflows.

For a local Ubuntu 24.04 x86-64 build with Clang 23, LLD 23, GCC 14, CMake,
Ninja and dependencies installed, run `scripts/linux-release.sh`. Inspect the
resulting `dist/linux/` archive and run `sha256sum -c` on its checksum file.
