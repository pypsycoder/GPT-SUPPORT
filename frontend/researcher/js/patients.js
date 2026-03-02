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

  document.querySelectorAll('.r-nav-btn[data-tab]').forEach(function (btn) {
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

      var u = data.usage;
      if (u) {
        if (u.vitals) {
          document.getElementById('usage-vitals-bp').textContent = u.vitals.bp_measurements ?? '—';
          document.getElementById('usage-vitals-pulse').textContent = u.vitals.pulse_measurements ?? '—';
          document.getElementById('usage-vitals-weight').textContent = u.vitals.weight_measurements ?? '—';
          document.getElementById('usage-vitals-water').textContent = u.vitals.water_intake ?? '—';
          document.getElementById('usage-vitals-users').textContent = u.vitals.unique_patients ?? '—';
        }
        if (u.scales) {
          var scaleNames = { 'HADS': 'HADS', 'KOP25A': 'КОП-25 А1', 'KOP_25A1': 'КОП-25 А1', 'PSQI': 'PSQI' };
          var byScale = u.scales.by_scale || [];
          var container = document.getElementById('usage-scales-by-scale');
          container.innerHTML = byScale.length ? byScale.map(function (s) {
            var name = scaleNames[s.scale_code] || s.scale_code;
            return '<div class="r-usage-row"><span>' + name + '</span><span>' + s.records + ' пр. / ' + s.unique_patients + ' пац.</span></div>';
          }).join('') : '<div class="r-usage-row"><span>—</span><span>Нет данных</span></div>';
          document.getElementById('usage-scales-users').textContent = u.scales.unique_patients ?? '—';
        }
        if (u.education) {
          document.getElementById('usage-edu-progress').textContent = u.education.lesson_progress ?? '—';
          document.getElementById('usage-edu-tests').textContent = u.education.test_results ?? '—';
          document.getElementById('usage-edu-practices').textContent = u.education.practice_logs ?? '—';
          document.getElementById('usage-edu-users').textContent = u.education.unique_patients ?? '—';
        }
        if (u.sleep) {
          document.getElementById('usage-sleep-records').textContent = u.sleep.records ?? '—';
          document.getElementById('usage-sleep-users').textContent = u.sleep.unique_patients ?? '—';
        }
        if (u.routine) {
          document.getElementById('usage-routine-baselines').textContent = u.routine.baselines ?? '—';
          document.getElementById('usage-routine-plans').textContent = u.routine.plans ?? '—';
          document.getElementById('usage-routine-verifications').textContent = u.routine.verifications ?? '—';
          document.getElementById('usage-routine-users').textContent = u.routine.unique_patients ?? '—';
        }
      }
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

  function centerDisplay(p) {
    if (p.center_name) {
      return (p.center_city ? p.center_name + ' (' + p.center_city + ')' : p.center_name);
    }
    return '—';
  }

  function scheduleDisplay(p) {
    if (!p.active_schedule_days || p.active_schedule_days.length === 0) {
      return '<span style="color:#9ca3af">—</span>';
    }
    var WD = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    var days = p.active_schedule_days.map(function (d) { return WD[d - 1] || d; }).join('/');
    var shift = p.active_schedule_shift === 'morning' ? 'Утро'
              : p.active_schedule_shift === 'afternoon' ? 'День'
              : p.active_schedule_shift === 'evening' ? 'Вечер' : '';
    return '<span class="r-schedule-cell">' + days + (shift ? ' · ' + shift : '') + '</span>';
  }

  function scaleMiniDisplay(p) {
    var points = p.kdqol_points || [];
    // Group by point_type (may contain multiple scales per point)
    var byType = { T0: [], T1: [], T2: [] };
    points.forEach(function (pt) {
      if (byType[pt.point_type]) byType[pt.point_type].push(pt);
    });
    var badges = ['T0', 'T1', 'T2'].map(function (type) {
      var pts = byType[type];
      var cls;
      if (pts.length === 0) {
        cls = 'r-kdqol-mini-badge-none';
      } else if (pts.every(function (pt) { return pt.is_completed; })) {
        cls = 'r-kdqol-mini-badge-done';
      } else {
        cls = 'r-kdqol-mini-badge-pending';
      }
      return '<span class="r-kdqol-mini-badge ' + cls + '">' + type + '</span>';
    }).join('');
    return '<span class="r-kdqol-mini">' + badges + '</span>';
  }

  function cohortDisplay(p) {
    if (!p.active_schedule_days || p.active_schedule_days.length === 0 || !p.center_name) {
      return '<span style="color:#9ca3af">—</span>';
    }
    var WD = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    var shift = p.active_schedule_shift === 'morning' ? 'Утро'
              : p.active_schedule_shift === 'afternoon' ? 'День'
              : p.active_schedule_shift === 'evening' ? 'Вечер' : '';
    var days = p.active_schedule_days.map(function (d) { return WD[d - 1] || d; }).join('-');
    var city = p.center_city || p.center_name;
    return '<span class="r-cohort-cell" title="' + p.center_name + '">' + city + '&nbsp;/&nbsp;' + shift + '&nbsp;/&nbsp;' + days + '</span>';
  }

  function renderPatients(patients) {
    if (!patients || patients.length === 0) {
      patientsBody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:#9ca3af;padding:2rem;">Нет пациентов</td></tr>';
      return;
    }

    patientsBody.innerHTML = patients.map(function (p) {
      var name = (p.full_name || '').replace(/'/g, "\\'");
      var centerId = (p.center_id || '').replace(/'/g, "\\'");
      var dropdown =
        '<div class="r-actions-menu" id="am-' + p.id + '">' +
          '<button class="r-actions-trigger" onclick="window._toggleActionsMenu(event,' + p.id + ')">&#8942;</button>' +
          '<div class="r-actions-dropdown">' +
            '<button onclick="window._closeAllActionsMenus();window._openAssignCenterModal(' + p.id + ',\'' + name + '\',\'' + centerId + '\')">Центр диализа</button>' +
            '<button onclick="window._closeAllActionsMenus();window._openScheduleModal(' + p.id + ',\'' + name + '\')">Расписание диализа</button>' +
            '<button onclick="window._closeAllActionsMenus();window._openKdqolModal(' + p.id + ',\'' + name + '\')">T0-T1-T2</button>' +
            '<div class="r-dropdown-divider"></div>' +
            '<button onclick="window._closeAllActionsMenus();window._resetPin(' + p.id + ')">Сбросить PIN</button>' +
            (p.is_locked
              ? '<button class="danger" onclick="window._closeAllActionsMenus();window._unlockPatient(' + p.id + ')">Разблокировать</button>'
              : '') +
          '</div>' +
        '</div>';

      return '<tr>' +
        '<td><strong>' + (p.patient_number || '—') + '</strong></td>' +
        '<td>' + (p.full_name || '—') + '</td>' +
        '<td>' + (p.age || '—') + '</td>' +
        '<td>' + (p.gender || '—') + '</td>' +
        '<td>' + centerDisplay(p) + '</td>' +
        '<td>' + scheduleDisplay(p) + '</td>' +
        '<td>' + scaleMiniDisplay(p) + '</td>' +
        '<td>' + cohortDisplay(p) + '</td>' +
        '<td>' + statusBadge(p) + '</td>' +
        '<td style="text-align:right;">' + dropdown + '</td>' +
        '</tr>';
    }).join('');
  }

  window._closeAllActionsMenus = function () {
    document.querySelectorAll('.r-actions-menu.open').forEach(function (el) {
      el.classList.remove('open');
    });
  };

  window._toggleActionsMenu = function (event, patientId) {
    event.stopPropagation();
    var menu = document.getElementById('am-' + patientId);
    var isOpen = menu.classList.contains('open');
    window._closeAllActionsMenus();
    if (!isOpen) {
      menu.classList.add('open');
    }
  };

  document.addEventListener('click', function () {
    window._closeAllActionsMenus();
  });

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
  // Assign dialysis center modal
  // =========================================================================

  var assignCenterModal = document.getElementById('modal-assign-center');
  var assignCenterForm = document.getElementById('form-assign-center');
  var assignCenterSelect = document.getElementById('assign-center-select');
  var assignCenterPatientId = null;

  window._openAssignCenterModal = async function (patientId, patientName, currentCenterId) {
    assignCenterPatientId = patientId;
    document.getElementById('assign-center-modal-title').textContent = 'Центр диализа — ' + (patientName || 'Пациент #' + patientId);
    assignCenterSelect.innerHTML = '<option value="">— Не назначен —</option>';
    assignCenterModal.classList.add('visible');

    try {
      var resp = await fetch('/api/v1/centers', { credentials: 'include' });
      if (!resp.ok) return;
      var centers = await resp.json();
      centers.forEach(function (c) {
        var opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.city ? c.name + ' (' + c.city + ')' : c.name;
        assignCenterSelect.appendChild(opt);
      });
      assignCenterSelect.value = currentCenterId || '';
    } catch (e) {
      console.warn('Failed to load centers', e);
    }
  };

  document.getElementById('assign-center-cancel').addEventListener('click', function () {
    assignCenterModal.classList.remove('visible');
  });

  assignCenterForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    var patientId = assignCenterPatientId;
    if (!patientId) return;
    var centerId = assignCenterSelect.value.trim() || null;
    var submitBtn = document.getElementById('assign-center-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Сохранение...';
    try {
      var resp = await fetch('/api/v1/researcher/patients/' + patientId + '/center', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ center_id: centerId }),
      });
      if (!resp.ok) {
        var err = await resp.json().catch(function () { return {}; });
        var msg = typeof err.detail === 'string' ? err.detail : (err.detail && (err.detail.detail || err.detail.message || err.detail.msg)) || 'Ошибка сохранения';
        alert(msg);
        return;
      }
      assignCenterModal.classList.remove('visible');
      loadPatients();
    } catch (err) {
      alert('Ошибка соединения');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Сохранить';
    }
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
        loadPatients();
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
        loadPatients();
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
  // KDQOL measurement points
  // =========================================================================

  var kdqolModal = document.getElementById('modal-kdqol');

  var POINT_LABELS = {
    T0: 'T0 — исходный',
    T1: 'T1 — 6 месяцев',
    T2: 'T2 — 12 месяцев',
  };

  var SCALE_LABELS = {
    KDQOL_SF:    'KDQOL-SF 1.3',
    WCQ_LAZARUS: 'Опросник Лазаруса',
    KOP_25A:     'КОП-25 А1',
  };

  var ALL_SCALES = ['KDQOL_SF', 'WCQ_LAZARUS', 'KOP_25A'];

  var _scalesCurrentPatientId = null;

  window._openKdqolModal = async function (patientId, patientName) {
    _scalesCurrentPatientId = patientId;
    document.getElementById('kdqol-modal-title').textContent = 'Точки измерения — ' + (patientName || 'Пациент #' + patientId);
    kdqolModal.classList.add('visible');
    await loadScalePoints(patientId);
  };

  async function loadScalePoints(patientId) {
    var container = document.getElementById('kdqol-points-list');
    container.innerHTML = '<div style="text-align:center;color:#9ca3af;padding:1rem;">Загрузка...</div>';
    try {
      var resp = await fetch('/api/v1/researcher/patients/' + patientId + '/measurement-points', {
        credentials: 'include',
      });
      if (!resp.ok) {
        container.innerHTML = '<div style="color:#dc2626;padding:0.5rem;">Ошибка загрузки данных</div>';
        return;
      }
      var points = await resp.json();
      renderScalePoints(points, patientId);
    } catch (e) {
      container.innerHTML = '<div style="color:#dc2626;padding:0.5rem;">Ошибка соединения</div>';
    }
  }

  function renderScalePoints(points, patientId) {
    var container = document.getElementById('kdqol-points-list');

    // Группируем: byPoint[T0][KDQOL_SF] = pointObj | null
    var byPoint = {};
    ['T0', 'T1', 'T2'].forEach(function (type) {
      byPoint[type] = {};
      ALL_SCALES.forEach(function (sc) { byPoint[type][sc] = null; });
    });
    points.forEach(function (pt) {
      if (byPoint[pt.point_type] !== undefined) {
        byPoint[pt.point_type][pt.scale_code] = pt;
      }
    });

    var html = ['T0', 'T1', 'T2'].map(function (type) {
      var scalesMap = byPoint[type];
      var nonActivated = ALL_SCALES.filter(function (sc) { return scalesMap[sc] === null; });

      var headerBtn = nonActivated.length > 0
        ? '<button class="r-kdqol-activate-btn" style="margin-left:auto;font-size:0.8rem;" onclick="window._activateAllScales(\'' + type + '\',' + patientId + ')">Активировать все</button>'
        : '';

      var header = '<div class="r-scales-point-header">' +
        '<span class="r-kdqol-row-label">' + POINT_LABELS[type] + '</span>' +
        headerBtn +
        '</div>';

      var scaleRows = ALL_SCALES.map(function (sc) {
        var pt = scalesMap[sc];
        var scaleName = SCALE_LABELS[sc] || sc;
        var statusHtml, btnHtml = '';

        if (!pt) {
          statusHtml = '<span class="r-kdqol-row-status r-kdqol-status-none">Не активирована</span>';
          btnHtml = '<button class="r-kdqol-activate-btn" onclick="window._activateScalePoint(\'' + type + '\',\'' + sc + '\',' + patientId + ')">Активировать</button>';
        } else if (pt.is_completed) {
          statusHtml = '<span class="r-kdqol-row-status r-kdqol-status-done">✓ Завершена ' + formatDateStr(pt.completed_at) + '</span>';
        } else {
          statusHtml = '<span class="r-kdqol-row-status r-kdqol-status-pending">⏳ Ожидает (с ' + formatDateStr(pt.activated_at) + ')</span>';
        }

        return '<div class="r-kdqol-scale-row">' +
          '<div class="r-kdqol-scale-name">' + scaleName + '</div>' +
          statusHtml + btnHtml +
          '</div>';
      }).join('');

      return '<div class="r-scales-point-section">' + header + scaleRows + '</div>';
    }).join('');

    container.innerHTML = html;
  }

  async function _doActivateScale(pointType, scaleCode, patientId) {
    var resp = await fetch('/api/v1/researcher/patients/' + patientId + '/measurement-points', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ point_type: pointType, scale_code: scaleCode }),
    });
    if (!resp.ok) {
      var err = await resp.json().catch(function () { return {}; });
      var msg = typeof err.detail === 'string' ? err.detail : 'Ошибка активации';
      alert(msg);
      return false;
    }
    return true;
  }

  window._activateScalePoint = async function (pointType, scaleCode, patientId) {
    var scaleLabel = SCALE_LABELS[scaleCode] || scaleCode;
    var pointLabel = POINT_LABELS[pointType] || pointType;
    if (!confirm('Активировать «' + scaleLabel + '» для точки «' + pointLabel + '»?')) return;
    document.querySelectorAll('.r-kdqol-activate-btn').forEach(function (b) { b.disabled = true; });
    await _doActivateScale(pointType, scaleCode, patientId);
    await loadScalePoints(patientId);
    loadPatients();
  };

  window._activateAllScales = async function (pointType, patientId) {
    var pointLabel = POINT_LABELS[pointType] || pointType;
    if (!confirm('Активировать все шкалы для точки «' + pointLabel + '»?')) return;
    document.querySelectorAll('.r-kdqol-activate-btn').forEach(function (b) { b.disabled = true; });

    try {
      var resp = await fetch('/api/v1/researcher/patients/' + patientId + '/measurement-points', {
        credentials: 'include',
      });
      var existing = resp.ok ? await resp.json() : [];
      var activatedScales = existing
        .filter(function (pt) { return pt.point_type === pointType; })
        .map(function (pt) { return pt.scale_code; });
      var toActivate = ALL_SCALES.filter(function (sc) { return activatedScales.indexOf(sc) === -1; });

      for (var i = 0; i < toActivate.length; i++) {
        await _doActivateScale(pointType, toActivate[i], patientId);
      }
    } catch (e) {
      alert('Ошибка соединения');
    }

    await loadScalePoints(patientId);
    loadPatients();
  };

  document.getElementById('kdqol-modal-close').addEventListener('click', function () {
    kdqolModal.classList.remove('visible');
  });

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
