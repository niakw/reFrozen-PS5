cmake_minimum_required(VERSION 3.25)
project(refrozen_ps5_host_gates LANGUAGES C CXX)

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


  add_library(ps5_win64_memory_bridge_compile OBJECT
              "../../ps5/runtime/win64_memory_bridge_ps5.cpp")
  target_compile_features(ps5_win64_memory_bridge_compile PRIVATE cxx_std_20)
  target_include_directories(ps5_win64_memory_bridge_compile PRIVATE
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/host"
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/runtime")
  if(MSVC)
    target_compile_options(ps5_win64_memory_bridge_compile PRIVATE /W4 /WX)
  else()
    target_compile_options(ps5_win64_memory_bridge_compile PRIVATE
                           -Wall -Wextra -Werror -Wpedantic -Wconversion)
  endif()

  add_library(ps5_win64_frontend_shims_compile OBJECT
              "../../ps5/runtime/ps5_win64_frontend_shims.cpp")
  target_compile_features(ps5_win64_frontend_shims_compile PRIVATE cxx_std_20)
  target_include_directories(ps5_win64_frontend_shims_compile PRIVATE
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/runtime")
  if(MSVC)
    target_compile_options(ps5_win64_frontend_shims_compile PRIVATE /W4 /WX)
  else()
    target_compile_options(ps5_win64_frontend_shims_compile PRIVATE
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

add_executable(wgl_platform_contract_test
               wgl_platform_contract_test.cpp
               "../../ps5/graphics/wgl_platform_contract.cpp")
target_compile_features(wgl_platform_contract_test PRIVATE cxx_std_20)
target_include_directories(wgl_platform_contract_test PRIVATE
                           "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/graphics")
if(MSVC)
  target_compile_options(wgl_platform_contract_test PRIVATE /W4 /WX)
else()
  target_compile_options(wgl_platform_contract_test PRIVATE
                         -Wall -Wextra -Werror -Wpedantic -Wconversion)
endif()
add_test(NAME wgl_platform_contract COMMAND wgl_platform_contract_test)

option(REFROZEN_EGL_BACKEND_CHECK
       "Compile the WGL EGL backend against available EGL headers" OFF)
if(REFROZEN_EGL_BACKEND_CHECK)
  add_executable(wgl_egl_backend_mock_test
                 wgl_egl_backend_mock_test.cpp
                 "../../ps5/graphics/wgl_platform_contract.cpp"
                 "../../ps5/graphics/wgl_egl_backend_ps5.cpp")
  target_compile_features(wgl_egl_backend_mock_test PRIVATE cxx_std_20)
  target_include_directories(wgl_egl_backend_mock_test PRIVATE
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/graphics")
  if(MSVC)
    target_compile_options(wgl_egl_backend_mock_test PRIVATE /W4 /WX)
  else()
    target_compile_options(wgl_egl_backend_mock_test PRIVATE
                           -Wall -Wextra -Werror -Wpedantic -Wconversion)
  endif()
  add_test(NAME wgl_egl_backend_mock COMMAND wgl_egl_backend_mock_test)

  add_library(wgl_egl_backend_compile OBJECT
              "../../ps5/graphics/wgl_platform_contract.cpp"
              "../../ps5/graphics/wgl_egl_backend_ps5.cpp")
  target_compile_features(wgl_egl_backend_compile PRIVATE cxx_std_20)
  target_include_directories(wgl_egl_backend_compile PRIVATE
                             "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/graphics")
  if(MSVC)
    target_compile_options(wgl_egl_backend_compile PRIVATE /W4 /WX)
  else()
    target_compile_options(wgl_egl_backend_compile PRIVATE
                           -Wall -Wextra -Werror -Wpedantic -Wconversion)
  endif()
endif()

if(NOT REFROZEN_PS5_COMPILE_ONLY)
  add_executable(ps5_audio_out_bridge_test
    ps5_audio_out_bridge_test.c
    ../../ps5/runtime/ps5_audio_out_bridge.c)
  target_include_directories(ps5_audio_out_bridge_test PRIVATE ../../ps5/runtime)
  if(MSVC)
    target_compile_options(ps5_audio_out_bridge_test PRIVATE /W4 /WX)
  else()
    target_compile_options(ps5_audio_out_bridge_test PRIVATE -Wall -Wextra -Werror -Wpedantic)
  endif()
  add_test(NAME ps5_audio_out_bridge COMMAND ps5_audio_out_bridge_test)
endif()

if(NOT REFROZEN_PS5_COMPILE_ONLY)
  add_executable(ps5_win64_frontend_shims_test
    ps5_win64_frontend_shims_test.cpp
    ../../ps5/runtime/ps5_win64_frontend_shims.cpp
    ../../ps5/runtime/ps5_dinput_pad_bridge.cpp)
  target_include_directories(ps5_win64_frontend_shims_test PRIVATE ../../ps5/runtime)
  target_compile_features(ps5_win64_frontend_shims_test PRIVATE cxx_std_20)
  if(MSVC)
    target_compile_options(ps5_win64_frontend_shims_test PRIVATE /W4 /WX)
  else()
    target_compile_options(ps5_win64_frontend_shims_test PRIVATE
      -Wall -Wextra -Werror -Wpedantic -Wconversion)
  endif()
  add_test(NAME ps5_win64_frontend_shims COMMAND ps5_win64_frontend_shims_test)
endif()

if(NOT REFROZEN_PS5_COMPILE_ONLY)
  add_executable(ps5_dinput_pad_bridge_test
    ps5_dinput_pad_bridge_test.cpp
    ../../ps5/runtime/ps5_dinput_pad_bridge.cpp)
  target_include_directories(ps5_dinput_pad_bridge_test PRIVATE ../../ps5/runtime)
  target_compile_features(ps5_dinput_pad_bridge_test PRIVATE cxx_std_20)
  if(MSVC)
    target_compile_options(ps5_dinput_pad_bridge_test PRIVATE /W4 /WX)
  else()
    target_compile_options(ps5_dinput_pad_bridge_test PRIVATE
      -Wall -Wextra -Werror -Wpedantic -Wconversion)
  endif()
  add_test(NAME ps5_dinput_pad_bridge COMMAND ps5_dinput_pad_bridge_test)
endif()
