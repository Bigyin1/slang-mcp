# Build and install

Use CMake 3.28 or newer and a C++26 compiler. The implementation is tested with
LLVM/Clang 23.1.5. Slang's build uses Python to generate its parser and diagnostic
sources; Python is not required to run the resulting executable.

```sh
CXX=/path/to/llvm/bin/clang++ cmake --preset dev
cmake --build --preset dev --parallel 6
build/cpp/slang_mcp
```

CMake fetches pinned versions of Slang, the MCP C++ SDK, nlohmann/json, and Catch2.
Upstream tools, Python bindings, and upstream tests are excluded. On macOS, all
targets use the system SDK's libc++ headers and runtime consistently.
Slang's mimalloc integration defaults to off on macOS because it can abort during
process shutdown; `SLANG_USE_MIMALLOC` remains available as a CMake option.
Release builds with upstream LLVM on macOS also use matching `llvm-ar`,
`llvm-ranlib`, and `ld64.lld` tools for the MCP SDK's ThinLTO archives.

For a release build, use the `release` configure and build presets. To install:

```sh
cmake --install build/release --prefix /your/install/prefix
```

Configure the MCP client to launch the executable over stdio:

```json
{
  "mcpServers": {
    "slang": {
      "command": "/absolute/path/to/slang-mcp/build/cpp/slang_mcp",
      "args": []
    }
  }
}
```
