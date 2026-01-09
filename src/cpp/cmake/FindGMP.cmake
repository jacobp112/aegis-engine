
# FindGMP.cmake - Find GNU Multiple Precision Arithmetic Library
#
# This module defines:
#  GMP_FOUND - If false, do not try to use GMP.
#  GMP_INCLUDE_DIR - The path to the GMP include directory.
#  GMP_LIBRARIES - The path to the GMP library.

find_path(GMP_INCLUDE_DIR gmp.h
    HINTS /usr/include /usr/local/include
)

find_library(GMP_LIBRARIES NAMES gmp libgmp
    HINTS /usr/lib /usr/local/lib
)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(GMP DEFAULT_MSG GMP_LIBRARIES GMP_INCLUDE_DIR)

mark_as_advanced(GMP_INCLUDE_DIR GMP_LIBRARIES)
