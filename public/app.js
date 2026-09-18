// Frontend Application Logic
// Handles file uploads, tab navigation, job polling, and result rendering.

// ─── State ──────────────────────────────────────────────────────────
let queryFile = null;
let pollingInterval = null;

// ─── DOM Elements ───────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

// ─── Tab Navigation ─────────────────────────────────────────────────
$$('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        $$('.nav-btn').forEach(b => b.classList.remove('active'));
        $$('.tab-content').forEach(t => t.classList.remove('active'));
        btn.classList.add('active');
        $(`tab-${tab}`).classList.add('active');

        // Load database info when switching to db tab
        if (tab === 'database') loadDatabaseInfo();
    });
});

// ─── File Size Formatter ────────────────────────────────────────────
function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

// ─── Upload Zone Setup ──────────────────────────────────────────────
function setupUploadZone(zoneId, inputId, onFile) {
    const zone = $(zoneId);
    const input = $(inputId);

    zone.addEventListener('click', () => input.click());

    zone.addEventListener('dragover', e => {
        e.preventDefault();
        zone.classList.add('drag-over');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('drag-over');
    });

    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) onFile(e.dataTransfer.files[0]);
    });

    input.addEventListener('change', () => {
        if (input.files.length) onFile(input.files[0]);
        input.value = '';
    });
}

// ─── REGISTER: Multi-File Handling ──────────────────────────────────
let registerFiles = [];

function addRegisterFiles(newFiles) {
    for (const file of newFiles) {
        // Avoid duplicates by name+size
        if (!registerFiles.some(f => f.name === file.name && f.size === file.size)) {
            registerFiles.push(file);
        }
    }
    renderRegisterFileList();
}

function renderRegisterFileList() {
    const list = $('register-file-list');
    const items = $('register-file-items');
    const count = $('register-file-count');

    if (registerFiles.length === 0) {
        list.classList.add('hidden');
        $('register-drop-zone').classList.remove('hidden');
        return;
    }

    list.classList.remove('hidden');
    count.textContent = `${registerFiles.length} video${registerFiles.length > 1 ? 's' : ''} selected`;

    items.innerHTML = registerFiles.map((file, i) => `
        <div class="batch-item" data-index="${i}">
            <div class="batch-item-icon">🎬</div>
            <div class="batch-item-info">
                <div class="batch-item-name">${file.name}</div>
                <div class="batch-item-size">${formatSize(file.size)}</div>
            </div>
            <button class="batch-item-remove" onclick="removeRegisterFile(${i})" title="Remove">✕</button>
        </div>
    `).join('');
}

function removeRegisterFile(index) {
    registerFiles.splice(index, 1);
    renderRegisterFileList();
}

// Setup upload zone for register (multi-file)
(function() {
    const zone = $('register-drop-zone');
    const input = $('register-file-input');

    zone.addEventListener('click', () => input.click());

    zone.addEventListener('dragover', e => {
        e.preventDefault();
        zone.classList.add('drag-over');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('drag-over');
    });

    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) {
            addRegisterFiles(e.dataTransfer.files);
            hideRegisterResults();
        }
    });

    input.addEventListener('change', () => {
        if (input.files.length) {
            addRegisterFiles(input.files);
            hideRegisterResults();
        }
        input.value = '';
    });
})();

$('register-clear-all').addEventListener('click', () => {
    registerFiles = [];
    renderRegisterFileList();
});

function hideRegisterResults() {
    $('register-batch-results')?.classList.add('hidden');
    $('register-batch-progress')?.classList.add('hidden');
    $('register-error')?.classList.add('hidden');
}

// ─── REGISTER: Batch Upload ─────────────────────────────────────────
$('register-submit-btn').addEventListener('click', async () => {
    if (registerFiles.length === 0) return;
    try {
        await batchRegister();
    } catch (err) {
        console.error('[Batch Register] Unexpected error:', err);
        $('register-batch-progress').classList.add('hidden');
        $('register-drop-zone').classList.remove('hidden');
        $('register-error-msg').textContent = 'Unexpected error: ' + err.message;
        $('register-error').classList.remove('hidden');
    }
});

async function batchRegister() {
    const files = [...registerFiles];
    const total = files.length;

    console.log(`[Batch Register] Starting registration of ${total} files`);

    // Hide file list, show progress
    $('register-file-list').classList.add('hidden');
    $('register-drop-zone').classList.add('hidden');
    hideRegisterResults();
    $('register-batch-progress').classList.remove('hidden');
    $('register-batch-counter').textContent = `0 / ${total}`;
    $('register-progress-fill').style.width = '0%';

    const results = [];

    for (let i = 0; i < total; i++) {
        const file = files[i];
        console.log(`[Batch Register] Processing file ${i + 1}/${total}: ${file.name}`);
        $('register-batch-current').textContent = `Processing: ${file.name}`;
        $('register-batch-counter').textContent = `${i + 1} / ${total}`;
        $('register-progress-fill').style.width = `${((i) / total) * 100}%`;

        try {
            // Upload
            const formData = new FormData();
            formData.append('video', file);

            console.log(`[Batch Register] Uploading ${file.name}...`);
            const res = await fetch('/api/register', { method: 'POST', body: formData });

            if (!res.ok) {
                console.error(`[Batch Register] Upload failed for ${file.name}: HTTP ${res.status}`);
                results.push({ name: file.name, status: 'error', error: `Upload failed (HTTP ${res.status})` });
                continue;
            }

            const data = await res.json();
            console.log(`[Batch Register] Upload response for ${file.name}:`, data);

            if (data.error) {
                results.push({ name: file.name, status: 'error', error: data.error });
                continue;
            }

            if (!data.jobId) {
                results.push({ name: file.name, status: 'error', error: 'No job ID returned' });
                continue;
            }

            // Poll for completion (with 5-minute timeout)
            console.log(`[Batch Register] Waiting for job ${data.jobId}...`);
            const result = await waitForJob(data.jobId, 300000);
            console.log(`[Batch Register] Job result for ${file.name}:`, result.status);

            if (result.status === 'completed') {
                results.push({ name: file.name, status: 'success', result: result.result });
            } else {
                results.push({ name: file.name, status: 'error', error: result.error || 'Processing failed' });
            }

        } catch (err) {
            console.error(`[Batch Register] Error processing ${file.name}:`, err);
            results.push({ name: file.name, status: 'error', error: err.message || 'Unknown error' });
        }
    }

    // Complete
    console.log(`[Batch Register] All done. Results:`, results);
    $('register-progress-fill').style.width = '100%';
    $('register-batch-current').textContent = 'All done!';

    setTimeout(() => {
        $('register-batch-progress').classList.add('hidden');
        showBatchResults(results);
        registerFiles = [];
        $('register-drop-zone').classList.remove('hidden');
    }, 600);
}

function waitForJob(jobId, timeoutMs = 300000) {
    return new Promise((resolve) => {
        const startTime = Date.now();

        const poll = setInterval(async () => {
            // Timeout check
            if (Date.now() - startTime > timeoutMs) {
                clearInterval(poll);
                console.warn(`[waitForJob] Timeout for job ${jobId}`);
                resolve({ status: 'error', error: 'Processing timed out (5 min)' });
                return;
            }

            try {
                const res = await fetch(`/api/job/${jobId}`);
                if (!res.ok) {
                    console.warn(`[waitForJob] Bad response polling job ${jobId}: HTTP ${res.status}`);
                    return; // Keep polling on transient errors
                }
                const job = await res.json();
                if (job.status === 'completed' || job.status === 'error') {
                    clearInterval(poll);
                    resolve(job);
                }
            } catch (err) {
                console.error(`[waitForJob] Poll error for job ${jobId}:`, err);
                // Don't give up on transient network errors, keep polling
            }
        }, 2000);
    });
}

function showBatchResults(results) {
    const successCount = results.filter(r => r.status === 'success').length;
    const errorCount = results.filter(r => r.status === 'error').length;

    $('register-batch-result-title').textContent =
        errorCount === 0 ? `${successCount} Video${successCount > 1 ? 's' : ''} Registered Successfully` :
        `${successCount} Registered, ${errorCount} Failed`;

    const listEl = $('register-batch-result-list');
    listEl.innerHTML = results.map(r => `
        <div class="batch-result-item ${r.status}">
            <span class="batch-result-status">${r.status === 'success' ? '✓' : '✕'}</span>
            <div class="batch-result-info">
                <div class="batch-result-name">${r.name}</div>
                <div class="batch-result-meta">${
                    r.status === 'success'
                        ? `${r.result?.total_segments || 0} segments · ${r.result?.total_descriptors || 0} descriptors`
                        : r.error
                }</div>
            </div>
        </div>
    `).join('');

    $('register-batch-results').classList.remove('hidden');
}

setupUploadZone('query-drop-zone', 'query-file-input', file => {
    queryFile = file;
    $('query-file-name').textContent = file.name;
    $('query-file-size').textContent = formatSize(file.size);
    $('query-preview').classList.remove('hidden');
    $('query-drop-zone').classList.add('hidden');
    hideResults('query');
});

$('query-remove-file').addEventListener('click', () => {
    queryFile = null;
    $('query-preview').classList.add('hidden');
    $('query-drop-zone').classList.remove('hidden');
});

$('query-submit-btn').addEventListener('click', () => {
    if (!queryFile) return;
    uploadVideo('query', queryFile);
});

// ─── Hide Result Cards ──────────────────────────────────────────────
function hideResults(type) {
    $(`${type}-result`)?.classList.add('hidden');
    $(`${type}-error`)?.classList.add('hidden');
    $(`${type}-processing`)?.classList.add('hidden');
}

// ─── Upload & Process (Query only) ──────────────────────────────────
async function uploadVideo(type, file) {
    hideResults(type);

    // Show processing
    $(`${type}-preview`).classList.add('hidden');
    $(`${type}-processing`).classList.remove('hidden');

    // Animate pipeline steps
    animatePipeline(type);

    const formData = new FormData();
    formData.append('video', file);

    try {
        const res = await fetch(`/api/${type}`, { method: 'POST', body: formData });
        const data = await res.json();

        if (data.error) {
            showError(type, data.error);
            return;
        }

        // Poll for job completion
        pollJob(data.jobId, type);

    } catch (err) {
        showError(type, `Network error: ${err.message}`);
    }
}

// ─── Pipeline Step Animation ────────────────────────────────────────
function animatePipeline(type) {
    const steps = $$(`#${type}-pipeline .pipeline-step`);
    let current = 0;

    const interval = setInterval(() => {
        steps.forEach((s, i) => {
            s.classList.remove('active', 'completed');
            if (i < current) s.classList.add('completed');
            if (i === current) s.classList.add('active');
        });
        current++;
        if (current > steps.length) {
            current = 0;
        }
    }, 2000);

    // Store interval ID on element
    $(`${type}-processing`).dataset.animInterval = interval;
}

function stopPipelineAnimation(type) {
    const interval = $(`${type}-processing`).dataset.animInterval;
    if (interval) clearInterval(parseInt(interval));

    // Mark all as completed
    $$(`#${type}-pipeline .pipeline-step`).forEach(s => {
        s.classList.remove('active');
        s.classList.add('completed');
    });
}

// ─── Job Polling (Query only) ───────────────────────────────────────
function pollJob(jobId, type) {
    const poll = setInterval(async () => {
        try {
            const res = await fetch(`/api/job/${jobId}`);
            const job = await res.json();

            if (job.status === 'completed') {
                clearInterval(poll);
                stopPipelineAnimation(type);

                setTimeout(() => {
                    $(`${type}-processing`).classList.add('hidden');
                    showQueryResult(job.result);
                }, 800);

            } else if (job.status === 'error') {
                clearInterval(poll);
                stopPipelineAnimation(type);
                showError(type, job.error);
            }
        } catch (err) {
            clearInterval(poll);
            showError(type, `Polling error: ${err.message}`);
        }
    }, 1500);
}

// ─── Confidence Threshold ───────────────────────────────────────────
// Only matches at or above this percentage are treated as real copyright alerts.
const CONFIDENCE_THRESHOLD = 50;

// ─── Show Query Result ──────────────────────────────────────────────
function showQueryResult(result) {
    const header = $('query-result-header');
    const body = $('query-result-body');

    if (result.status === 'no_references') {
        header.innerHTML = `
            <div class="detection-header">
                <div class="detection-icon no-copy">⚠️</div>
                <div class="detection-title">
                    <h3>No References Available</h3>
                    <p>Register reference videos first, then try again.</p>
                </div>
            </div>
        `;
        body.innerHTML = '';
    } else if (result.detections && result.detections.length > 0) {
        // Split into high-confidence (alert-worthy) vs low-confidence (informational only)
        const highConf = result.detections.filter(d => d.confidence_pct >= CONFIDENCE_THRESHOLD);
        const lowConf  = result.detections.filter(d => d.confidence_pct <  CONFIDENCE_THRESHOLD);

        if (highConf.length > 0) {
            // ── COPYRIGHT ALERT: at least one match above threshold ──────────
            const bestMatch = highConf[0];
            header.innerHTML = `
                <div class="detection-header">
                    <div class="detection-icon copy-found">⚠️</div>
                    <div class="detection-title">
                        <h3 style="color: var(--accent-red)">Potential Copies Detected!</h3>
                        <p>${highConf.length} high-confidence match(es) found across reference database</p>
                    </div>
                </div>
                <div class="query-video-info">
                    <div class="query-video-row">
                        <div class="query-video-card">
                            <div class="qv-label">QUERY VIDEO</div>
                            <div class="qv-name">🔍 ${result.query_info?.video_name || 'Unknown'}</div>
                            <div class="qv-meta">${result.query_info?.total_segments || 0} segments analyzed</div>
                        </div>
                        <div class="qv-arrow">→</div>
                        <div class="query-video-card qv-match">
                            <div class="qv-label">BEST MATCH</div>
                            <div class="qv-name">🎬 ${bestMatch.reference_video_name}</div>
                            <div class="qv-meta">${bestMatch.confidence_pct}% confidence</div>
                        </div>
                    </div>
                </div>
            `;

            body.innerHTML = highConf.map((d, i) => {
                const confColor = '#ef4444';
                return `
                    <div class="detection-item">
                        <div class="detection-item-header">
                            <h4>Match #${i + 1}: ${d.reference_video_name}</h4>
                            <span class="confidence-badge confidence-high">${d.confidence_pct}% confidence</span>
                        </div>
                        <div class="confidence-bar">
                            <div class="confidence-fill" style="width: ${d.confidence_pct}%; background: ${confColor};"></div>
                        </div>
                        <div class="detection-details">
                            <div class="detail-item">
                                <div class="detail-label">Query Range</div>
                                <div class="detail-value">${d.query_time_range[0]}s — ${d.query_time_range[1]}s</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Reference Range</div>
                                <div class="detail-value">${d.reference_time_range[0]}s — ${d.reference_time_range[1]}s</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Matched Segments</div>
                                <div class="detail-value">${d.matched_segments} (${d.unique_ref_segments || '?'} unique ref)</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Detection Method</div>
                                <div class="detail-value">📊 Temporal Hough Voting${d.peak_strength ? ' · Peak: ' + (d.peak_strength * 100).toFixed(0) + '%' : ''}</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');

            // Append low-confidence as a collapsible informational note
            if (lowConf.length > 0) {
                body.innerHTML += `
                    <details class="low-conf-details">
                        <summary>
                            <span class="low-conf-summary-icon">ℹ️</span>
                            ${lowConf.length} low-confidence match(es) below threshold — click to expand
                        </summary>
                        <div class="low-conf-list">
                            ${lowConf.map(d => `
                                <div class="low-conf-item">
                                    <span class="low-conf-name">🎬 ${d.reference_video_name}</span>
                                    <span class="confidence-badge confidence-low">${d.confidence_pct}% confidence</span>
                                </div>
                            `).join('')}
                        </div>
                    </details>
                `;
            }

        } else {
            // ── ALL matches are below threshold → treat as clean ─────────────
            header.innerHTML = `
                <div class="detection-header">
                    <div class="detection-icon no-copy">✓</div>
                    <div class="detection-title">
                        <h3 style="color: var(--accent-green)">No Copies Detected</h3>
                        <p>No high-confidence matches found in the reference database.</p>
                    </div>
                </div>
            `;

            body.innerHTML = `
                <div class="detection-details" style="margin-top: 16px;">
                    <div class="detail-item">
                        <div class="detail-label">Segments Analyzed</div>
                        <div class="detail-value">${result.query_info?.total_segments || 0}</div>
                    </div>
                    <div class="detail-item">
                        <div class="detail-label">Status</div>
                        <div class="detail-value" style="color: var(--accent-green);">Clean ✓</div>
                    </div>
                </div>
                <details class="low-conf-details">
                    <summary>
                        <span class="low-conf-summary-icon">ℹ️</span>
                        ${lowConf.length} low-confidence signal(s) below ${CONFIDENCE_THRESHOLD}% threshold — click to expand
                    </summary>
                    <div class="low-conf-list">
                        ${lowConf.map(d => `
                            <div class="low-conf-item">
                                <span class="low-conf-name">🎬 ${d.reference_video_name}</span>
                                <span class="confidence-badge confidence-low">${d.confidence_pct}% confidence</span>
                            </div>
                        `).join('')}
                    </div>
                </details>
            `;
        }
    } else {
        header.innerHTML = `
            <div class="detection-header">
                <div class="detection-icon no-copy">✓</div>
                <div class="detection-title">
                    <h3 style="color: var(--accent-green)">No Copies Detected</h3>
                    <p>This video does not match any registered references.</p>
                </div>
            </div>
        `;

        body.innerHTML = `
            <div class="detection-details" style="margin-top: 16px;">
                <div class="detail-item">
                    <div class="detail-label">Segments Analyzed</div>
                    <div class="detail-value">${result.query_info?.total_segments || 0}</div>
                </div>
                <div class="detail-item">
                    <div class="detail-label">Status</div>
                    <div class="detail-value" style="color: var(--accent-green);">Clean ✓</div>
                </div>
            </div>
        `;
    }

    $('query-result').classList.remove('hidden');
    $('query-drop-zone').classList.remove('hidden');
    queryFile = null;
}

// ─── Show Error ─────────────────────────────────────────────────────
function showError(type, message) {
    $(`${type}-processing`).classList.add('hidden');
    $(`${type}-error-msg`).textContent = message;
    $(`${type}-error`).classList.remove('hidden');
    $(`${type}-drop-zone`).classList.remove('hidden');

    if (type === 'register') registerFile = null;
    else queryFile = null;
}

// ─── Database Tab ───────────────────────────────────────────────────
async function loadDatabaseInfo() {
    try {
        const res = await fetch('/api/database');
        const data = await res.json();

        const totalSegments = data.videos?.reduce((sum, v) => sum + (v.total_segments || 0), 0) || 0;

        $('stat-videos').querySelector('.stat-value').textContent = data.total_videos || 0;
        $('stat-descriptors').querySelector('.stat-value').textContent = data.total_descriptors || 0;
        $('stat-segments').querySelector('.stat-value').textContent = totalSegments;

        const list = $('db-video-list');

        if (data.videos && data.videos.length > 0) {
            $('db-empty').classList.add('hidden');
            // Remove existing items
            list.querySelectorAll('.db-video-item').forEach(el => el.remove());

            data.videos.forEach(v => {
                const item = document.createElement('div');
                item.className = 'db-video-item';
                item.innerHTML = `
                    <div class="db-video-icon">🎬</div>
                    <div class="db-video-info">
                        <div class="db-video-name">${v.video_name}</div>
                        <div class="db-video-meta">${v.total_segments} segments · ${v.total_frames} frames · ${v.frame_size?.[0]}×${v.frame_size?.[1]}</div>
                    </div>
                `;
                list.insertBefore(item, $('db-empty'));
            });
        } else {
            $('db-empty').classList.remove('hidden');
            list.querySelectorAll('.db-video-item').forEach(el => el.remove());
        }
    } catch (err) {
        console.error('Failed to load database info:', err);
    }
}

$('db-refresh-btn').addEventListener('click', loadDatabaseInfo);

$('db-clear-btn').addEventListener('click', async () => {
    if (!confirm('Are you sure you want to clear the entire reference database? This cannot be undone.')) return;

    try {
        await fetch('/api/database', { method: 'DELETE' });
        loadDatabaseInfo();
    } catch (err) {
        alert('Failed to clear database: ' + err.message);
    }
});

// ─── Initial Load ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Pre-load database info
    loadDatabaseInfo();
});
