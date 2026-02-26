(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Constants & config
  // ---------------------------------------------------------------------------

  var LIMIT = 50;

  var DOMAIN_CSS = {
    sleep:       'bd-sleep',
    emotion:     'bd-emotion',
    routine:     'bd-routine',
    stress:      'bd-stress',
    self_care:   'bd-self_care',
    social:      'bd-social',
    motivation:  'bd-motivation',
  };

  var REQUEST_TYPE_CSS = {
    simple:       'bt-simple',
    clinical:     'bt-clinical',
    emotional:    'bt-emotional',
    safety:       'bt-safety',
    quick_action: 'bt-quick_action',
    proactive:    'bt-proactive',
  };

  var TIER_CSS    = { lite: 'bm-lite', pro: 'bm-pro', max: 'bm-max' };
  var TIER_LABELS = { lite: 'Lite', pro: 'Pro', max: 'Max' };

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  var currentOffset = 0;
  var currentTotal  = 0;
  var autoTimer     = null;

  // Charts state
  var chartPeriod    = '7d';
  var chartTokens    = null;
  var chartModels    = null;
  var chartDomains   = null;

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function badge(value, cssMap, labelMap) {
    if (!value) return '<span class="cm-na">—</span>';
    var cls   = cssMap[value]   || 'bt-simple';
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
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
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

  function getFilters() {
    return {
      patient_id:   document.getElementById('filter-patient').value      || null,
      domain:       document.getElementById('filter-domain').value        || null,
      request_type: document.getElementById('filter-request-type').value  || null,
      date_from:    document.getElementById('filter-date-from').value     || null,
      date_to:      document.getElementById('filter-date-to').value       || null,
    };
  }

  // ---------------------------------------------------------------------------
  // Chart helpers
  // ---------------------------------------------------------------------------

  function getPeriodDates() {
    var now  = new Date();
    var to   = now.toISOString().slice(0, 10);
    var from = null;
    if (chartPeriod === 'today') {
      from = to;
    } else if (chartPeriod === '7d') {
      var d = new Date(now); d.setDate(d.getDate() - 6);
      from = d.toISOString().slice(0, 10);
    } else if (chartPeriod === '30d') {
      var d = new Date(now); d.setDate(d.getDate() - 29);
      from = d.toISOString().slice(0, 10);
    }
    return { from: from, to: to };
  }

  async function loadStats() {
    var dates     = getPeriodDates();
    var filters   = getFilters();
    var params    = new URLSearchParams();
    if (filters.patient_id) params.append('patient_id', filters.patient_id);
    if (dates.from)         params.append('date_from',  dates.from);
    if (dates.to)           params.append('date_to',    dates.to);

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
  }

  function renderTokensChart(rows) {
    var empty  = document.getElementById('chart-tokens-empty');
    var canvas = document.getElementById('chart-tokens');

    if (!rows.length) {
      empty.style.display = '';
      canvas.style.display = 'none';
      return;
    }
    empty.style.display = 'none';
    canvas.style.display = 'block';

    var labels  = rows.map(function (r) { return r.date; });
    var inputs  = rows.map(function (r) { return r.input; });
    var outputs = rows.map(function (r) { return r.output; });
    var totals  = rows.map(function (r) { return r.input + r.output; });

    if (chartTokens) { chartTokens.destroy(); }
    chartTokens = new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          { label: 'Total',  data: totals,  borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.08)', tension: 0.3, fill: true,  pointRadius: 3 },
          { label: 'Input',  data: inputs,  borderColor: '#3b82f6', backgroundColor: 'transparent',           tension: 0.3, fill: false, pointRadius: 3 },
          { label: 'Output', data: outputs, borderColor: '#10b981', backgroundColor: 'transparent',           tension: 0.3, fill: false, pointRadius: 3 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: { legend: { position: 'top', labels: { font: { size: 11 }, boxWidth: 14 } } },
        scales: {
          x: { ticks: { font: { size: 10 }, maxTicksLimit: 10 } },
          y: { ticks: { font: { size: 10 } }, beginAtZero: true },
        },
      },
    });
  }

  function renderModelsChart(dist) {
    var empty  = document.getElementById('chart-models-empty');
    var canvas = document.getElementById('chart-models');
    var keys   = Object.keys(dist);

    if (!keys.length) {
      empty.style.display = '';
      canvas.style.display = 'none';
      return;
    }
    empty.style.display = 'none';
    canvas.style.display = 'block';

    var COLORS = { lite: '#10b981', pro: '#3b82f6', max: '#8b5cf6' };
    var labels = keys;
    var values = keys.map(function (k) { return dist[k]; });
    var colors = keys.map(function (k) { return COLORS[k] || '#9ca3af'; });

    if (chartModels) { chartModels.destroy(); }
    chartModels = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: labels.map(function (l) { return l.charAt(0).toUpperCase() + l.slice(1); }),
        datasets: [{ data: values, backgroundColor: colors, borderWidth: 2, borderColor: '#fff' }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
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

  var DOMAIN_LABELS = {
    sleep: 'Сон', emotion: 'Эмоции', routine: 'Режим',
    stress: 'Стресс', self_care: 'Уход', social: 'Соц.', motivation: 'Мотив.',
  };
  var ALL_DOMAINS = ['sleep', 'emotion', 'routine', 'stress', 'self_care', 'social', 'motivation'];

  function renderDomainsChart(dist) {
    var empty  = document.getElementById('chart-domains-empty');
    var canvas = document.getElementById('chart-domains');
    var hasData = Object.keys(dist).some(function (k) { return dist[k] > 0; });

    if (!hasData) {
      empty.style.display = '';
      canvas.style.display = 'none';
      return;
    }
    empty.style.display = 'none';
    canvas.style.display = 'block';

    var labels = ALL_DOMAINS.map(function (d) { return DOMAIN_LABELS[d] || d; });
    var values = ALL_DOMAINS.map(function (d) { return dist[d] || 0; });
    var colors = ['#3b82f6','#8b5cf6','#10b981','#f59e0b','#06b6d4','#ec4899','#f97316'];

    if (chartDomains) { chartDomains.destroy(); }
    chartDomains = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Запросов',
          data: values,
          backgroundColor: colors,
          borderRadius: 4,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { font: { size: 10 } } },
          y: { ticks: { font: { size: 10 } }, beginAtZero: true, precision: 0 },
        },
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Export
  // ---------------------------------------------------------------------------

  function buildExportUrl() {
    var filters = getFilters();
    var params  = new URLSearchParams({ format: 'csv' });
    if (filters.patient_id)   params.append('patient_id',   filters.patient_id);
    if (filters.domain)       params.append('domain',       filters.domain);
    if (filters.request_type) params.append('request_type', filters.request_type);
    if (filters.date_from)    params.append('date_from',    filters.date_from);
    if (filters.date_to)      params.append('date_to',      filters.date_to);
    return '/api/v1/researcher/chat-logs/export?' + params.toString();
  }

  function triggerExport() {
    var url = buildExportUrl();
    var a   = document.createElement('a');
    a.href  = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------

  async function loadPatients() {
    var resp = await fetch('/api/v1/researcher/patients', { credentials: 'include' });
    if (!resp.ok) return;
    var patients = await resp.json();
    var sel = document.getElementById('filter-patient');
    patients.forEach(function (p) {
      var opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = '#' + (p.patient_number || p.id) + (p.full_name ? ' ' + p.full_name : '');
      sel.appendChild(opt);
    });
  }

  async function loadData() {
    var tbody = document.getElementById('cm-tbody');
    tbody.innerHTML =
      '<tr><td colspan="10" style="text-align:center;color:#9ca3af;padding:2rem;">Загрузка\u2026</td></tr>';

    var filters = getFilters();
    var params  = new URLSearchParams({ limit: LIMIT, offset: currentOffset });
    if (filters.patient_id)   params.append('patient_id',   filters.patient_id);
    if (filters.domain)       params.append('domain',       filters.domain);
    if (filters.request_type) params.append('request_type', filters.request_type);
    if (filters.date_from)    params.append('date_from',    filters.date_from);
    if (filters.date_to)      params.append('date_to',      filters.date_to);

    var resp;
    try {
      resp = await fetch('/api/v1/researcher/chat-logs?' + params.toString(), {
        credentials: 'include',
      });
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

    // --- Stats ---
    document.getElementById('stat-total').textContent        = data.total.toLocaleString('ru-RU');
    document.getElementById('stat-safety-today').textContent = data.safety_today.toLocaleString('ru-RU');
    document.getElementById('stat-avg-ms').textContent       =
      data.avg_response_ms > 0 ? Math.round(data.avg_response_ms).toLocaleString('ru-RU') : '—';

    // --- Pagination info ---
    var from = data.total === 0 ? 0 : currentOffset + 1;
    var to   = Math.min(currentOffset + LIMIT, data.total);
    document.getElementById('pagination-display').textContent =
      from + '\u2013' + to + ' из ' + data.total.toLocaleString('ru-RU');
    document.getElementById('pagination-count').textContent =
      from + '\u2013' + to + ' из ' + data.total.toLocaleString('ru-RU');

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

      var tierHtml  = badge(item.model_tier,    TIER_CSS,          TIER_LABELS);
      var domainHtml = badge(item.domain,        DOMAIN_CSS,        null);
      var rtHtml     = badge(item.request_type,  REQUEST_TYPE_CSS,  null);

      tr.innerHTML =
        '<td style="font-size:0.82rem;">' + fmtDate(item.created_at) + '</td>' +
        '<td><span style="font-weight:600;">#' + item.patient_id + '</span></td>' +
        '<td>' + domainHtml + '</td>' +
        '<td>' + rtHtml + '</td>' +
        '<td>' + tierHtml + '</td>' +
        '<td class="cm-content-cell">' + truncate(item.user_content, 80) + '</td>' +
        '<td class="cm-content-cell">' + truncate(item.assistant_content, 80) + '</td>' +
        '<td class="cm-tokens">' + item.tokens_input + '&rarr;' + item.tokens_output + '</td>' +
        '<td class="cm-ms">' + item.response_time_ms + '</td>' +
        '<td style="text-align:center;">' + successHtml + '</td>';

      tr.addEventListener('click', function () {
        var next = tr.nextElementSibling;
        if (next && next.classList.contains('cm-expanded-row')) {
          next.remove();
          tr.style.background = '';
          return;
        }
        tr.style.background = '#f0f9ff';
        var expTr = document.createElement('tr');
        expTr.classList.add('cm-expanded-row');

        var errorHtml = item.error_message
          ? '<div class="cm-expand-error">Ошибка: ' + escHtml(item.error_message) + '</div>'
          : '';

        var metaHtml =
          '<div style="margin-top:0.75rem;display:flex;gap:1rem;flex-wrap:wrap;font-size:0.8rem;color:#6b7280;">' +
          '<span>log_id: ' + item.log_id + '</span>' +
          '<span>patient_id: ' + item.patient_id + '</span>' +
          (item.model_tier ? '<span>tier: ' + escHtml(item.model_tier) + '</span>' : '') +
          '<span>tokens: ' + item.tokens_input + ' in / ' + item.tokens_output + ' out</span>' +
          '<span>' + item.response_time_ms + ' ms</span>' +
          '</div>';

        expTr.innerHTML =
          '<td colspan="10" style="padding:1rem 1.5rem;">' +
          '<div class="cm-expand-grid">' +
            '<div>' +
              '<div class="cm-expand-label">Вопрос пациента</div>' +
              '<div class="cm-expand-text">' + escHtml(item.user_content || '—') + '</div>' +
            '</div>' +
            '<div>' +
              '<div class="cm-expand-label">Ответ ассистента</div>' +
              '<div class="cm-expand-text">' + escHtml(item.assistant_content || '—') + '</div>' +
              errorHtml +
            '</div>' +
          '</div>' +
          metaHtml +
          '</td>';

        tr.after(expTr);
      });

      tbody.appendChild(tr);
    });
  }

  // ---------------------------------------------------------------------------
  // Auto-refresh
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

    await loadPatients();

    // Period buttons for charts
    document.querySelectorAll('.cm-period-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.cm-period-btn').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        chartPeriod = btn.dataset.period;
        loadStats();
      });
    });

    document.getElementById('btn-apply').addEventListener('click', function () {
      currentOffset = 0;
      loadData();
      loadStats();
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

    loadData();
    loadStats();
  }

  document.addEventListener('DOMContentLoaded', init);
}());
