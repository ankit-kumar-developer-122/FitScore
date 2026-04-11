document.addEventListener('DOMContentLoaded', () => {
    const resourceCache = new Map();
    const chartInstances = [];
    let drawflowStylesLoaded = false;
    let drawflowReady = false;
    let jobsLoaded = false;
    let analyticsReady = false;
    let dashboardChartsReady = false;
    let dbData = null;
    let jobsAbortController = null;
    let resumesAbortController = null;
    let dbAbortController = null;

    const user = JSON.parse(localStorage.getItem('fitscore_user') || 'null');
    const navItems = document.querySelectorAll('.nav-item[data-page]');
    const pages = document.querySelectorAll('.page');
    const sidebar = document.getElementById('sidebar');
    const collapseBtn = document.getElementById('collapse-btn');
    const themeBtn = document.getElementById('theme-btn');
    const darkToggle = document.getElementById('dark-mode-toggle');
    const autoEmailToggle = document.getElementById('auto-email-toggle');
    const logoutBtn = document.getElementById('logout-btn');
    const settingsLogout = document.getElementById('settings-logout');
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('resume-file');
    const uploadStatus = document.getElementById('upload-status');
    const resumeAnalysisSummary = document.getElementById('resume-analysis-summary');
    const jobsGrid = document.getElementById('jobs-grid');
    const jobCreateForm = document.getElementById('job-create-form');
    const jobCreateStatus = document.getElementById('job-create-status');
    const resumeTimeline = document.getElementById('resume-timeline');
    const dbTabBar = document.getElementById('db-tab-bar');
    const dbTableCard = document.getElementById('db-table-card');
    const dashAts = document.getElementById('dash-ats');
    const dashAtsStatus = document.getElementById('dash-ats-status');
    const resumeScoreRing = document.getElementById('resume-ats-ring');
    const resumeScoreValue = document.getElementById('resume-ats-score');
    const suggestionsContainer = document.getElementById('resume-suggestions');

    function getApiUrl(path) {
        const baseUrl = ((window.FITSCORE_CONFIG && window.FITSCORE_CONFIG.apiBaseUrl) || '').trim().replace(/\/+$/, '');
        return baseUrl ? `${baseUrl}${path}` : path;
    }

    function loadScriptOnce(src) {
        if (resourceCache.has(src)) return resourceCache.get(src);
        const promise = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.async = true;
            script.onload = resolve;
            script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
            document.head.appendChild(script);
        });
        resourceCache.set(src, promise);
        return promise;
    }

    function loadStylesheetOnce(href) {
        if (resourceCache.has(href)) return resourceCache.get(href);
        const promise = new Promise((resolve, reject) => {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = href;
            link.onload = resolve;
            link.onerror = () => reject(new Error(`Failed to load stylesheet: ${href}`));
            document.head.appendChild(link);
        });
        resourceCache.set(href, promise);
        return promise;
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function normalizeSkills(rawSkills) {
        if (Array.isArray(rawSkills)) return rawSkills;
        try {
            return JSON.parse(rawSkills || '[]');
        } catch {
            return [];
        }
    }

    function updateChartTheme() {
        chartInstances.forEach((chart) => chart.update());
    }

    function formatScore(score) {
        return String(Math.max(0, Number(score) || 0)).padStart(2, '0');
    }

    function renderEmptyResumeAnalysis() {
        if (dashAts) dashAts.textContent = '00';
        if (dashAtsStatus) dashAtsStatus.textContent = 'Upload a resume to analyze';
        if (resumeScoreRing) resumeScoreRing.setAttribute('stroke-dasharray', '0, 100');
        if (resumeScoreValue) resumeScoreValue.textContent = '00';
        if (resumeAnalysisSummary) {
            resumeAnalysisSummary.textContent = 'Latest ATS Score: 00/100';
        }
        if (suggestionsContainer) {
            suggestionsContainer.innerHTML = `
                <div class="flex-center text-sm"><i class="ph ph-info text-blue"></i> Upload a resume to generate ATS suggestions.</div>
                <div class="flex-center text-sm"><i class="ph ph-info text-blue"></i> We will analyze keywords, sections, metrics, and action verbs.</div>
            `;
        }
    }

    function renderResumeAnalysis(analysis) {
        if (!analysis || typeof analysis.ats_score !== 'number') {
            renderEmptyResumeAnalysis();
            return;
        }
        if (dashAts) dashAts.textContent = formatScore(analysis.ats_score);
        if (dashAtsStatus) {
            dashAtsStatus.textContent = analysis.ats_score >= 80 ? 'Resume optimized' : 'Resume needs improvement';
            dashAtsStatus.className = `card-delta ${analysis.ats_score >= 80 ? 'up' : 'down'}`;
        }
        if (resumeScoreRing && typeof analysis.ats_score === 'number') {
            resumeScoreRing.setAttribute('stroke-dasharray', `${analysis.ats_score}, 100`);
        }
        if (resumeScoreValue && typeof analysis.ats_score === 'number') {
            resumeScoreValue.textContent = formatScore(analysis.ats_score);
        }
        if (suggestionsContainer && Array.isArray(analysis.suggestions) && analysis.suggestions.length) {
            suggestionsContainer.innerHTML = analysis.suggestions
                .map((suggestion, index) => {
                    const iconClass = index < 2 ? 'ph-warning-circle text-red' : 'ph-info text-blue';
                    return `<div class="flex-center text-sm"><i class="ph ${iconClass}"></i> ${escapeHtml(suggestion)}</div>`;
                })
                .join('');
        } else if (suggestionsContainer) {
            suggestionsContainer.innerHTML = `
                <div class="flex-center text-sm"><i class="ph ph-check-circle text-green"></i> Your resume looks ATS-friendly for the current scoring rules.</div>
                <div class="flex-center text-sm"><i class="ph ph-info text-blue"></i> Try tailoring keywords for each job description to improve matching further.</div>
            `;
        }
        if (resumeAnalysisSummary && typeof analysis.ats_score === 'number') {
            const keywords = Array.isArray(analysis.keywords_found) ? analysis.keywords_found.length : 0;
            const metrics = analysis.metrics_count ?? 0;
            resumeAnalysisSummary.innerHTML = `<strong>Latest ATS Score:</strong> ${analysis.ats_score}/100 <span class="text-muted">• Keywords matched: ${keywords} • Metrics found: ${metrics}</span>`;
        }
    }

    function setTheme(dark) {
        document.body.className = dark ? 'dark' : 'light';
        if (themeBtn) {
            const icon = themeBtn.querySelector('i');
            if (icon) icon.className = dark ? 'ph ph-moon' : 'ph ph-sun';
        }
        if (darkToggle) darkToggle.classList.toggle('on', dark);
        localStorage.setItem('fitscore_theme', dark ? 'dark' : 'light');
        updateChartTheme();
    }

    function logout() {
        localStorage.removeItem('fitscore_user');
        window.location.href = '/login';
    }

    async function initDashboardCharts() {
        const radarCtx = document.getElementById('skillsRadar');
        if (!radarCtx) return;

        await loadScriptOnce('https://cdn.jsdelivr.net/npm/chart.js');
        Chart.defaults.color = '#8b8b9e';
        Chart.defaults.font.family = 'Inter';

        const chart = new Chart(radarCtx, {
            type: 'radar',
            data: {
                labels: ['Frontend', 'Backend', 'DevOps', 'Design', 'Communication', 'Data'],
                datasets: [{
                    label: 'Your Skills',
                    data: [88, 95, 60, 72, 90, 85],
                    backgroundColor: 'rgba(0,97,255,0.15)',
                    borderColor: '#0061FF',
                    pointBackgroundColor: '#0061FF',
                    borderWidth: 2
                }, {
                    label: 'Market Demand',
                    data: [85, 90, 80, 70, 75, 88],
                    backgroundColor: 'rgba(16,185,129,0.1)',
                    borderColor: '#10b981',
                    pointBackgroundColor: '#10b981',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    r: {
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        angleLines: { color: 'rgba(255,255,255,0.05)' },
                        pointLabels: { font: { size: 11 } },
                        ticks: { display: false },
                        suggestedMin: 0,
                        suggestedMax: 100
                    }
                },
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { boxWidth: 12, padding: 16 }
                    }
                }
            }
        });
        chartInstances.push(chart);
    }

    async function initAnalyticsCharts() {
        await loadScriptOnce('https://cdn.jsdelivr.net/npm/chart.js');

        const demandCtx = document.getElementById('demandChart');
        if (demandCtx) {
            const demandChart = new Chart(demandCtx, {
                type: 'bar',
                data: {
                    labels: ['Python', 'JavaScript', 'React', 'SQL', 'AWS', 'Docker', 'Go', 'ML'],
                    datasets: [
                        { label: 'Market Demand', data: [92, 88, 82, 78, 75, 70, 65, 60], backgroundColor: 'rgba(0,97,255,0.6)', borderRadius: 6 },
                        { label: 'Your Skills', data: [95, 85, 80, 90, 40, 30, 20, 55], backgroundColor: 'rgba(16,185,129,0.5)', borderRadius: 6 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { grid: { display: false } },
                        y: { grid: { color: 'rgba(255,255,255,0.04)' }, beginAtZero: true }
                    },
                    plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } } }
                }
            });
            chartInstances.push(demandChart);
        }

        const distCtx = document.getElementById('distChart');
        if (distCtx) {
            const distChart = new Chart(distCtx, {
                type: 'bar',
                data: {
                    labels: ['0-20', '21-40', '41-60', '61-80', '81-100'],
                    datasets: [{ label: 'Candidates', data: [12, 34, 89, 156, 78], backgroundColor: 'rgba(0,97,255,0.5)', borderRadius: 6 }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { grid: { display: false } },
                        y: { grid: { color: 'rgba(255,255,255,0.04)' }, beginAtZero: true }
                    },
                    plugins: { legend: { display: false } }
                }
            });
            chartInstances.push(distChart);
        }
    }

    async function loadJobs() {
        if (!jobsGrid) return;
        if (jobsAbortController) jobsAbortController.abort();
        jobsAbortController = new AbortController();

        try {
            const res = await fetch(getApiUrl('/api/jobs'), { signal: jobsAbortController.signal });
            const jobs = (await res.json()).map((job) => ({
                ...job,
                skills_list: normalizeSkills(job.skills)
            }));

            jobsGrid.innerHTML = jobs.map((job) => {
                const pct = job.match_pct || 0;
                const color = pct >= 85 ? 'green' : pct >= 70 ? 'blue' : 'amber';
                return `
                <div class="card">
                    <div class="flex-between mb-1">
                        <span class="badge ${color}">${pct}% Match</span>
                        <span class="text-sm text-muted">${escapeHtml(job.experience || '')}</span>
                    </div>
                    <h3 class="fw-600" style="margin-bottom:4px">${escapeHtml(job.title)}</h3>
                    <p class="text-sm text-muted flex-center" style="margin-bottom:10px"><i class="ph ph-buildings"></i> ${escapeHtml(job.company)}</p>
                    <p class="fw-600" style="margin-bottom:12px">${escapeHtml(job.salary || '')}</p>
                    <div class="chip-group" style="margin-bottom:14px">
                        ${job.skills_list.map((skill) => `<span class="chip">${escapeHtml(skill)}</span>`).join('')}
                    </div>
                    <div class="flex-between" style="gap:8px">
                        <button class="btn btn-outline btn-sm" style="flex:1;justify-content:center">Save</button>
                        ${job.application_url
                            ? `<a class="btn btn-primary btn-sm" style="flex:1;justify-content:center" href="${escapeHtml(job.application_url)}" target="_blank" rel="noopener noreferrer">Apply</a>`
                            : '<button class="btn btn-primary btn-sm" style="flex:1;justify-content:center">Apply</button>'}
                    </div>
                </div>`;
            }).join('');
        } catch (error) {
            if (error.name === 'AbortError') return;
            jobsGrid.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><i class="ph ph-warning"></i><p>Failed to load jobs.</p></div>';
        }
    }

    async function createJob(event) {
        event.preventDefault();
        if (!jobCreateForm || !jobCreateStatus) return;

        const formData = new FormData(jobCreateForm);
        const skills = String(formData.get('skills') || '')
            .split(',')
            .map((skill) => skill.trim())
            .filter(Boolean);

        formData.set('skills', JSON.stringify(skills));
        jobCreateStatus.innerHTML = '<span class="text-blue">Creating job and notifying matched users...</span>';

        try {
            const res = await fetch(getApiUrl('/api/jobs'), {
                method: 'POST',
                body: formData,
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(data.detail || data.message || `Job creation failed (${res.status})`);
            }

            jobCreateForm.reset();
            const notifications = data.notifications || {};
            jobCreateStatus.innerHTML = `
                <span class="text-green">Job created successfully.</span>
                <span class="text-muted"> Notified ${escapeHtml(notifications.notified_count ?? 0)} matched users for ${escapeHtml(notifications.job_title || 'this role')}.</span>
            `;
            jobsLoaded = false;
            await loadJobs();
            jobsLoaded = true;
        } catch (error) {
            jobCreateStatus.innerHTML = `<span class="text-red">${escapeHtml(error.message || 'Could not create job.')}</span>`;
        }
    }

    async function doUpload() {
        if (!fileInput || !fileInput.files.length || !uploadStatus) return;
        const uid = user ? user.id : 'guest';
        const fd = new FormData();
        fd.append('user_id', uid);
        fd.append('file', fileInput.files[0]);
        fd.append('version_tag', 'Original');
        uploadStatus.innerHTML = '<p class="text-sm text-blue">Uploading...</p>';

        try {
            const res = await fetch(getApiUrl('/api/resumes/upload'), { method: 'POST', body: fd });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const message = data.detail || data.message || `Upload failed (${res.status})`;
                throw new Error(message);
            }
            uploadStatus.innerHTML = `<p class="text-sm text-green">Uploaded: ${escapeHtml(data.filename)}</p>`;
            renderResumeAnalysis(data.analysis);
            loadResumes(uid);
        } catch (error) {
            uploadStatus.innerHTML = `<p class="text-sm text-red">${escapeHtml(error.message || 'Upload failed.')}</p>`;
        }
    }

    async function loadResumes(uid) {
        if (!resumeTimeline) return;
        if (resumesAbortController) resumesAbortController.abort();
        resumesAbortController = new AbortController();

        try {
            const res = await fetch(getApiUrl(`/api/resumes/${uid}`), { signal: resumesAbortController.signal });
            const list = await res.json();
            if (!list.length) {
                resumeTimeline.innerHTML = '<div class="empty-state text-sm">No resumes uploaded yet.</div>';
                renderEmptyResumeAnalysis();
                return;
            }
            renderResumeAnalysis(list[0].analysis);

            resumeTimeline.innerHTML = list.map((resume) => `
                <div class="timeline-item">
                    <div class="tl-date">${new Date(resume.uploaded_at).toLocaleDateString()}</div>
                    <div class="tl-title">${escapeHtml(resume.filename)} <span class="badge blue" style="margin-left:6px">${escapeHtml(resume.version_tag)}</span> <span class="badge green" style="margin-left:6px">ATS ${escapeHtml(resume.ats_score ?? 0)}</span></div>
                </div>
            `).join('');
        } catch (error) {
            if (error.name !== 'AbortError') {
                resumeTimeline.innerHTML = '<div class="empty-state text-sm">Could not load resumes.</div>';
            }
        }
    }

    async function initDrawflow() {
        const el = document.getElementById('drawflow-canvas');
        const panel = document.getElementById('props-panel');
        if (!el || !panel) return;

        if (!drawflowStylesLoaded) {
            await loadStylesheetOnce('https://cdn.jsdelivr.net/gh/jerosoler/Drawflow/dist/drawflow.min.css');
            drawflowStylesLoaded = true;
        }
        await loadScriptOnce('https://cdn.jsdelivr.net/gh/jerosoler/Drawflow/dist/drawflow.min.js');

        const editor = new Drawflow(el);
        editor.start();

        const mkNode = (icon, label, sub, color) => `
            <div style="padding:10px;display:flex;align-items:center;gap:8px">
                <i class="ph ph-${icon}" style="color:${color};font-size:1.4rem"></i>
                <div>
                    <strong style="display:block;font-size:.85rem">${escapeHtml(label)}</strong>
                    <span style="font-size:.72rem;color:#8b8b9e">${escapeHtml(sub)}</span>
                </div>
            </div>`;

        editor.addNode('scraper', 0, 1, 80, 80, 'scraper', {}, mkNode('globe', 'LinkedIn Scraper', 'Active', '#10b981'));
        editor.addNode('clean', 1, 1, 350, 60, 'clean', {}, mkNode('funnel', 'Data Cleaner', 'Ready', '#0061FF'));
        editor.addNode('db', 1, 0, 620, 80, 'db', {}, mkNode('database', 'DB Store', 'Connected', '#f59e0b'));
        editor.addConnection(1, 2, 'output_1', 'input_1');
        editor.addConnection(2, 3, 'output_1', 'input_1');

        let dragNode = null;
        document.querySelectorAll('.palette-item').forEach((item) => {
            item.addEventListener('dragstart', () => {
                dragNode = item.dataset.node;
            });
        });

        el.addEventListener('dragover', (event) => event.preventDefault());
        el.addEventListener('drop', (event) => {
            event.preventDefault();
            if (!dragNode) return;
            const rect = el.getBoundingClientRect();
            editor.addNode(dragNode, 1, 1, event.clientX - rect.left, event.clientY - rect.top, dragNode, {}, mkNode('cube', dragNode, 'New', '#0061FF'));
            dragNode = null;
        });

        editor.on('nodeSelected', (id) => {
            panel.innerHTML = `
                <h3 class="section-title">Node #${id}</h3>
                <label class="text-sm text-muted" style="display:block;margin-bottom:4px">Name</label>
                <input style="width:100%;padding:8px 10px;background:var(--bg-input);border:1px solid var(--border);border-radius:var(--r-md);color:var(--text-1);outline:none" value="Node ${id}">
                <button class="btn btn-primary btn-sm mt-1" style="width:100%;justify-content:center">Save</button>`;
        });

        editor.on('nodeUnselected', () => {
            panel.innerHTML = '<h3 class="section-title">Properties</h3><p class="text-muted text-sm">Select a node to configure.</p>';
        });
    }

    async function loadDbTables() {
        if (!dbTabBar || !dbTableCard || dbData) return;
        if (dbAbortController) dbAbortController.abort();
        dbAbortController = new AbortController();

        try {
            const res = await fetch(getApiUrl('/api/db/tables'), { signal: dbAbortController.signal });
            dbData = await res.json();
            const names = Object.keys(dbData);

            dbTabBar.innerHTML = names.map((name, index) =>
                `<button class="btn ${index === 0 ? 'btn-primary' : 'btn-outline'} btn-sm" data-tbl="${escapeHtml(name)}">${escapeHtml(name)}</button>`
            ).join('');

            dbTabBar.querySelectorAll('button').forEach((btn) => {
                btn.addEventListener('click', () => {
                    dbTabBar.querySelectorAll('button').forEach((button) => {
                        button.className = 'btn btn-outline btn-sm';
                    });
                    btn.className = 'btn btn-primary btn-sm';
                    renderTable(btn.dataset.tbl);
                });
            });

            if (names.length) renderTable(names[0]);
        } catch (error) {
            if (error.name === 'AbortError') return;
            dbTableCard.innerHTML = '<div class="empty-state"><i class="ph ph-warning"></i><p>Could not load tables.</p></div>';
        }
    }

    function renderTable(name) {
        if (!dbTableCard) return;
        const rows = dbData[name] || [];
        if (!rows.length) {
            dbTableCard.innerHTML = '<div class="empty-state text-sm">Table is empty.</div>';
            return;
        }

        const cols = Object.keys(rows[0]);
        dbTableCard.innerHTML = `<div style="overflow-x:auto"><table class="data-table">
            <thead><tr>${cols.map((col) => `<th>${escapeHtml(col)}</th>`).join('')}</tr></thead>
            <tbody>${rows.map((row) => `<tr>${cols.map((col) => `<td>${escapeHtml(row[col] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody>
        </table></div>`;
    }

    async function showPage(name) {
        navItems.forEach((navItem) => navItem.classList.toggle('active', navItem.dataset.page === name));
        pages.forEach((page) => {
            page.classList.toggle('active', page.id === `page-${name}`);
        });

        if (name === 'dashboard' && !dashboardChartsReady) {
            await initDashboardCharts();
            dashboardChartsReady = true;
        }
        if (name === 'automation' && !drawflowReady) {
            await initDrawflow();
            drawflowReady = true;
        }
        if (name === 'jobs' && !jobsLoaded) {
            await loadJobs();
            jobsLoaded = true;
        }
        if (name === 'analytics' && !analyticsReady) {
            await initAnalyticsCharts();
            analyticsReady = true;
        }
        if (name === 'database') {
            await loadDbTables();
        }
    }

    if (user) {
        const nameEl = document.getElementById('user-display-name');
        const roleEl = document.getElementById('user-display-role');
        const emailEl = document.getElementById('settings-email');
        if (nameEl) nameEl.textContent = user.name || 'User';
        if (roleEl) roleEl.textContent = user.role === 'recruiter' ? 'Recruiter' : 'Candidate';
        if (emailEl) emailEl.textContent = user.email || '';
    }

    const savedTheme = localStorage.getItem('fitscore_theme');
    setTheme(savedTheme !== 'light');

    navItems.forEach((item) => {
        item.addEventListener('click', () => {
            showPage(item.dataset.page);
        });
    });

    if (collapseBtn && sidebar) {
        collapseBtn.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            sidebar.classList.toggle('open');
        });
    }

    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            setTheme(document.body.classList.contains('light'));
        });
    }

    if (darkToggle) {
        darkToggle.addEventListener('click', () => {
            setTheme(!darkToggle.classList.contains('on'));
        });
    }

    document.querySelectorAll('.toggle').forEach((toggle) => {
        if (toggle.id === 'dark-mode-toggle') return;
        toggle.addEventListener('click', () => toggle.classList.toggle('on'));
    });

    if (autoEmailToggle && user) {
        autoEmailToggle.addEventListener('click', async () => {
            try {
                const res = await fetch(getApiUrl(`/api/users/${user.id}/toggle-email`), { method: 'POST' });
                const data = await res.json();
                autoEmailToggle.classList.toggle('on', data.auto_email);
            } catch {
                // Keep the current state if the update fails.
            }
        });
    }

    if (logoutBtn) logoutBtn.addEventListener('click', logout);
    if (settingsLogout) settingsLogout.addEventListener('click', logout);

    if (uploadZone && fileInput) {
        uploadZone.addEventListener('dragover', (event) => {
            event.preventDefault();
            uploadZone.classList.add('dragover');
        });
        uploadZone.addEventListener('dragleave', () => {
            uploadZone.classList.remove('dragover');
        });
        uploadZone.addEventListener('drop', (event) => {
            event.preventDefault();
            uploadZone.classList.remove('dragover');
            if (event.dataTransfer.files.length) {
                fileInput.files = event.dataTransfer.files;
                doUpload();
            }
        });
        fileInput.addEventListener('change', doUpload);
    }

    if (jobCreateForm) {
        jobCreateForm.addEventListener('submit', createJob);
    }

    renderEmptyResumeAnalysis();
    loadResumes(user ? user.id : 'guest');
    showPage('dashboard');
});
