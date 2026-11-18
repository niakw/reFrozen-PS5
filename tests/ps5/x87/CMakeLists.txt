cmake_minimum_required(VERSION 3.25)
project(refrozen_ps5_x87_softfloat LANGUAGES C CXX)

if(NOT DEFINED X86RECOMP_ROOT OR NOT EXISTS "${X86RECOMP_ROOT}/cmake/softfloat.cmake")
  message(FATAL_ERROR "X86RECOMP_ROOT must point at the exact patched x86recomp source")
endif()

include(FetchContent)
include("${X86RECOMP_ROOT}/cmake/softfloat.cmake")

add_library(refrozen_x87_ps5 STATIC
  "${X86RECOMP_ROOT}/src/runtime/x87.cpp"
  "${X86RECOMP_ROOT}/src/runtime/sse.cpp")
target_include_directories(refrozen_x87_ps5 PUBLIC "${X86RECOMP_ROOT}/src")
target_compile_features(refrozen_x87_ps5 PUBLIC cxx_std_20)
target_link_libraries(refrozen_x87_ps5 PRIVATE softfloat)
target_compile_options(refrozen_x87_ps5 PRIVATE
  -O2 -fno-stack-protector -ffp-contract=off -fno-fast-math
  -Wall -Wextra -Werror)

# The CMake target relationship deliberately matches upstream: SoftFloat's
# PUBLIC endian/FPU layout definitions propagate to x87.cpp/sse.cpp.
