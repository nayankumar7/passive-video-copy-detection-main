import cv2
import numpy as np


class FeatureExtractor:

    # 5 edge orientation kernels
    EDGE_KERNELS = [
        # Vertical
        np.array([[ 1,  0, -1],
                  [ 1,  0, -1],
                  [ 1,  0, -1]], dtype=np.float32),
        # Horizontal
        np.array([[ 1,  1,  1],
                  [ 0,  0,  0],
                  [-1, -1, -1]], dtype=np.float32),
        # 45 degrees
        np.array([[ 0,  1,  1],
                  [-1,  0,  1],
                  [-1, -1,  0]], dtype=np.float32),
        # 135 degrees
        np.array([[ 1,  1,  0],
                  [ 1,  0, -1],
                  [ 0, -1, -1]], dtype=np.float32),
        # Non-directional (isotropic)
        np.array([[ 2, -1, -1],
                  [-1,  2, -1],
                  [-1, -1,  2]], dtype=np.float32) / 3.0,
    ]

    GRID_ROWS = 4
    GRID_COLS = 4
    NUM_ORIENTATIONS = 5
    EHD_SIZE = GRID_ROWS * GRID_COLS * NUM_ORIENTATIONS  # 80

    # CLD: 6 Y + 3 Cb + 3 Cr DCT coefficients
    CLD_SIZE = 12

    # Ordinal: 4x4 block rank ordering
    ORDINAL_SIZE = 16

    # Total descriptor size
    DESCRIPTOR_SIZE = EHD_SIZE + CLD_SIZE + ORDINAL_SIZE  # 108

    # Weights for combining features in distance computation
    FEATURE_WEIGHTS = {
        'ehd': 0.40,
        'cld': 0.30,
        'ordinal': 0.30,
    }

    def __init__(self, edge_threshold=50):
        self.edge_threshold = edge_threshold

    def extract(self, segment, fps):
        """
        Extract all descriptors for a given segment.

        Args:
            segment: Dict with 'frames', 'keyframe', etc.
            fps: Video FPS

        Returns:
            Dict with feature vectors as lists of floats
        """
        keyframe = segment["keyframe"]
        all_frames = segment["frames"]

        # Compute combined descriptor for keyframe
        kf_combined = self._extract_combined(keyframe)

        # Spatio-temporal: average combined descriptor across sampled frames
        # 4 samples is sufficient for a robust average; more adds cost without benefit
        num_samples = min(4, len(all_frames))
        if num_samples <= 1:
            spatiotemporal = kf_combined
        else:
            step = max(1, len(all_frames) // num_samples)
            sampled_frames = all_frames[::step][:num_samples]

            all_combined = np.empty((len(sampled_frames), self.DESCRIPTOR_SIZE), dtype=np.float32)
            for i, frame in enumerate(sampled_frames):
                all_combined[i] = self._extract_combined(frame)
            spatiotemporal = np.mean(all_combined, axis=0)

        return {
            "edge_histogram": kf_combined.tolist(),
            "spatiotemporal": spatiotemporal.tolist(),
        }

    def _extract_combined(self, frame):
        """Extract and concatenate all three feature types for one frame."""
        ehd = self._edge_histogram(frame)
        cld = self._color_layout(frame)
        ordinal = self._ordinal_measure(frame)

        # Weight each feature component
        w = self.FEATURE_WEIGHTS
        ehd_weighted = ehd * w['ehd']
        cld_weighted = cld * w['cld']
        ordinal_weighted = ordinal * w['ordinal']

        return np.concatenate([ehd_weighted, cld_weighted, ordinal_weighted])

    # Feature 1: Edge Histogram Descriptor (80-D)

    def _edge_histogram(self, frame): 
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        h, w = gray.shape
        zone_h = h // self.GRID_ROWS
        zone_w = w // self.GRID_COLS

        histogram = np.zeros(self.EHD_SIZE, dtype=np.float32)

        for row in range(self.GRID_ROWS):
            for col in range(self.GRID_COLS):
                y1 = row * zone_h
                y2 = y1 + zone_h
                x1 = col * zone_w
                x2 = x1 + zone_w
                zone = gray[y1:y2, x1:x2].astype(np.float32)

                if zone.size == 0:
                    continue

                responses = np.zeros(self.NUM_ORIENTATIONS, dtype=np.float32)
                for k, kernel in enumerate(self.EDGE_KERNELS):
                    filtered = cv2.filter2D(zone, -1, kernel)
                    responses[k] = np.mean(np.abs(filtered))

                max_resp = np.max(responses)
                if max_resp > self.edge_threshold:
                    responses = responses / (max_resp + 1e-8)

                idx = (row * self.GRID_COLS + col) * self.NUM_ORIENTATIONS
                histogram[idx:idx + self.NUM_ORIENTATIONS] = responses

        # L2 normalize
        norm = np.linalg.norm(histogram)
        if norm > 0:
            histogram = histogram / norm

        return histogram

    # Feature 2: Color Layout Descriptor (12-D) — MPEG-7

    def _color_layout(self, frame):
        """ 
        1. Resize frame to 8x8 in YCrCb color space
        2. Apply 2D DCT to each channel
        3. Keep top coefficients: 6 Y + 3 Cb + 3 Cr = 12-D
        """
        if len(frame.shape) == 2:
            # Grayscale — create 3-channel
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        # Convert to YCrCb (perceptually meaningful)
        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)

        # Resize to 8x8 for compact representation
        tiny = cv2.resize(ycrcb, (8, 8), interpolation=cv2.INTER_AREA).astype(np.float32)

        coeffs = []
        for ch in range(3):
            channel = tiny[:, :, ch]
            # Apply 2D DCT
            dct = cv2.dct(channel)
            # Zigzag-order top coefficients
            if ch == 0:  # Y channel: keep 6 coefficients
                coeffs.extend([
                    dct[0, 0], dct[0, 1], dct[1, 0],
                    dct[2, 0], dct[1, 1], dct[0, 2]
                ])
            else:  # Cr, Cb: keep 3 coefficients each
                coeffs.extend([dct[0, 0], dct[0, 1], dct[1, 0]])

        cld = np.array(coeffs, dtype=np.float32)

        # Normalize to [0, 1] range
        cld_min = np.min(cld)
        cld_max = np.max(cld)
        if cld_max - cld_min > 1e-8:
            cld = (cld - cld_min) / (cld_max - cld_min)
        else:
            cld = np.zeros_like(cld)

        return cld

    # Feature 3: Ordinal Measure (16-D)

    def _ordinal_measure(self, frame):
        """ 
        1. Convert to grayscale
        2. Divide frame into 4x4 blocks
        3. Compute mean intensity of each block
        4. Return the rank ordering (normalized to [0, 1]) 
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        h, w = gray.shape
        block_h = h // 4
        block_w = w // 4

        means = np.zeros(16, dtype=np.float32)
        for row in range(4):
            for col in range(4):
                y1 = row * block_h
                y2 = y1 + block_h
                x1 = col * block_w
                x2 = x1 + block_w
                block = gray[y1:y2, x1:x2]
                means[row * 4 + col] = np.mean(block) if block.size > 0 else 0

        # Convert to rank ordering (normalized)
        ranks = np.argsort(np.argsort(means)).astype(np.float32)
        ranks = ranks / 15.0  # Normalize to [0, 1]

        return ranks
