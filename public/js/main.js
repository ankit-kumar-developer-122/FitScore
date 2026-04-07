// ═══════════════════════════════════════════════════════════════
//  FitScore — Main Application Logic
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    // ── Auth guard ───────────────────────────────────────────────
    const user = JSON.parse(localStorage.getItem('fitscore_user') || 'null');
    if (user) {
        const nameEl = document.getElementById('user-display-name');
        const roleEl = document.getElementById('user-display-role');
        const emailEl = document.getElementById('settings-email');
        if (nameEl) nameEl.textContent = user.name || 'User';
        if (roleEl) roleEl.textContent = user.role === 'recruiter' ? 'Recruiter' : 'Candidate';
        if (emailEl) emailEl.textContent = user.email || '';
    }

    // ── Navigation ──────────────────────────────────────────────
    const navItems = document.querySelectorAll('.nav-item[data-page]');
    const pages   = document.querySelectorAll('.page');
    let drawflowReady = false;
    let jobsLoaded = false;
    let analyticsReady = false;

    function showPage(name) {
        navItems.forEach(n => n.classList.toggle('active', n.dataset.page === name));
        pages.forEach(p => {
            p.classList.remove('active');
            if (p.id === 'page-' + name) p.classList.add('active');
        });
        // Lazy init
        if (name === 'automation' && !drawflowReady) { initDrawflow(); drawflowReady = true; }
        if (name === 'jobs' && !jobsLoaded) { loadJobs(); jobsLoaded = true; }
        if (name === 'analytics' && !analyticsReady) { initAnalyticsCharts(); analyticsReady = true; }
        if (name === 'database') { loadDbTables(); }
    }

    navItems.forEach(item => {
        item.addEventListener('click', () => showPage(item.dataset.page));
    });

    // ── Sidebar collapse ────────────────────────────────────────
    document.getElementById('collapse-btn').addEventListener('click', () => {
        document.getElementById('sidebar').classList.toggle('collapsed');
    });

    // ── Theme toggle ────────────────────────────────────────────
    const themeBtn = document.getElementById('theme-btn');
    const darkToggle = document.getElementById('dark-mode-toggle');

    function setTheme(dark) {
        document.body.className = dark ? 'dark' : 'light';
        themeBtn.querySelector('i').className = dark ? 'ph ph-moon' : 'ph ph-sun';
        if (darkToggle) darkToggle.classList.toggle('on', dark);
        localStorage.setItem('fitscore_theme', dark ? 'dark' : 'light');
    }

    const savedTheme = localStorage.getItem('fitscore_theme');
    setTheme(savedTheme !== 'light');

    themeBtn.addEventListener('click', () => setTheme(document.body.classList.contains('light')));
    if (darkToggle) darkToggle.addEventListener('click', () => setTheme(!darkToggle.classList.contains('on')));

    // ── Toggles (generic) ───────────────────────────────────────
    document.querySelectorAll('.toggle').forEach(t => {
        if (t.id === 'dark-mode-toggle') return; // handled above
        t.addEventListener('click', () => t.classList.toggle('on'));
    });

    // ── Auto-email toggle (API) ─────────────────────────────────
    const autoEmailToggle = document.getElementById('auto-email-toggle');
    if (autoEmailToggle && user) {
        autoEmailToggle.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/users/' + user.id + '/toggle-email', { method: 'POST' });
                const data = await res.json();
                autoEmailToggle.classList.toggle('on', data.auto_email);
            } catch(e) { /* silent */ }
        });
    }

    // ── Logout ──────────────────────────────────────────────────
    function logout() {
        localStorage.removeItem('fitscore_user');
        window.location.href = '/login';
    }
    document.getElementById('logout-btn').addEventListener('click', logout);
    const settingsLogout = document.getElementById('settings-logout');
    if (settingsLogout) settingsLogout.addEventListener('click', logout);

    // ── Dashboard Radar Chart ───────────────────────────────────
    const radarCtx = document.getElementById('skillsRadar');
    if (radarCtx) {
        const isDark = () => document.body.classList.contains('dark');
        Chart.defaults.color = '#8b8b9e';
        Chart.defaults.font.family = 'Inter';
        new Chart(radarCtx, {
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
                responsive: true, maintainAspectRatio: false,
                scales: { r: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    angleLines: { color: 'rgba(255,255,255,0.05)' },
                    pointLabels: { font: { size: 11 } },
                    ticks: { display: false }, suggestedMin: 0, suggestedMax: 100
                }},
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } } }
            }
        });
    }

    // ── Load Jobs ───────────────────────────────────────────────
    async function loadJobs() {
        const grid = document.getElementById('jobs-grid');
        try {
            const res = await fetch('/api/jobs');
            const jobs = await res.json();
            grid.innerHTML = jobs.map(j => {
                const pct = j.match_pct || 0;
                const color = pct >= 85 ? 'green' : pct >= 70 ? 'blue' : 'amber';
                return `
                <div class="card">
                    <div class="flex-between mb-1">
                        <span class="badge ${color}">${pct}% Match</span>
                        <span class="text-sm text-muted">${j.experience || ''}</span>
                    </div>
                    <h3 class="fw-600" style="margin-bottom:4px">${j.title}</h3>
                    <p class="text-sm text-muted flex-center" style="margin-bottom:10px"><i class="ph ph-buildings"></i> ${j.company}</p>
                    <p class="fw-600" style="margin-bottom:12px">${j.salary || ''}</p>
                    <div class="chip-group" style="margin-bottom:14px">
                        ${(JSON.parse(j.skills || '[]')).map(s => `<span class="chip">${s}</span>`).join('')}
                    </div>
                    <div class="flex-between" style="gap:8px">
                        <button class="btn btn-outline btn-sm" style="flex:1;justify-content:center">Save</button>
                        <button class="btn btn-primary btn-sm" style="flex:1;justify-content:center">Apply</button>
                    </div>
                </div>`;
            }).join('');
        } catch(e) {
            grid.innerHTML = '<div class="empty-state" style="grid-column:1/-1"><i class="ph ph-warning"></i><p>Failed to load jobs.</p></div>';
        }
    }

    // ── Resume Upload ───────────────────────────────────────────
    const fileInput = document.getElementById('resume-file');
    const uploadZone = document.getElementById('upload-zone');
    const uploadStatus = document.getElementById('upload-status');

    if (uploadZone) {
        uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('dragover'); });
        uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
        uploadZone.addEventListener('drop', e => { e.preventDefault(); uploadZone.classList.remove('dragover');
            if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; doUpload(); }
        });
        fileInput.addEventListener('change', doUpload);
    }

    async function doUpload() {
        if (!fileInput.files.length) return;
        const uid = user ? user.id : 'guest';
        const fd = new FormData();
        fd.append('user_id', uid);
        fd.append('file', fileInput.files[0]);
        fd.append('version_tag', 'Original');
        uploadStatus.innerHTML = '<p class="text-sm text-blue">Uploading…</p>';
        try {
            const res = await fetch('/api/resumes/upload', { method: 'POST', body: fd });
            const data = await res.json();
            uploadStatus.innerHTML = `<p class="text-sm text-green">✓ Uploaded: ${data.filename}</p>`;
            loadResumes(uid);
        } catch(e) {
            uploadStatus.innerHTML = '<p class="text-sm text-red">Upload failed.</p>';
        }
    }

    async function loadResumes(uid) {
        const tl = document.getElementById('resume-timeline');
        try {
            const res = await fetch('/api/resumes/' + uid);
            const list = await res.json();
            if (!list.length) { tl.innerHTML = '<div class="empty-state text-sm">No resumes uploaded yet.</div>'; return; }
            tl.innerHTML = list.map(r => `
                <div class="timeline-item">
                    <div class="tl-date">${new Date(r.uploaded_at).toLocaleDateString()}</div>
                    <div class="tl-title">${r.filename} <span class="badge blue" style="margin-left:6px">${r.version_tag}</span></div>
                </div>
            `).join('');
        } catch(e) {}
    }
    if (user) loadResumes(user.id);

    // ── Drawflow ────────────────────────────────────────────────
    function initDrawflow() {
        const el = document.getElementById('drawflow-canvas');
        if (!el) return;
        const editor = new Drawflow(el);
        editor.start();

        const mkNode = (icon, label, sub, color) => `
            <div style="padding:10px;display:flex;align-items:center;gap:8px">
                <i class="ph ph-${icon}" style="color:${color};font-size:1.4rem"></i>
                <div><strong style="display:block;font-size:.85rem">${label}</strong>
                <span style="font-size:.72rem;color:#8b8b9e">${sub}</span></div>
            </div>`;

        editor.addNode('scraper',0,1,80,80,'scraper',{},mkNode('globe','LinkedIn Scraper','Active','#10b981'));
        editor.addNode('clean',1,1,350,60,'clean',{},mkNode('funnel','Data Cleaner','Ready','#0061FF'));
        editor.addNode('db',1,0,620,80,'db',{},mkNode('database','DB Store','Connected','#f59e0b'));
        editor.addConnection(1,2,'output_1','input_1');
        editor.addConnection(2,3,'output_1','input_1');

        // Drag from palette
        let dragNode = null;
        document.querySelectorAll('.palette-item').forEach(item => {
            item.addEventListener('dragstart', () => { dragNode = item.dataset.node; });
        });
        el.addEventListener('dragover', e => e.preventDefault());
        el.addEventListener('drop', e => {
            e.preventDefault();
            if (!dragNode) return;
            const x = e.clientX - el.getBoundingClientRect().left;
            const y = e.clientY - el.getBoundingClientRect().top;
            editor.addNode(dragNode,1,1,x,y,dragNode,{},mkNode('cube',dragNode,'New','#0061FF'));
            dragNode = null;
        });

        // Props panel
        const panel = document.getElementById('props-panel');
        editor.on('nodeSelected', id => {
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

    // ── Analytics Charts ────────────────────────────────────────
    function initAnalyticsCharts() {
        // Demand vs Supply
        const dCtx = document.getElementById('demandChart');
        if (dCtx) {
            new Chart(dCtx, {
                type: 'bar',
                data: {
                    labels: ['Python','JavaScript','React','SQL','AWS','Docker','Go','ML'],
                    datasets: [
                        { label: 'Market Demand', data: [92,88,82,78,75,70,65,60], backgroundColor: 'rgba(0,97,255,0.6)', borderRadius: 6 },
                        { label: 'Your Skills',   data: [95,85,80,90,40,30,20,55], backgroundColor: 'rgba(16,185,129,0.5)', borderRadius: 6 }
                    ]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    scales: {
                        x: { grid: { display: false } },
                        y: { grid: { color: 'rgba(255,255,255,0.04)' }, beginAtZero: true }
                    },
                    plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } } }
                }
            });
        }
        // Distribution
        const hCtx = document.getElementById('distChart');
        if (hCtx) {
            new Chart(hCtx, {
                type: 'bar',
                data: {
                    labels: ['0-20','21-40','41-60','61-80','81-100'],
                    datasets: [{ label: 'Candidates', data: [12,34,89,156,78], backgroundColor: 'rgba(0,97,255,0.5)', borderRadius: 6 }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    scales: {
                        x: { grid: { display: false } },
                        y: { grid: { color: 'rgba(255,255,255,0.04)' }, beginAtZero: true }
                    },
                    plugins: { legend: { display: false } }
                }
            });
        }
    }

    // ── Database Explorer ────────────────────────────────────────
    let dbData = null;
    async function loadDbTables() {
        const bar = document.getElementById('db-tab-bar');
        const card = document.getElementById('db-table-card');
        if (dbData) return;
        try {
            const res = await fetch('/api/db/tables');
            dbData = await res.json();
            const names = Object.keys(dbData);
            bar.innerHTML = names.map((n,i) =>
                `<button class="btn ${i===0?'btn-primary':'btn-outline'} btn-sm" data-tbl="${n}">${n}</button>`
            ).join('');
            bar.querySelectorAll('button').forEach(btn => {
                btn.addEventListener('click', () => {
                    bar.querySelectorAll('button').forEach(b => { b.className = 'btn btn-outline btn-sm'; });
                    btn.className = 'btn btn-primary btn-sm';
                    renderTable(btn.dataset.tbl);
                });
            });
            if (names.length) renderTable(names[0]);
        } catch(e) {
            card.innerHTML = '<div class="empty-state"><i class="ph ph-warning"></i><p>Could not load tables.</p></div>';
        }
    }

    function renderTable(name) {
        const card = document.getElementById('db-table-card');
        const rows = dbData[name] || [];
        if (!rows.length) { card.innerHTML = '<div class="empty-state text-sm">Table is empty.</div>'; return; }
        const cols = Object.keys(rows[0]);
        card.innerHTML = `<div style="overflow-x:auto"><table class="data-table">
            <thead><tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr></thead>
            <tbody>${rows.map(r => `<tr>${cols.map(c => `<td>${r[c] ?? ''}</td>`).join('')}</tr>`).join('')}</tbody>
        </table></div>`;
    }

    // ── Init dashboard chart on load ────────────────────────────
    // Radar chart is already created above. Done!
});
