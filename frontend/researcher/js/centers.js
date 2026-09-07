(function () {
  'use strict';

  var centersBody = document.getElementById('r-centers-tbody');
  var addModal = document.getElementById('modal-add-center');
  var addForm = document.getElementById('form-add-center');
  var errorEl = document.getElementById('center-error');
  var modalTitle = document.getElementById('center-modal-title');

  // Дефолтные часы смен — совпадают с server_default колонок centers.
  var DEFAULT_SHIFTS = {
    morning_start: '08:00', morning_end: '11:00',
    afternoon_start: '13:00', afternoon_end: '17:00',
    evening_start: '18:00', evening_end: '21:00'
  };

  var SHIFT_FIELDS = [
    'morning_start', 'morning_end',
    'afternoon_start', 'afternoon_end',
    'evening_start', 'evening_end'
  ];

  // id центра в режиме редактирования, либо null (создание).
  var editingId = null;

  function hideError() {
    errorEl.textContent = '';
    errorEl.classList.remove('visible');
  }

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.classList.add('visible');
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function hhmm(t) {
    // "08:00:00" -> "08:00"; пусто -> "—"
    if (!t) return '—';
    return String(t).slice(0, 5);
  }

  // Нормализация ввода к "ЧЧ:ММ" (24 ч) либо "" — если невалидно.
  function normalizeHHMM(s) {
    s = (s || '').trim();
    var m = /^(\d{1,2}):?(\d{2})$/.exec(s) || /^(\d{1,2})$/.exec(s);
    if (!m) return '';
    var h = parseInt(m[1], 10);
    var mm = m[2] ? parseInt(m[2], 10) : 0;
    if (h > 23 || mm > 59) return '';
    return (h < 10 ? '0' + h : h) + ':' + (mm < 10 ? '0' + mm : mm);
  }

  function fieldId(name) {
    return 'center-' + name.replace('_', '-');
  }

  // Маска ЧЧ:ММ на 6 полей часов смен (24 ч, без AM/PM).
  function attachTimeMasks() {
    SHIFT_FIELDS.forEach(function (name) {
      var el = document.getElementById(fieldId(name));
      if (!el || el._maskAttached) return;
      el._maskAttached = true;
      el.addEventListener('input', function () {
        var d = el.value.replace(/\D/g, '').slice(0, 4);
        el.value = d.length > 2 ? d.slice(0, 2) + ':' + d.slice(2) : d;
      });
      el.addEventListener('blur', function () {
        var n = normalizeHHMM(el.value);
        if (n) el.value = n;
      });
    });
  }

  function renderCenters(centers) {
    if (!centers || centers.length === 0) {
      centersBody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#9ca3af;padding:2rem;">Нет центров</td></tr>';
      return;
    }
    centersBody.innerHTML = centers.map(function (c) {
      var shifts = hhmm(c.morning_start) + '–' + hhmm(c.morning_end) + '  /  ' +
        hhmm(c.afternoon_start) + '–' + hhmm(c.afternoon_end) + '  /  ' +
        hhmm(c.evening_start) + '–' + hhmm(c.evening_end);
      return '<tr>' +
        '<td><strong>' + esc(c.name || '—') + '</strong></td>' +
        '<td>' + esc(c.city || '—') + '</td>' +
        '<td>' + esc(c.timezone || '—') + '</td>' +
        '<td class="r-center-shifts">' + esc(shifts) + '</td>' +
        '<td><button type="button" class="r-center-edit" data-center-id="' + esc(c.id) + '">Изменить</button></td>' +
        '</tr>';
    }).join('');

    centersBody.querySelectorAll('.r-center-edit').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = btn.getAttribute('data-center-id');
        var center = centers.filter(function (c) { return String(c.id) === String(id); })[0];
        if (center) openModal(center);
      });
    });
  }

  async function loadCenters() {
    try {
      var resp = await fetch('/api/v1/centers', { credentials: 'include' });
      if (!resp.ok) {
        centersBody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#dc2626;">Ошибка загрузки</td></tr>';
        return;
      }
      var data = await resp.json();
      renderCenters(data);
    } catch (e) {
      console.warn('Failed to load centers', e);
      centersBody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#dc2626;">Ошибка соединения</td></tr>';
    }
  }

  function setShiftInputs(values) {
    SHIFT_FIELDS.forEach(function (name) {
      var el = document.getElementById(fieldId(name));
      if (el) el.value = hhmm(values[name]) === '—' ? '' : hhmm(values[name]);
    });
  }

  function readShiftInputs() {
    var out = {};
    for (var i = 0; i < SHIFT_FIELDS.length; i++) {
      var name = SHIFT_FIELDS[i];
      var el = document.getElementById(fieldId(name));
      var norm = normalizeHHMM(el && el.value);
      if (!norm) return null;
      if (el) el.value = norm;
      out[name] = norm;
    }
    return out;
  }

  // Строгая проверка порядка на клиенте (сервер проверяет так же).
  function shiftOrderError(s) {
    var seq = [
      s.morning_start, s.morning_end,
      s.afternoon_start, s.afternoon_end,
      s.evening_start, s.evening_end
    ];
    for (var i = 1; i < seq.length; i++) {
      if (seq[i - 1] >= seq[i]) {
        return 'Часы смен должны идти строго по возрастанию: ' +
          'утро < день < вечер, начало < конец.';
      }
    }
    return null;
  }

  function openModal(center) {
    addForm.reset();
    hideError();
    attachTimeMasks();
    if (center) {
      editingId = center.id;
      modalTitle.textContent = 'Центр: ' + (center.name || '');
      document.getElementById('center-name').value = center.name || '';
      document.getElementById('center-city').value = center.city || '';
      document.getElementById('center-timezone').value = center.timezone || 'Europe/Moscow';
      setShiftInputs(center);
    } else {
      editingId = null;
      modalTitle.textContent = 'Добавить центр';
      setShiftInputs(DEFAULT_SHIFTS);
    }
    addModal.classList.add('visible');
  }

  document.getElementById('r-add-center-btn').addEventListener('click', function () {
    openModal(null);
  });

  document.getElementById('center-cancel').addEventListener('click', function () {
    addModal.classList.remove('visible');
  });

  addForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    hideError();

    var shifts = readShiftInputs();
    if (!shifts) {
      showError('Заполните все шесть значений часов смен.');
      return;
    }
    var orderErr = shiftOrderError(shifts);
    if (orderErr) {
      showError(orderErr);
      return;
    }

    var submitBtn = document.getElementById('center-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Сохранение...';

    var payload = {
      name: document.getElementById('center-name').value.trim(),
      city: document.getElementById('center-city').value.trim() || null,
      timezone: document.getElementById('center-timezone').value,
      shift_times: shifts
    };
    var url = editingId ? '/api/v1/centers/' + encodeURIComponent(editingId) : '/api/v1/centers';
    var method = editingId ? 'PATCH' : 'POST';

    try {
      var resp = await fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload)
      });
      var data = await resp.json().catch(function () { return {}; });
      if (!resp.ok) {
        showError(typeof data.detail === 'string' ? data.detail : 'Ошибка сохранения центра');
        return;
      }
      addModal.classList.remove('visible');
      loadCenters();
    } catch (err) {
      showError('Ошибка соединения');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Сохранить';
    }
  });

  document.getElementById('r-logout-btn').addEventListener('click', function () {
    if (window.ResearcherAuth) window.ResearcherAuth.logout();
  });

  document.addEventListener('DOMContentLoaded', async function () {
    if (!window.ResearcherAuth) return;
    var researcher = await window.ResearcherAuth.requireAuth();
    var nameEl = document.getElementById('r-user-name');
    if (nameEl) nameEl.textContent = researcher.full_name || researcher.username;
    loadCenters();
  });
})();
