// SPDX-License-Identifier: GPL-3.0-or-later
#include "ps5_win32_audio_driver.h"

#include "ps5_audio_out_bridge.h"
#include "ps5_stereo_resampler.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <new>
#include <thread>
#include <vector>

struct refrozen_ps5_win32_audio_driver {
  refrozen_ps5_audio_out out{.handle = -1};
  uint32_t source_rate = 0;
  void* userdata = nullptr;
  refrozen_ps5_mix_callback mix = nullptr;
  std::atomic<bool> stop{false};
  std::thread worker;
};

namespace {

void AudioThread(refrozen_ps5_win32_audio_driver* driver) {
  refrozen::ps5::StereoLinearResampler resampler(
      driver->source_rate, REFROZEN_PS5_AUDIO_RATE);
  std::vector<float> source;
  std::array<float, REFROZEN_PS5_AUDIO_GRAIN * 2> output{};

  while (!driver->stop.load(std::memory_order_acquire)) {
    const std::size_t required =
        resampler.RequiredBufferedFrames(REFROZEN_PS5_AUDIO_GRAIN);
    if (required == 0) break;

    while (resampler.buffered_frames() < required &&
           !driver->stop.load(std::memory_order_acquire)) {
      const std::size_t missing = required - resampler.buffered_frames();
      const std::size_t frames =
          std::max<std::size_t>(missing, REFROZEN_PS5_AUDIO_GRAIN);
      if (frames > static_cast<std::size_t>(INT32_MAX)) return;
      source.assign(frames * 2, 0.0f);
      driver->mix(driver->userdata, source.data(), static_cast<int>(frames));
      resampler.Push(source.data(), frames);
    }
    if (driver->stop.load(std::memory_order_acquire)) break;

    if (!resampler.Produce(output.data(), REFROZEN_PS5_AUDIO_GRAIN)) break;
    if (refrozen_ps5_audio_out_push_f32(
            &driver->out, output.data(), REFROZEN_PS5_AUDIO_GRAIN) < 0)
      break;
  }
}

}  // namespace

extern "C" refrozen_ps5_win32_audio_driver*
refrozen_ps5_win32_audio_driver_start(uint32_t source_rate,
                                      void* userdata,
                                      refrozen_ps5_mix_callback mix) {
  if (!userdata || !mix) return nullptr;
  refrozen::ps5::StereoLinearResampler probe(
      source_rate, REFROZEN_PS5_AUDIO_RATE);
  if (!probe.valid()) return nullptr;

  auto* driver = new (std::nothrow) refrozen_ps5_win32_audio_driver;
  if (!driver) return nullptr;
  driver->source_rate = source_rate;
  driver->userdata = userdata;
  driver->mix = mix;
  if (refrozen_ps5_audio_out_open(&driver->out) < 0) {
    delete driver;
    return nullptr;
  }

  try {
    driver->worker = std::thread(AudioThread, driver);
  } catch (...) {
    refrozen_ps5_audio_out_close(&driver->out);
    delete driver;
    return nullptr;
  }
  return driver;
}

extern "C" void refrozen_ps5_win32_audio_driver_stop(
    refrozen_ps5_win32_audio_driver* driver) {
  if (!driver) return;
  driver->stop.store(true, std::memory_order_release);
  if (driver->worker.joinable()) driver->worker.join();
  refrozen_ps5_audio_out_close(&driver->out);
  delete driver;
}
