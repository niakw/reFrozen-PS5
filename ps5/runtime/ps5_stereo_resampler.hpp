// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace refrozen::ps5 {

// Streaming stereo linear resampler used only at the native PS5 output edge.
// The game mixer keeps its requested source rate; PS5 audio stays at 48 kHz.
class StereoLinearResampler {
 public:
  StereoLinearResampler(uint32_t input_rate, uint32_t output_rate);

  [[nodiscard]] bool valid() const noexcept { return valid_; }
  [[nodiscard]] uint32_t input_rate() const noexcept { return input_rate_; }
  [[nodiscard]] uint32_t output_rate() const noexcept { return output_rate_; }
  [[nodiscard]] std::size_t buffered_frames() const noexcept {
    return stereo_.size() / 2;
  }

  void Push(const float* stereo, std::size_t frames);
  [[nodiscard]] std::size_t RequiredBufferedFrames(
      std::size_t output_frames) const noexcept;
  [[nodiscard]] bool Produce(float* output, std::size_t output_frames);

 private:
  uint32_t input_rate_{};
  uint32_t output_rate_{};
  double step_{};
  double phase_{};
  bool valid_{};
  std::vector<float> stereo_;
};

}  // namespace refrozen::ps5
