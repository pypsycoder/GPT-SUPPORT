(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  var LIMIT = 50;

  var DOMAIN_CSS = {
    sleep: 'bd-sleep', emotion: 'bd-emotion', routine: 'bd-routine',
    stress: 'bd-stress', self_care: 'bd-self_care', social: 'bd-social',
    motivation: 'bd-motivation',
  };
  var REQUEST_TYPE_CSS = {
    simple: 'bt-simple', clinical: 'bt-clinical', emotional: 'bt-emotional',
    safety: 'bt-safety', quick_action: 'bt-quick_action', proactive: 'bt-proactive',
  };
  var TIER_CSS    = { lite: 'bm-lite', pro: 'bm-pro', max: 'bm-max' };
  var TIER_LABELS = { lite: 'Lite', pro: 'Pro', max: 'Max' };

  var TYPE_PILL_STYLE = {
    simple:       'background:#f3f4f6;color:#374151;',
    clinical:     'background:#eff6ff;color:#1e40af;',
    emotional:    'background:#f5f3ff;color:#6d28d9;',
    safety:       'background:#fef2f2;color:#991b1b;',
    quick_action: 'background:#f0fdf4;color:#166534;',
    proactive:    'background:#fffbeb;color:#92400e;',
  };
  var TYPE_SHORT = {
    simple: 'Simple', clinical: 'Clinical', emotional: 'Emotion',
    safety: 'Safety', quick_action: 'Q.Action', proactive: 'Proactive',
  };
  var TYPES_ORDER = ['simple', 'clinical', 'emotional', 'safety', 'quick_action', 'proactive'];
  var DOMAIN_LABELS = {
    sleep: 'Сон', emotion: 'Эмоции', routine: 'Режим',
    stress: 'Стресс', self_care: 'Уход', social: 'Соц.', motivation: 'Мотив.',
  };
  var ALL_DOMAINS = ['sleep', 'emotion', 'routine', 'stress', 'self_care', 'social', 'motivation'];
  var WEEKDAY_NAMES = ['', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

  // ---------------------------------------------------------------------------
  // Logs table state
  // ---------------------------------------------------------------------------

  var currentOffset = 0;
  var currentTotal  = 0;
  var autoTimer     = null;

  // ---------------------------------------------------------------------------
  // Analytics state
  // ---------------------------------------------------------------------------

  var analyticsGrouping = 'all';   // all | center | cohort | patient
  var analyticsPeriod   = '7d';    // today | 7d | 30d | (custom)

  // Charts
  var chartTokens   = null;
  var chartModels   = null;
  var chartDomains  = null;
  var chartHours    = null;
  var chartDialysis = null;

  // Cached data for cascading selects
  var allPatients = [];   // from /researcher/patients
  var allCenters  = [];   // from /centers
  var allCohorts  = [];   // from /researcher/cohorts (filtered by center)

  // ---------------------------------------------------------------------------
  // Utility
  // ---------------------------------------------------------------------------

  function badge(value, cssMap, labelMap) {
    if (!value) return '<span class="cm-na">—</span>';
    var cls   = cssMap[value] || 'bt-simple';
    var label = labelMap ? (labelMap[value] || value) : value;
    return '<span class="r-badge ' + cls + '">' + escHtml(label) + '</span>';
  }

  function truncate(text, n) {
    if (!text) return '<span class="cm-na">—</span>';
    var s = text.length > n ? text.substring(0, n) + '\u2026' : text;
    return escHtml(s);
  }

  function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;')
              .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fmtDate(iso) {
    var d = new Date(iso);
    var pad = function (n) { return String(n).padStart(2, '0'); };
    return (
      pad(d.getDate()) + '.' + pad(d.getMonth() + 1) + '.' + d.getFullYear() +
      '<br><span style="color:#6b7280;font-size:0.78rem;">' +
      pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()) +
      '</span>'
    );
  }

  function getLogsFilters() {
    return {
      patient_id:   document.getElementById('filter-patient').value      || null,
      domain:       document.getElementById('filter-domain').value        || null,
      request_type: document.getElementById('filter-request-type').value  || null,
      date_from:    document.getElementById('filter-date-from').value     || null,
      date_to:      document.getElementById('filter-date-to').value       || null,
    };
  }

  // ---------------------------------------------------------------------------
  // Analytics filters helpers
  // ---------------------------------------------------------------------------

  function getAnalyticsFilters() {
    var center_id  = null;
    var cohort_id  = null;
    var patient_id = null;

    if (analyticsGrouping === 'center') {
      center_id = document.getElementById('af-center').value || null;
    } else if (analyticsGrouping === 'cohort') {
      center_id = document.getElementById('af-center').value || null;
      cohort_id = document.getElementById('af-cohort').value || null;
    } else if (analyticsGrouping === 'patient') {
      center_id  = document.getElementById('af-center').value  || null;
      cohort_id  = document.getElementById('af-cohort').value  || null;
      patient_id = document.getElementById('af-patient').value || null;
    }

    // Period: custom dates take priority over preset buttons
    var dateFrom = document.getElementById('af-date-from').value || null;
    var dateTo   = document.getElementById('af-date-to').value   || null;

    if (!dateFrom && !dateTo) {
      var now = new Date();
      var to  = now.toISOString().slice(0, 10);
      if (analyticsPeriod === 'today') {
        dateFrom = to; dateTo = to;
      } else if (analyticsPeriod === '7d') {
        var d = new Date(now); d.setDate(d.getDate() - 6);
        dateFrom = d.toISOString().slice(0, 10); dateTo = to;
      } else if (analyticsPeriod === '30d') {
        var d2 = new Date(now); d2.setDate(d2.getDate() - 29);
        dateFrom = d2.toISOString().slice(0, 10); dateTo = to;
      }
      // 'all' → no date filter
    }

    return {
      center_id:  center_id,
      cohort_id:  cohort_id,
      patient_id: patient_id,
      date_from:  dateFrom,
      date_to:    dateTo,
    };
  }

  function updateSpecificsVisibility() {
    var g = analyticsGrouping;
    var specifics = document.getElementById('af-specifics');

    if (g === 'all') {
      specifics.style.display = 'none';
      return;
    }
    specifics.style.display = '';

    document.getElementById('af-center-wrap').style.display =
      (g === 'center' || g === 'cohort' || g === 'patient') ? '' : 'none';
    document.getElementById('af-cohort-wrap').style.display =
      (g === 'cohort' || g === 'patient') ? '' : 'none';
    document.getElementById('af-patient-wrap').style.display =
      (g === 'patient') ? '' : 'none';
  }

  // ---------------------------------------------------------------------------
  // Cascading selects for analytics
  // ---------------------------------------------------------------------------

  function populateCenters() {
    var sel = document.getElementById('af-center');
    sel.innerHTML = '<option value="">— Все центры —</option>';
    allCenters.forEach(function (c) {
      var opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = (c.city ? c.city + ' — ' : '') + c.name;
      sel.appendChild(opt);
    });
  }

  function populateCohorts(centerId) {
    var sel = document.getElementById('af-cohort');
    sel.innerHTML = '<option value="">— Когорта —</option>';
    var list = centerId
      ? allCohorts.filter(function (c) { return c.center_id === centerId; })
      : allCohorts;
    list.forEach(function (c) {
      var opt = document.createElement('option');
      opt.value = c.cohort_id;
      opt.textContent = c.label + ' (' + c.patient_count + ' пац.)';
      sel.appendChild(opt);
    });
  }

  function populateAnalyticsPatients(centerId, cohortObj) {
    var sel = document.getElementById('af-patient');
    sel.innerHTML = '<option value="">— Пациент —</option>';

    var list = allPatients.filter(function (p) {
      if (centerId && p.center_id !== centerId) return false;
      if (cohortObj) {
        if (p.active_schedule_shift !== cohortObj.shift) return false;
        var pDays = (p.active_schedule_days || []).slice().sort().join(',');
        var cDays = cohortObj.weekdays.slice().sort().join(',');
        if (pDays !== cDays) return false;
      }
      return true;
    });

    list.forEach(function (p) {
      var opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = '#' + (p.patient_number || p.id) + (p.full_name ? ' ' + p.full_name : '');
      sel.appendChild(opt);
    });
  }

  async function loadCohorts(centerId) {
    var url = '/api/v1/researcher/cohorts';
    if (centerId) url += '?center_id=' + encodeURIComponent(centerId);
    try {
      var resp = await fetch(url, { credentials: 'include' });
      if (resp.ok) allCohorts = await resp.json();
    } catch (_) {}
  }

  // ---------------------------------------------------------------------------
  // Chart helpers
  // ---------------------------------------------------------------------------

  function showChart(emptyId, canvasId, hasData) {
    document.getElementById(emptyId).style.display  = hasData ? 'none' : '';
    document.getElementById(canvasId).style.display = hasData ? 'block' : 'none';
  }

  async function loadStats() {
    var af  = getAnalyticsFilters();
    var params = new URLSearchParams();
    if (af.patient_id) params.append('patient_id', af.patient_id);
    else if (af.cohort_id) params.append('cohort_id', af.cohort_id);
    else if (af.center_id) params.append('center_id', af.center_id);
    if (af.date_from) params.append('date_from', af.date_from);
    if (af.date_to)   params.append('date_to',   af.date_to);

    var resp;
    try {
      resp = await fetch('/api/v1/researcher/chat-stats?' + params.toString(), {
        credentials: 'include',
      });
    } catch (_) { return; }
    if (!resp.ok) return;

    var data = await resp.json();
    renderTokensChart(data.tokens_by_date || []);
    renderModelsChart(data.models_distribution || {});
    renderDomainsChart(data.domains_distribution || {});
    renderHoursChart(data.activity_by_hour || {});
    renderDialysisChart(data.dialysis_vs_nondialysis || null);
  }

  function renderTokensChart(rows) {
    showChart('chart-tokens-empty', 'chart-tokens', rows.length > 0);
    if (!rows.length) { if (chartTokens) { chartTokens.destroy(); chartTokens = null; } return; }

    var labels  = rows.map(function (r) { return r.date; });
    var inputs  = rows.map(function (r) { return r.input; });
    var outputs = rows.map(function (r) { return r.output; });
    var totals  = rows.map(function (r) { return r.input + r.output; });

    if (chartTokens) { chartTokens.destroy(); }
    chartTokens = new Chart(document.getElementById('chart-tokens'), {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          { label: 'Total',  data: totals,  borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.08)', tension: 0.3, fill: true,  pointRadius: 3 },
          { label: 'Input',  data: inputs,  borderColor: '#3b82f6', backgroundColor: 'transparent', tension: 0.3, fill: false, pointRadius: 3 },
          { label: 'Output', data: outputs, borderColor: '#10b981', backgroundColor: 'transparent', tension: 0.3, fill: false, pointRadius: 3 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { position: 'top', labels: { font: { size: 11 }, boxWidth: 14 } } },
        scales: {
          x: { ticks: { font: { size: 10 }, maxTicksLimit: 10 } },
          y: { ticks: { font: { size: 10 } }, beginAtZero: true },
        },
      },
    });
  }

  function renderModelsChart(dist) {
    var keys = Object.keys(dist);
    showChart('chart-models-empty', 'chart-models', keys.length > 0);
    if (!keys.length) { if (chartModels) { chartModels.destroy(); chartModels = null; } return; }

    var COLORS = { lite: '#10b981', pro: '#3b82f6', max: '#8b5cf6' };
    if (chartModels) { chartModels.destroy(); }
    chartModels = new Chart(document.getElementById('chart-models'), {
      type: 'doughnut',
      data: {
        labels: keys.map(function (l) { return l.charAt(0).toUpperCase() + l.slice(1); }),
        datasets: [{
          data: keys.map(function (k) { return dist[k]; }),
          backgroundColor: keys.map(function (k) { return COLORS[k] || '#9ca3af'; }),
          borderWidth: 2, borderColor: '#fff',
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 11 }, boxWidth: 14 } },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var total = ctx.dataset.data.reduce(function (a, b) { return a + b; }, 0);
                var pct   = total ? Math.round(ctx.parsed / total * 100) : 0;
                return ctx.label + ': ' + ctx.parsed + ' (' + pct + '%)';
              },
            },
          },
        },
      },
    });
  }

  function renderDomainsChart(dist) {
    var hasData = Object.keys(dist).some(function (k) { return dist[k] > 0; });
    showChart('chart-domains-empty', 'chart-domains', hasData);
    if (!hasData) { if (chartDomains) { chartDomains.destroy(); chartDomains = null; } return; }

    var labels = ALL_DOMAINS.map(function (d) { return DOMAIN_LABELS[d] || d; });
    var values = ALL_DOMAINS.map(function (d) { return dist[d] || 0; });
    var colors = ['#3b82f6','#8b5cf6','#10b981','#f59e0b','#06b6d4','#ec4899','#f97316'];

    if (chartDomains) { chartDomains.destroy(); }
    chartDomains = new Chart(document.getElementById('chart-domains'), {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{ label: 'Запросов', data: values, backgroundColor: colors, borderRadius: 4, borderSkipped: false }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { font: { size: 10 } } },
          y: { ticks: { font: { size: 10 } }, beginAtZero: true, precision: 0 },
        },
      },
    });
  }

  function renderHoursChart(hourDict) {
    var hasData = Object.keys(hourDict).some(function (k) { return hourDict[k] > 0; });
    showChart('chart-hours-empty', 'chart-hours', hasData);
    if (!hasData) { if (chartHours) { chartHours.destroy(); chartHours = null; } return; }

    var hours  = Array.from({ length: 24 }, function (_, i) { return i; });
    var values = hours.map(function (h) { return hourDict[String(h)] || 0; });
    var labels = hours.map(function (h) {
      return h % 2 === 0 ? String(h).padStart(2, '0') + ':00' : '';
    });

    // Color accent hours: 8 (morning), 14 (afternoon), 20 (evening)
    var ACCENT = { 8: '#3b82f6', 14: '#f59e0b', 20: '#8b5cf6' };
    var bgColors = hours.map(function (h) { return ACCENT[h] || 'rgba(99,102,241,0.55)'; });

    if (chartHours) { chartHours.destroy(); }
    chartHours = new Chart(document.getElementById('chart-hours'), {
      type: 'bar',
      data: {
        labels: hours.map(function (h) { return String(h).padStart(2, '0') + ':00'; }),
        datasets: [{
          label: 'Запросов',
          data: values,
          backgroundColor: bgColors,
          borderRadius: 3,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function (items) {
                var h = items[0].dataIndex;
                var name = h === 8 ? ' (Утро)' : h === 14 ? ' (День)' : h === 20 ? ' (Вечер)' : '';
                return String(h).padStart(2, '0') + ':00' + name;
              },
            },
          },
        },
        scales: {
          x: { ticks: { font: { size: 9 }, maxTicksLimit: 12 } },
          y: { ticks: { font: { size: 10 } }, beginAtZero: true, precision: 0 },
        },
      },
    });
  }

  function renderDialysisChart(data) {
    if (!data || (data.dialysis_day + data.non_dialysis_day) === 0) {
      showChart('chart-dialysis-empty', 'chart-dialysis', false);
      document.getElementById('chart-dialysis-empty').textContent =
        analyticsGrouping === 'all' || analyticsGrouping === 'center'
          ? 'Выберите когорту или пациента'
          : 'Нет данных';
      if (chartDialysis) { chartDialysis.destroy(); chartDialysis = null; }
      return;
    }
    showChart('chart-dialysis-empty', 'chart-dialysis', true);

    if (chartDialysis) { chartDialysis.destroy(); }
    chartDialysis = new Chart(document.getElementById('chart-dialysis'), {
      type: 'doughnut',
      data: {
        labels: ['День диализа', 'Обычный день'],
        datasets: [{
          data: [data.dialysis_day, data.non_dialysis_day],
          backgroundColor: ['#3b82f6', '#e5e7eb'],
          borderWidth: 2,
          borderColor: '#fff',
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 11 }, boxWidth: 14 } },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var total = ctx.dataset.data.reduce(function (a, b) { return a + b; }, 0);
                var pct   = total ? Math.round(ctx.parsed / total * 100) : 0;
                return ctx.label + ': ' + ctx.parsed + ' (' + pct + '%)';
              },
            },
          },
        },
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Export
  // ---------------------------------------------------------------------------

  function buildExportUrl() {
    var f = getLogsFilters();
    var params = new URLSearchParams({ format: 'csv' });
    if (f.patient_id)   params.append('patient_id',   f.patient_id);
    if (f.domain)       params.append('domain',       f.domain);
    if (f.request_type) params.append('request_type', f.request_type);
    if (f.date_from)    params.append('date_from',    f.date_from);
    if (f.date_to)      params.append('date_to',      f.date_to);
    return '/api/v1/researcher/chat-logs/export?' + params.toString();
  }

  function triggerExport() {
    var a = document.createElement('a');
    a.href = buildExportUrl();
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function renderTypesCard(dist) {
    var grid = document.getElementById('stat-types-grid');
    var hasAny = TYPES_ORDER.some(function (t) { return dist[t] > 0; });
    if (!hasAny) {
      grid.innerHTML = '<span style="color:#9ca3af;font-size:0.82rem;grid-column:1/-1;">Нет данных</span>';
      return;
    }
    grid.innerHTML = TYPES_ORDER.map(function (t) {
      var cnt   = dist[t] || 0;
      var style = TYPE_PILL_STYLE[t] || '';
      var name  = TYPE_SHORT[t] || t;
      return (
        '<div class="cm-type-pill" style="' + style + '">' +
        '<span class="cm-type-name">' + name + '</span>' +
        '<span class="cm-type-cnt">' + cnt + '</span>' +
        '</div>'
      );
    }).join('');
  }

  // ---------------------------------------------------------------------------
  // Logs data loading
  // ---------------------------------------------------------------------------

  async function loadPatients() {
    var resp = await fetch('/api/v1/researcher/patients', { credentials: 'include' });
    if (!resp.ok) return;
    allPatients = await resp.json();

    // Fill logs patient select
    var sel = document.getElementById('filter-patient');
    allPatients.forEach(function (p) {
      var opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = '#' + (p.patient_number || p.id) + (p.full_name ? ' ' + p.full_name : '');
      sel.appendChild(opt);
    });
  }

  async function loadCenters() {
    var resp = await fetch('/api/v1/centers', { credentials: 'include' });
    if (!resp.ok) return;
    allCenters = await resp.json();
    populateCenters();
  }

  async function loadData() {
    var tbody = document.getElementById('cm-tbody');
    tbody.innerHTML =
      '<tr><td colspan="10" style="text-align:center;color:#9ca3af;padding:2rem;">Загрузка\u2026</td></tr>';

    var f = getLogsFilters();
    var params = new URLSearchParams({ limit: LIMIT, offset: currentOffset });
    if (f.patient_id)   params.append('patient_id',   f.patient_id);
    if (f.domain)       params.append('domain',       f.domain);
    if (f.request_type) params.append('request_type', f.request_type);
    if (f.date_from)    params.append('date_from',    f.date_from);
    if (f.date_to)      params.append('date_to',      f.date_to);

    var resp;
    try {
      resp = await fetch('/api/v1/researcher/chat-logs?' + params.toString(), { credentials: 'include' });
    } catch (err) {
      tbody.innerHTML =
        '<tr><td colspan="10" style="text-align:center;color:#ef4444;padding:2rem;">Ошибка соединения</td></tr>';
      return;
    }
    if (!resp.ok) {
      tbody.innerHTML =
        '<tr><td colspan="10" style="text-align:center;color:#ef4444;padding:2rem;">Ошибка загрузки (' + resp.status + ')</td></tr>';
      return;
    }

    var data = await resp.json();
    currentTotal = data.total;

    document.getElementById('stat-total').textContent        = data.total.toLocaleString('ru-RU');
    document.getElementById('stat-safety-today').textContent = data.safety_today.toLocaleString('ru-RU');
    document.getElementById('stat-avg-ms').textContent =
      data.avg_response_ms > 0 ? Math.round(data.avg_response_ms).toLocaleString('ru-RU') : '—';
    renderTypesCard(data.request_types_today || {});

    var from = data.total === 0 ? 0 : currentOffset + 1;
    var to   = Math.min(currentOffset + LIMIT, data.total);
    var pageInfo = from + '\u2013' + to + ' из ' + data.total.toLocaleString('ru-RU');
    document.getElementById('pagination-display').textContent = pageInfo;
    document.getElementById('pagination-count').textContent   = pageInfo;
    document.getElementById('btn-prev').disabled = currentOffset === 0;
    document.getElementById('btn-next').disabled = currentOffset + LIMIT >= data.total;

    renderTable(data.items);
  }

  // ---------------------------------------------------------------------------
  // Table rendering
  // ---------------------------------------------------------------------------

  function renderTable(items) {
    var tbody = document.getElementById('cm-tbody');
    if (!items || !items.length) {
      tbody.innerHTML =
        '<tr><td colspan="10" style="text-align:center;color:#9ca3af;padding:2rem;">Нет записей по текущему фильтру</td></tr>';
      return;
    }
    tbody.innerHTML = '';

    items.forEach(function (item) {
      var tr = document.createElement('tr');
      tr.style.cursor = 'pointer';

      var successHtml = item.success
        ? '<span class="cm-status-ok">✓</span>'
        : '<span class="cm-status-err">✗</span>';

      tr.innerHTML =
        '<td style="font-size:0.82rem;">' + fmtDate(item.created_at) + '</td>' +
        '<td><span style="font-weight:600;">#' + item.patient_id + '</span></td>' +
        '<td>' + badge(item.domain, DOMAIN_CSS, null) + '</td>' +
        '<td>' + badge(item.request_type, REQUEST_TYPE_CSS, null) + '</td>' +
        '<td>' + badge(item.model_tier, TIER_CSS, TIER_LABELS) + '</td>' +
        '<td class="cm-content-cell">' + truncate(item.user_content, 80) + '</td>' +
        '<td class="cm-content-cell">' + truncate(item.assistant_content, 80) + '</td>' +
        '<td class="cm-tokens">' + item.tokens_input + '&rarr;' + item.tokens_output + '</td>' +
        '<td class="cm-ms">' + item.response_time_ms + '</td>' +
        '<td style="text-align:center;">' + successHtml + '</td>';

      tr.addEventListener('click', function () {
        var next = tr.nextElementSibling;
        if (next && next.classList.contains('cm-expanded-row')) {
          next.remove(); tr.style.background = ''; return;
        }
        tr.style.background = '#f0f9ff';
        var expTr = document.createElement('tr');
        expTr.classList.add('cm-expanded-row');
        var errorHtml = item.error_message
          ? '<div class="cm-expand-error">Ошибка: ' + escHtml(item.error_message) + '</div>' : '';
        var metaHtml =
          '<div style="margin-top:0.75rem;display:flex;gap:1rem;flex-wrap:wrap;font-size:0.8rem;color:#6b7280;">' +
          '<span>log_id: ' + item.log_id + '</span>' +
          '<span>patient_id: ' + item.patient_id + '</span>' +
          (item.model_tier ? '<span>tier: ' + escHtml(item.model_tier) + '</span>' : '') +
          '<span>tokens: ' + item.tokens_input + ' in / ' + item.tokens_output + ' out</span>' +
          '<span>' + item.response_time_ms + ' ms</span></div>';
        expTr.innerHTML =
          '<td colspan="10" style="padding:1rem 1.5rem;">' +
          '<div class="cm-expand-grid">' +
            '<div><div class="cm-expand-label">Вопрос пациента</div>' +
            '<div class="cm-expand-text">' + escHtml(item.user_content || '—') + '</div></div>' +
            '<div><div class="cm-expand-label">Ответ ассистента</div>' +
            '<div class="cm-expand-text">' + escHtml(item.assistant_content || '—') + '</div>' +
            errorHtml + '</div>' +
          '</div>' + metaHtml + '</td>';
        tr.after(expTr);
      });

      tbody.appendChild(tr);
    });
  }

  // ---------------------------------------------------------------------------
  // Auto-refresh (logs table only)
  // ---------------------------------------------------------------------------

  function syncAutoRefresh() {
    clearInterval(autoTimer);
    if (document.getElementById('auto-refresh-cb').checked) {
      autoTimer = setInterval(loadData, 30000);
    }
  }

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  async function init() {
    var me = await window.ResearcherAuth.requireAuth();
    document.getElementById('r-user-name').textContent = me.username || '';
    document.getElementById('r-logout-btn').addEventListener('click', function () {
      window.ResearcherAuth.logout();
    });

    // Load initial data in parallel
    await Promise.all([loadPatients(), loadCenters()]);
    await loadCohorts('');   // load all cohorts for when grouping changes later

    // ---- Analytics grouping buttons ----
    document.querySelectorAll('.cm-group-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.cm-group-btn').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        analyticsGrouping = btn.dataset.group;
        updateSpecificsVisibility();
        loadStats();
      });
    });

    // ---- Analytics center select ----
    document.getElementById('af-center').addEventListener('change', async function () {
      var centerId = this.value;
      await loadCohorts(centerId);
      populateCohorts(centerId);
      // Reset cohort + patient
      document.getElementById('af-cohort').value  = '';
      document.getElementById('af-patient').innerHTML = '<option value="">— Пациент —</option>';
      loadStats();
    });

    // ---- Analytics cohort select ----
    document.getElementById('af-cohort').addEventListener('change', function () {
      var cohortId  = this.value;
      var cohortObj = allCohorts.find(function (c) { return c.cohort_id === cohortId; }) || null;
      var centerId  = document.getElementById('af-center').value;
      populateAnalyticsPatients(centerId, cohortObj);
      document.getElementById('af-patient').value = '';
      loadStats();
    });

    // ---- Analytics patient select ----
    document.getElementById('af-patient').addEventListener('change', function () {
      loadStats();
    });

    // ---- Period preset buttons ----
    document.querySelectorAll('.cm-period-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.cm-period-btn').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        analyticsPeriod = btn.dataset.period;
        // Clear custom dates
        document.getElementById('af-date-from').value = '';
        document.getElementById('af-date-to').value   = '';
        loadStats();
      });
    });

    // ---- Custom date inputs (clear period buttons when typing) ----
    ['af-date-from', 'af-date-to'].forEach(function (id) {
      document.getElementById(id).addEventListener('change', function () {
        document.querySelectorAll('.cm-period-btn').forEach(function (b) { b.classList.remove('active'); });
        analyticsPeriod = '';
        loadStats();
      });
    });

    // ---- Logs filters ----
    document.getElementById('btn-apply').addEventListener('click', function () {
      currentOffset = 0;
      loadData();
    });

    document.getElementById('btn-export-csv').addEventListener('click', triggerExport);

    document.getElementById('btn-prev').addEventListener('click', function () {
      if (currentOffset > 0) {
        currentOffset = Math.max(0, currentOffset - LIMIT);
        loadData();
      }
    });
    document.getElementById('btn-next').addEventListener('click', function () {
      if (currentOffset + LIMIT < currentTotal) {
        currentOffset += LIMIT;
        loadData();
      }
    });
    document.getElementById('auto-refresh-cb').addEventListener('change', syncAutoRefresh);
    syncAutoRefresh();

    // Initial load
    loadData();
    loadStats();
  }

  document.addEventListener('DOMContentLoaded', init);
}());
