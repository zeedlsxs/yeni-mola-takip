/**
 * Çok Kullanıcılı Mola Yönetim Sistemi — Frontend
 * Backend: http://127.0.0.1:8000
 */

const API_BASE =
    (window.MOLA_API_BASE && window.MOLA_API_BASE.length > 0)
        ? window.MOLA_API_BASE
        : window.location.protocol === "file:"
            ? "http://127.0.0.1:8000"
            : window.location.origin;
const ADMIN_CODE = "EREN";
const THEME_KEY = "mola_theme";

let employees = [];
let dashboardSummary = null;
let selectedEmployeeId = null;
let selectedHistoryEmployeeId = null;
let selectedHistoryPeriod = "dun";
let selectedDuration = 15;
let countdownInterval = null;
let refreshInterval = null;
let pollInterval = null;
let progressInterval = null;
let lastBreakState = null;
let currentBreakTotal = 0;
let breakExpiredNotified = false;

// ---------------------------------------------------------------------------
// Yardımcılar
// ---------------------------------------------------------------------------

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function isSuperAdmin(user) {
    return user?.is_super_admin === true
        || (user?.employee_code || "").toUpperCase() === ADMIN_CODE;
}

/** API hatalarını anlaşılır Türkçe mesaja çevirir */
function parseApiError(detail, status) {
    if (!detail) {
        if (status === 401) return "Kullanıcı adı veya şifre hatalı.";
        if (status >= 500) return "Sunucu hatası. Lütfen daha sonra tekrar deneyin.";
        return `Bir hata oluştu (${status}).`;
    }
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
        const field = detail[0]?.loc?.[detail[0].loc.length - 1];
        if (field === "password") return "Şifre en az 4 karakter olmalıdır.";
        if (field === "username") return "Kullanıcı adı zorunludur.";
        return detail[0]?.msg || "Geçersiz bilgi girdiniz.";
    }
    return "Bir hata oluştu. Lütfen tekrar deneyin.";
}

function showToast(message, type = "info", duration = 4000) {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add("show"));
    setTimeout(() => {
        toast.classList.remove("show");
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

async function apiRequest(endpoint, options = {}, retries = 2) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            headers: { "Content-Type": "application/json", ...options.headers },
            ...options,
        });

        let data = null;
        const text = await response.text();
        if (text) {
            try { data = JSON.parse(text); } catch { data = { detail: text }; }
        }

        if (!response.ok) {
            const msg = parseApiError(data?.detail, response.status);
            if (response.status >= 500 && retries > 0) {
                showToast("Bağlantı koptu, tekrar deneniyor...", "warning");
                await sleep(1500);
                return apiRequest(endpoint, options, retries - 1);
            }
            throw new Error(msg);
        }
        return data;
    } catch (err) {
        if (err instanceof TypeError || err.message === "Failed to fetch") {
            if (retries > 0) {
                showToast("Bağlantı koptu, tekrar deneniyor...", "warning");
                await sleep(1500);
                return apiRequest(endpoint, options, retries - 1);
            }
            showToast("Sunucuya bağlanılamıyor. İnternet bağlantınızı kontrol edin.", "error");
            throw new Error("Sunucuya bağlanılamıyor.");
        }
        throw err;
    }
}

function initTheme() {
    const saved = localStorage.getItem(THEME_KEY) || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    updateThemeIcon(saved);

    document.getElementById("theme-toggle")?.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme") || "dark";
        const next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem(THEME_KEY, next);
        updateThemeIcon(next);
    });
}

function updateThemeIcon(theme) {
    const btn = document.getElementById("theme-toggle");
    if (btn) btn.textContent = theme === "dark" ? "☀️" : "🌙";
}

function getUser() {
    return JSON.parse(sessionStorage.getItem("mola_user") || "{}");
}

function saveSession(user) {
    sessionStorage.setItem("mola_user", JSON.stringify(user));
    sessionStorage.setItem("mola_logged_in", "true");
}

function requireAuth() {
    if (sessionStorage.getItem("mola_logged_in") !== "true") {
        window.location.href = "index.html";
        return false;
    }
    return true;
}

function requireRole(role) {
    const user = getUser();
    if (role === "yonetici" && !isSuperAdmin(user)) {
        window.location.href = "employee.html";
        return false;
    }
    if (role === "personel" && isSuperAdmin(user)) {
        window.location.href = "dashboard.html";
        return false;
    }
    return true;
}

function requireAdmin() {
    if (!requireAuth()) return false;
    if (!isSuperAdmin(getUser())) {
        window.location.href = "employee.html";
        return false;
    }
    return true;
}

function logout() {
    sessionStorage.clear();
    window.location.href = "index.html";
}

function redirectByRole(user) {
    window.location.href = isSuperAdmin(user) ? "dashboard.html" : "employee.html";
}

function showPanelMessage(text, type = "info") {
    const el = document.getElementById("panel-message");
    if (!el) return;
    el.textContent = text;
    el.className = `panel-message ${type}`;
    el.hidden = false;
    setTimeout(() => { el.hidden = true; }, 4000);
}

function formatCountdown(totalSeconds) {
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** Admin adı — onay modalı için */
function getAdminTitle() {
    const user = getUser();
    const name = user?.full_name || "Eren";
    return name.toLowerCase().includes("bey") ? name : `${name} Bey`;
}

let confirmCallback = null;

/**
 * Neon onay modalını açar.
 * @param {string} message - Gösterilecek mesaj
 * @param {Function} onConfirm - Evet tıklandığında çalışacak fonksiyon
 */
function showConfirmModal(message, onConfirm) {
    const overlay = document.getElementById("confirm-modal");
    const msgEl = document.getElementById("confirm-message");
    if (!overlay || !msgEl) return;

    msgEl.textContent = message;
    confirmCallback = onConfirm;
    overlay.hidden = false;
    document.body.classList.add("modal-open");
}

function closeConfirmModal() {
    const overlay = document.getElementById("confirm-modal");
    if (overlay) overlay.hidden = true;
    document.body.classList.remove("modal-open");
    confirmCallback = null;
}

function initConfirmModal() {
    document.getElementById("confirm-yes")?.addEventListener("click", async () => {
        const cb = confirmCallback;
        closeConfirmModal();
        if (cb) await cb();
    });
    document.getElementById("confirm-no")?.addEventListener("click", closeConfirmModal);
    document.getElementById("confirm-modal")?.addEventListener("click", (e) => {
        if (e.target.id === "confirm-modal") closeConfirmModal();
    });
}

// ---------------------------------------------------------------------------
// Yağmur Efekti
// ---------------------------------------------------------------------------

function initRainEffect() {
    const canvas = document.getElementById("rain-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let drops = [];

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        drops = Array.from({ length: 180 }, () => ({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            length: Math.random() * 18 + 6,
            speed: Math.random() * 4 + 3,
            opacity: Math.random() * 0.35 + 0.15,
        }));
    }

    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (const d of drops) {
            ctx.beginPath();
            ctx.strokeStyle = `rgba(255,255,255,${d.opacity})`;
            ctx.moveTo(d.x, d.y);
            ctx.lineTo(d.x, d.y + d.length);
            ctx.stroke();
            d.y += d.speed;
            if (d.y > canvas.height) { d.y = -d.length; d.x = Math.random() * canvas.width; }
        }
        requestAnimationFrame(draw);
    }

    resize();
    draw();
    window.addEventListener("resize", resize);
}

// ---------------------------------------------------------------------------
// Giriş / Kayıt Sayfası
// ---------------------------------------------------------------------------

function initAuthTabs() {
    document.querySelectorAll(".auth-tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".auth-tab").forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");
            const isLogin = tab.dataset.tab === "login";
            document.getElementById("login-form").hidden = !isLogin;
            document.getElementById("register-form").hidden = isLogin;
        });
    });
}

async function handleLogin(e) {
    e.preventDefault();
    const btn = document.getElementById("login-btn");
    const errEl = document.getElementById("login-error");
    errEl.hidden = true;
    btn.disabled = true;
    btn.textContent = "Giriş yapılıyor…";

    try {
        const data = await apiRequest("/auth/login", {
            method: "POST",
            body: JSON.stringify({
                username: document.getElementById("username").value.trim(),
                password: document.getElementById("password").value,
            }),
        });
        saveSession(data);
        redirectByRole(data);
    } catch (err) {
        errEl.textContent = err.message;
        errEl.hidden = false;
    } finally {
        btn.disabled = false;
        btn.textContent = "Giriş Yap";
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const btn = document.getElementById("register-btn");
    const errEl = document.getElementById("register-error");
    const okEl = document.getElementById("register-success");
    errEl.hidden = true;
    okEl.hidden = true;
    btn.disabled = true;

    try {
        await apiRequest("/auth/register", {
            method: "POST",
            body: JSON.stringify({
                username: document.getElementById("reg-username").value.trim(),
                password: document.getElementById("reg-password").value,
            }),
        });
        okEl.textContent = "Kayıt başarılı! Giriş yapabilirsiniz.";
        okEl.hidden = false;
        document.querySelector('.auth-tab[data-tab="login"]').click();
    } catch (err) {
        errEl.textContent = err.message;
        errEl.hidden = false;
    } finally {
        btn.disabled = false;
    }
}

function initLoginPage() {
    if (!document.getElementById("login-form")) return;
    if (sessionStorage.getItem("mola_logged_in") === "true") {
        redirectByRole(getUser());
        return;
    }
    initTheme();
    initRainEffect();
    initAuthTabs();
    document.getElementById("login-form").addEventListener("submit", handleLogin);
    document.getElementById("register-form").addEventListener("submit", handleRegister);
}

// ---------------------------------------------------------------------------
// Yönetici Paneli
// ---------------------------------------------------------------------------

async function loadEmployees() {
    const [overview, summary] = await Promise.all([
        apiRequest("/employees/overview"),
        apiRequest("/dashboard/summary"),
    ]);
    employees = overview;
    dashboardSummary = summary;
    renderDashboardSummary();
    renderEmployeeTable();
    const countEl = document.getElementById("employee-count");
    if (countEl) countEl.textContent = `${employees.length} personel`;
}

function renderDashboardSummary() {
    if (!dashboardSummary) return;
    const activeEl = document.getElementById("summary-active");
    const breakEl = document.getElementById("summary-on-break");
    const exhaustedEl = document.getElementById("summary-exhausted");
    if (activeEl) activeEl.textContent = dashboardSummary.toplam_aktif_personel ?? 0;
    if (breakEl) breakEl.textContent = dashboardSummary.su_an_molada ?? 0;
    if (exhaustedEl) exhaustedEl.textContent = dashboardSummary.mola_hakki_biten ?? 0;
}

function formatDateTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("tr-TR", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit",
    });
}

function formatHistoryDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

async function openHistoryModal(employeeId, name) {
    selectedHistoryEmployeeId = employeeId;
    selectedHistoryPeriod = "dun";
    document.getElementById("history-modal-employee").textContent = name;
    document.querySelectorAll(".history-filter-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.period === "dun");
    });
    document.getElementById("history-modal").hidden = false;
    await loadBreakHistory();
}

function closeHistoryModal() {
    document.getElementById("history-modal").hidden = true;
    selectedHistoryEmployeeId = null;
}

async function loadBreakHistory() {
    if (!selectedHistoryEmployeeId) return;
    const listEl = document.getElementById("history-list");
    listEl.innerHTML = '<li class="history-loading">Yükleniyor…</li>';

    try {
        const data = await apiRequest(
            `/employees/${selectedHistoryEmployeeId}/history?period=${selectedHistoryPeriod}`
        );
        document.getElementById("history-total-records").textContent = `${data.total_records} kayıt`;
        document.getElementById("history-total-duration").textContent =
            `${data.total_duration_minutes} dk toplam`;

        if (!data.records.length) {
            listEl.innerHTML = '<li class="history-empty">Bu dönemde mola kaydı bulunamadı.</li>';
            return;
        }

        listEl.innerHTML = data.records.map((r) => `
            <li class="history-item">
                <div class="history-item-date">${formatHistoryDate(r.date)}</div>
                <div class="history-item-times">
                    <span>${formatDateTime(r.start_time)}</span>
                    <span class="history-arrow">→</span>
                    <span>${formatDateTime(r.end_time)}</span>
                </div>
                <div class="history-item-duration">${r.duration} dk</div>
            </li>
        `).join("");
    } catch (err) {
        listEl.innerHTML = `<li class="history-empty error-text">${err.message}</li>`;
    }
}

function renderEmployeeTable() {
    const tbody = document.getElementById("employee-tbody");
    if (!tbody) return;

    if (!employees.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="table-empty">Henüz personel eklenmemiş.</td></tr>`;
        return;
    }

    tbody.innerHTML = employees.map((emp) => {
        const onBreak = emp.work_status === "molada";
        const remaining = emp.active_break?.remaining_seconds ?? 0;
        const quotaUsed = emp.kullanilan_mola ?? 0;
        const quotaLimit = emp.mola_hakki_limit ?? 2;
        const quotaExhausted = emp.mola_hakki_bitti === true;
        const canStart = emp.can_start_break === true;
        const totalMinutes = emp.bugunku_toplam_mola_dk ?? 0;

        const exhaustedIcon = quotaExhausted && !onBreak
            ? `<span class="quota-exhausted-icon" title="Mola Bitti">🔴</span>`
            : "";

        const statusHtml = onBreak
            ? `<div class="status-cell-inner">
                   <span class="badge badge-break">Molada</span>
                   <span class="countdown" data-employee-id="${emp.id}"
                         data-remaining="${remaining}">${formatCountdown(remaining)}</span>
               </div>`
            : `<div class="status-cell-inner"><span class="badge badge-work">Çalışıyor</span></div>`;

        const quotaBadge = `<span class="quota-badge ${quotaExhausted ? "quota-full" : ""}">${quotaUsed}/${quotaLimit}</span>`;

        let startBtnHtml;
        if (onBreak) {
            startBtnHtml = `<button class="btn-row btn-end-break" data-id="${emp.id}" type="button">Mola Bitir</button>`;
        } else if (quotaExhausted) {
            startBtnHtml = `<button class="btn-row btn-quota-disabled" type="button" disabled title="Mola Hakkı Bitti">Mola Hakkı Bitti</button>`;
        } else if (canStart) {
            startBtnHtml = `<button class="btn-row btn-add-break" data-id="${emp.id}"
                                    data-name="${emp.full_name}" type="button"
                                    title="Mola Başlat" aria-label="Mola Başlat">+</button>`;
        } else {
            startBtnHtml = `<button class="btn-row btn-quota-disabled" type="button" disabled>Mola Başlatılamaz</button>`;
        }

        const actionHtml = `<div class="action-buttons">
            ${startBtnHtml}
            <button class="btn-row btn-delete" data-id="${emp.id}"
                    data-name="${emp.employee_code}" type="button" title="Sil">🗑️</button>
        </div>`;

        return `<tr class="employee-row ${quotaExhausted && !onBreak ? "row-quota-exhausted" : ""}">
            <td class="cell-name" data-label="Ad Soyad">
                <button type="button" class="employee-name-link" data-id="${emp.id}"
                        data-name="${emp.full_name}" title="Geçmiş analiz">
                    <span class="name-with-icon">${exhaustedIcon}${emp.full_name}</span>
                </button>
                <span class="quota-inline">Mola Hakkı: ${quotaUsed}/${quotaLimit}</span>
            </td>
            <td class="cell-code" data-label="Kullanıcı Adı">${emp.employee_code}</td>
            <td class="cell-status" data-label="Durum">${statusHtml}</td>
            <td class="cell-total-min" data-label="Bugünkü Toplam Mola (dk)">${totalMinutes}</td>
            <td class="cell-quota" data-label="Mola Hakkı">${quotaBadge}</td>
            <td class="cell-action" data-label="İşlem">${actionHtml}</td>
        </tr>`;
    }).join("");

    document.querySelectorAll(".employee-name-link").forEach((btn) => {
        btn.addEventListener("click", () => openHistoryModal(+btn.dataset.id, btn.dataset.name));
    });
    document.querySelectorAll(".btn-add-break").forEach((btn) => {
        btn.addEventListener("click", () => openBreakModal(+btn.dataset.id, btn.dataset.name));
    });
    document.querySelectorAll(".btn-end-break").forEach((btn) => {
        btn.addEventListener("click", () => endEmployeeBreak(+btn.dataset.id));
    });
    document.querySelectorAll(".btn-delete").forEach((btn) => {
        btn.addEventListener("click", () => deleteUser(+btn.dataset.id, btn.dataset.name));
    });
    startAdminCountdowns();
}

function startAdminCountdowns() {
    if (countdownInterval) clearInterval(countdownInterval);
    countdownInterval = setInterval(() => {
        document.querySelectorAll(".countdown").forEach((el) => {
            let rem = parseInt(el.dataset.remaining, 10);
            if (rem <= 0) {
                autoEndBreak(+el.dataset.employeeId);
                return;
            }
            rem -= 1;
            el.dataset.remaining = rem;
            el.textContent = formatCountdown(rem);
        });
    }, 1000);
}

async function autoEndBreak(employeeId) {
    try {
        await apiRequest(`/employees/${employeeId}/status`, {
            method: "PATCH",
            body: JSON.stringify({ is_on_break: false }),
        });
        showPanelMessage("Mola süresi doldu, otomatik sonlandırıldı.", "info");
    } catch { /* ignore */ }
    await loadEmployees();
}

function openBreakModal(employeeId, name) {
    selectedEmployeeId = employeeId;
    selectedDuration = 15;
    document.getElementById("break-modal-employee").textContent = name;
    document.getElementById("manual-duration").value = "";
    document.querySelectorAll(".duration-btn").forEach((b) =>
        b.classList.toggle("active", b.dataset.duration === "15"));
    document.getElementById("break-modal").hidden = false;
}

function closeBreakModal() {
    document.getElementById("break-modal").hidden = true;
    selectedEmployeeId = null;
}

function getSelectedDuration() {
    const manual = parseInt(document.getElementById("manual-duration")?.value, 10);
    return manual > 0 ? manual : selectedDuration;
}

async function confirmStartBreak() {
    if (!selectedEmployeeId) return;
    const btn = document.getElementById("break-modal-confirm");
    const duration = getSelectedDuration();
    const admin = getUser();

    btn.disabled = true;
    try {
        await apiRequest(`/employees/${selectedEmployeeId}/status`, {
            method: "PATCH",
            body: JSON.stringify({
                is_on_break: true,
                break_duration_minutes: duration,
                assigned_by: admin.full_name || "Bölüm Müdürü",
            }),
        });
        closeBreakModal();
        showPanelMessage(`Mola başlatıldı (${duration} dk)`, "success");
        await loadEmployees();
    } catch (err) {
        showPanelMessage(err.message, "error");
    } finally {
        btn.disabled = false;
    }
}

async function endEmployeeBreak(employeeId) {
    try {
        await apiRequest(`/employees/${employeeId}/status`, {
            method: "PATCH",
            body: JSON.stringify({ is_on_break: false }),
        });
        showPanelMessage("Mola sonlandırıldı.", "success");
        await loadEmployees();
    } catch (err) {
        showPanelMessage(err.message, "error");
    }
}

function openAddModal() {
    document.getElementById("add-full-name").value = "";
    document.getElementById("add-employee-code").value = "";
    document.getElementById("add-password").value = "123456";
    document.getElementById("add-error").hidden = true;
    document.getElementById("add-modal").hidden = false;
}

function closeAddModal() {
    document.getElementById("add-modal").hidden = true;
}

async function handleAddEmployee(e) {
    e.preventDefault();
    const btn = document.getElementById("add-modal-confirm");
    const errEl = document.getElementById("add-error");
    errEl.hidden = true;
    btn.disabled = true;

    try {
        await apiRequest("/employees", {
            method: "POST",
            body: JSON.stringify({
                full_name: document.getElementById("add-full-name").value.trim(),
                employee_code: document.getElementById("add-employee-code").value.trim(),
                password: document.getElementById("add-password").value || "123456",
            }),
        });
        closeAddModal();
        showPanelMessage("Personel eklendi.", "success");
        await loadEmployees();
    } catch (err) {
        errEl.textContent = err.message;
        errEl.hidden = false;
    } finally {
        btn.disabled = false;
    }
}

// ---------------------------------------------------------------------------
// Panel Sekmeleri & Kullanıcı Yönetimi
// ---------------------------------------------------------------------------

function initPanelTabs() {
    document.querySelectorAll(".panel-tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".panel-tab").forEach((t) => t.classList.remove("active"));
            tab.classList.add("active");
            const panel = tab.dataset.panel;
            document.getElementById("panel-personel").hidden = panel !== "personel";
            document.getElementById("panel-users").hidden = panel !== "users";
        });
    });
}

async function searchUsers() {
    const query = document.getElementById("user-search-input").value.trim();
    const resultsEl = document.getElementById("user-results");
    if (!query) {
        resultsEl.innerHTML = '<p class="search-hint">Lütfen bir kullanıcı adı girin.</p>';
        return;
    }

    resultsEl.innerHTML = '<p class="search-hint">Aranıyor…</p>';

    try {
        const users = await apiRequest(`/users/search?q=${encodeURIComponent(query)}`);

        if (!users.length) {
            resultsEl.innerHTML = '<p class="search-hint">Kullanıcı bulunamadı.</p>';
            return;
        }

        resultsEl.innerHTML = users.map((u) => {
            const isManager = u.role === "yonetici";
            const roleBadge = isManager
                ? '<span class="badge badge-manager">Yönetici</span>'
                : '<span class="badge badge-work">Personel</span>';

            const actionBtn = isManager
                ? '<span class="already-manager">Zaten yönetici</span>'
                : `<button class="btn-promote" data-id="${u.id}" data-name="${u.username}" type="button">Yönetici Yap</button>`;

            const deleteBtn = u.username.toUpperCase() !== ADMIN_CODE
                ? `<button class="btn-delete-user" data-id="${u.id}" data-name="${u.username}" type="button" title="Sil">🗑️</button>`
                : "";

            return `<div class="user-card">
                <div class="user-card-info">
                    <strong>${u.full_name}</strong>
                    <span class="user-card-username">@${u.username}</span>
                    ${roleBadge}
                </div>
                <div class="user-card-action">
                    ${actionBtn}
                    ${deleteBtn}
                </div>
            </div>`;
        }).join("");

        document.querySelectorAll(".btn-promote").forEach((btn) => {
            btn.addEventListener("click", () => promoteUser(+btn.dataset.id, btn.dataset.name));
        });
        document.querySelectorAll(".btn-delete-user").forEach((btn) => {
            btn.addEventListener("click", () => deleteUser(+btn.dataset.id, btn.dataset.name));
        });
    } catch (err) {
        resultsEl.innerHTML = `<p class="search-hint error-text">${err.message}</p>`;
    }
}

async function promoteUser(userId, username) {
    const adminTitle = getAdminTitle();
    showConfirmModal(
        `${adminTitle}, ${username} kişisini yönetici yapmak istediğinize emin misiniz?`,
        async () => {
            try {
                await apiRequest(`/users/${userId}/promote`, { method: "PATCH" });
                showPanelMessage(`${username} yönetici yapıldı.`, "success");
                searchUsers();
            } catch (err) {
                showPanelMessage(err.message, "error");
            }
        }
    );
}

async function deleteUser(userId, username) {
    const adminTitle = getAdminTitle();
    showConfirmModal(
        `${adminTitle}, ${username} personeli silmek istediğinize emin misiniz?`,
        async () => {
            try {
                await apiRequest(`/users/${userId}`, { method: "DELETE" });
                showPanelMessage(`${username} silindi.`, "success");
                showToast(`${username} başarıyla silindi.`, "success");
                await loadEmployees();
                const searchInput = document.getElementById("user-search-input");
                if (searchInput?.value.trim()) searchUsers();
            } catch (err) {
                showPanelMessage(err.message, "error");
                showToast(err.message, "error");
            }
        }
    );
}

function initAdminPage() {
    if (!requireAdmin()) return;

    initTheme();

    const user = getUser();
    const greeting = document.getElementById("user-greeting");
    if (greeting) greeting.textContent = `Hoş geldiniz, ${user.full_name}`;

    initConfirmModal();

    document.getElementById("break-modal-close")?.addEventListener("click", closeBreakModal);
    document.getElementById("break-modal-cancel")?.addEventListener("click", closeBreakModal);
    document.getElementById("break-modal-confirm")?.addEventListener("click", confirmStartBreak);

    document.getElementById("history-modal-close")?.addEventListener("click", closeHistoryModal);
    document.getElementById("history-modal-cancel")?.addEventListener("click", closeHistoryModal);
    document.querySelectorAll(".history-filter-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            selectedHistoryPeriod = btn.dataset.period;
            document.querySelectorAll(".history-filter-btn").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            await loadBreakHistory();
        });
    });

    document.querySelectorAll(".duration-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            selectedDuration = +btn.dataset.duration;
            document.getElementById("manual-duration").value = "";
            document.querySelectorAll(".duration-btn").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
        });
    });

    document.getElementById("manual-duration")?.addEventListener("input", () => {
        document.querySelectorAll(".duration-btn").forEach((b) => b.classList.remove("active"));
    });

    document.getElementById("add-employee-btn")?.addEventListener("click", openAddModal);
    document.getElementById("add-modal-close")?.addEventListener("click", closeAddModal);
    document.getElementById("add-modal-cancel")?.addEventListener("click", closeAddModal);
    document.getElementById("add-employee-form")?.addEventListener("submit", handleAddEmployee);
    document.getElementById("logout-btn")?.addEventListener("click", logout);

    document.querySelectorAll(".modal-overlay").forEach((o) => {
        o.addEventListener("click", (e) => { if (e.target === o) o.hidden = true; });
    });

    initPanelTabs();

    document.getElementById("user-search-btn")?.addEventListener("click", searchUsers);
    document.getElementById("user-search-input")?.addEventListener("keydown", (e) => {
        if (e.key === "Enter") searchUsers();
    });

    loadEmployees();
    refreshInterval = setInterval(loadEmployees, 15000);
}

// ---------------------------------------------------------------------------
// Personel Paneli — Polling & Bildirim
// ---------------------------------------------------------------------------

function requestNotificationPermission() {
    if (!("Notification" in window)) return;
    const onGranted = () => {
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (AudioCtx && !audioContext) audioContext = new AudioCtx();
        } catch { /* ignore */ }
    };
    if (Notification.permission === "default") {
        Notification.requestPermission().then((perm) => {
            if (perm === "granted") onGranted();
        }).catch(() => {});
    } else if (Notification.permission === "granted") {
        onGranted();
    }
}

function sendBreakExpiredNotification() {
    playPingSound();
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    try {
        const notif = new Notification("Mola Süreniz Doldu", {
            body: "Mola süreniz doldu, lütfen vardiyanıza dönün",
            tag: "mola-expired",
            requireInteraction: true,
        });
        notif.onclick = () => {
            window.focus();
            notif.close();
        };
    } catch {
        /* Tarayıcı bildirimi desteklenmiyorsa sessizce geç */
    }
}

let audioContext = null;

function playPingSound() {
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        if (!audioContext) audioContext = new AudioCtx();
        if (audioContext.state === "suspended") audioContext.resume();

        const now = audioContext.currentTime;
        const osc = audioContext.createOscillator();
        const gain = audioContext.createGain();

        osc.type = "sine";
        osc.frequency.setValueAtTime(880, now);
        osc.frequency.exponentialRampToValueAtTime(660, now + 0.12);

        gain.gain.setValueAtTime(0.0001, now);
        gain.gain.exponentialRampToValueAtTime(0.18, now + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.35);

        osc.connect(gain);
        gain.connect(audioContext.destination);
        osc.start(now);
        osc.stop(now + 0.4);
    } catch {
        /* Ses çalınamazsa sessizce geç */
    }
}

function updateProgressBar(status) {
    const wrap = document.getElementById("neon-progress-wrap");
    const bar = document.getElementById("neon-progress-bar");
    const text = document.getElementById("neon-progress-text");
    const assigned = document.getElementById("neon-progress-assigned");

    if (!wrap || !bar) return;

    if (!status.is_on_break || status.is_expired) {
        wrap.hidden = true;
        if (progressInterval) { clearInterval(progressInterval); progressInterval = null; }
        bar.classList.remove("expired");
        return;
    }

    const total = (status.break_duration_minutes || 15) * 60;
    currentBreakTotal = total;
    const remaining = status.remaining_seconds;
    const percent = Math.max(0, (remaining / total) * 100);

    wrap.hidden = false;
    bar.style.width = `${percent}%`;
    bar.classList.toggle("expired", status.is_expired);
    text.textContent = formatCountdown(remaining);
    assigned.textContent = `${status.assigned_by || "Bölüm Müdürü"} tarafından mola atandı`;
}

function updateEmployeeUI(status) {
    document.getElementById("emp-name").textContent = status.full_name;
    document.getElementById("emp-code").textContent = `@${status.employee_code}`;
    document.getElementById("profile-name").textContent = status.employee_code;
    document.getElementById("profile-dept").textContent = status.department || "—";

    const notif = document.getElementById("break-notification");
    const title = document.getElementById("notif-title");
    const message = document.getElementById("notif-message");
    const assigned = document.getElementById("notif-assigned");
    const icon = document.getElementById("notif-icon");

    updateProgressBar(status);

    if (status.is_on_break) {
        const mins = Math.ceil(status.remaining_seconds / 60);

        if (status.is_expired) {
            notif.className = "break-notification expired";
            icon.textContent = "⏰";
            title.textContent = "Mola Süresi Doldu!";
            message.textContent = "Lütfen vardiyanıza dönün.";
        } else {
            notif.className = "break-notification active";
            icon.textContent = "🎉";
            title.textContent = "Mola Başladı!";
            message.textContent = `Kalan Süre: ${mins} dakika`;
        }

        assigned.textContent = `${status.assigned_by || "Bölüm Müdürü"} tarafından mola atandı`;
        assigned.hidden = false;
    } else {
        notif.className = "break-notification idle";
        icon.textContent = "☕";
        title.textContent = "Çalışma Modundasınız";
        message.textContent = "Şu an aktif bir mola bulunmuyor.";
        assigned.hidden = true;
    }
}

function startLocalProgressTick() {
    if (progressInterval) clearInterval(progressInterval);
    progressInterval = setInterval(() => {
        const bar = document.getElementById("neon-progress-bar");
        const text = document.getElementById("neon-progress-text");
        if (!bar || bar.parentElement?.closest("[hidden]")) return;

        let rem = parseInt(bar.dataset.remaining || "0", 10);
        if (rem <= 0) return;
        rem -= 1;
        bar.dataset.remaining = rem;
        const total = currentBreakTotal || 1;
        bar.style.width = `${Math.max(0, (rem / total) * 100)}%`;
        if (text) text.textContent = formatCountdown(rem);
    }, 1000);
}

async function pollEmployeeStatus() {
    const user = getUser();
    try {
        const status = await apiRequest(`/employees/${user.id}/status`);

        // Yeni mola başladıysa animasyon tetikle
        if (status.is_on_break && !lastBreakState) {
            breakExpiredNotified = false;
            document.getElementById("break-notification")?.classList.add("pulse-once");
            showToast("Mola başladı! İyi molalar.", "success");
            setTimeout(() => {
                document.getElementById("break-notification")?.classList.remove("pulse-once");
            }, 2000);
        }

        if (!status.is_on_break) {
            breakExpiredNotified = false;
        }

        if (status.is_on_break && status.is_expired && !breakExpiredNotified) {
            sendBreakExpiredNotification();
            breakExpiredNotified = true;
        }

        lastBreakState = status.is_on_break;
        updateEmployeeUI(status);

        const bar = document.getElementById("neon-progress-bar");
        if (bar && status.is_on_break) {
            bar.dataset.remaining = status.remaining_seconds;
            startLocalProgressTick();
        }

        if (status.is_on_break && status.is_expired) {
            await apiRequest(`/employees/${user.id}/status`, {
                method: "PATCH",
                body: JSON.stringify({ is_on_break: false }),
            });
        }
    } catch (err) {
        showToast(err.message || "Durum güncellenemedi.", "error");
    }
}

function initEmployeePage() {
    if (!requireAuth()) return;
    if (isSuperAdmin(getUser())) {
        window.location.href = "dashboard.html";
        return;
    }

    initTheme();
    requestNotificationPermission();
    document.body.addEventListener("click", () => {
        if (audioContext?.state === "suspended") audioContext.resume();
    }, { once: true });

    pollEmployeeStatus();
    pollInterval = setInterval(pollEmployeeStatus, 3000);
    document.getElementById("logout-btn")?.addEventListener("click", logout);
}

// ---------------------------------------------------------------------------
// Başlatma
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("login-form")) initLoginPage();
    else if (document.getElementById("panel-tabs")) initAdminPage();
    else if (document.getElementById("neon-progress-wrap")) initEmployeePage();
});
