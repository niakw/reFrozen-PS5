cmake_minimum_required(VERSION 3.25)
project(refrozen_ps5_host_gates LANGUAGES CXX)

enable_testing()

add_executable(guest32_ranges_test guest32_ranges_test.cpp)
target_compile_features(guest32_ranges_test PRIVATE cxx_std_20)
target_include_directories(guest32_ranges_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../ps5/host")
if(MSVC)
  target_compile_options(guest32_ranges_test PRIVATE /W4 /WX)
else()
  target_compile_options(guest32_ranges_test PRIVATE -Wall -Wextra -Werror -Wpedantic -Wconversion)
endif()
add_test(NAME guest32_ranges COMMAND guest32_ranges_test)
