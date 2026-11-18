// SPDX-License-Identifier: GPL-3.0-or-later
#include "ps5_audio_out_bridge.h"

#include <stddef.h>
#include <string.h>

extern int sceAudioOutOpen(int user, int type, int index,
                           unsigned int grain_frames,
                           unsigned int frequency,
                           unsigned int format);
extern int sceAudioOutOutput(int handle, const void* samples);
extern int sceAudioOutClose(int handle);

enum {
  kSystemUser = 0xff,
  kMainPort = 0,
  kStereoS16 = 1,
};

static int16_t to_s16(float value) {
  if (value >= 1.0f) return 32767;
  if (value <= -1.0f) return -32768;
  const float scaled = value * 32767.0f;
  return (int16_t)scaled;
}

static int flush(struct refrozen_ps5_audio_out* out) {
  if (!out || out->handle < 0 || out->fill_frames != REFROZEN_PS5_AUDIO_GRAIN)
    return -1;
  const int result = sceAudioOutOutput(out->handle, out->grain);
  if (result < 0) return result;
  out->fill_frames = 0;
  return 0;
}

int refrozen_ps5_audio_out_open(struct refrozen_ps5_audio_out* out) {
  if (!out) return -1;
  memset(out, 0, sizeof *out);
  out->handle = sceAudioOutOpen(kSystemUser, kMainPort, 0,
                                REFROZEN_PS5_AUDIO_GRAIN,
                                REFROZEN_PS5_AUDIO_RATE,
                                kStereoS16);
  return out->handle < 0 ? out->handle : 0;
}

int refrozen_ps5_audio_out_push_f32(struct refrozen_ps5_audio_out* out,
                                    const float* stereo,
                                    uint32_t frames) {
  if (!out || out->handle < 0 || (!stereo && frames)) return -1;
  for (uint32_t frame = 0; frame < frames; ++frame) {
    const uint32_t slot = out->fill_frames++;
    out->grain[slot * 2] = to_s16(stereo[frame * 2]);
    out->grain[slot * 2 + 1] = to_s16(stereo[frame * 2 + 1]);
    if (out->fill_frames == REFROZEN_PS5_AUDIO_GRAIN) {
      const int result = flush(out);
      if (result < 0) return result;
    }
  }
  return 0;
}

int refrozen_ps5_audio_out_silence(struct refrozen_ps5_audio_out* out,
                                   uint32_t frames) {
  if (!out || out->handle < 0) return -1;
  static const float silent[REFROZEN_PS5_AUDIO_GRAIN * 2] = {0};
  while (frames) {
    const uint32_t step =
        frames > REFROZEN_PS5_AUDIO_GRAIN ? REFROZEN_PS5_AUDIO_GRAIN : frames;
    const int result = refrozen_ps5_audio_out_push_f32(out, silent, step);
    if (result < 0) return result;
    frames -= step;
  }
  return 0;
}

void refrozen_ps5_audio_out_close(struct refrozen_ps5_audio_out* out) {
  if (!out || out->handle < 0) return;
  if (out->fill_frames) {
    while (out->fill_frames < REFROZEN_PS5_AUDIO_GRAIN) {
      const uint32_t slot = out->fill_frames++;
      out->grain[slot * 2] = 0;
      out->grain[slot * 2 + 1] = 0;
    }
    (void)flush(out);
  }
  (void)sceAudioOutOutput(out->handle, NULL);
  (void)sceAudioOutClose(out->handle);
  out->handle = -1;
  out->fill_frames = 0;
}
