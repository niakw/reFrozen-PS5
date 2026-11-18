// SPDX-License-Identifier: GPL-3.0-or-later
// Minimal blocking PS5 stereo PCM output bridge for Win64 runtime backends.
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum { REFROZEN_PS5_AUDIO_RATE = 48000, REFROZEN_PS5_AUDIO_GRAIN = 256 };

struct refrozen_ps5_audio_out {
  int handle;
  uint32_t fill_frames;
  int16_t grain[REFROZEN_PS5_AUDIO_GRAIN * 2];
};

int refrozen_ps5_audio_out_open(struct refrozen_ps5_audio_out* out);
int refrozen_ps5_audio_out_push_f32(struct refrozen_ps5_audio_out* out,
                                    const float* stereo,
                                    uint32_t frames);
int refrozen_ps5_audio_out_silence(struct refrozen_ps5_audio_out* out,
                                   uint32_t frames);
void refrozen_ps5_audio_out_close(struct refrozen_ps5_audio_out* out);

#ifdef __cplusplus
}
#endif
