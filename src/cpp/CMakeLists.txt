cmake_minimum_required(VERSION 3.14)
project(AegisEngine)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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

# Fetch libff locally
FetchContent_Declare(
  libff
  GIT_REPOSITORY https://github.com/scipr-lab/libff.git
  GIT_TAG        v1.0.0
)
FetchContent_MakeAvailable(libff)

# Fetch libsnark locally
FetchContent_Declare(
  libsnark
  GIT_REPOSITORY https://github.com/scipr-lab/libsnark.git
  GIT_TAG        v1.0.0
)
FetchContent_MakeAvailable(libsnark)

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
    ${LIBSNARK_INCLUDE_DIR}
    ${LIBFF_INCLUDE_DIR}
    ${ZeroMQ_INCLUDE_DIRS}
    ${RdKafka_INCLUDE_DIRS}
    .
)

link_directories(
    ${ZeroMQ_LIBRARY_DIRS}
    ${RdKafka_LIBRARY_DIRS}
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

    # Find GTest
    find_package(GTest QUIET)
    if(NOT GTest_FOUND)
        # Fallback: Use FetchContent to download GTest
        include(FetchContent)
        FetchContent_Declare(
            googletest
            GIT_REPOSITORY https://github.com/google/googletest.git
            GIT_TAG        v1.14.0
        )
        FetchContent_MakeAvailable(googletest)
    endif()

    # AddressSanitizer for memory safety (optional, for Debug builds)
    option(ENABLE_ASAN "Enable AddressSanitizer for memory safety checks" OFF)
    if(ENABLE_ASAN)
        add_compile_options(-fsanitize=address -fno-omit-frame-pointer)
        add_link_options(-fsanitize=address)
        message(STATUS "[Aegis] AddressSanitizer ENABLED")
    endif()

    # Test Executable
    add_executable(aegis_tests
        tests/cpp/test_ring_buffer.cpp
        tests/cpp/test_iso_parser.cpp
    )

    target_include_directories(aegis_tests PRIVATE ${CMAKE_SOURCE_DIR})

    target_link_libraries(aegis_tests
        PRIVATE
        GTest::gtest_main
        pugixml::pugixml
        pthread
    )

    # Register tests with CTest
    include(GoogleTest)
    gtest_discover_tests(aegis_tests)

    message(STATUS "[Aegis] Test suite configured. Run with: ctest --output-on-failure")
endif()
