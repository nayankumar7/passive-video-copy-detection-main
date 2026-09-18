import math
import cv2
import numpy as np


class Segmenter:
    def __init__(self, segment_duration=1.0): 
        self.segment_duration = segment_duration

    def segment(self, frames, fps): 
        frames_per_segment = max(1, int(math.ceil(fps * self.segment_duration)))
        total_frames = len(frames)
        segments = []

        for start in range(0, total_frames, frames_per_segment):
            end = min(start + frames_per_segment, total_frames)
            segment_frames = frames[start:end]

            # Smart keyframe selection: pick the most representative frame
            keyframe_idx = self._select_keyframe(segment_frames)
            keyframe = segment_frames[keyframe_idx]

            segments.append({
                "frames": segment_frames,
                "keyframe_index": keyframe_idx,
                "keyframe": keyframe,
                "start_frame": start,
                "end_frame": end - 1,
                "segment_index": len(segments)
            })

        return segments

    def _select_keyframe(self, segment_frames):
        n = len(segment_frames)
        if n <= 3:
            return n // 2

        # Downsample frames for fast comparison
        small_frames = []
        for f in segment_frames:
            small = cv2.resize(f, (32, 32), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if len(small.shape) == 3 else small
            small_frames.append(gray.astype(np.float32).flatten())

        small_frames = np.array(small_frames)

        # Compute mean frame
        mean_frame = np.mean(small_frames, axis=0)

        # Find the frame closest to the mean (L1 distance)
        distances = np.sum(np.abs(small_frames - mean_frame), axis=1)
        best_idx = int(np.argmin(distances))

        return best_idx
