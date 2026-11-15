cmake_minimum_required(VERSION 3.28)
project(slang_mcp VERSION 0.1.2 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 26)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(APPLE)
    execute_process(COMMAND xcrun --show-sdk-path OUTPUT_VARIABLE macos_sdk
        OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
    add_compile_options(-stdlib=libc++ -nostdinc++ "SHELL:-isystem ${macos_sdk}/usr/include/c++/v1")
    add_link_options(-stdlib=libc++)
endif()
if(APPLE AND CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    get_filename_component(llvm_bin "${CMAKE_CXX_COMPILER}" DIRECTORY)
    find_program(SLANG_MCP_LLVM_AR NAMES llvm-ar HINTS "${llvm_bin}")
    find_program(SLANG_MCP_LLVM_RANLIB NAMES llvm-ranlib HINTS "${llvm_bin}")
    if(SLANG_MCP_LLVM_AR AND SLANG_MCP_LLVM_RANLIB)
        set(CMAKE_AR "${SLANG_MCP_LLVM_AR}")
        set(CMAKE_RANLIB "${SLANG_MCP_LLVM_RANLIB}")
    elseif(CMAKE_BUILD_TYPE STREQUAL "Release")
        message(FATAL_ERROR "LLVM Release builds on macOS require matching llvm-ar and llvm-ranlib")
    endif()
endif()

include(FetchContent)
include(CTest)
include(GNUInstallDirs)

set(SLANG_INCLUDE_TOOLS OFF CACHE BOOL "" FORCE)
set(SLANG_INCLUDE_TESTS OFF CACHE BOOL "" FORCE)
set(SLANG_INCLUDE_PYLIB OFF CACHE BOOL "" FORCE)
set(SLANG_INCLUDE_INSTALL OFF CACHE BOOL "" FORCE)
# Slang's mimalloc build can abort during process shutdown on macOS.
if(APPLE)
    set(SLANG_USE_MIMALLOC OFF CACHE BOOL "Use mimalloc in Slang")
endif()
option(SLANG_MCP_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
if(SLANG_MCP_SANITIZERS)
    if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
        message(FATAL_ERROR "Sanitizers require Clang or GCC")
    endif()
    set(SLANG_USE_MIMALLOC OFF CACHE BOOL "" FORCE)
    add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer -fno-sanitize-recover=all)
    add_link_options(-fsanitize=address,undefined -fno-sanitize-recover=all)
endif()
set(MCP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(MCP_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(MCP_WITH_OPENSSL OFF CACHE STRING "" FORCE)
FetchContent_Declare(slang
    GIT_REPOSITORY https://github.com/MikePopoloski/slang.git
    GIT_TAG 42710c788ce76cd08ce2080773e0b8286c428a05 EXCLUDE_FROM_ALL SYSTEM)
FetchContent_Declare(mcp_sdk
    GIT_REPOSITORY https://github.com/jesspig/modelcontextprotocol-cpp-sdk.git
    GIT_TAG 93e18ef8bf9766754a5320b167389e094c28cca7 EXCLUDE_FROM_ALL SYSTEM)
FetchContent_Declare(json
    URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
    URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
    SYSTEM EXCLUDE_FROM_ALL)
FetchContent_MakeAvailable(slang mcp_sdk json)

# The SDK emits LLVM bitcode in Release; consumers must enable LTO at the final link.
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    target_link_options(mcp-core INTERFACE "$<$<CONFIG:Release>:-flto=thin>")
endif()
if(APPLE AND CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    get_filename_component(llvm_bin "${CMAKE_CXX_COMPILER}" DIRECTORY)
    find_program(SLANG_MCP_LD64_LLD NAMES ld64.lld HINTS "${llvm_bin}")
    if(SLANG_MCP_LD64_LLD)
        target_link_options(mcp-core INTERFACE
            "$<$<CONFIG:Release>:-fuse-ld=${SLANG_MCP_LD64_LLD}>")
    elseif(CMAKE_BUILD_TYPE STREQUAL "Release")
        message(FATAL_ERROR "LLVM Release builds on macOS require matching ld64.lld beside clang++")
    endif()
endif()

set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS src/contract.json)
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/src/contract.json" SLANG_MCP_CONTRACT)
configure_file(src/contract.hpp.in generated/contract.hpp @ONLY)

add_library(slang_mcp_core
    src/project.cpp src/semantic_service.cpp src/rtl_queries.cpp
    src/inspection.cpp src/connectivity.cpp
    src/adapters/design.cpp src/adapters/normalization.cpp
    src/adapters/access_index.cpp)
target_compile_features(slang_mcp_core PUBLIC cxx_std_26)
target_compile_definitions(slang_mcp_core PUBLIC SLANG_MCP_VERSION="${PROJECT_VERSION}")
target_include_directories(slang_mcp_core PUBLIC src)
target_link_libraries(slang_mcp_core PUBLIC nlohmann_json::nlohmann_json PRIVATE slang::slang)

add_executable(slang-mcp src/main.cpp src/server.cpp)
set_target_properties(slang-mcp PROPERTIES OUTPUT_NAME slang_mcp)
target_include_directories(slang-mcp PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated")
target_link_libraries(slang-mcp PRIVATE slang_mcp_core mcp-server)

foreach(target slang_mcp_core slang-mcp)
    if(MSVC)
        target_compile_options(${target} PRIVATE /W4 /WX /permissive-)
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -Werror
            -Wconversion -Wsign-conversion -Wshadow -Wnon-virtual-dtor)
    endif()
endforeach()
install(TARGETS slang-mcp RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})

get_filename_component(compiler_bin "${CMAKE_CXX_COMPILER}" DIRECTORY)
find_program(CLANG_FORMAT NAMES clang-format-23 clang-format HINTS "${compiler_bin}")
find_program(CLANG_TIDY NAMES clang-tidy-23 clang-tidy HINTS "${compiler_bin}")
foreach(mode format format-check lint)
    add_custom_target(${mode}
        COMMAND "${CMAKE_COMMAND}" "-DSOURCE_ROOT=${CMAKE_CURRENT_SOURCE_DIR}"
            "-DBUILD_ROOT=${CMAKE_CURRENT_BINARY_DIR}" "-DMODE=${mode}"
            "-DFORMATTER=${CLANG_FORMAT}" "-DLINTER=${CLANG_TIDY}"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/cmake/Quality.cmake"
        VERBATIM)
endforeach()
find_program(LIZARD_EXECUTABLE NAMES lizard)
if(NOT LIZARD_EXECUTABLE)
    set(LIZARD_EXECUTABLE lizard)
endif()
add_custom_target(complexity
    COMMAND "${LIZARD_EXECUTABLE}" -C 6 -L 50 -a 4 -w "${CMAKE_CURRENT_SOURCE_DIR}/src"
    VERBATIM)

if(BUILD_TESTING)
    FetchContent_Declare(Catch2
        GIT_REPOSITORY https://github.com/catchorg/Catch2.git
        GIT_TAG v3.16.1 GIT_SHALLOW TRUE EXCLUDE_FROM_ALL SYSTEM)
    FetchContent_MakeAvailable(Catch2)
    add_executable(slang_mcp_tests tests/cpp/semantics.cpp tests/cpp/regressions.cpp tests/cpp/stdio.cpp)
    target_include_directories(slang_mcp_tests PRIVATE tests/cpp "${CMAKE_CURRENT_BINARY_DIR}/generated")
    target_link_libraries(slang_mcp_tests PRIVATE slang_mcp_core Catch2::Catch2WithMain mcp-client)
    target_compile_features(slang_mcp_tests PRIVATE cxx_std_26)
    target_compile_definitions(slang_mcp_tests PRIVATE
        SLANG_MCP_TEST_BINARY="$<TARGET_FILE:slang-mcp>")
    add_dependencies(slang_mcp_tests slang-mcp)
    add_test(NAME native_mcp COMMAND slang_mcp_tests)
    set_tests_properties(native_mcp PROPERTIES TIMEOUT 120)
endif()
