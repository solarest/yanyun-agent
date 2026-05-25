/* ============================================================
   College Budget Tracker – Application Logic
   ============================================================ */

(function () {
  "use strict";

  // ── Default categories with icons & suggested budgets ──────
  const DEFAULT_CATEGORIES = [
    { id: "housing",        icon: "🏠", name: "Housing / Rent",     budget: 800  },
    { id: "food",           icon: "🍕", name: "Food & Groceries",   budget: 350  },
    { id: "tuition",        icon: "📚", name: "Tuition & Fees",     budget: 500  },
    { id: "textbooks",      icon: "📖", name: "Textbooks & Supplies", budget: 75 },
    { id: "transportation", icon: "🚌", name: "Transportation",     budget: 100  },
    { id: "entertainment",  icon: "🎮", name: "Entertainment",      budget: 80   },
    { id: "subscriptions",  icon: "📱", name: "Subscriptions",      budget: 30   },
    { id: "personal",       icon: "🧴", name: "Personal Care",      budget: 40   },
    { id: "clothing",       icon: "👕", name: "Clothing",            budget: 50   },
    { id: "savings",        icon: "🏦", name: "Savings",             budget: 100  },
    { id: "misc",           icon: "📦", name: "Miscellaneous",       budget: 50   },
  ];

  const PALETTE = [
    "#4f6df5", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6",
    "#06b6d4", "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#a3a3a3",
  ];

  // ── State ──────────────────────────────────────────────────
  let currentDate = new Date();
  let data = loadData();

  // ── Persistence ────────────────────────────────────────────
  function storageKey() { return "college_budget_tracker"; }

  function loadData() {
    try {
      const raw = localStorage.getItem(storageKey());
      return raw ? JSON.parse(raw) : {};
    } catch { return {}; }
  }

  function saveData() {
    localStorage.setItem(storageKey(), JSON.stringify(data));
  }

  function monthKey(d) {
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    return `${d.getFullYear()}-${mm}`;
  }

  function getMonth(key) {
    if (!data[key]) {
      data[key] = {
        budgets: Object.fromEntries(DEFAULT_CATEGORIES.map(c => [c.id, c.budget])),
        expenses: [],
      };
      saveData();
    }
    return data[key];
  }

  // ── Formatting helpers ─────────────────────────────────────
  function fmt(n) {
    return "$" + Math.abs(n).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function fmtSigned(n) {
    if (n > 0) return "+" + fmt(n);
    if (n < 0) return "-" + fmt(n);
    return fmt(0);
  }

  function monthLabel(d) {
    return d.toLocaleString("en-US", { month: "long", year: "numeric" });
  }

  function shortDate(iso) {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  // ── Rendering ──────────────────────────────────────────────
  function render() {
    const key = monthKey(currentDate);
    const m = getMonth(key);

    // Month label
    document.getElementById("current-month").textContent = monthLabel(currentDate);

    // Compute totals
    let totalBudget = 0;
    let totalSpent = 0;
    const spentPerCat = {};

    DEFAULT_CATEGORIES.forEach(c => {
      const b = m.budgets[c.id] || 0;
      totalBudget += b;
      spentPerCat[c.id] = 0;
    });

    m.expenses.forEach(e => {
      spentPerCat[e.category] = (spentPerCat[e.category] || 0) + e.amount;
      totalSpent += e.amount;
    });

    const remaining = totalBudget - totalSpent;
    const variance = remaining;

    document.getElementById("total-budget").textContent = fmt(totalBudget);
    document.getElementById("total-spent").textContent = fmt(totalSpent);

    const remEl = document.getElementById("total-remaining");
    remEl.textContent = fmt(remaining);
    remEl.style.color = remaining >= 0 ? "var(--success)" : "var(--danger)";

    const varEl = document.getElementById("overall-variance");
    varEl.textContent = fmtSigned(variance);
    varEl.className = "card-value";
    if (variance > 0) varEl.style.color = "var(--success)";
    else if (variance < 0) varEl.style.color = "var(--danger)";
    else varEl.style.color = "var(--text-muted)";

    // Categories list
    const list = document.getElementById("categories-list");
    list.innerHTML = "";

    DEFAULT_CATEGORIES.forEach((c, i) => {
      const budget = m.budgets[c.id] || 0;
      const spent = spentPerCat[c.id] || 0;
      const catVariance = budget - spent;
      const pct = budget > 0 ? Math.min((spent / budget) * 100, 100) : (spent > 0 ? 100 : 0);

      let barColor = PALETTE[i % PALETTE.length];
      if (spent > budget && budget > 0) barColor = "var(--danger)";

      let varianceClass = "variance-zero";
      if (catVariance > 0) varianceClass = "variance-positive";
      else if (catVariance < 0) varianceClass = "variance-negative";

      const row = document.createElement("div");
      row.className = "category-row";
      row.innerHTML = `
        <div class="cat-top">
          <span class="cat-name"><span class="cat-icon">${c.icon}</span> ${c.name}</span>
          <div class="cat-amounts">
            <span>Budget: <strong>${fmt(budget)}</strong></span>
            <span>Spent: <strong>${fmt(spent)}</strong></span>
          </div>
        </div>
        <div class="progress-bar">
          <div class="progress-fill" style="width:${pct}%;background:${barColor}"></div>
        </div>
        <div class="cat-bottom">
          <span class="variance ${varianceClass}">${fmtSigned(catVariance)} variance</span>
          <span style="font-size:.8rem;color:var(--text-muted)">${Math.round(pct)}% used</span>
        </div>
      `;
      list.appendChild(row);
    });

    // Recent transactions
    renderTransactions(m);

    // Charts
    renderDoughnut(spentPerCat);
    renderBarChart(m, spentPerCat);
  }

  function renderTransactions(m) {
    const ul = document.getElementById("recent-transactions");
    ul.innerHTML = "";

    const sorted = [...m.expenses].sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);
    if (sorted.length === 0) {
      ul.innerHTML = '<li class="empty-state"><div class="big-icon">📭</div>No expenses yet this month</li>';
      return;
    }

    sorted.slice(0, 20).forEach(e => {
      const cat = DEFAULT_CATEGORIES.find(c => c.id === e.category);
      const li = document.createElement("li");
      li.innerHTML = `
        <div class="tx-left">
          <span class="tx-desc">${cat ? cat.icon : ""} ${escHtml(e.description)}</span>
          <span class="tx-meta">${cat ? cat.name : e.category} · ${shortDate(e.date)}</span>
        </div>
        <div class="tx-actions">
          <span class="tx-amount">-${fmt(e.amount)}</span>
          <button class="btn btn-sm btn-danger" data-delete="${e.id}" title="Delete">✕</button>
        </div>
      `;
      ul.appendChild(li);
    });

    ul.querySelectorAll("[data-delete]").forEach(btn => {
      btn.addEventListener("click", () => {
        const id = Number(btn.dataset.delete);
        const key = monthKey(currentDate);
        const month = getMonth(key);
        month.expenses = month.expenses.filter(e => e.id !== id);
        saveData();
        render();
      });
    });
  }

  // ── Charts (Canvas 2D – no dependencies) ──────────────────
  function renderDoughnut(spentPerCat) {
    const canvas = document.getElementById("chart-doughnut");
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    canvas.width = 280 * dpr;
    canvas.height = 280 * dpr;
    ctx.scale(dpr, dpr);
    canvas.style.width = "280px";
    canvas.style.height = "280px";

    const cx = 140, cy = 140, outerR = 120, innerR = 70;
    ctx.clearRect(0, 0, 280, 280);

    const values = DEFAULT_CATEGORIES.map(c => spentPerCat[c.id] || 0);
    const total = values.reduce((a, b) => a + b, 0);

    if (total === 0) {
      ctx.beginPath();
      ctx.arc(cx, cy, outerR, 0, Math.PI * 2);
      ctx.arc(cx, cy, innerR, 0, Math.PI * 2, true);
      ctx.fillStyle = "#e9ecef";
      ctx.fill();

      ctx.fillStyle = "var(--text-muted)";
      ctx.font = "500 14px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "#94a3b8";
      ctx.fillText("No spending yet", cx, cy);
    } else {
      let startAngle = -Math.PI / 2;
      values.forEach((val, i) => {
        if (val === 0) return;
        const slice = (val / total) * Math.PI * 2;
        ctx.beginPath();
        ctx.arc(cx, cy, outerR, startAngle, startAngle + slice);
        ctx.arc(cx, cy, innerR, startAngle + slice, startAngle, true);
        ctx.closePath();
        ctx.fillStyle = PALETTE[i % PALETTE.length];
        ctx.fill();
        startAngle += slice;
      });

      ctx.fillStyle = "#1e293b";
      ctx.font = "700 20px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(fmt(total), cx, cy - 8);
      ctx.font = "400 12px Inter, sans-serif";
      ctx.fillStyle = "#64748b";
      ctx.fillText("total spent", cx, cy + 12);
    }

    // Legend
    const legend = document.getElementById("chart-legend");
    legend.innerHTML = "";
    DEFAULT_CATEGORIES.forEach((c, i) => {
      const v = spentPerCat[c.id] || 0;
      if (v === 0) return;
      const item = document.createElement("span");
      item.className = "legend-item";
      item.innerHTML = `<span class="legend-dot" style="background:${PALETTE[i]}"></span>${c.name}`;
      legend.appendChild(item);
    });
  }

  function renderBarChart(m, spentPerCat) {
    const canvas = document.getElementById("chart-bar");
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const W = 360, H = 220;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    ctx.scale(dpr, dpr);
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";

    ctx.clearRect(0, 0, W, H);

    const cats = DEFAULT_CATEGORIES.filter(c => (m.budgets[c.id] || 0) > 0 || (spentPerCat[c.id] || 0) > 0);
    if (cats.length === 0) return;

    const padL = 10, padR = 10, padT = 20, padB = 40;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;
    const barGroupW = chartW / cats.length;
    const barW = Math.min(barGroupW * 0.3, 18);
    const gap = 3;

    const maxVal = Math.max(...cats.map(c => Math.max(m.budgets[c.id] || 0, spentPerCat[c.id] || 0)), 1);

    // Baseline
    ctx.strokeStyle = "#e2e8f0";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, padT + chartH);
    ctx.lineTo(padL + chartW, padT + chartH);
    ctx.stroke();

    cats.forEach((c, i) => {
      const budget = m.budgets[c.id] || 0;
      const spent = spentPerCat[c.id] || 0;
      const cx = padL + barGroupW * i + barGroupW / 2;

      const bH = (budget / maxVal) * chartH;
      const sH = (spent / maxVal) * chartH;

      // Budget bar
      ctx.fillStyle = "#c7d2fe";
      roundRect(ctx, cx - barW - gap / 2, padT + chartH - bH, barW, bH, 3);
      ctx.fill();

      // Spent bar
      ctx.fillStyle = spent > budget ? "#ef4444" : "#4f6df5";
      roundRect(ctx, cx + gap / 2, padT + chartH - sH, barW, sH, 3);
      ctx.fill();

      // Label
      ctx.fillStyle = "#64748b";
      ctx.font = "400 9px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(c.icon, cx, padT + chartH + 14);
      ctx.fillText(c.name.split(" ")[0], cx, padT + chartH + 26);
    });

    // Tiny legend
    ctx.font = "400 10px Inter, sans-serif";
    ctx.fillStyle = "#c7d2fe";
    ctx.fillRect(W - 120, 4, 10, 10);
    ctx.fillStyle = "#64748b";
    ctx.textAlign = "left";
    ctx.fillText("Budget", W - 106, 13);

    ctx.fillStyle = "#4f6df5";
    ctx.fillRect(W - 60, 4, 10, 10);
    ctx.fillStyle = "#64748b";
    ctx.fillText("Spent", W - 46, 13);
  }

  function roundRect(ctx, x, y, w, h, r) {
    if (h <= 0) { ctx.beginPath(); return; }
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h);
    ctx.lineTo(x, y + h);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  // ── Expense Modal ──────────────────────────────────────────
  const modalOverlay = document.getElementById("modal-overlay");
  const expenseForm = document.getElementById("expense-form");
  const catSelect = document.getElementById("expense-category");
  const dateInput = document.getElementById("expense-date");

  function openExpenseModal() {
    // Populate category dropdown
    catSelect.innerHTML = "";
    DEFAULT_CATEGORIES.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = `${c.icon} ${c.name}`;
      catSelect.appendChild(opt);
    });

    // Default date to today
    const today = new Date();
    dateInput.value = today.toISOString().split("T")[0];

    expenseForm.reset();
    dateInput.value = today.toISOString().split("T")[0];
    modalOverlay.classList.remove("hidden");
  }

  function closeExpenseModal() {
    modalOverlay.classList.add("hidden");
  }

  document.getElementById("btn-add-expense").addEventListener("click", openExpenseModal);
  document.getElementById("btn-cancel").addEventListener("click", closeExpenseModal);
  modalOverlay.addEventListener("click", e => { if (e.target === modalOverlay) closeExpenseModal(); });

  expenseForm.addEventListener("submit", e => {
    e.preventDefault();
    const category = catSelect.value;
    const description = document.getElementById("expense-desc").value.trim();
    const amount = parseFloat(document.getElementById("expense-amount").value);
    const date = dateInput.value;

    if (!description || !amount || !date) return;

    // Determine the correct month from the expense date
    const expDate = new Date(date + "T00:00:00");
    const key = monthKey(expDate);
    const m = getMonth(key);

    m.expenses.push({
      id: Date.now() + Math.random(),
      category,
      description,
      amount,
      date,
    });

    saveData();
    closeExpenseModal();

    // If the expense is for the currently viewed month, re-render
    if (key === monthKey(currentDate)) {
      render();
    }
  });

  // ── Budget Edit Modal ──────────────────────────────────────
  const budgetOverlay = document.getElementById("budget-modal-overlay");
  const budgetForm = document.getElementById("budget-form");
  const budgetFields = document.getElementById("budget-fields");

  function openBudgetModal() {
    const key = monthKey(currentDate);
    const m = getMonth(key);

    budgetFields.innerHTML = "";
    DEFAULT_CATEGORIES.forEach(c => {
      const val = m.budgets[c.id] || 0;
      const div = document.createElement("div");
      div.className = "budget-field";
      div.innerHTML = `
        <label>${c.icon} ${c.name}</label>
        <input type="number" step="1" min="0" name="budget_${c.id}" value="${val}" />
      `;
      budgetFields.appendChild(div);
    });

    budgetOverlay.classList.remove("hidden");
  }

  function closeBudgetModal() {
    budgetOverlay.classList.add("hidden");
  }

  document.getElementById("btn-edit-budgets").addEventListener("click", openBudgetModal);
  document.getElementById("btn-budget-cancel").addEventListener("click", closeBudgetModal);
  budgetOverlay.addEventListener("click", e => { if (e.target === budgetOverlay) closeBudgetModal(); });

  budgetForm.addEventListener("submit", e => {
    e.preventDefault();
    const key = monthKey(currentDate);
    const m = getMonth(key);

    DEFAULT_CATEGORIES.forEach(c => {
      const input = budgetForm.querySelector(`[name="budget_${c.id}"]`);
      m.budgets[c.id] = Math.max(0, parseFloat(input.value) || 0);
    });

    saveData();
    closeBudgetModal();
    render();
  });

  // ── Month Navigation ───────────────────────────────────────
  document.getElementById("prev-month").addEventListener("click", () => {
    currentDate = new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1);
    render();
  });

  document.getElementById("next-month").addEventListener("click", () => {
    currentDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1);
    render();
  });

  // ── Helpers ────────────────────────────────────────────────
  function escHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Init ───────────────────────────────────────────────────
  render();
})();
