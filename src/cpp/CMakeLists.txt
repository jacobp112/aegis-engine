cmake_minimum_required(VERSION 3.14)
project(AegisEngine)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ------------------------------------------------------------------------------
# 1. BUILD CONFIGURATION
# ------------------------------------------------------------------------------

# Define the elliptic curve (Must match the libsnark build)
add_definitions(-DCURVE_BN128)

# Policies for FetchContent
if(POLICY CMP0079)
  cmake_policy(SET CMP0079 NEW)
endif()
if(POLICY CMP0002)
  cmake_policy(SET CMP0002 NEW)
endif()

# FIXED: Changed from 'option' (bool) to 'set CACHE STRING' to support "AUTO"
set(ENABLE_AVX512 "AUTO" CACHE STRING "Enable AVX-512 optimizations (ON/OFF/AUTO)")

# Auto-detect AVX-512
if(ENABLE_AVX512 STREQUAL "AUTO")
    include(CheckCXXCompilerFlag)
    check_cxx_compiler_flag("-mavx512f" HALF_AVX512_SUPPORTED)
    if(HALF_AVX512_SUPPORTED)
        set(ENABLE_AVX512 ON)
        message(STATUS "[Aegis] AVX-512 detected. Building Enterprise Edition.")
    else()
        set(ENABLE_AVX512 OFF)
        message(STATUS "[Aegis] AVX-512 NOT detected. Building Standard Edition.")
    endif()
endif()

# Apply Flags
if(ENABLE_AVX512)
    add_compile_options(-O3 -mavx512f -march=native)
    add_definitions(-DAEGIS_ENTERPRISE_MODE)
else()
    add_compile_options(-O3)
    add_definitions(-DAEGIS_STANDARD_MODE)
endif()

# ------------------------------------------------------------------------------
# 2. DEPENDENCIES
# ------------------------------------------------------------------------------

find_package(PkgConfig REQUIRED)

# --- A. GMP (Robust Search) ---
# FIXED: Replaced standard find_package with manual search (CMake has no default FindGMP)
find_path(GMP_INCLUDE_DIR NAMES gmp.h)
find_library(GMP_LIBRARY NAMES gmp libgmp)
find_library(GMPXX_LIBRARY NAMES gmpxx libgmpxx)

if(GMP_INCLUDE_DIR AND GMP_LIBRARY)
    set(GMP_LIBRARIES ${GMP_LIBRARY} ${GMPXX_LIBRARY})
    message(STATUS "[Aegis] Found GMP: ${GMP_LIBRARIES}")
else()
    message(FATAL_ERROR "[Aegis] GMP not found. Please install libgmp-dev.")
endif()

# --- B. ZeroMQ & RdKafka ---
pkg_check_modules(ZeroMQ REQUIRED libzmq)
pkg_check_modules(RdKafka REQUIRED rdkafka++)

# --- C. Pugixml ---
include(FetchContent)
FetchContent_Declare(
  pugixml
  GIT_REPOSITORY https://github.com/zeux/pugixml.git
  GIT_TAG        v1.13
)
FetchContent_MakeAvailable(pugixml)

# --- D. Libsnark (Hybrid: System or Source) ---
# Check if provided by the CI system/environment first
find_path(LIBSNARK_INCLUDE_DIR NAMES libsnark/gadgetlib/gadget.hpp)
find_library(LIBSNARK_LIBRARY NAMES snark libsnark)

if(LIBSNARK_INCLUDE_DIR AND LIBSNARK_LIBRARY)
    message(STATUS "[Aegis] Found system libsnark: ${LIBSNARK_LIBRARY}")
    set(LIBSNARK_TARGET ${LIBSNARK_LIBRARY})
    include_directories(${LIBSNARK_INCLUDE_DIR})
else()
    message(STATUS "[Aegis] System libsnark not found. Fetching from source...")

    # Save test state
    set(Aegis_BUILD_TESTING ${BUILD_TESTING})

    # Disable libsnark build bloat
    set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
    set(WITH_SUPERCOP OFF CACHE BOOL "" FORCE)
    set(WITH_PROCPS OFF CACHE BOOL "" FORCE)
    set(WITH_GMOCK OFF CACHE BOOL "" FORCE)

    FetchContent_Declare(
      libsnark
      GIT_REPOSITORY https://github.com/scipr-lab/libsnark.git
      GIT_TAG        master
    )
    FetchContent_MakeAvailable(libsnark)

    # Restore test state
    set(BUILD_TESTING ${Aegis_BUILD_TESTING} CACHE BOOL "" FORCE)

    # In source builds, the target is named 'snark'
    set(LIBSNARK_TARGET snark)

    # Helper to include internal headers if needed
    FetchContent_GetProperties(libsnark)
    if(libsnark_POPULATED)
        include_directories(${libsnark_SOURCE_DIR} ${libsnark_SOURCE_DIR}/depends/libff)
    endif()
endif()

# ------------------------------------------------------------------------------
# 3. GLOBAL INCLUDES
# ------------------------------------------------------------------------------
include_directories(
    ${GMP_INCLUDE_DIR}
    ${ZeroMQ_INCLUDE_DIRS}
    ${RdKafka_INCLUDE_DIRS}
    .
)

# ------------------------------------------------------------------------------
# 4. TARGETS
# ------------------------------------------------------------------------------

# --- Main Engine ---
add_executable(aegis_engine main.cpp)
target_link_libraries(aegis_engine
    PRIVATE
    pugixml::pugixml
    pthread
    ${ZeroMQ_LIBRARIES}
    ${RdKafka_LIBRARIES}
)

# --- ZKP Prover ---
add_executable(zkp_prover zkp_prover.cpp)
target_link_libraries(zkp_prover
    PRIVATE
    ${LIBSNARK_TARGET}
    ${GMP_LIBRARIES}
    pthread
)

# --- ZKP Verifier ---
add_executable(zkp_verifier zkp_verifier.cpp)
target_link_libraries(zkp_verifier
    PRIVATE
    ${LIBSNARK_TARGET}
    ${GMP_LIBRARIES}
    pthread
)

# ------------------------------------------------------------------------------
# 5. TESTS
# ------------------------------------------------------------------------------
option(BUILD_TESTS "Build test suite with GTest" OFF)

if(BUILD_TESTS)
    enable_testing()

    if(NOT TARGET gtest)
        FetchContent_Declare(
          googletest
          GIT_REPOSITORY https://github.com/google/googletest.git
          GIT_TAG        v1.14.0
        )
        # Prevent GTest from overriding parent compiler flags (Windows specific, but good practice)
        set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
        FetchContent_MakeAvailable(googletest)
    else()
        message(STATUS "[Aegis] Using existing gtest target provided by libsnark.")
    endif()

    # Unit Tests
    add_executable(test_ring_buffer tests/cpp/test_ring_buffer.cpp)
    target_link_libraries(test_ring_buffer PRIVATE gtest_main pugixml::pugixml pthread)

    add_executable(test_iso_parser tests/cpp/test_iso_parser.cpp)
    target_link_libraries(test_iso_parser PRIVATE gtest_main pugixml::pugixml pthread)

    # Auto-discover
    include(GoogleTest)
    gtest_discover_tests(test_ring_buffer)
    gtest_discover_tests(test_iso_parser)
endif()