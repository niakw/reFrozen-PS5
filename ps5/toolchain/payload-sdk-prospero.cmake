# SPDX-License-Identifier: GPL-3.0-or-later
# CMake cross toolchain using the compiler facade shipped by the public
# PS5 Payload SDK. Intended for static/object qualification, not packaging.
if(NOT DEFINED ENV{PS5_PAYLOAD_SDK} OR "$ENV{PS5_PAYLOAD_SDK}" STREQUAL "")
  message(FATAL_ERROR "PS5_PAYLOAD_SDK is required")
endif()
set(_sdk "$ENV{PS5_PAYLOAD_SDK}")
if(NOT EXISTS "${_sdk}/bin/prospero-clang" OR
   NOT EXISTS "${_sdk}/bin/prospero-clang++")
  message(FATAL_ERROR "Payload SDK compiler facade missing")
endif()

set(CMAKE_SYSTEM_NAME FreeBSD)
set(CMAKE_SYSTEM_VERSION 9)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

set(CMAKE_C_COMPILER "${_sdk}/bin/prospero-clang")
set(CMAKE_CXX_COMPILER "${_sdk}/bin/prospero-clang++")
set(CMAKE_ASM_COMPILER "${_sdk}/bin/prospero-clang")

find_program(_llvm_ar NAMES llvm-ar-18 llvm-ar REQUIRED)
find_program(_llvm_ranlib NAMES llvm-ranlib-18 llvm-ranlib REQUIRED)
set(CMAKE_AR "${_llvm_ar}" CACHE FILEPATH "" FORCE)
set(CMAKE_RANLIB "${_llvm_ranlib}" CACHE FILEPATH "" FORCE)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
