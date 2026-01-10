cmake_minimum_required(VERSION 3.14)
project(AegisEngine)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# Force CI Rebuild: Header inclusions update

# Define the elliptic curve for libsnark
add_definitions(-DCURVE_BN128)

# Fix for "Target already exists" errors when linking to FetchContent targets
if(POLICY CMP0079)
  cmake_policy(SET CMP0079 NEW)
endif()
if(POLICY CMP0002)
  cmake_policy(SET CMP0002 NEW)
endif()

# Prevent dependencies from building their own tests/docs (fixes duplicate target names "doc", "check")
set(BUILD_TESTING ON CACHE BOOL "" FORCE)
set(BUILD_DOCS OFF CACHE BOOL "" FORCE)
set(PERFORMANCE_TESTING OFF CACHE BOOL "" FORCE)
# Specific flags for libsnark/libff to prevent them from building tests/docs if they use different variables
set(WITH_SUPERCOP OFF CACHE BOOL "" FORCE)
set(WITH_PROCPS OFF CACHE BOOL "" FORCE)

# --- POLYMORPHIC DEPLOYMENT OPTIONS ---
option(ENABLE_AVX512 "Enable AVX-512 optimizations for Enterprise Edition" AUTO)

# Auto-detect AVX-512 if set to AUTO
if(ENABLE_AVX512 STREQUAL "AUTO")
    include(CheckCXXCompilerFlag)
    check_cxx_compiler_flag("-mavx512f" HALF_AVX512_SUPPORTED)
    if(HALF_AVX512_SUPPORTED)
        set(ENABLE_AVX512 ON)
        message(STATUS "[Aegis] AVX-512 detected. Building Enterprise Edition (Ultra-Low Latency).")
    else()
        set(ENABLE_AVX512 OFF)
        message(STATUS "[Aegis] AVX-512 NOT detected. Building Standard Edition (Cloud Compatible).")
    endif()
endif()

# Apply Flags
if(ENABLE_AVX512)
    add_compile_options(-O3 -mavx512f -march=native)
    add_definitions(-DAEGIS_ENTERPRISE_MODE)
else()
    add_compile_options(-O3) # Standard Cloud Optimization
    add_definitions(-DAEGIS_STANDARD_MODE)
endif()

# --- DEPENDENCIES (Secure Supply Chain) ---

# 1. XML Parsing: Pugixml (Industry Standard, Header-Only option available)
include(FetchContent)
FetchContent_Declare(
  pugixml
  GIT_REPOSITORY https://github.com/zeux/pugixml.git
  GIT_TAG        v1.13
)
FetchContent_MakeAvailable(pugixml)

# 2. Cryptography: libsnark (Real ZKP)
list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
find_package(GMP REQUIRED)

# Try to find system libsnark first (since we install it in CI)
# Try to find system libsnark first (since we install it in CI)
find_path(LIBSNARK_INCLUDE_DIR libsnark/gadgetlib/gadget.hpp)
find_library(LIBSNARK_LIBRARY NAMES snark libsnark)

if(LIBSNARK_INCLUDE_DIR AND LIBSNARK_LIBRARY)
    message(STATUS "[Aegis] Found system libsnark: ${LIBSNARK_LIBRARY}")
    set(LIBSNARK_LIBRARIES ${LIBSNARK_LIBRARY})
    # Ensure include directories are global or added to targets later
    include_directories(${LIBSNARK_INCLUDE_DIR})
else()
    message(STATUS "[Aegis] System libsnark not found. Fetching from source...")

    # Disable libsnark tests/docs to prevent pollution
    # WE MUST SAVE the global state first so we don't disable Aegis tests
    set(Aegis_BUILD_TESTING ${BUILD_TESTING})
    set(Aegis_BUILD_TESTS ${BUILD_TESTS})

    set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
    set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(BUILD_GTEST OFF CACHE BOOL "" FORCE)
    set(WITH_SUPERCOP OFF CACHE BOOL "" FORCE)
    set(WITH_PROCPS OFF CACHE BOOL "" FORCE)
    set(WITH_GMOCK OFF CACHE BOOL "" FORCE)

    # Fetch libsnark (which will pull in libff)
    FetchContent_Declare(
      libsnark
      GIT_REPOSITORY https://github.com/scipr-lab/libsnark.git
      GIT_TAG        master
    )
    # We use FetchContent_MakeAvailable for libsnark.
    # If libsnark's CMakeLists.txt adds libff, we are good.
    FetchContent_MakeAvailable(libsnark)

    # RESTORE global testing state for Aegis
    set(BUILD_TESTING ${Aegis_BUILD_TESTING} CACHE BOOL "" FORCE)
    set(BUILD_TESTS ${Aegis_BUILD_TESTS} CACHE BOOL "" FORCE)

    # If using FetchContent, we need to know the target name.
    # Usually it's 'snark' or 'libsnark'. We can assume targets are available.
    # But to be safe for our linking below, we set variables if targets exist
    if(TARGET snark)
        set(LIBSNARK_LIBRARIES snark)
    endif()

    # Explicitly include header paths for the fetched source interaction
    # (Legacy support for code that doesn't rely solely on target includes)
    FetchContent_GetProperties(libsnark)
    if(libsnark_POPULATED)
        include_directories(
            ${libsnark_SOURCE_DIR}
            ${libsnark_SOURCE_DIR}/depends/libff
        )
    endif()
endif()

# 4. Testing Framework: GoogleTest (Explicit Fetch)
FetchContent_Declare(
  googletest
  GIT_REPOSITORY https://github.com/google/googletest.git
  GIT_TAG        v1.14.0
)
# For Windows: Prevent overriding the parent project's compiler/linker settings
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)

# 3. Messaging: ZeroMQ & RdKafka (Enterprise Integration)
# Using PkgConfig as a fallback if strict find_package fails, ensuring broad compatibility
find_package(PkgConfig REQUIRED)

find_package(ZeroMQ QUIET)
if (NOT ZeroMQ_FOUND)
    pkg_check_modules(ZeroMQ REQUIRED libzmq)
endif()

# Librdkafka (Kafka C++ Driver)
pkg_check_modules(RdKafka REQUIRED rdkafka++)

# --- INCLUDES ---
include_directories(
    ${GMP_INCLUDE_DIR}
    ${ZeroMQ_INCLUDE_DIRS}
    ${RdKafka_INCLUDE_DIRS}
    .
)

link_directories(
    ${ZeroMQ_LIBRARY_DIRS}
    ${RdKafka_LIBRARY_DIRS}
    /usr/local/lib
)
include_directories(
    /usr/local/include/libsnark
    ${GMP_INCLUDE_DIR}
)

# --- TARGETS ---

# The Main Engine
add_executable(aegis_engine main.cpp)
target_link_libraries(aegis_engine
    PRIVATE
    pugixml::pugixml
    pthread
    ${ZeroMQ_LIBRARIES}
    ${RdKafka_LIBRARIES}
)

# The ZKP Prover (Microservice)
add_executable(zkp_prover zkp_prover.cpp)
target_link_libraries(zkp_prover
    ${LIBSNARK_LIBRARIES}
    ${LIBFF_LIBRARIES}
    ${GMP_LIBRARIES}
)

# The ZKP Verifier (Microservice)
add_executable(zkp_verifier zkp_verifier.cpp)
target_link_libraries(zkp_verifier
    ${LIBSNARK_LIBRARIES}
    ${LIBFF_LIBRARIES}
    ${GMP_LIBRARIES}
)

# --- TESTING (GTest Suite) ---
option(BUILD_TESTS "Build test suite with GTest" OFF)

if(BUILD_TESTS)
    message(STATUS "[Aegis] Building test suite...")
    enable_testing()

    # Make GoogleTest available
    FetchContent_MakeAvailable(googletest)

    # AddressSanitizer for memory safety (optional, for Debug builds)
    option(ENABLE_ASAN "Enable AddressSanitizer for memory safety checks" OFF)
    if(ENABLE_ASAN)
        add_compile_options(-fsanitize=address -fno-omit-frame-pointer)
        add_link_options(-fsanitize=address)
        message(STATUS "[Aegis] AddressSanitizer ENABLED")
    endif()

    # Test Ring Buffer
    add_executable(test_ring_buffer tests/cpp/test_ring_buffer.cpp)
    target_include_directories(test_ring_buffer PRIVATE ${CMAKE_SOURCE_DIR})
    target_link_libraries(test_ring_buffer PRIVATE gtest_main pugixml::pugixml pthread)

    # Test ISO Parser
    add_executable(test_iso_parser tests/cpp/test_iso_parser.cpp)
    target_include_directories(test_iso_parser PRIVATE ${CMAKE_SOURCE_DIR})
    target_link_libraries(test_iso_parser PRIVATE gtest_main pugixml::pugixml pthread)

    # Register tests
    include(GoogleTest)
    gtest_discover_tests(test_ring_buffer)
    gtest_discover_tests(test_iso_parser)

    message(STATUS "[Aegis] Test suite configured. Run with: ctest --output-on-failure")
endif()
