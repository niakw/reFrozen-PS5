// SPDX-License-Identifier: GPL-3.0-or-later
#include "ps5_audio_out_bridge.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int open_calls;
static int output_calls;
static int drain_calls;
static int close_calls;
static int16_t captured[4][REFROZEN_PS5_AUDIO_GRAIN * 2];

int sceAudioOutOpen(int user, int type, int index, unsigned int grain_frames,
                    unsigned int frequency, unsigned int format) {
  ++open_calls;
  assert(user == 0xff);
  assert(type == 0);
  assert(index == 0);
  assert(grain_frames == REFROZEN_PS5_AUDIO_GRAIN);
  assert(frequency == REFROZEN_PS5_AUDIO_RATE);
  assert(format == 1);
  return 7;
}

int sceAudioOutOutput(int handle, const void* samples) {
  assert(handle == 7);
  if (!samples) {
    ++drain_calls;
    return 0;
  }
  assert(output_calls < 4);
  memcpy(captured[output_calls], samples,
         sizeof captured[output_calls]);
  ++output_calls;
  return 0;
}

int sceAudioOutClose(int handle) {
  assert(handle == 7);
  ++close_calls;
  return 0;
}

int main(void) {
  struct refrozen_ps5_audio_out out = {.handle = -1};
  assert(refrozen_ps5_audio_out_open(&out) == 0);
  assert(open_calls == 1 && out.handle == 7 && out.fill_frames == 0);

  float pcm[REFROZEN_PS5_AUDIO_GRAIN * 2] = {0};
  for (uint32_t i = 0; i < REFROZEN_PS5_AUDIO_GRAIN; ++i) {
    pcm[i * 2] = i == 0 ? -1.0f : 0.5f;
    pcm[i * 2 + 1] = i == 0 ? 1.0f : -0.5f;
  }
  assert(refrozen_ps5_audio_out_push_f32(
             &out, pcm, REFROZEN_PS5_AUDIO_GRAIN - 1) == 0);
  assert(output_calls == 0);
  assert(out.fill_frames == REFROZEN_PS5_AUDIO_GRAIN - 1);
  assert(refrozen_ps5_audio_out_push_f32(
             &out, pcm + (REFROZEN_PS5_AUDIO_GRAIN - 1) * 2, 1) == 0);
  assert(output_calls == 1 && out.fill_frames == 0);
  assert(captured[0][0] == -32768);
  assert(captured[0][1] == 32767);
  assert(captured[0][2] == 16383);
  assert(captured[0][3] == -16383);

  assert(refrozen_ps5_audio_out_silence(&out, 480) == 0);
  assert(output_calls == 2);
  assert(out.fill_frames == 224);
  for (uint32_t i = 0; i < REFROZEN_PS5_AUDIO_GRAIN * 2; ++i)
    assert(captured[1][i] == 0);

  refrozen_ps5_audio_out_close(&out);
  assert(output_calls == 3);
  assert(drain_calls == 1);
  assert(close_calls == 1);
  assert(out.handle == -1 && out.fill_frames == 0);
  for (uint32_t i = 0; i < REFROZEN_PS5_AUDIO_GRAIN * 2; ++i)
    assert(captured[2][i] == 0);

  puts("ps5_audio_out_bridge: PASS");
  return 0;
}
