import numpy as np
from collections import defaultdict


class CopyLocalizer:

    # Copy localization using Temporal Hough Voting.

    def __init__(self, confidence_threshold=0.20): 
        self.confidence_threshold = confidence_threshold

    def localize(self, all_matches, ref_videos, query_total_segments): 
        if not all_matches or query_total_segments == 0:
            return []

        # ── Step 1: Collect match pairs per reference video ──────────────
        video_pairs = defaultdict(list)  # vid -> list of (q_seg, r_seg, distance)
        all_distances = []

        for match in all_matches:
            q_seg = match["query_segment"]
            neighbors = match.get("neighbors", [])

            for neighbor in neighbors:
                vid = neighbor["video_id"]
                ref_seg = neighbor["segment_index"]
                dist = neighbor["distance"]
                all_distances.append(dist)
                video_pairs[vid].append((q_seg, ref_seg, dist))

        if not all_distances:
            return []

        # ── Step 2: Global distance statistics ───────────────────────────
        sorted_dists = sorted(all_distances)
        median_dist = sorted_dists[len(sorted_dists) // 2]
        p10 = sorted_dists[max(0, len(sorted_dists) // 10)]
        p25 = sorted_dists[max(0, len(sorted_dists) // 4)]

        # ── Step 3: Apply THV per reference video ────────────────────────
        detections = []

        for vid, pairs in video_pairs.items():
            ref_info = ref_videos.get(vid, {})
            ref_total = ref_info.get("total_segments", 1)

            result = self._temporal_hough_voting(
                pairs, query_total_segments, ref_total, p25, median_dist
            )

            if result is None:
                continue

            if result["confidence"] < self.confidence_threshold:
                continue

            detections.append({
                "reference_video_id": vid,
                "reference_video_name": ref_info.get("video_name", "Unknown"),
                "confidence": round(result["confidence"], 4),
                "confidence_pct": round(result["confidence"] * 100, 1),
                "matched_segments": result["matched_segments"],
                "unique_ref_segments": result["unique_ref_segments"],
                "query_range": result["query_range"],
                "reference_range": result["ref_range"],
                "query_time_range": [result["query_range"][0], result["query_range"][1] + 1],
                "reference_time_range": [result["ref_range"][0], result["ref_range"][1] + 1],
                "avg_distance": round(result["avg_distance"], 4),
                "peak_strength": round(result["peak_strength"], 4),
                "detection_method": "hough_voting",
            })

        # Sort by confidence (highest first)
        detections.sort(key=lambda x: x["confidence"], reverse=True)

        return detections

    # Temporal Hough Voting

    def _temporal_hough_voting(self, pairs, query_total, ref_total, close_threshold, median_dist):
        
        if not pairs:
            return None

        offset_votes = defaultdict(float)   # offset -> total weighted votes
        offset_pairs = defaultdict(list)    # offset -> list of (q, r, dist)

        for q_seg, r_seg, dist in pairs:
            offset = q_seg - r_seg

            # Distance-weighted vote: closer matches get exponentially more weight
            # Using Gaussian-like weighting: w = exp(-dist / median_dist)
            if median_dist > 0:
                weight = np.exp(-dist / median_dist)
            else:
                weight = 1.0 if dist < 0.1 else 0.0

            # Only count matches that are reasonably close
            if dist <= median_dist * 1.5:
                offset_votes[offset] += weight
                offset_pairs[offset].append((q_seg, r_seg, dist))

        if not offset_votes:
            return None

        # ── Also check neighboring offsets (±1 tolerance) ────────────────
        merged_votes = defaultdict(float)
        merged_pairs = defaultdict(list)

        for offset, vote in offset_votes.items():
            # Merge with adjacent offsets (±1 tolerance for frame alignment)
            for adj in [offset - 1, offset, offset + 1]:
                if adj in offset_votes:
                    merged_votes[offset] += offset_votes[adj]
                    merged_pairs[offset].extend(offset_pairs[adj])

        # Deduplicate pairs in merged groups
        for offset in merged_pairs:
            seen = set()
            unique = []
            for p in merged_pairs[offset]:
                key = (p[0], p[1])
                if key not in seen:
                    seen.add(key)
                    unique.append(p)
            merged_pairs[offset] = unique

        # ── Find the peak offset ────────────────────────────────────────
        if not merged_votes:
            return None

        peak_offset = max(merged_votes, key=merged_votes.get)
        peak_vote = merged_votes[peak_offset]
        peak_pairs = merged_pairs[peak_offset]

        # ── Compute peak strength (ratio of peak to total votes) ─────────
        total_votes = sum(offset_votes.values())
        peak_strength = peak_vote / total_votes if total_votes > 0 else 0

        # ── Extract match quality metrics ────────────────────────────────
        matched_query_segs = set(p[0] for p in peak_pairs)
        matched_ref_segs = set(p[1] for p in peak_pairs)
        close_distances = [p[2] for p in peak_pairs if p[2] <= close_threshold]

        unique_query = len(matched_query_segs)
        unique_ref = len(matched_ref_segs)

        #   Anti-false-positive checks  

        # Check 1: Enough unique reference segments (not many-to-one)
        if unique_ref < 2:
            return None

        # Check 2: Peak must be significantly above noise
        num_offsets = len(offset_votes)
        expected_uniform = total_votes / max(num_offsets, 1)
        if peak_vote < expected_uniform * 1.5:
            return None  # Peak is not significantly above uniform distribution

        #   Compute confidence score  

        # Factor 1: Query coverage — what fraction of query is matched at this offset
        query_coverage = unique_query / max(query_total, 1)

        # Factor 2: Uniqueness ratio — unique ref segs / matched query segs
        uniqueness = unique_ref / max(unique_query, 1)

        # Factor 3: Peak strength — how concentrated are votes at this offset
        # Higher = more consistent temporal alignment = more likely a true copy

        # Factor 4: Distance quality — how close are the matches at this offset
        if close_distances:
            avg_close_dist = np.mean(close_distances)
            dist_quality = 1.0 / (1.0 + avg_close_dist)
        else:
            # Fall back to all distances at this offset
            all_peak_dists = [p[2] for p in peak_pairs]
            avg_close_dist = np.mean(all_peak_dists) if all_peak_dists else 0
            dist_quality = 1.0 / (1.0 + avg_close_dist) * 0.7  # Slight penalty

        # Weighted combination
        confidence = (
            0.30 * query_coverage +    # How much of the query matches
            0.20 * uniqueness +        # Diversity of reference matches
            0.25 * peak_strength +     # Temporal consistency (THE key Hough signal)
            0.25 * dist_quality        # Feature-level similarity
        )

        # Bonus: if peak is very strong AND good coverage, boost confidence
        if peak_strength > 0.5 and query_coverage > 0.3:
            confidence = min(1.0, confidence * 1.2)

        # Hard penalty: if uniqueness is very low, it's a false positive
        if uniqueness < 0.25:
            confidence *= 0.3

        # ── Build result ─────────────────────────────────────────────────
        q_min = min(matched_query_segs)
        q_max = max(matched_query_segs)
        r_min = min(matched_ref_segs)
        r_max = max(matched_ref_segs)

        return {
            "confidence": min(1.0, confidence),
            "matched_segments": unique_query,
            "unique_ref_segments": unique_ref,
            "query_range": [q_min, q_max],
            "ref_range": [r_min, r_max],
            "avg_distance": float(avg_close_dist),
            "peak_strength": float(peak_strength),
        }
