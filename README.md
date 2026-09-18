# Passive Video Copy Detection (P-VCD) 🎥🔍

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![OpenCV](https://img.shields.io/badge/OpenCV-Enabled-brightgreen.svg)
![NumPy](https://img.shields.io/badge/NumPy-Optimized-orange.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## 📌 Overview
The **Passive Video Copy Detection (P-VCD)** system is a highly robust, content-based video retrieval and copyright detection framework. 

Unlike **Active Watermarking** (such as LSB substitution or frequency-domain embedding), which is inherently fragile and easily destroyed by social media compression algorithms, this system relies on **Passive Detection**. It mathematically extracts permanent structural and spatial features from video frames. This allows the system to identify pirated or heavily modified copies even after severe degradation.

### 🛡️ Resilient Against Common Piracy Attacks:
* Frame Dropping, Cropping, and Padding
* Color Alterations & Extreme Brightness Shifts
* Resolution Downsampling & Gaussian Blurring
* Lossy Video Compression (e.g., WhatsApp/Telegram compression)

---

## 🧠 Core Architecture & Mathematical Pipeline

Our framework fundamentally avoids the brute-force $O(N^2)$ comparison bottleneck by utilizing a highly optimized spatial and temporal indexing architecture. The pipeline consists of four major phases:

### 1. Smart Keyframe Extraction (Avoiding "Ghosting")
Blindly selecting the first frame of a 1-second segment often captures motion blur or camera flashes, corrupting the feature extraction process. 
* **The Solution:** We extract all frames within a 1-second segment, downsample them, and compute a mathematical **"Temporal Mean Frame"**.
* **L1 Distance Anchor:** Because the Mean Frame is an "imaginary" frame suffering from ghosting effects during high motion, we calculate the **L1 (Cityblock) Distance** between the Mean Frame and every real frame in the segment. The real frame with the minimum L1 distance is selected as the Keyframe. This guarantees a sharp, motion-blur-free representative frame.

### 2. The 108-Dimensional Feature Descriptor
Every Keyframe is mapped into a highly unique 108-D spatial vector. The dimensionality ($D = 108$) is formed by concatenating three specific descriptors:
* **80-D Edge Histogram Descriptor (EHD):** The frame is divided into a 4x4 grid. We extract 5 types of edges (Vertical, Horizontal, 45-degree, 135-degree, Non-directional) per block ($16 \times 5 = 80$ dimensions). This captures structural integrity regardless of color loss.
* **12-D Color Layout Descriptor (CLD):** The image is converted from RGB to the **YCrCb** color space to decouple luminance (brightness) from chrominance (true color), mimicking human visual perception. After applying Discrete Cosine Transform (DCT), we extract the top 12 low-frequency coefficients.
* **16-D Ordinal Measures:** The 4x4 blocks are ranked based on their relative average brightness, adding resilience against global brightness shifts.

### 3. Metric Space Indexing via LAESA
Matching a query video against a massive database of 108-D vectors natively requires $O(N \cdot D)$ time complexity per frame, which is too slow for real-time detection.
* **The Solution:** We implemented the **Linear Approximating and Eliminating Search Algorithm (LAESA)**.
* **The Math (Triangle Inequality):** The database relies on pre-computed distances to specific "Pivots" ($P$). For a given Query ($Q$) and Reference ($R$), LAESA utilizes the Triangle Inequality theorem:
  $$|d(Q,P) - d(R,P)| \le d(Q,R)$$
* **Pruning:** By computing the absolute difference between cached pivot distances, the system establishes a strict Lower Bound. If this bound exceeds the search threshold, the Reference point is instantly eliminated without computing the heavy 108-D Euclidean distance. 
* **Result:** This prunes over **93.6%** of the search space, bringing query time from **~18.2 seconds down to ~1.15 seconds**, scaling the continuous sequence search to $O(N)$.

### 4. Temporal Hough Voting (Confidence Score)
The system does not rely on isolated spatial matches. It utilizes **Temporal Hough Voting** to guarantee chronological alignment.
* When a Query segment matches a Reference segment, the temporal offset (`Offset = Query Time - Reference Time`) is calculated.
* Sequential matches cast "votes" into offset bins. A massive peak in a specific bin mathematically proves a continuous, chronological copy. The final **Confidence Percentage** is derived from the strength of this peak relative to background noise.

---

## ✨ Features

- **Reference Video Registration** — Upload and index reference videos into a searchable database.
- **Copy Detection Query** — Upload a suspect video to check if any segments match registered references.
- **Robust Feature Extraction** — Extracts edge histogram and spatio-temporal descriptors from video segments.
- **Efficient Similarity Search** — Uses a Pivot Table-based metric space search (LAESA) for fast nearest-neighbor lookup.
- **Copy Localization** — Chains segment-level matches to pinpoint the exact copied portions in both query and reference videos.
- **Asynchronous Processing** — Background job processing with real-time status polling from the UI.
- **Web-Based Interface** — Clean, modern frontend for managing the database and submitting queries.

---

## 🏗️ Project Structure

```
pvcd-video-copyright/
├── engine/                        # Python processing engine
│   ├── pipeline.py                # Main entry point & CLI for the engine
│   ├── preprocessor.py            # Video decoding & frame extraction (OpenCV)
│   ├── segmenter.py               # Splits frames into fixed-duration segments
│   ├── feature_extractor.py       # Edge histogram & spatio-temporal feature extraction
│   ├── similarity_search.py       # LAESA / Pivot Table nearest-neighbor search
│   └── copy_localizer.py          # Match chaining & copy localization logic
├── server/
│   └── index.js                   # Node.js Express API server & job manager
├── public/
│   ├── index.html                 # Frontend HTML
│   ├── style.css                  # Frontend styles
│   └── app.js                     # Frontend logic (vanilla JS)
├── data/
│   ├── uploads/                   # Uploaded video files (auto-created)
│   └── database.json              # JSON database of registered descriptors
├── package.json                   # Node.js dependencies & scripts
├── package-lock.json
├── requirements.txt               # Python dependencies
└── README.md
```

---

## 🔧 Prerequisites

| Dependency   | Version  |
|--------------|----------|
| Python       | 3.8+     |
| Node.js      | 14+      |
| npm          | 6+       |

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/nayankumar7/passive-video-copy-detection-main.git
cd passive-video-copy-detection
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

Key Python packages:
- `opencv-python` — Video decoding and frame processing
- `numpy` — Numerical computation
- `scipy` — Distance metrics and spatial algorithms
- `librosa` — Audio feature extraction
- `soundfile` — Audio I/O

### 3. Install Node.js Dependencies

```bash
npm install
```

Key Node packages:
- `express` — HTTP server framework
- `multer` — Multipart file upload handling
- `cors` — Cross-origin resource sharing
- `uuid` — Unique ID generation for jobs and videos

---

## ▶️ Usage

### Start the Server

```bash
npm start
# or
npm run dev
```

The server starts on **http://localhost:3000** by default.

### Workflow

1. **Register Reference Videos**
   Navigate to the registration section in the web UI and upload one or more reference videos. The system will extract features and store them in the database.

2. **Query for Copies**
   Upload a suspect video through the query section. The engine will compare its features against all registered references and report any detected copies, including confidence scores and localized timestamps.

3. **Manage Database**
   View registered video statistics or clear the database through the UI or the API.

---

## 📡 API Reference

| Method   | Endpoint              | Description                                      |
|----------|-----------------------|--------------------------------------------------|
| `POST`   | `/api/register`       | Register a reference video (`multipart/form-data`, key: `video`) |
| `POST`   | `/api/query`          | Query a video for copyright matches (`multipart/form-data`, key: `video`) |
| `GET`    | `/api/job/:jobId`     | Poll the status of a background processing job   |
| `GET`    | `/api/database`       | Retrieve database statistics and registered videos |
| `DELETE` | `/api/database`       | Clear all reference data from the database        |

**Note:** Registration and query endpoints return a `jobId` immediately. Poll `/api/job/:jobId` for results.

---

## ⚙️ How It Works

```
Upload → Preprocess → Segment → Extract Features → Similarity Search → Copy Localization → Results
```

1. **Preprocessing** — Decodes the video, extracts frames, and normalizes resolution.
2. **Segmentation** — Splits the frame sequence into 1-second segments.
3. **Feature Extraction** — Computes edge histogram and spatio-temporal descriptors per segment.
4. **Similarity Search** — Uses LAESA (Linear Approximating and Eliminating Search Algorithm) with pivot tables to efficiently find the k-nearest reference descriptors for each query segment.
5. **Copy Localization** — Chains consecutive segment matches to identify contiguous copied regions, computing confidence scores for each detection.

---

## 🛠️ Technologies

| Layer              | Technology                          |
|--------------------|-------------------------------------|
| Backend Server     | Node.js, Express                    |
| Processing Engine  | Python 3, OpenCV, NumPy, SciPy      |
| Frontend           | HTML5, CSS3, Vanilla JavaScript      |
| File Handling      | Multer (uploads), JSON (database)   |

---

## 📄 License

This project is developed as a Minor Project for academic purposes.

---

## 🤝 Contributing

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Commit your changes (`git commit -m 'Add your feature'`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a Pull Request.
