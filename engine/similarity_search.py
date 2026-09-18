# Similarity Search Module (Metric Space Indexing)
import numpy as np
from scipy.spatial.distance import cdist

class SimilaritySearchEngine: 
    def __init__(self, reference_descriptors, num_pivots=None, distance_order=1.0):
        self.distance_order = distance_order
        self.ref_descriptors = reference_descriptors

        if len(reference_descriptors) == 0:
            self.ref_matrix = np.array([])
            self.pivots = []
            self.pivot_distances = np.array([])
            return

        # Build descriptor matrix (combine EH + spatiotemporal)
        self.ref_matrix = self._build_matrix(reference_descriptors)

        # Select pivots using SSS
        n = len(reference_descriptors)
        if num_pivots is None:
            num_pivots = min(max(5, int(np.sqrt(n))), n, 50)

        self.pivots = self._select_pivots_sss(self.ref_matrix, num_pivots)

        # Precompute distances from every reference to each pivot
        self.pivot_distances = self._compute_pivot_distances(self.ref_matrix, self.pivots)

    def _build_matrix(self, descriptors):
        vectors = []
        for d in descriptors:
            eh = np.array(d.get("edge_histogram", []), dtype=np.float32)
            st = np.array(d.get("spatiotemporal", []), dtype=np.float32)
            combined = np.concatenate([eh, st])
            vectors.append(combined)
        return np.array(vectors, dtype=np.float32)

    def _lp_distance(self, a, b):
        p = self.distance_order
        if p == 1.0:
            return np.sum(np.abs(a - b))
        else:
            return np.sum(np.abs(a - b) ** p) ** (1.0 / p)

    def _select_pivots_sss(self, matrix, num_pivots):
        n = len(matrix)
        if n == 0:
            return []

        # Start with the first element
        pivot_indices = [0]

        # Compute mean inter-object distance for threshold
        sample_size = min(100, n)
        sample_idx = np.random.choice(n, sample_size, replace=False) if n > sample_size else np.arange(n)
        sample = matrix[sample_idx]

        if len(sample) > 1:
            dists = cdist(sample, sample, metric='cityblock')
            mean_dist = np.mean(dists[np.triu_indices(len(sample), k=1)])
            threshold = mean_dist * 0.5
        else:
            threshold = 0

        # Greedily add pivots that are far from all existing pivots
        for _ in range(num_pivots - 1):
            best_idx = -1
            best_min_dist = -1

            # Check a random subset for efficiency
            candidates = np.random.choice(n, min(200, n), replace=False)

            for idx in candidates:
                if idx in pivot_indices:
                    continue

                # Minimum distance to any existing pivot
                min_dist = min(
                    self._lp_distance(matrix[idx], matrix[p])
                    for p in pivot_indices
                )

                if min_dist > threshold and min_dist > best_min_dist:
                    best_min_dist = min_dist
                    best_idx = idx

            if best_idx == -1:
                break

            pivot_indices.append(best_idx)

        return pivot_indices

    def _compute_pivot_distances(self, matrix, pivot_indices):
        if len(matrix) == 0 or len(pivot_indices) == 0:
            return np.array([])

        pivot_vectors = matrix[pivot_indices]
        # Shape: (n_references, n_pivots)
        distances = cdist(matrix, pivot_vectors, metric='cityblock')
        return distances.astype(np.float32)

    def find_knn(self, query_descriptor, k=5):
        """
        Args: 
            query_descriptor: Dict with 'edge_histogram' and 'spatiotemporal'
            k: Number of nearest neighbors

        Returns: List of matches with video_id, segment_index, and distance
        """
        if len(self.ref_matrix) == 0:
            return []

        # Build query vector
        eh = np.array(query_descriptor.get("edge_histogram", []), dtype=np.float32)
        st = np.array(query_descriptor.get("spatiotemporal", []), dtype=np.float32)
        query_vec = np.concatenate([eh, st])

        n = len(self.ref_matrix)

        # Compute query-to-pivot distances
        query_pivot_dists = np.array([
            self._lp_distance(query_vec, self.ref_matrix[p])
            for p in self.pivots
        ]) if self.pivots else np.array([])

        # LAESA: Use triangle inequality to prune candidates
        # |d(q,p) - d(r,p)| <= d(q,r) for all pivots p
        # So: max_p |d(q,p) - d(r,p)| is a lower bound for d(q,r)

        if len(self.pivots) > 0 and len(self.pivot_distances) > 0:
            # Lower bounds for each reference
            lower_bounds = np.max(
                np.abs(self.pivot_distances - query_pivot_dists[np.newaxis, :]),
                axis=1
            )
        else:
            lower_bounds = np.zeros(n)

        # Sort by lower bound and compute exact distances only  
        sorted_indices = np.argsort(lower_bounds)

        results = []
        current_kth_dist = float('inf')

        for idx in sorted_indices:
            # Prune: if lower bound exceeds current kth distance, skip all remaining
            if lower_bounds[idx] > current_kth_dist:
                break

            # Compute exact distance
            dist = self._lp_distance(query_vec, self.ref_matrix[idx])

            if len(results) < k or dist < current_kth_dist:
                ref = self.ref_descriptors[idx]
                results.append({
                    "video_id": ref["video_id"],
                    "segment_index": ref["segment_index"],
                    "distance": float(dist),
                })

                # Keep only top k
                results.sort(key=lambda x: x["distance"])
                results = results[:k]

                if len(results) == k:
                    current_kth_dist = results[-1]["distance"]

        return results
