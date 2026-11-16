# Linux release artifacts

CI builds and tests the release executable in a digest-pinned
`manylinux_2_28_x86_64` container using Clang 23.1.5, LLD and GCC 14's C++ runtime.
The downloadable archive is flat: `slang_mcp`, agent instructions in `AGENTS.md`,
README and documentation as Markdown files, and license texts in `LICENSES.md`.
It contains no directories or source/schema files. A SHA-256 checksum is published
alongside the archive. It targets Linux x86-64 with **glibc 2.28 or
newer**. libstdc++ and libgcc are linked statically, so the target does not need
the build machine's C++ runtime. glibc remains dynamically linked.

Before packaging, CI runs all native tests in the glibc 2.28 container and checks
the ELF version requirements. Requirements above `GLIBC_2.28`, unsupported glibc
ABI names, or shared C++/sanitizer runtimes fail the release build. The separate
Ubuntu sanitizer job checks memory safety; its binary is not distributed.

Native glibc 2.18 execution is not supported by this build. If an older host has
a complete glibc 2.28 sysroot, launch via that sysroot's loader and libraries:

```sh
/opt/sysroot/lib64/ld-linux-x86-64.so.2 \\
  --library-path /opt/sysroot/lib64:/opt/sysroot/usr/lib64 \\
  /absolute/path/to/slang_mcp
```

Adjust loader/library paths for the sysroot layout. Configure the MCP client to
run this command, or place it in a launcher script. This uses the sysroot's glibc
without replacing the host's libc. The host kernel must still support that runtime.

The normal CI workflow builds the same archive and retains it as an Actions
artifact. Pushing a `v*` tag starts the release workflow. It checks out the tagged
commit, requires the tag to match `v` plus the CMake project version, builds and
tests the binary, and creates a GitHub Release with the archive and checksum only
after the build succeeds. An existing release is not overwritten. A manual workflow
run builds an Actions artifact without creating a release. The workflow does not
create or move Git tags.

To reproduce the release, use the container pinned in the workflow, install the
toolchain with `.github/actions/portable-linux-toolchain/action.yml`, and run
`scripts/linux-release.sh` inside it. Inspect the resulting `dist/linux/` archive
and run `sha256sum -c` on its checksum file. Ordinary development builds still use
the host's libc and do not establish release compatibility.
