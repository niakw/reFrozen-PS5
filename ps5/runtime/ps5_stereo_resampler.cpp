// SPDX-License-Identifier: GPL-3.0-or-later
#include "ps5_stereo_resampler.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace refrozen::ps5 {

StereoLinearResampler::StereoLinearResampler(uint32_t input_rate,
                                             uint32_t output_rate)
    : input_rate_(input_rate),
      output_rate_(output_rate),
      step_(output_rate ? double(input_rate) / double(output_rate) : 0.0),
      valid_(input_rate >= 8000 && input_rate <= 192000 &&
             output_rate >= 8000 && output_rate <= 192000 &&
             std::isfinite(step_) && step_ > 0.0) {}

void StereoLinearResampler::Push(const float* input, std::size_t frames) {
  if (!valid_ || !frames || !input) return;
  if (frames > (std::numeric_limits<std::size_t>::max() - stereo_.size()) / 2)
    return;
  stereo_.insert(stereo_.end(), input, input + frames * 2);
}

std::size_t StereoLinearResampler::RequiredBufferedFrames(
    std::size_t output_frames) const noexcept {
  if (!valid_ || output_frames == 0) return 0;
  const double last = phase_ + double(output_frames - 1) * step_;
  if (!std::isfinite(last) || last < 0.0) return 0;
  const double need = std::floor(last) + 2.0;
  if (need > double(std::numeric_limits<std::size_t>::max())) return 0;
  return static_cast<std::size_t>(need);
}

bool StereoLinearResampler::Produce(float* output,
                                    std::size_t output_frames) {
  if (!valid_ || (!output && output_frames)) return false;
  const std::size_t required = RequiredBufferedFrames(output_frames);
  if (required == 0 && output_frames != 0) return false;
  if (buffered_frames() < required) return false;

  for (std::size_t frame = 0; frame < output_frames; ++frame) {
    const double pos = phase_ + double(frame) * step_;
    const std::size_t index = static_cast<std::size_t>(std::floor(pos));
    const float t = static_cast<float>(pos - double(index));
    for (std::size_t channel = 0; channel < 2; ++channel) {
      const float a = stereo_[(index * 2) + channel];
      const float b = stereo_[((index + 1) * 2) + channel];
      output[(frame * 2) + channel] = a + (b - a) * t;
    }
  }

  phase_ += double(output_frames) * step_;
  const std::size_t consumed = static_cast<std::size_t>(std::floor(phase_));
  phase_ -= double(consumed);
  const std::size_t samples = std::min(consumed * 2, stereo_.size());
  stereo_.erase(stereo_.begin(), stereo_.begin() + static_cast<std::ptrdiff_t>(samples));
  return true;
}

}  // namespace refrozen::ps5
