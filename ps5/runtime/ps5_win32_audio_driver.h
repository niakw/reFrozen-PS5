// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct refrozen_ps5_win32_audio_driver;
typedef void (*refrozen_ps5_mix_callback)(void* userdata, float* stereo,
                                          int frames);

struct refrozen_ps5_win32_audio_driver*
refrozen_ps5_win32_audio_driver_start(uint32_t source_rate,
                                      void* userdata,
                                      refrozen_ps5_mix_callback mix);

void refrozen_ps5_win32_audio_driver_stop(
    struct refrozen_ps5_win32_audio_driver* driver);

#ifdef __cplusplus
}
#endif
