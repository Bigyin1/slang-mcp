# Linux release artifacts

CI builds and tests the release executable on Ubuntu 24.04 x86-64 using Clang 23,
LLD and the Ubuntu GCC 14 C++ runtime. The downloadable archive contains the
server, license files and README, with a separate SHA-256 checksum. It targets
Ubuntu 24.04 x86-64 and compatible systems with the required glibc and libstdc++;
it is not a statically linked universal Linux binary.

The normal CI workflow builds the same archive and retains it as an Actions
artifact. Pushing a `v*` tag starts the release workflow. It checks out the tagged
commit, requires the tag to match `v` plus the CMake project version, builds and
tests the binary, and creates a GitHub Release with the archive and checksum only
after the build succeeds. An existing release is not overwritten. A manual workflow
run builds an Actions artifact without creating a release. The workflow does not
create or move Git tags.

For a local Ubuntu 24.04 x86-64 build with Clang 23, LLD 23, GCC 14, CMake,
Ninja and dependencies installed, run `scripts/linux-release.sh`. Inspect the
resulting `dist/linux/` archive and run `sha256sum -c` on its checksum file.
