import sys
import cv2
import numpy as np

# Video preprocessor.
class Preprocessor:
    # Isotropic target.
    PROCESSING_WIDTH = 320

    # Threshold initialization.
    def __init__(self, variance_threshold=100, outlier_threshold=3.0, border_threshold=15):
        self.variance_threshold = variance_threshold
        self.outlier_threshold = outlier_threshold
        self.border_threshold = border_threshold

    # Execution pipeline.
    def process(self, video_path):
        # Stream initialization.
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return [], 0, (0, 0)

        # Extract metadata.
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30.0

        total_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        print(f"  [Preprocess] Reading ~{total_frame_count} frames...", file=sys.stderr)

        raw_frames = []
        intensities = []
        variances = []
        frame_idx = 0

        # Sequential decimation.
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = self._downscale(frame)
            raw_frames.append(frame)

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            intensities.append(np.mean(gray))
            variances.append(np.var(gray))

            frame_idx += 1
            if frame_idx % 500 == 0:
                print(f"  [Preprocess] Read {frame_idx}/{total_frame_count} frames", file=sys.stderr)

        cap.release()

        if len(raw_frames) == 0:
            return [], fps, (0, 0)

        print(f"  [Preprocess] Read {len(raw_frames)} frames, filtering...", file=sys.stderr)

        # Statistical moments.
        intensities = np.array(intensities)
        variances = np.array(variances)
        mean_intensity = np.mean(intensities)
        std_intensity = np.std(intensities) + 1e-6

        # Variance thresholding.
        valid_mask = np.ones(len(raw_frames), dtype=bool)
        valid_mask[variances < self.variance_threshold] = False

        # Outlier pruning.
        z_scores = np.abs(intensities - mean_intensity) / std_intensity
        valid_mask[z_scores > self.outlier_threshold] = False

        num_invalid = int(np.sum(~valid_mask))
        if num_invalid > 0:
            print(f"  [Preprocess] Replacing {num_invalid} plain/outlier frames", file=sys.stderr)

        # Tensor interpolation.
        if num_invalid > 0 and np.any(valid_mask):
            valid_indices = np.where(valid_mask)[0]
            for i in range(len(raw_frames)):
                if not valid_mask[i]:
                    pos = np.searchsorted(valid_indices, i)
                    candidates = []
                    if pos < len(valid_indices):
                        candidates.append(valid_indices[pos])
                    if pos > 0:
                        candidates.append(valid_indices[pos - 1])
                    if candidates:
                        nearest = min(candidates, key=lambda x: abs(x - i))
                        raw_frames[i] = raw_frames[nearest]

        # Spatial cropping.
        crop_rect = self._detect_borders(raw_frames)
        if crop_rect is not None:
            x, y, w, h = crop_rect
            raw_frames = [f[y:y+h, x:x+w] for f in raw_frames]
            print(f"  [Preprocess] Cropped borders: {w}x{h}", file=sys.stderr)

        frame_size = (raw_frames[0].shape[1], raw_frames[0].shape[0]) if raw_frames else (0, 0)
        print(f"  [Preprocess] Done: {len(raw_frames)} frames @ {frame_size[0]}x{frame_size[1]}", file=sys.stderr)

        return raw_frames, fps, frame_size

    # Area decimation.
    def _downscale(self, frame):
        h, w = frame.shape[:2]
        if w <= self.PROCESSING_WIDTH:
            return frame
        scale = self.PROCESSING_WIDTH / w
        new_w = self.PROCESSING_WIDTH
        new_h = int(h * scale)
        return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Median projection.
    def _detect_borders(self, frames):
        if len(frames) == 0:
            return None

        # Chronological sampling.
        sample_indices = list(range(0, len(frames), max(1, len(frames) // 30)))[:30]
        samples = [cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY) for i in sample_indices]

        # Temporal median.
        stack = np.stack(samples, axis=0)
        median_frame = np.median(stack, axis=0).astype(np.uint8)

        # Orthogonal vectors.
        content_mask = median_frame > self.border_threshold
        rows = np.any(content_mask, axis=1)
        cols = np.any(content_mask, axis=0)

        if not rows.any() or not cols.any():
            return None

        # Coordinate extrema.
        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]

        # Margin enforcement.
        h, w = frames[0].shape[:2]
        margin = 0.03
        if (y_min > h * margin or y_max < h * (1 - margin) or
            x_min > w * margin or x_max < w * (1 - margin)):
            return (x_min, y_min, x_max - x_min + 1, y_max - y_min + 1)

        return None