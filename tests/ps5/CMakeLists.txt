cmake_minimum_required(VERSION 3.25)
project(refrozen_ps5_host_gates LANGUAGES CXX)

enable_testing()
option(REFROZEN_PS5_COMPILE_ONLY "Compile the fixtures into objects without linking host executables" OFF)

function(add_guest_layout_fixture name)
  if(REFROZEN_PS5_COMPILE_ONLY)
    add_library(${name}_compile OBJECT ${name}_test.cpp)
    set(target ${name}_compile)
  else()
    add_executable(${name}_test ${name}_test.cpp)
    set(target ${name}_test)
    add_test(NAME ${name} COMMAND ${name}_test)
  endif()
  target_compile_features(${target} PRIVATE cxx_std_20)
  target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/host")
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /WX)
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra -Werror -Wpedantic -Wconversion)
  endif()
endfunction()

add_guest_layout_fixture(guest32_ranges)
add_guest_layout_fixture(guest64_ranges)
add_guest_layout_fixture(exact_guest_reservation)
add_guest_layout_fixture(pe_image_materializer)
add_guest_layout_fixture(direct_guest_backing)
add_guest_layout_fixture(guest_image_mapping)

if(NOT REFROZEN_PS5_COMPILE_ONLY AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
  add_executable(guest_memory_probe_host_test
                 guest_memory_probe_host_test.cpp
                 "../../ps5/runtime/exact_reservation_ps5.cpp"
                 "../../ps5/runtime/direct_guest_backing_ps5.cpp"
                 "../../ps5/runtime/guest_image_mapping_ps5.cpp"
                 "../../ps5/runtime/guest_memory_probe_ps5.cpp")
  target_compile_features(guest_memory_probe_host_test PRIVATE cxx_std_20)
  target_include_directories(guest_memory_probe_host_test PRIVATE
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/host"
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/runtime")
  target_compile_options(guest_memory_probe_host_test PRIVATE
                         -Wall -Wextra -Werror -Wpedantic -Wconversion)
  add_test(NAME guest_memory_probe_host COMMAND guest_memory_probe_host_test)
endif()

if(REFROZEN_PS5_COMPILE_ONLY)
  add_library(ps5_exact_reservation_adapter_compile OBJECT
              "../../ps5/runtime/exact_reservation_ps5.cpp")
  target_compile_features(ps5_exact_reservation_adapter_compile PRIVATE cxx_std_20)
  target_include_directories(ps5_exact_reservation_adapter_compile PRIVATE
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/host"
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/runtime")
  if(MSVC)
    target_compile_options(ps5_exact_reservation_adapter_compile PRIVATE /W4 /WX)
  else()
    target_compile_options(ps5_exact_reservation_adapter_compile PRIVATE
                           -Wall -Wextra -Werror -Wpedantic -Wconversion)
  endif()

  add_library(ps5_direct_guest_backing_adapter_compile OBJECT
              "../../ps5/runtime/direct_guest_backing_ps5.cpp")
  target_compile_features(ps5_direct_guest_backing_adapter_compile PRIVATE cxx_std_20)
  target_include_directories(ps5_direct_guest_backing_adapter_compile PRIVATE
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/host"
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/runtime")
  if(MSVC)
    target_compile_options(ps5_direct_guest_backing_adapter_compile PRIVATE /W4 /WX)
  else()
    target_compile_options(ps5_direct_guest_backing_adapter_compile PRIVATE
                           -Wall -Wextra -Werror -Wpedantic -Wconversion)
  endif()
  add_library(ps5_guest_image_mapping_adapter_compile OBJECT
              "../../ps5/runtime/guest_image_mapping_ps5.cpp")
  target_compile_features(ps5_guest_image_mapping_adapter_compile PRIVATE cxx_std_20)
  target_include_directories(ps5_guest_image_mapping_adapter_compile PRIVATE
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/host"
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/runtime")
  if(MSVC)
    target_compile_options(ps5_guest_image_mapping_adapter_compile PRIVATE /W4 /WX)
  else()
    target_compile_options(ps5_guest_image_mapping_adapter_compile PRIVATE
                           -Wall -Wextra -Werror -Wpedantic -Wconversion)
  endif()

  add_library(ps5_guest_memory_probe_compile OBJECT
              "../../ps5/runtime/guest_memory_probe_ps5.cpp")
  target_compile_features(ps5_guest_memory_probe_compile PRIVATE cxx_std_20)
  target_include_directories(ps5_guest_memory_probe_compile PRIVATE
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/host"
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/runtime")
  if(MSVC)
    target_compile_options(ps5_guest_memory_probe_compile PRIVATE /W4 /WX)
  else()
    target_compile_options(ps5_guest_memory_probe_compile PRIVATE
                           -Wall -Wextra -Werror -Wpedantic -Wconversion)
  endif()
endif()
