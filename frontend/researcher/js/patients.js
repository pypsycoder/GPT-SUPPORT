(function () {
  'use strict';

  // --- State ---
  var currentTab = 'dashboard';
  var patientsCache = [];

  // --- DOM refs ---
  var tabDashboard = document.getElementById('tab-dashboard');
  var tabPatients = document.getElementById('tab-patients');
  var patientsBody = document.getElementById('r-patients-tbody');
  var addModal = document.getElementById('modal-add-patient');
  var pinModal = document.getElementById('modal-pin-result');
  var addForm = document.getElementById('form-add-patient');
  var addResult = document.getElementById('add-result');

  // =========================================================================
  // Tabs
  // =========================================================================

  function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.r-nav-btn').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    tabDashboard.style.display = tab === 'dashboard' ? '' : 'none';
    tabPatients.style.display = tab === 'patients' ? '' : 'none';
    if (tab === 'patients') loadPatients();
  }

  document.querySelectorAll('.r-nav-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      switchTab(this.dataset.tab);
    });
  });

  // =========================================================================
  // Stats
  // =========================================================================

  async function loadStats() {
    try {
      var resp = await fetch('/api/v1/researcher/stats', {
        credentials: 'include',
      });
      if (!resp.ok) return;
      var data = await resp.json();
      document.getElementById('stat-total').textContent = data.total_patients;
      document.getElementById('stat-consented').textContent = data.consented_patients;
      document.getElementById('stat-locked').textContent = data.locked_patients;
    } catch (e) {
      console.warn('Failed to load stats', e);
    }
  }

  // =========================================================================
  // Patients list
  // =========================================================================

  function statusBadge(patient) {
    if (patient.is_locked) {
      return '<span class="r-badge r-badge-locked">Заблокирован</span>';
    }
    if (!patient.consent_personal_data) {
      return '<span class="r-badge r-badge-no-consent">Нет согласия</span>';
    }
    return '<span class="r-badge r-badge-active">Активен</span>';
  }

  function renderPatients(patients) {
    if (!patients || patients.length === 0) {
      patientsBody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#9ca3af;padding:2rem;">Нет пациентов</td></tr>';
      return;
    }

    patientsBody.innerHTML = patients.map(function (p) {
      var actions = '';
      actions += '<button class="r-action-btn" onclick="window._openScheduleModal(' + p.id + ', \'' + (p.full_name || '').replace(/'/g, "\\'") + '\')">Расписание диализа</button>';
      if (p.is_locked) {
        actions += '<button class="r-action-btn" onclick="window._unlockPatient(' + p.id + ')">Разблокировать</button>';
      }
      actions += '<button class="r-action-btn" onclick="window._resetPin(' + p.id + ')">Сбросить PIN</button>';
      return '<tr>' +
        '<td><strong>' + (p.patient_number || '—') + '</strong></td>' +
        '<td>' + (p.full_name || '—') + '</td>' +
        '<td>' + (p.age || '—') + '</td>' +
        '<td>' + (p.gender || '—') + '</td>' +
        '<td>' + statusBadge(p) + '</td>' +
        '<td>' + actions + '</td>' +
        '</tr>';
    }).join('');
  }

  async function loadPatients() {
    try {
      var resp = await fetch('/api/v1/researcher/patients', {
        credentials: 'include',
      });
      if (!resp.ok) return;
      patientsCache = await resp.json();
      renderPatients(patientsCache);
    } catch (e) {
      console.warn('Failed to load patients', e);
    }
  }

  // =========================================================================
  // Add patient
  // =========================================================================

  document.getElementById('r-add-patient-btn').addEventListener('click', function () {
    addForm.style.display = '';
    addResult.style.display = 'none';
    addForm.reset();
    addModal.classList.add('visible');
  });

  document.getElementById('add-cancel').addEventListener('click', function () {
    addModal.classList.remove('visible');
  });

  addForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    var submitBtn = document.getElementById('add-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Создание...';

    try {
      var resp = await fetch('/api/v1/researcher/patients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          full_name: document.getElementById('add-fullname').value.trim(),
          age: parseInt(document.getElementById('add-age').value) || null,
          gender: document.getElementById('add-gender').value || null,
        }),
      });

      if (!resp.ok) {
        alert('Ошибка создания пациента');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Создать';
        return;
      }

      var data = await resp.json();

      // Show result
      addForm.style.display = 'none';
      addResult.style.display = '';
      document.getElementById('result-number').textContent = data.patient_number;
      document.getElementById('result-pin').textContent = data.pin;

      // Refresh data
      loadStats();
      loadPatients();
    } catch (err) {
      alert('Ошибка соединения');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Создать';
    }
  });

  document.getElementById('result-close').addEventListener('click', function () {
    addModal.classList.remove('visible');
  });

  document.getElementById('result-print').addEventListener('click', function () {
    var number = document.getElementById('result-number').textContent;
    var pin = document.getElementById('result-pin').textContent;
    printCard(number, pin);
  });

  // =========================================================================
  // Reset PIN
  // =========================================================================

  window._resetPin = async function (patientId) {
    if (!confirm('Сбросить PIN-код для этого пациента?')) return;

    try {
      var resp = await fetch('/api/v1/researcher/patients/' + patientId + '/reset-pin', {
        method: 'POST',
        credentials: 'include',
      });
      if (!resp.ok) {
        alert('Ошибка сброса PIN');
        return;
      }
      var data = await resp.json();
      document.getElementById('reset-number').textContent = data.patient_number;
      document.getElementById('reset-pin').textContent = data.new_pin;
      pinModal.classList.add('visible');
      loadPatients();
    } catch (e) {
      alert('Ошибка соединения');
    }
  };

  document.getElementById('reset-close').addEventListener('click', function () {
    pinModal.classList.remove('visible');
  });

  document.getElementById('reset-print').addEventListener('click', function () {
    var number = document.getElementById('reset-number').textContent;
    var pin = document.getElementById('reset-pin').textContent;
    printCard(number, pin);
  });

  // =========================================================================
  // Dialysis schedule modal
  // =========================================================================

  var scheduleModal = document.getElementById('modal-schedule');
  var scheduleFormModal = document.getElementById('modal-schedule-form');
  var currentSchedulePatientId = null;
  var currentActiveSchedule = null;
  var scheduleList = [];

  var WEEKDAY_NAMES = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

  function shiftLabel(s) {
    if (s === 'morning') return 'Утренняя смена';
    if (s === 'afternoon') return 'Дневная смена';
    if (s === 'evening') return 'Вечерняя смена';
    return s;
  }

  function formatWeekdays(weekdays) {
    if (!weekdays || weekdays.length === 0) return '—';
    return weekdays.map(function (d) { return WEEKDAY_NAMES[d - 1] || d; }).join(' / ');
  }

  function formatDateStr(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    var day = ('0' + d.getDate()).slice(-2);
    var month = ('0' + (d.getMonth() + 1)).slice(-2);
    var year = d.getFullYear();
    return day + '.' + month + '.' + year;
  }

  function renderScheduleCurrent(active, patientName) {
    var content = document.getElementById('schedule-current-content');
    var editBtn = document.getElementById('schedule-edit-btn');
    var addBtn = document.getElementById('schedule-add-btn');
    if (active) {
      content.innerHTML = formatWeekdays(active.weekdays) + ' | ' + shiftLabel(active.shift) + ' | с ' + formatDateStr(active.valid_from) + ' | действует';
      editBtn.style.display = '';
      addBtn.style.display = 'none';
      currentActiveSchedule = active;
    } else {
      content.innerHTML = 'Расписание не задано';
      editBtn.style.display = 'none';
      addBtn.style.display = '';
      currentActiveSchedule = null;
    }
  }

  function renderScheduleHistory(list) {
    var el = document.getElementById('schedule-history-content');
    var closed = list.filter(function (s) { return s.valid_to != null; });
    if (closed.length === 0) {
      el.innerHTML = '<p style="color:#9ca3af;font-size:0.9rem;">Нет записей в истории</p>';
      return;
    }
    var rows = closed.map(function (s) {
      var period = formatDateStr(s.valid_from) + ' – ' + formatDateStr(s.valid_to);
      var closedInfo = s.closed_at ? ' Закрыто: ' + formatDateStr(s.closed_at) : '';
      var reason = s.change_reason ? ' | Причина: ' + s.change_reason : '';
      return '<tr><td>' + formatWeekdays(s.weekdays) + '</td><td>' + shiftLabel(s.shift) + '</td><td>' + period + '</td><td>' + closedInfo + reason + '</td></tr>';
    });
    el.innerHTML = '<table class="r-schedule-history-table"><thead><tr><th>Дни</th><th>Смена</th><th>Период</th><th>Закрытие</th></tr></thead><tbody>' + rows.join('') + '</tbody></table>';
  }

  window._openScheduleModal = async function (patientId, patientName) {
    currentSchedulePatientId = patientId;
    currentActiveSchedule = null;
    document.getElementById('schedule-modal-title').textContent = 'Расписание диализа — ' + (patientName || 'Пациент #' + patientId);
    scheduleModal.classList.add('visible');
    document.getElementById('schedule-current-content').textContent = 'Загрузка...';
    document.getElementById('schedule-history-content').innerHTML = '';
    try {
      var resp = await fetch('/api/v1/patients/' + patientId + '/schedules', { credentials: 'include' });
      if (!resp.ok) {
        document.getElementById('schedule-current-content').textContent = 'Ошибка загрузки';
        return;
      }
      scheduleList = await resp.json();
      var active = scheduleList.find(function (s) { return s.valid_to == null; });
      renderScheduleCurrent(active, patientName);
      renderScheduleHistory(scheduleList);
    } catch (e) {
      document.getElementById('schedule-current-content').textContent = 'Ошибка соединения';
    }
  };

  document.getElementById('schedule-modal-close').addEventListener('click', function () {
    scheduleModal.classList.remove('visible');
  });

  document.getElementById('schedule-edit-btn').addEventListener('click', function () {
    document.getElementById('schedule-form-title').textContent = 'Изменить расписание';
    var tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    document.getElementById('schedule-valid-from').min = tomorrow.toISOString().slice(0, 10);
    document.getElementById('schedule-valid-from').value = '';
    document.getElementById('schedule-reason').value = '';
    document.querySelectorAll('#form-schedule input[name=wd]').forEach(function (cb) { cb.checked = false; });
    scheduleFormModal.classList.add('visible');
  });

  document.getElementById('schedule-add-btn').addEventListener('click', function () {
    document.getElementById('schedule-form-title').textContent = 'Добавить расписание';
    document.getElementById('schedule-valid-from').removeAttribute('min');
    document.getElementById('schedule-valid-from').value = '';
    document.getElementById('schedule-reason').value = '';
    document.querySelectorAll('#form-schedule input[name=wd]').forEach(function (cb) { cb.checked = false; });
    scheduleFormModal.classList.add('visible');
  });

  document.getElementById('schedule-form-cancel').addEventListener('click', function () {
    scheduleFormModal.classList.remove('visible');
  });

  document.getElementById('form-schedule').addEventListener('submit', async function (e) {
    e.preventDefault();
    var wd = [];
    document.querySelectorAll('#form-schedule input[name=wd]:checked').forEach(function (cb) {
      wd.push(parseInt(cb.value, 10));
    });
    if (wd.length === 0) {
      alert('Выберите хотя бы один день недели');
      return;
    }
    var shift = document.getElementById('schedule-shift').value;
    var validFrom = document.getElementById('schedule-valid-from').value;
    var reason = document.getElementById('schedule-reason').value.trim() || null;
    var patientId = currentSchedulePatientId;
    var body = { weekdays: wd, shift: shift, valid_from: validFrom, change_reason: reason };

    if (currentActiveSchedule) {
      var msg = 'Текущее расписание (' + formatWeekdays(currentActiveSchedule.weekdays) + ', ' + shiftLabel(currentActiveSchedule.shift).toLowerCase() + ') будет закрыто до ' + validFrom + '. Продолжить?';
      if (!confirm(msg)) return;
      var submitBtn = document.getElementById('schedule-form-submit');
      submitBtn.disabled = true;
      try {
        var resp = await fetch('/api/v1/schedules/' + currentActiveSchedule.id + '/close-and-replace', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          var err = await resp.json().catch(function () { return {}; });
          alert(err.detail && err.detail.message ? err.detail.message : 'Ошибка изменения расписания');
          return;
        }
        scheduleFormModal.classList.remove('visible');
        var data = await fetch('/api/v1/patients/' + patientId + '/schedules', { credentials: 'include' }).then(function (r) { return r.json(); });
        scheduleList = data;
        var active = scheduleList.find(function (s) { return s.valid_to == null; });
        renderScheduleCurrent(active, null);
        renderScheduleHistory(scheduleList);
      } catch (err) {
        alert('Ошибка соединения');
      } finally {
        submitBtn.disabled = false;
      }
    } else {
      var submitBtn = document.getElementById('schedule-form-submit');
      submitBtn.disabled = true;
      try {
        var resp = await fetch('/api/v1/patients/' + patientId + '/schedules', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          var err = await resp.json().catch(function () { return {}; });
          alert(err.detail && (err.detail.message || err.detail) || 'Ошибка создания расписания');
          return;
        }
        scheduleFormModal.classList.remove('visible');
        var data = await fetch('/api/v1/patients/' + patientId + '/schedules', { credentials: 'include' }).then(function (r) { return r.json(); });
        scheduleList = data;
        var active = scheduleList.find(function (s) { return s.valid_to == null; });
        renderScheduleCurrent(active, null);
        renderScheduleHistory(scheduleList);
      } catch (err) {
        alert('Ошибка соединения');
      } finally {
        submitBtn.disabled = false;
      }
    }
  });

  // =========================================================================
  // Unlock
  // =========================================================================

  window._unlockPatient = async function (patientId) {
    if (!confirm('Разблокировать этого пациента?')) return;

    try {
      var resp = await fetch('/api/v1/researcher/patients/' + patientId + '/unlock', {
        method: 'POST',
        credentials: 'include',
      });
      if (!resp.ok) {
        alert('Ошибка разблокировки');
        return;
      }
      loadPatients();
      loadStats();
    } catch (e) {
      alert('Ошибка соединения');
    }
  };

  // =========================================================================
  // Print card
  // =========================================================================

  function printCard(number, pin) {
    var printArea = document.getElementById('print-area');
    document.getElementById('print-number').textContent = number;
    document.getElementById('print-pin').textContent = pin;
    document.getElementById('print-url').textContent = window.location.origin;

    printArea.style.display = '';
    window.print();
    printArea.style.display = 'none';
  }

  // =========================================================================
  // Logout
  // =========================================================================

  document.getElementById('r-logout-btn').addEventListener('click', function () {
    if (window.ResearcherAuth) {
      window.ResearcherAuth.logout();
    }
  });

  // =========================================================================
  // Init
  // =========================================================================

  document.addEventListener('DOMContentLoaded', async function () {
    if (!window.ResearcherAuth) return;

    var researcher = await window.ResearcherAuth.requireAuth();
    var nameEl = document.getElementById('r-user-name');
    if (nameEl) {
      nameEl.textContent = researcher.full_name || researcher.username;
    }

    loadStats();
  });
})();
