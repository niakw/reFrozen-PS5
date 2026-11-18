// SPDX-License-Identifier: GPL-3.0-or-later
#include "ps5_stereo_resampler.hpp"

#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <vector>

using refrozen::ps5::StereoLinearResampler;

static bool near(float a, float b, float eps = 1e-5f) {
  return std::fabs(a - b) <= eps;
}

static std::vector<float> ramp(std::size_t frames) {
  std::vector<float> out(frames * 2);
  for (std::size_t i = 0; i < frames; ++i) {
    out[i * 2] = static_cast<float>(i);
    out[i * 2 + 1] = -static_cast<float>(i);
  }
  return out;
}

int main() {
  {
    StereoLinearResampler r(48000, 48000);
    assert(r.valid());
    auto in = ramp(300);
    std::vector<float> out(256 * 2);
    r.Push(in.data(), 300);
    assert(r.RequiredBufferedFrames(256) == 257);
    assert(r.Produce(out.data(), 256));
    for (std::size_t i = 0; i < 256; ++i) {
      assert(out[i * 2] == in[i * 2]);
      assert(out[i * 2 + 1] == in[i * 2 + 1]);
    }
    assert(r.buffered_frames() == 44);
  }

  {
    StereoLinearResampler r(44100, 48000);
    assert(r.valid());
    auto in = ramp(700);
    r.Push(in.data(), 700);
    std::vector<float> first(256 * 2), second(256 * 2);
    assert(r.RequiredBufferedFrames(256) == 236);
    assert(r.Produce(first.data(), 256));
    assert(near(first[0], 0.0f));
    assert(near(first[2], 0.91875f));
    assert(near(first[255 * 2], 234.28125f, 1e-4f));
    assert(r.buffered_frames() == 465);

    assert(r.RequiredBufferedFrames(256) == 236);
    assert(r.Produce(second.data(), 256));
    assert(near(second[0], 235.2f, 1e-4f));
    assert(near(second[1], -235.2f, 1e-4f));
    assert(near(second[2], 236.11875f, 1e-4f));
  }

  {
    StereoLinearResampler bad_zero(0, 48000);
    StereoLinearResampler bad_high(44100, 500000);
    assert(!bad_zero.valid());
    assert(!bad_high.valid());
    float out[2] = {};
    assert(!bad_zero.Produce(out, 1));
  }

  std::puts("ps5_stereo_resampler: PASS");
  return 0;
}
