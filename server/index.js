const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { v4: uuidv4 } = require('uuid');

const app = express();
const PORT = process.env.PORT || 3000;


const UPLOADS_DIR = path.join(__dirname, '..', 'data', 'uploads');
const DATA_DIR = path.join(__dirname, '..', 'data');
const ENGINE_DIR = path.join(__dirname, '..', 'engine');

[UPLOADS_DIR, DATA_DIR].forEach(dir => {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});


const storage = multer.diskStorage({
    destination: (req, file, cb) => cb(null, UPLOADS_DIR),
    filename: (req, file, cb) => {
        const ext = path.extname(file.originalname);
        cb(null, `${uuidv4()}${ext}`);
    }
});

// file uploading using multer
const upload = multer({
    storage,
    limits: { fileSize: 500 * 1024 * 1024 }, // 500MB
    fileFilter: (req, file, cb) => {
        const allowed = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'];
        const ext = path.extname(file.originalname).toLowerCase();
        if (allowed.includes(ext)) {
            cb(null, true);
        } else {
            cb(new Error(`Unsupported format: ${ext}. Supported: ${allowed.join(', ')}`));
        }
    }
});

//   middleware 
app.use(express.json());
app.use(express.static(path.join(__dirname, '..', 'public')));

// ─── Python Pipeline Runner ─────────────────────────────────────────────────
function runPipeline(command, args = []) {
    return new Promise((resolve, reject) => {
        const pipelinePath = path.join(ENGINE_DIR, 'pipeline.py');
        const proc = spawn('python3', [pipelinePath, command, ...args], {
            cwd: ENGINE_DIR,
            timeout: 300000 // 5 min timeout
        });

        let stdout = '';
        let stderr = '';

        proc.stdout.on('data', data => { stdout += data.toString(); });
        proc.stderr.on('data', data => { stderr += data.toString(); });

        proc.on('close', code => {
            if (stderr) console.log('[Engine]', stderr);
            if (code !== 0) {
                reject(new Error(`Pipeline exited with code ${code}: ${stderr || stdout}`));
            } else {
                try {
                    resolve(JSON.parse(stdout));
                } catch (e) {
                    reject(new Error(`Invalid pipeline output: ${stdout}`));
                }
            }
        });

        proc.on('error', err => {
            reject(new Error(`Failed to spawn pipeline: ${err.message}`));
        });
    });
}


const activeJobs = new Map();

//   api routes

// registering a reference video in the database
app.post('/api/register', upload.single('video'), async (req, res) => {
    if (!req.file) return res.status(400).json({ error: 'No video file uploaded.' });

    const videoId = uuidv4();
    const videoName = req.file.originalname;
    const videoPath = req.file.path;

    const jobId = uuidv4();
    activeJobs.set(jobId, { status: 'processing', type: 'register', videoName, startTime: Date.now() });

    // Respond immediately with job ID
    res.json({ jobId, status: 'processing', message: `Processing "${videoName}"...` });

    // Process in background
    try {
        const result = await runPipeline('register', [videoPath, videoId, videoName]);
        activeJobs.set(jobId, { status: 'completed', type: 'register', result, videoName });
    } catch (err) {
        activeJobs.set(jobId, { status: 'error', type: 'register', error: err.message, videoName });
    }
});

// query video 
app.post('/api/query', upload.single('video'), async (req, res) => {
    if (!req.file) return res.status(400).json({ error: 'No video file uploaded.' });

    const videoId = uuidv4();
    const videoName = req.file.originalname;
    const videoPath = req.file.path;

    const jobId = uuidv4();
    activeJobs.set(jobId, { status: 'processing', type: 'query', videoName, startTime: Date.now() });

    res.json({ jobId, status: 'processing', message: `Analyzing "${videoName}" for copies...` });

    try {
        const result = await runPipeline('query', [videoPath, videoId, videoName]);
        activeJobs.set(jobId, { status: 'completed', type: 'query', result, videoName });
    } catch (err) {
        activeJobs.set(jobId, { status: 'error', type: 'query', error: err.message, videoName });
    }
});

// job status
app.get('/api/job/:jobId', (req, res) => {
    const job = activeJobs.get(req.params.jobId);
    if (!job) return res.status(404).json({ error: 'Job not found.' });
    res.json(job);
});

// database statistics
app.get('/api/database', async (req, res) => {
    try {
        const result = await runPipeline('info');
        res.json(result);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// clear all reference data
app.delete('/api/database', (req, res) => {
    const dbPath = path.join(DATA_DIR, 'database.json');
    if (fs.existsSync(dbPath)) {
        fs.writeFileSync(dbPath, JSON.stringify({ videos: [], descriptors: [] }, null, 2));
    }
    res.json({ status: 'cleared', message: 'Database has been reset.' });
});

// error handling 
app.use((err, req, res, next) => {
    console.error('[Error]', err.message);
    res.status(500).json({ error: err.message });
});

// start server 
app.listen(PORT, () => {
    console.log(` Server Running at: http://localhost:${PORT} `);
});
