""" 
Pipeline: Upload -> Preprocess -> Segment -> Extract Features -> Similarity Search -> Copy Localization -> Results
"""

import sys
import json
import os
import time

from preprocessor import Preprocessor
from segmenter import Segmenter
from feature_extractor import FeatureExtractor
from similarity_search import SimilaritySearchEngine
from copy_localizer import CopyLocalizer

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'database.json')

def load_db():
    if os.path.exists(DB_PATH):
        with open(DB_PATH, 'r') as f:
            return json.load(f)
    return {"videos": [], "descriptors": []}

def save_db(db):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, 'w') as f:
        json.dump(db, f, indent=2)

# ─── Pipeline Stages ────────────────────────────────────────────────────────

def process_video(video_path, video_id, video_name):
    preprocessor = Preprocessor()
    segmenter = Segmenter(segment_duration=1.0)
    extractor = FeatureExtractor()
    pipeline_start = time.time()

    print(f" Preprocessing: {video_name}", file=sys.stderr)
    t0 = time.time()
    frames, fps, frame_size = preprocessor.process(video_path)
    print(f" Preprocessing took {time.time() - t0:.1f}s", file=sys.stderr)
    if len(frames) == 0:
        return {"error": "No frames could be extracted from the video."}

    print(f" Segmenting: {len(frames)} frames @ {fps:.1f} fps", file=sys.stderr)
    t0 = time.time()
    segments = segmenter.segment(frames, fps)
    print(f" Segmentation took {time.time() - t0:.1f}s", file=sys.stderr)

    print(f" Extracting features from {len(segments)} segments", file=sys.stderr)
    t0 = time.time()
    descriptors = []
    for i, segment in enumerate(segments):
        desc = extractor.extract(segment, fps)
        descriptors.append({
            "video_id": video_id,
            "segment_index": i,
            "edge_histogram": desc["edge_histogram"],
            "spatiotemporal": desc["spatiotemporal"],
        })
        if (i + 1) % 5 == 0 or i == len(segments) - 1:
            print(f"  → Features: {i + 1}/{len(segments)} segments", file=sys.stderr)

    print(f" Feature extraction took {time.time() - t0:.1f}s", file=sys.stderr)
    print(f" Total pipeline: {time.time() - pipeline_start:.1f}s", file=sys.stderr)

    return {
        "video_id": video_id,
        "video_name": video_name,
        "fps": fps,
        "total_frames": len(frames),
        "total_segments": len(segments),
        "frame_size": list(frame_size),
        "descriptors": descriptors
    }


def register_video(video_path, video_id, video_name):
    result = process_video(video_path, video_id, video_name)
    if "error" in result:
        return result

    db = load_db()
    db["videos"].append({
        "video_id": video_id,
        "video_name": video_name,
        "fps": result["fps"],
        "total_frames": result["total_frames"],
        "total_segments": result["total_segments"],
        "frame_size": result["frame_size"]
    })
    db["descriptors"].extend(result["descriptors"])
    save_db(db)

    return {
        "status": "registered",
        "video_id": video_id,
        "video_name": video_name,
        "total_segments": result["total_segments"],
        "total_descriptors": len(result["descriptors"]),
    }


def query_video(video_path, video_id, video_name):
    result = process_video(video_path, video_id, video_name)
    if "error" in result:
        return result

    db = load_db()
    ref_descriptors = db.get("descriptors", [])
    ref_videos = {v["video_id"]: v for v in db.get("videos", [])}

    if len(ref_descriptors) == 0:
        return {
            "status": "no_references",
            "message": "No reference videos in the database. Register videos first.",
            "query_info": {
                "video_id": video_id,
                "video_name": video_name,
                "total_segments": result["total_segments"]
            }
        }

    # Similarity Search using Pivot Tables (LAESA)
    search_engine = SimilaritySearchEngine(ref_descriptors)
    localizer = CopyLocalizer()

    query_descriptors = result["descriptors"]
    all_matches = []

    for q_desc in query_descriptors:
        neighbors = search_engine.find_knn(q_desc, k=3)
        all_matches.append({
            "query_segment": q_desc["segment_index"],
            "neighbors": neighbors
        })

    #  find chains of matches
    detections = localizer.localize(all_matches, ref_videos, result["total_segments"])

    return {
        "status": "completed",
        "query_info": {
            "video_id": video_id,
            "video_name": video_name,
            "total_segments": result["total_segments"]
        },
        "detections": detections,
        "total_matches_found": len(detections)
    }


def get_database_info():
    """Return current database statistics."""
    db = load_db()
    return {
        "total_videos": len(db.get("videos", [])),
        "total_descriptors": len(db.get("descriptors", [])),
        "videos": db.get("videos", [])
    }


#  CLI Interface  
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: pipeline.py <command> [args...]"}))
        sys.exit(1)

    command = sys.argv[1]

    try:
        if command == "register":
            video_path, video_id, video_name = sys.argv[2], sys.argv[3], sys.argv[4]
            result = register_video(video_path, video_id, video_name)

        elif command == "query":
            video_path, video_id, video_name = sys.argv[2], sys.argv[3], sys.argv[4]
            result = query_video(video_path, video_id, video_name)

        elif command == "info":
            result = get_database_info()

        else:
            result = {"error": f"Unknown command: {command}"}

        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
