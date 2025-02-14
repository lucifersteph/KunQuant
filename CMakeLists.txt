cmake_policy(SET CMP0048 NEW)
project(KunRunner VERSION 0.0.1)
cmake_minimum_required(VERSION 3.5)
add_subdirectory(3rdparty/pybind11)
include_directories(${pybind11_INCLUDE_DIRS} ${PROJECT_SOURCE_DIR}/cpp)
message(STATUS ${pybind11_INCLUDE_DIRS})
if (CMAKE_CXX_COMPILER_ID STREQUAL "Clang" OR CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11 -fvisibility=hidden -fvisibility-inlines-hidden -mavx2 -mfma")
else()
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /wd4251")
endif()
file(GLOB_RECURSE KunRuntimeSrc ${PROJECT_SOURCE_DIR}/cpp/*.cpp)
pybind11_add_module(KunRunner SHARED ${KunRuntimeSrc})

target_compile_definitions(KunRunner PRIVATE KUN_CORE_LIB=1)

if (NOT WIN32)
    target_link_libraries(KunRunner PRIVATE dl)
endif()


file(GLOB_RECURSE KunTestSrc ${PROJECT_SOURCE_DIR}/tests/cpp/*.cpp)
add_library(KunTest SHARED EXCLUDE_FROM_ALL ${KunTestSrc})
target_link_libraries(KunTest KunRunner)
if(NOT DEFINED PYTHON_EXECUTABLE)
    set(PYTHON_EXECUTABLE ${Python_EXECUTABLE})
endif()

message(STATUS "PYTHON_EXECUTABLE = ${PYTHON_EXECUTABLE}")

add_subdirectory(projects)