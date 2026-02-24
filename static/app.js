const BASE_URL = "";

// Token helpers
const getToken = () => localStorage.getItem('fittrack_token');
const setToken = (token) => localStorage.setItem('fittrack_token', token);
const removeToken = () => localStorage.removeItem('fittrack_token');

// API Wrapper
async function apiFetch(endpoint, options = {}) {
    const token = getToken();
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        const response = await fetch(`${BASE_URL}${endpoint}`, {
            ...options,
            headers
        });

        if (response.status === 401) {
            removeToken();
            window.location.href = '/';
            throw new Error('Oturum süresi doldu. Lütfen tekrar giriş yapın.');
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Bir hata oluştu');
        }

        return data;
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// UI Helpers
function showError(msg) {
    const el = document.getElementById('error-message');
    if (el) {
        el.textContent = msg;
        el.style.display = 'block';
        setTimeout(() => el.style.display = 'none', 5000);
    } else {
        alert(msg);
    }
}

function showToast(msg) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Auth Functions
async function login(e) {
    e.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    try {
        const data = await apiFetch('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password })
        });

        if (data.access_token) {
            setToken(data.access_token);
            window.location.href = '/dashboard';
        }
    } catch (err) {
        showError(err.message);
    }
}

async function register(e) {
    e.preventDefault();
    const email = document.getElementById('register-email').value;
    const password = document.getElementById('register-password').value;
    const username = document.getElementById('register-username').value;

    try {
        const data = await apiFetch('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify({ email, password, username })
        });

        if (data.access_token) {
            setToken(data.access_token);
            window.location.href = '/dashboard';
        } else {
            alert("Kayıt başarılı! Lütfen giriş yapın.");
            switchTab('login');
        }
    } catch (err) {
        showError(err.message);
    }
}

function logout() {
    removeToken();
    window.location.href = '/';
}


// --- Dashboard Functions ---

let allStats = null;
let progressionChartInstance = null;
let frequencyChartInstance = null;

async function initDashboard() {
    try {
        const profile = await apiFetch('/api/profile');
        if (profile) {
            document.getElementById('username-display').textContent = profile.username || 'Kullanıcı';
        }
    } catch (e) {
        console.warn("Profil yüklenemedi", e);
    }

    await loadExercises();
    await loadWorkoutsHistory();
    await loadStatsAndCharts();
}

async function loadExercises() {
    try {
        const exercises = await apiFetch('/api/exercises');
        const select = document.getElementById('workout-exercise');
        select.innerHTML = '<option value="">Seçiniz</option>';
        exercises.forEach(ex => {
            const opt = document.createElement('option');
            opt.value = ex.id;
            opt.textContent = `${ex.name} (${ex.muscle_group})`;
            select.appendChild(opt);
        });
    } catch (e) {
        console.error(e);
    }
}

async function loadWorkoutsHistory() {
    try {
        const workouts = await apiFetch('/api/workouts/history');
        const container = document.getElementById('today-workouts-list');

        if (!workouts || workouts.length === 0) {
            container.innerHTML = '<div class="empty-state">Geçmişte henüz antrenman kaydı yok.</div>';
            return;
        }

        container.innerHTML = '';
        workouts.forEach(w => {
            const el = document.createElement('div');
            el.className = 'workout-item';
            const exName = w.exercises ? w.exercises.name : 'Bilinmeyen';

            // Format the date (dd.mm.yyyy)
            const dParts = w.workout_date.split('-');
            const displayDate = dParts.length === 3 ? `${dParts[2]}.${dParts[1]}.${dParts[0]}` : w.workout_date;

            el.innerHTML = `
                <div class="workout-info">
                    <strong>${exName}</strong>
                    <div><span class="workout-date-badge">${displayDate}</span></div>
                    <span>${w.sets} set × ${w.reps} tekrar × ${w.weight_kg} kg</span>
                </div>
                <button class="btn btn-danger" onclick="deleteWorkout('${w.id}')">Sil</button>
            `;
            container.appendChild(el);
        });
    } catch (e) {
        console.error(e);
    }
}

async function loadStatsAndCharts() {
    try {
        allStats = await apiFetch('/api/stats');

        // Update DOM
        document.getElementById('stat-total-workouts').textContent = allStats.total_workouts || 0;
        document.getElementById('stat-week-workouts').textContent = allStats.this_week_workouts || 0;
        document.getElementById('stat-most-used').textContent = allStats.most_used_exercise || '-';
        document.getElementById('stat-total-exercises').textContent = allStats.total_exercises || 0;

        // Fill chart dropdown
        const select = document.getElementById('chart-exercise-select');
        select.innerHTML = '<option value="">Egzersiz Seç</option>';
        if (allStats.progress_by_exercise) {
            Object.keys(allStats.progress_by_exercise).forEach(ex => {
                const opt = document.createElement('option');
                opt.value = ex;
                opt.textContent = ex;
                select.appendChild(opt);
            });
        }

        drawCharts();
    } catch (e) {
        console.error(e);
    }
}

async function saveWorkout(e) {
    e.preventDefault();

    const data = {
        exercise_id: document.getElementById('workout-exercise').value,
        workout_date: document.getElementById('workout-date').value,
        sets: parseInt(document.getElementById('workout-sets').value),
        reps: parseInt(document.getElementById('workout-reps').value),
        weight_kg: parseFloat(document.getElementById('workout-weight').value),
        notes: document.getElementById('workout-notes').value || ''
    };

    try {
        await apiFetch('/api/workouts', {
            method: 'POST',
            body: JSON.stringify(data)
        });

        // Reset parts of form
        document.getElementById('workout-sets').value = '';
        document.getElementById('workout-reps').value = '';
        document.getElementById('workout-weight').value = '';
        document.getElementById('workout-notes').value = '';

        showToast("Antrenman başarıyla eklendi! ✓");

        // Reload sections
        await loadWorkoutsHistory();
        await loadStatsAndCharts();
    } catch (e) {
        alert("Kaydedilemedi: " + e.message);
    }
}

async function deleteWorkout(id) {
    if (!confirm("Bu antrenmanı silmek istediğinize emin misiniz?")) return;

    try {
        await apiFetch(`/api/workouts/${id}`, { method: 'DELETE' });
        showToast("Antrenman silindi.");
        await loadWorkoutsHistory();
        await loadStatsAndCharts();
    } catch (e) {
        alert("Silinemedi: " + e.message);
    }
}

async function getAIAnalysis() {
    const btn = document.querySelector('.ai-btn');
    const loading = document.getElementById('ai-loading');
    const resultBox = document.getElementById('ai-result');

    btn.style.display = 'none';
    loading.style.display = 'block';
    resultBox.style.display = 'none';

    try {
        const data = await apiFetch('/api/ai/analysis');
        resultBox.textContent = data.analysis;
        resultBox.style.display = 'block';
    } catch (e) {
        resultBox.textContent = "Analiz alınırken bir hata oluştu: " + e.message;
        resultBox.style.display = 'block';
    } finally {
        loading.style.display = 'none';
        btn.style.display = 'inline-flex';
    }
}

// --- Charts ---
Chart.defaults.color = '#e0e0e0';
Chart.defaults.font.family = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif";

function drawCharts() {
    if (!allStats) return;

    // Frequency Chart (Last 30 days)
    const dates = {};
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    Object.values(allStats.progress_by_exercise).forEach(records => {
        records.forEach(r => {
            const dStr = r.date;
            const dObj = new Date(dStr);
            if (dObj >= thirtyDaysAgo) {
                dates[dStr] = (dates[dStr] || 0) + 1; // Count sets/workouts
            }
        });
    });

    const sortedDates = Object.keys(dates).sort();
    const counts = sortedDates.map(d => dates[d]);

    const ctxFreq = document.getElementById('frequencyChart').getContext('2d');
    if (frequencyChartInstance) frequencyChartInstance.destroy();

    frequencyChartInstance = new Chart(ctxFreq, {
        type: 'bar',
        data: {
            labels: sortedDates.map(d => {
                const parts = d.split('-');
                return `${parts[2]}/${parts[1]}`;
            }),
            datasets: [{
                label: 'Antrenman (Set Sayısı)',
                data: counts,
                backgroundColor: '#00ff88',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: '#2a2a2a' } },
                x: { grid: { display: false } }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });

    updateProgressionChart();
}

function updateProgressionChart() {
    const selectedEx = document.getElementById('chart-exercise-select').value;
    const ctxProg = document.getElementById('progressionChart').getContext('2d');

    if (progressionChartInstance) progressionChartInstance.destroy();

    if (!selectedEx || !allStats || !allStats.progress_by_exercise[selectedEx]) {
        progressionChartInstance = new Chart(ctxProg, {
            type: 'line',
            data: { labels: [], datasets: [] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { grid: { color: '#2a2a2a' } },
                    x: { grid: { color: '#2a2a2a' } }
                }
            }
        });
        return;
    }

    const dataPoints = allStats.progress_by_exercise[selectedEx];

    // Max weight per day
    const maxWeightsPerDay = {};
    dataPoints.forEach(p => {
        if (!maxWeightsPerDay[p.date] || p.weight > maxWeightsPerDay[p.date]) {
            maxWeightsPerDay[p.date] = p.weight;
        }
    });

    const sortedDates = Object.keys(maxWeightsPerDay).sort();
    const weights = sortedDates.map(d => maxWeightsPerDay[d]);

    progressionChartInstance = new Chart(ctxProg, {
        type: 'line',
        data: {
            labels: sortedDates.map(d => {
                const parts = d.split('-');
                return `${parts[2]}/${parts[1]}`;
            }),
            datasets: [{
                label: 'Max Ağırlık (kg)',
                data: weights,
                borderColor: '#00ff88',
                backgroundColor: 'rgba(0, 255, 136, 0.1)',
                borderWidth: 3,
                tension: 0.3,
                fill: true,
                pointBackgroundColor: '#00cc6a'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: false, grid: { color: '#2a2a2a' } },
                x: { grid: { color: '#2a2a2a' } }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return context.parsed.y + ' kg';
                        }
                    }
                }
            }
        }
    });
}
