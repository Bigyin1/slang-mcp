file(GLOB_RECURSE cpp_sources "${SOURCE_ROOT}/src/*.cpp")
file(GLOB_RECURSE cpp_headers "${SOURCE_ROOT}/src/*.hpp")
file(GLOB_RECURSE cpp_tests "${SOURCE_ROOT}/tests/cpp/*.cpp" "${SOURCE_ROOT}/tests/cpp/*.hpp")

if(MODE STREQUAL "format")
    execute_process(COMMAND "${FORMATTER}" -i ${cpp_sources} ${cpp_headers} ${cpp_tests}
        COMMAND_ERROR_IS_FATAL ANY)
elseif(MODE STREQUAL "format-check")
    execute_process(COMMAND "${FORMATTER}" --dry-run --Werror ${cpp_sources} ${cpp_headers} ${cpp_tests}
        COMMAND_ERROR_IS_FATAL ANY)
elseif(MODE STREQUAL "lint")
    foreach(source IN LISTS cpp_sources)
        execute_process(COMMAND "${LINTER}" -p "${BUILD_ROOT}" "${source}"
            COMMAND_ERROR_IS_FATAL ANY)
    endforeach()
else()
    message(FATAL_ERROR "Unknown quality mode: ${MODE}")
endif()
