/**
 * Модуль «Препараты» — medications.js
 * API: /api/patient/medications/prescriptions, /api/patient/medications/intakes
 */
(function () {
  'use strict';

  // ── 4.1 Константы и состояние ──────────────────────────────────────────────
  const API = {
    prescriptions: '/api/patient/medications/prescriptions',
    intakes:       '/api/patient/medications/intakes',
  };

  const state = {
    prescriptions:      [],
    currentPrescription: null,
  };

  const SLOTS = {
    morning:   { label: 'Утро',  icon: '\u2600' },
    afternoon: { label: 'День',  icon: '\u2601' },
    evening:   { label: 'Вечер', icon: '\uD83C\uDF19' },
  };

  const SLOT_DEFAULTS = {
    1: ['morning'],
    2: ['morning', 'evening'],
    3: ['morning', 'afternoon', 'evening'],
    4: ['morning', 'morning', 'afternoon', 'evening'],
    5: ['morning', 'morning', 'afternoon', 'evening', 'evening'],
    6: ['morning', 'morning', 'afternoon', 'afternoon', 'evening', 'evening'],
  };

  // ── 4.2 Инициализация ─────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', async () => {
    setupModalSystem();
    setupDatePickerButtons();
    setupEventListeners();
    setupFrequencyPicker();
    await loadPrescriptions();
  });

  // ── Календарь: input type="date" наложен на кнопку, клик открывает нативный выбор ─
  function setupDatePickerButtons() {
    document.querySelectorAll('.date-picker-native').forEach(function (nativeInput) {
      nativeInput.addEventListener('change', function () {
        var targetId = this.getAttribute('data-target');
        var target = targetId ? document.getElementById(targetId) : null;
        if (target && this.value) {
          var d = new Date(this.value + 'T12:00:00');
          if (!isNaN(d.getTime())) target.value = formatDateForInput(d);
        }
      });
      nativeInput.addEventListener('click', function () {
        try { if (typeof this.showPicker === 'function') this.showPicker(); } catch (e) { }
      });
    });
  }

  function syncDatePickerInput(textInputId) {
    var textEl = document.getElementById(textInputId);
    var nativeEl = document.querySelector('.date-picker-native[data-target="' + textInputId + '"]');
    if (!textEl || !nativeEl) return;
    var apiDate = parseDateToApi(textEl.value);
    if (!apiDate) {
      var t = new Date();
      apiDate = t.getFullYear() + '-' + String(t.getMonth() + 1).padStart(2, '0') + '-' + String(t.getDate()).padStart(2, '0');
    }
    nativeEl.value = apiDate;
  }

  // ── 4.3 Система модальных окон ────────────────────────────────────────────
  function setupModalSystem() {
    document.querySelectorAll('[data-close]').forEach(btn => {
      btn.addEventListener('click', () => closeModal(btn.dataset.close));
    });
    document.querySelectorAll('.modal-backdrop').forEach(bd => {
      bd.addEventListener('click', () => closeModal(bd.closest('.modal').id));
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        const open = document.querySelector('.modal.is-open');
        if (open) closeModal(open.id);
      }
    });
  }

  function openModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.add('is-open');
    modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
  }

  function closeModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.style.display = 'none';
    if (!document.querySelector('.modal.is-open')) {
      document.body.style.overflow = '';
    }
  }

  // ── 4.4 Frequency Picker ──────────────────────────────────────────────────
  function setupFrequencyPicker() {
    const picker = document.getElementById('frequencyPicker');
    if (!picker) return;
    [1, 2, 3, 4, 5, 6].forEach(n => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'freq-btn';
      btn.textContent = n;
      btn.dataset.value = n;
      btn.addEventListener('click', () => setFrequency(n));
      picker.appendChild(btn);
    });
  }

  function setFrequency(value) {
    document.getElementById('fieldFrequency').value = value;
    document.querySelectorAll('.freq-btn').forEach(btn => {
      btn.classList.toggle('active', parseInt(btn.dataset.value) === parseInt(value));
    });
    renderSchedulePicker(parseInt(value));
  }

  // ── 4.5 Schedule Picker ───────────────────────────────────────────────────
  function renderSchedulePicker(freq, selectedSlots) {
    const picker = document.getElementById('schedulePicker');
    if (!picker) return;
    picker.innerHTML = '';

    if (freq >= 4) {
      const defaults = SLOT_DEFAULTS[freq] || [];
      const counts = {};
      defaults.forEach(s => counts[s] = (counts[s] || 0) + 1);

      const info = document.createElement('div');
      info.className = 'schedule-info';
      info.innerHTML = Object.entries(counts)
        .map(([slot, count]) =>
          escapeHtml(SLOTS[slot].icon) + ' ' + escapeHtml(SLOTS[slot].label) +
          (count > 1 ? ' \u00d7' + count : ''))
        .join('&nbsp;&nbsp;');
      picker.appendChild(info);

      updateScheduleHidden(defaults);
      return;
    }

    const allSlots = ['morning', 'afternoon', 'evening'];
    const defaultSelected = selectedSlots || SLOT_DEFAULTS[freq] || [];

    allSlots.forEach(slot => {
      const isSelected = defaultSelected.includes(slot);

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'slot-btn' + (isSelected ? ' active' : '');
      btn.dataset.slot = slot;
      btn.innerHTML =
        '<span class="slot-icon">' + SLOTS[slot].icon + '</span>' +
        '<span class="slot-label">' + SLOTS[slot].label + '</span>';

      btn.addEventListener('click', () => {
        if (freq === 3) return;
        if (freq === 1) {
          picker.querySelectorAll('.slot-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
        } else {
          const active = picker.querySelectorAll('.slot-btn.active');
          if (btn.classList.contains('active')) {
            if (active.length > 1) btn.classList.remove('active');
          } else {
            if (active.length < freq) btn.classList.add('active');
          }
        }
        const selected = [...picker.querySelectorAll('.slot-btn.active')].map(b => b.dataset.slot);
        updateScheduleHidden(selected);
      });

      picker.appendChild(btn);
    });

    updateScheduleHidden(defaultSelected);
  }

  function updateScheduleHidden(slots) {
    const form = document.getElementById('formPrescription');
    if (form) form.dataset.schedule = JSON.stringify(slots);
  }

  function getSelectedSchedule() {
    const form = document.getElementById('formPrescription');
    try {
      return JSON.parse(form.dataset.schedule || '[]');
    } catch {
      return [];
    }
  }

  // ── 4.6 Загрузка и отрисовка назначений ───────────────────────────────────
  async function loadPrescriptions() {
    const container = document.getElementById('prescriptionsContainer');
    const loading   = document.getElementById('loadingState');
    const empty     = document.getElementById('emptyState');
    if (!container) return;

    loading.style.display = 'block';
    container.innerHTML   = '';
    empty.style.display   = 'none';

    try {
      state.prescriptions = await apiFetch(API.prescriptions + '?status=active');
      loading.style.display = 'none';

      if (state.prescriptions.length === 0) {
        empty.style.display = 'block';
        return;
      }
      state.prescriptions.forEach(p => container.appendChild(buildPrescriptionCard(p)));
    } catch (err) {
      loading.style.display = 'none';
      container.innerHTML =
        '<div class="error-state">' +
        'Не удалось загрузить препараты. ' +
        '<button class="btn-link" onclick="loadPrescriptions()">Повторить</button>' +
        '</div>';
    }
  }

  function buildPrescriptionCard(p) {
    const rate  = Math.round((p.adherence_rate || 0) * 100);
    const color = rate >= 80 ? '#4caf50' : rate >= 50 ? '#ff9800' : '#f44336';
    const isSelf = !p.prescribed_by;

    const scheduleHtml = (p.intake_schedule || [])
      .map(s => '<span class="slot-tag">' + (SLOTS[s] ? SLOTS[s].icon : '') + ' ' + (SLOTS[s] ? SLOTS[s].label : escapeHtml(s)) + '</span>')
      .join('');

    const card = document.createElement('div');
    card.className = 'prescription-card' + (isSelf ? ' self-prescribed' : '');
    card.dataset.id = p.id;

    card.innerHTML =
      '<div class="card-header">' +
        '<div class="card-title-block">' +
          '<h3 class="card-title">' + escapeHtml(p.medication_name) + '</h3>' +
          (isSelf ? '<span class="badge-self">Самостоятельно</span>' : '') +
        '</div>' +
        '<span class="adherence-badge" style="background:' + color + '">' + rate + '%</span>' +
      '</div>' +
      '<div class="card-body">' +
        '<div class="card-row"><span>Доза:</span><span>' + escapeHtml(String(p.dose)) + ' ' + escapeHtml(p.dose_unit) + '</span></div>' +
        '<div class="card-row"><span>Частота:</span><span>' + p.frequency_times_per_day + '\u00d7/день</span></div>' +
        '<div class="card-row"><span>Время:</span><span class="slots-row">' + scheduleHtml + '</span></div>' +
        '<div class="card-row"><span>Приём:</span><span>' + escapeHtml(p.route) + '</span></div>' +
        '<div class="card-row"><span>Период:</span><span>' + formatDate(p.start_date) + ' \u2014 ' + (p.end_date ? formatDate(p.end_date) : 'постоянно') + '</span></div>' +
      '</div>' +
      '<div class="card-footer">' +
        '<button type="button" class="btn-link card-details-btn" data-prescription-id="' + p.id + '">Подробнее \u2192</button>' +
      '</div>';

    card.addEventListener('click', function (e) {
      if (e.target.closest('.card-details-btn')) return;
      openAddIntake(p.id);
    });
    card.querySelector('.card-details-btn').addEventListener('click', function (e) {
      e.stopPropagation();
      openDetails(p.id);
    });

    return card;
  }

  // ── 4.7 Форма добавления / редактирования препарата ───────────────────────
  function openAddPrescription() {
    const modal = document.getElementById('modalAddPrescription');
    modal.dataset.mode = 'add';

    document.getElementById('formPrescription').reset();
    document.getElementById('prescriptionId').value = '';
    document.getElementById('prescriptionModalTitle').textContent = 'Добавить препарат';
    document.getElementById('btnSubmitPrescription').textContent = 'Добавить';
    document.getElementById('btnSubmitPrescription').disabled = false;
    document.getElementById('prescribedByWarning').style.display = 'none';

    document.getElementById('fieldStartDate').value = todayStr();
    document.getElementById('fieldEndDate').value   = '';
    syncDatePickerInput('fieldStartDate');
    syncDatePickerInput('fieldEndDate');

    enableFormFields('formPrescription', true);
    setFrequency(1);
    clearFormErrors('formPrescription');
    openModal('modalAddPrescription');
  }

  function openEditPrescription(prescription) {
    const modal = document.getElementById('modalAddPrescription');
    modal.dataset.mode = 'edit';

    document.getElementById('prescriptionId').value = prescription.id;
    document.getElementById('prescriptionModalTitle').textContent = 'Редактировать препарат';
    document.getElementById('btnSubmitPrescription').textContent  = 'Сохранить изменения';

    document.getElementById('fieldMedName').value      = prescription.medication_name;
    document.getElementById('fieldDose').value         = prescription.dose;
    document.getElementById('fieldDoseUnit').value     = prescription.dose_unit;
    document.getElementById('fieldRoute').value        = prescription.route;
    document.getElementById('fieldStartDate').value    = formatDate(prescription.start_date);
    document.getElementById('fieldEndDate').value      = prescription.end_date ? formatDate(prescription.end_date) : '';
    syncDatePickerInput('fieldStartDate');
    syncDatePickerInput('fieldEndDate');
    document.getElementById('fieldIndication').value   = prescription.indication || '';
    document.getElementById('fieldInstructions').value = prescription.instructions || '';

    setFrequency(prescription.frequency_times_per_day);
    renderSchedulePicker(prescription.frequency_times_per_day, prescription.intake_schedule || []);

    const isSelf = !prescription.prescribed_by;
    document.getElementById('prescribedByWarning').style.display = isSelf ? 'none' : 'block';
    document.getElementById('btnSubmitPrescription').disabled = !isSelf;
    enableFormFields('formPrescription', isSelf);

    clearFormErrors('formPrescription');
    openModal('modalAddPrescription');
  }

  function enableFormFields(formId, enable) {
    document.querySelectorAll('#' + formId + ' input:not([type=hidden]), #' + formId + ' select, #' + formId + ' textarea')
      .forEach(el => el.disabled = !enable);
    document.querySelectorAll('#' + formId + ' .freq-btn, #' + formId + ' .slot-btn')
      .forEach(btn => btn.disabled = !enable);
  }

  async function submitPrescription(e) {
    e.preventDefault();
    if (!validatePrescriptionForm()) return;

    const modal  = document.getElementById('modalAddPrescription');
    const isEdit = modal.dataset.mode === 'edit';
    const id     = document.getElementById('prescriptionId').value;
    const btn    = document.getElementById('btnSubmitPrescription');

    const schedule = getSelectedSchedule();

    const payload = {
      medication_name:         document.getElementById('fieldMedName').value.trim(),
      dose:                    parseFloat(document.getElementById('fieldDose').value),
      dose_unit:               document.getElementById('fieldDoseUnit').value,
      frequency_times_per_day: parseInt(document.getElementById('fieldFrequency').value),
      intake_schedule:         schedule,
      route:                   document.getElementById('fieldRoute').value,
      start_date:              parseDateToApi(document.getElementById('fieldStartDate').value),
      end_date:                parseDateToApi(document.getElementById('fieldEndDate').value) || null,
      indication:              document.getElementById('fieldIndication').value.trim() || null,
      instructions:            document.getElementById('fieldInstructions').value.trim() || null,
      status:                  'active',
      prescribed_by:           null,
    };

    btn.disabled    = true;
    btn.textContent = 'Сохранение...';

    try {
      if (isEdit) {
        await apiFetch(API.prescriptions + '/' + id, 'PUT', payload);
        showToast('Препарат обновлён', 'success');
      } else {
        await apiFetch(API.prescriptions, 'POST', payload);
        showToast('Препарат добавлен', 'success');
      }
      closeModal('modalAddPrescription');
      await loadPrescriptions();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      btn.disabled    = false;
      btn.textContent = isEdit ? 'Сохранить изменения' : 'Добавить';
    }
  }

  // ── 4.8 Валидация формы препарата ─────────────────────────────────────────
  function validatePrescriptionForm() {
    clearFormErrors('formPrescription');
    let valid = true;

    const name = document.getElementById('fieldMedName').value.trim();
    if (!name) { setFieldError('errorMedName', 'Введите название препарата'); valid = false; }

    const dose = parseFloat(document.getElementById('fieldDose').value);
    if (isNaN(dose) || dose <= 0) { setFieldError('errorDose', 'Введите дозу больше 0'); valid = false; }

    const freq = parseInt(document.getElementById('fieldFrequency').value);
    if (!freq || freq < 1 || freq > 6) { setFieldError('errorFrequency', 'Выберите частоту приёма'); valid = false; }

    const schedule = getSelectedSchedule();
    if (!freq || schedule.length !== freq) {
      setFieldError('errorSchedule', 'Выберите ' + freq + ' слот(а) приёма');
      valid = false;
    }

    const route = document.getElementById('fieldRoute').value;
    if (!route) { setFieldError('errorRoute', 'Выберите способ приёма'); valid = false; }

    const startStr = document.getElementById('fieldStartDate').value;
    if (!startStr) { setFieldError('errorStartDate', 'Укажите дату начала (дд-мм-гг)'); valid = false; }
    const startApi = parseDateToApi(startStr);
    if (startStr && !startApi) { setFieldError('errorStartDate', 'Неверный формат даты (дд-мм-гг)'); valid = false; }

    const endStr = document.getElementById('fieldEndDate').value;
    if (endStr) {
      const endApi = parseDateToApi(endStr);
      if (!endApi) { setFieldError('errorEndDate', 'Неверный формат даты (дд-мм-гг)'); valid = false; }
      else if (startApi && endApi < startApi) {
        setFieldError('errorEndDate', 'Дата окончания не может быть раньше начала');
        valid = false;
      }
    }

    return valid;
  }

  function setFieldError(id, msg) {
    const el = document.getElementById(id);
    if (el) { el.textContent = msg; el.style.display = 'block'; }
  }

  function clearFormErrors(formId) {
    document.querySelectorAll('#' + formId + ' .form-error').forEach(el => {
      el.textContent = '';
      el.style.display = 'none';
    });
  }

  // ── 4.9 Форма отметки приёма ──────────────────────────────────────────────
  function openAddIntake(prescriptionId) {
    const select = document.getElementById('intakeSelectPrescription');
    select.innerHTML = '<option value="">— выберите препарат —</option>';
    state.prescriptions.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.medication_name + ' (' + p.dose + ' ' + p.dose_unit + ')';
      opt.dataset.dose = p.dose;
      opt.dataset.unit = p.dose_unit;
      opt.dataset.schedule = JSON.stringify(p.intake_schedule || []);
      select.appendChild(opt);
    });

    const now = new Date();
    document.getElementById('intakeDate').value = formatDateForInput(now);
    syncDatePickerInput('intakeDate');
    setTime24('intakeTimeH', 'intakeTimeM', formatTimeForInput(now));

    document.getElementById('slotGroup').style.display = 'none';
    document.getElementById('intakeSlot').value         = '';
    document.getElementById('intakeActualDose').value   = '';
    document.getElementById('intakeDoseUnit').textContent = '\u2014';
    document.getElementById('intakePrescribedHint').textContent = 'Назначено: \u2014';
    document.getElementById('intakeDoseWarning').style.display = 'none';
    document.getElementById('intakeNotes').value = '';
    document.getElementById('intakeNotesCount').textContent = '0';

    if (prescriptionId) {
      select.value = String(prescriptionId);
      handleIntakePrescriptionChange(prescriptionId);
    }

    clearFormErrors('formAddIntake');
    openModal('modalAddIntake');
  }

  function handleIntakePrescriptionChange(prescriptionId) {
    const select  = document.getElementById('intakeSelectPrescription');
    const opt     = select.querySelector('option[value="' + prescriptionId + '"]');
    const slotGrp = document.getElementById('slotGroup');

    if (!opt || !prescriptionId) {
      slotGrp.style.display = 'none';
      document.getElementById('intakeActualDose').value = '';
      document.getElementById('intakeDoseUnit').textContent = '\u2014';
      document.getElementById('intakePrescribedHint').textContent = 'Назначено: \u2014';
      return;
    }

    const dose     = parseFloat(opt.dataset.dose);
    const unit     = opt.dataset.unit;
    const schedule = JSON.parse(opt.dataset.schedule || '[]');

    document.getElementById('intakeActualDose').value     = dose;
    document.getElementById('intakeDoseUnit').textContent = unit;
    document.getElementById('intakePrescribedHint').textContent = 'Назначено: ' + dose + ' ' + unit;
    document.getElementById('intakeDoseWarning').style.display = 'none';

    renderIntakeSlotPicker(schedule);
    slotGrp.style.display = schedule.length > 0 ? 'block' : 'none';
  }

  function renderIntakeSlotPicker(schedule) {
    const picker = document.getElementById('intakeSlotPicker');
    picker.innerHTML = '';
    document.getElementById('intakeSlot').value = '';

    const counts = {};
    schedule.forEach(s => counts[s] = (counts[s] || 0) + 1);

    Object.entries(counts).forEach(([slot, count]) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'slot-btn';
      btn.dataset.slot = slot;
      btn.innerHTML =
        '<span class="slot-icon">' + (SLOTS[slot] ? SLOTS[slot].icon : '') + '</span>' +
        '<span class="slot-label">' + (SLOTS[slot] ? SLOTS[slot].label : escapeHtml(slot)) + (count > 1 ? ' \u00d7' + count : '') + '</span>';
      btn.addEventListener('click', () => {
        picker.querySelectorAll('.slot-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('intakeSlot').value = slot;
      });
      picker.appendChild(btn);
    });
  }

  function validateIntakeDose() {
    const select  = document.getElementById('intakeSelectPrescription');
    const opt     = select.options[select.selectedIndex];
    const actual  = parseFloat(document.getElementById('intakeActualDose').value);
    const warning = document.getElementById('intakeDoseWarning');

    if (!opt || !opt.dataset.dose || isNaN(actual)) { warning.style.display = 'none'; return; }

    const prescribed = parseFloat(opt.dataset.dose);
    const dev = Math.abs(actual - prescribed) / prescribed;
    warning.style.display = dev > 0.5 ? 'flex' : 'none';
  }

  async function submitAddIntake(e) {
    e.preventDefault();
    clearFormErrors('formAddIntake');

    const prescriptionId = parseInt(document.getElementById('intakeSelectPrescription').value);
    const dateStr = document.getElementById('intakeDate').value;
    const date  = parseDateToApi(dateStr);
    const time  = getTime24('intakeTimeH', 'intakeTimeM');
    const dose  = parseFloat(document.getElementById('intakeActualDose').value);
    const slot  = document.getElementById('intakeSlot').value || null;
    const notes = document.getElementById('intakeNotes').value.trim();

    if (!prescriptionId) { setFieldError('errorIntakePrescription', 'Выберите препарат'); return; }
    if (!date) { setFieldError('errorIntakeDate', 'Укажите дату в формате дд-мм-гг'); return; }
    if (!time) { setFieldError('errorIntakeTime', 'Укажите время (часы 0–23, минуты 0–59)'); return; }
    var todayApi = parseDateToApi(formatDateForInput(new Date()));
    var yesterdayApi = parseDateToApi(formatDateForInput(new Date(Date.now() - 24 * 60 * 60 * 1000)));
    if (date > todayApi || date < yesterdayApi) {
      setFieldError('errorIntakeDate', 'Можно отметить приём только за сегодня или вчера');
      return;
    }
    if (isNaN(dose) || dose <= 0) { setFieldError('errorIntakeDose', 'Введите корректную дозу'); return; }

    const btn = document.getElementById('btnSubmitIntake');
    btn.disabled    = true;
    btn.textContent = 'Сохранение...';

    try {
      await apiFetch(API.intakes, 'POST', {
        prescription_id: prescriptionId,
        intake_datetime: new Date(date + 'T' + time + ':00').toISOString(),
        actual_dose:     dose,
        intake_slot:     slot,
        notes:           notes || null,
      });
      showToast('Приём отмечен', 'success');
      closeModal('modalAddIntake');
      await loadPrescriptions();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      btn.disabled    = false;
      btn.textContent = 'Сохранить приём';
    }
  }

  // ── 4.10 Детали назначения ────────────────────────────────────────────────
  async function openDetails(prescriptionId) {
    const p = state.prescriptions.find(x => x.id === prescriptionId)
      || await apiFetch(API.prescriptions + '/' + prescriptionId);
    state.currentPrescription = p;

    document.getElementById('detailsTitle').textContent = p.medication_name;

    const isSelf = !p.prescribed_by;
    document.getElementById('btnEditPrescription').style.display   = isSelf ? '' : 'none';
    document.getElementById('btnDeletePrescription').style.display = isSelf ? '' : 'none';

    document.getElementById('detailsContent').innerHTML =
      '<div class="loading-state">Загрузка истории...</div>';
    openModal('modalDetails');

    try {
      const intakes = await apiFetch(API.intakes + '?prescription_id=' + prescriptionId);
      document.getElementById('detailsContent').innerHTML = renderDetailsContent(p, intakes);
    } catch (err) {
      document.getElementById('detailsContent').innerHTML =
        '<div class="error-state">Не удалось загрузить историю приёмов</div>';
    }
  }

  function renderDetailsContent(p, intakes) {
    const rate  = Math.round((p.adherence_rate || 0) * 100);
    const color = rate >= 80 ? '#4caf50' : rate >= 50 ? '#ff9800' : '#f44336';

    const scheduleHtml = (p.intake_schedule || [])
      .map(s => '<span class="slot-tag">' + (SLOTS[s] ? SLOTS[s].icon : '') + ' ' + (SLOTS[s] ? SLOTS[s].label : escapeHtml(s)) + '</span>')
      .join('&nbsp;');

    let html =
      '<div class="details-meta">' +
        '<div class="details-row"><b>Доза:</b> ' + escapeHtml(String(p.dose)) + ' ' + escapeHtml(p.dose_unit) + '</div>' +
        '<div class="details-row"><b>Частота:</b> ' + p.frequency_times_per_day + '\u00d7/день</div>' +
        '<div class="details-row"><b>Расписание:</b> ' + scheduleHtml + '</div>' +
        '<div class="details-row"><b>Приём:</b> ' + escapeHtml(p.route) + '</div>' +
        '<div class="details-row"><b>Период:</b> ' + formatDate(p.start_date) + ' \u2014 ' + (p.end_date ? formatDate(p.end_date) : 'постоянно') + '</div>' +
        (p.indication ? '<div class="details-row"><b>Показания:</b> ' + escapeHtml(p.indication) + '</div>' : '') +
        (p.instructions ? '<div class="details-row"><b>Указания:</b> ' + escapeHtml(p.instructions) + '</div>' : '') +
        '<div class="details-row"><b>Соблюдение:</b> <span style="color:' + color + ';font-weight:700">' + rate + '%</span></div>' +
        (!p.prescribed_by ? '<div style="margin-top:0.5rem"><span class="badge-self">Добавлен самостоятельно</span></div>' : '') +
      '</div>' +
      '<hr>' +
      '<h4>История приёмов</h4>';

    if (!intakes.length) {
      html += '<p class="text-muted">Приёмов ещё не отмечено</p>';
    } else {
      html +=
        '<div class="table-wrapper">' +
          '<table class="intakes-table">' +
            '<thead><tr>' +
              '<th>Дата и время</th>' +
              '<th>Слот</th>' +
              '<th>Доза</th>' +
              '<th>Примечания</th>' +
              '<th></th>' +
            '</tr></thead>' +
            '<tbody>';
      intakes.forEach(intake => {
        const slotLabel = intake.intake_slot
          ? (SLOTS[intake.intake_slot] ? SLOTS[intake.intake_slot].icon : '') + ' ' +
            (SLOTS[intake.intake_slot] ? SLOTS[intake.intake_slot].label : escapeHtml(intake.intake_slot))
          : '\u2014';
        html +=
          '<tr>' +
            '<td>' + formatDateTime(intake.intake_datetime) + '</td>' +
            '<td>' + slotLabel + '</td>' +
            '<td>' + escapeHtml(String(intake.actual_dose)) + ' ' + escapeHtml(p.dose_unit) + '</td>' +
            '<td class="notes-cell">' + (intake.notes ? escapeHtml(intake.notes) : '\u2014') + '</td>' +
            '<td class="actions-cell">' +
              '<button class="btn-icon" onclick="openEditIntake(' + intake.id + ')" title="Редактировать">\u270F</button>' +
              '<button class="btn-icon btn-icon-danger" onclick="confirmDeleteIntake(' + intake.id + ')" title="Удалить">\u2715</button>' +
            '</td>' +
          '</tr>';
      });
      html += '</tbody></table></div>';
    }
    return html;
  }

  // ── 4.11 Редактирование и удаление приёма ─────────────────────────────────
  async function openEditIntake(intakeId) {
    try {
      const intake = await apiFetch(API.intakes + '/' + intakeId);
      const p      = state.currentPrescription;

      document.getElementById('editIntakeId').value              = intake.id;
      document.getElementById('editIntakePrescribedDose').value  = p ? p.dose : '';
      document.getElementById('editIntakeDoseUnitValue').value   = p ? p.dose_unit : '';
      document.getElementById('editIntakeMedName').value         = p ? p.medication_name : '';
      document.getElementById('editIntakeDoseUnitLabel').textContent = p ? p.dose_unit : '\u2014';

      const dt = new Date(intake.intake_datetime);
      document.getElementById('editIntakeDate').value  = formatDateForInput(dt);
      syncDatePickerInput('editIntakeDate');
      setTime24('editIntakeTimeH', 'editIntakeTimeM', formatTimeForInput(dt));
      document.getElementById('editIntakeDose').value  = intake.actual_dose;
      document.getElementById('editIntakeNotes').value = intake.notes || '';

      openModal('modalEditIntake');
    } catch (err) {
      showToast(err.message || 'Ошибка загрузки данных приёма', 'error');
    }
  }

  async function submitEditIntake(e) {
    e.preventDefault();
    clearFormErrors('formEditIntake');
    const id    = document.getElementById('editIntakeId').value;
    const date  = parseDateToApi(document.getElementById('editIntakeDate').value);
    const time  = getTime24('editIntakeTimeH', 'editIntakeTimeM');
    const dose  = parseFloat(document.getElementById('editIntakeDose').value);
    const notes = document.getElementById('editIntakeNotes').value.trim();
    const btn   = document.getElementById('btnSubmitEditIntake');

    if (!date) { setFieldError('errorEditIntakeTime', 'Укажите дату в формате дд-мм-гг'); return; }
    if (!time) { setFieldError('errorEditIntakeTime', 'Укажите время (часы 0–23, минуты 0–59)'); return; }

    btn.disabled    = true;
    btn.textContent = 'Сохранение...';

    try {
      await apiFetch(API.intakes + '/' + id, 'PUT', {
        intake_datetime: new Date(date + 'T' + time + ':00').toISOString(),
        actual_dose:     dose,
        notes:           notes || null,
      });
      showToast('Приём обновлён', 'success');
      closeModal('modalEditIntake');
      if (state.currentPrescription) await openDetails(state.currentPrescription.id);
      await loadPrescriptions();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      btn.disabled    = false;
      btn.textContent = 'Сохранить изменения';
    }
  }

  function confirmDeleteIntake(intakeId) {
    showConfirm(
      'Удалить приём?',
      'Запись о приёме будет удалена безвозвратно.',
      async () => {
        try {
          await apiFetch(API.intakes + '/' + intakeId, 'DELETE');
          showToast('Запись удалена', 'success');
          if (state.currentPrescription) await openDetails(state.currentPrescription.id);
          await loadPrescriptions();
        } catch (err) {
          showToast(err.message, 'error');
        }
      }
    );
  }

  function confirmDeletePrescription(prescriptionId) {
    showConfirm(
      'Удалить препарат?',
      'Препарат и вся история его приёмов будут удалены безвозвратно.',
      async () => {
        try {
          await apiFetch(API.prescriptions + '/' + prescriptionId, 'DELETE');
          showToast('Препарат удалён', 'success');
          closeModal('modalDetails');
          await loadPrescriptions();
        } catch (err) {
          showToast(err.message, 'error');
        }
      }
    );
  }

  // ── 4.12 Вспомогательные функции ──────────────────────────────────────────

  // HTTP
  async function apiFetch(url, method, body) {
    method = method || 'GET';
    body = body || null;
    const opts = { method: method, credentials: 'include', headers: {} };
    if (body) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'HTTP ' + res.status }));
      throw new Error(err.detail || 'Ошибка сервера');
    }
    if (res.status === 204) return null;
    return res.json();
  }

  // Toast
  function showToast(message, type) {
    type = type || 'info';
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.innerHTML = '<span>' + escapeHtml(message) + '</span><button onclick="this.parentElement.remove()">\u2715</button>';
    container.appendChild(toast);
    setTimeout(() => { toast.style.animation = 'toastOut 0.3s forwards'; }, 4700);
    setTimeout(() => toast.remove(), 5000);
  }

  // Confirm (вместо window.confirm)
  function showConfirm(title, message, onConfirm, btnText, danger) {
    btnText = btnText || 'Удалить';
    danger = danger !== false;
    document.getElementById('confirmTitle').textContent   = title;
    document.getElementById('confirmMessage').textContent = message;
    const btn = document.getElementById('btnConfirmOk');
    btn.textContent = btnText;
    btn.className   = 'btn ' + (danger ? 'btn-danger' : 'btn-primary');
    const newBtn = btn.cloneNode(true);
    btn.parentNode.replaceChild(newBtn, btn);
    newBtn.addEventListener('click', () => { closeModal('modalConfirm'); onConfirm(); });
    document.getElementById('btnConfirmCancel').onclick = () => closeModal('modalConfirm');
    openModal('modalConfirm');
  }

  // XSS protection
  function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = String(str == null ? '' : str);
    return d.innerHTML;
  }

  // Форматирование дат — отображение: dd-mm-yy
  function formatDate(str) {
    if (!str) return '\u2014';
    const parts = String(str).split('-');
    if (parts.length < 3) return str;
    return parts[2] + '-' + parts[1] + '-' + parts[0].slice(2);
  }

  // Дата + время: dd-mm-yy HH:MM (24-часовой)
  function formatDateTime(str) {
    if (!str) return '\u2014';
    const dt = new Date(str);
    var d  = String(dt.getDate()).padStart(2, '0');
    var m  = String(dt.getMonth() + 1).padStart(2, '0');
    var y  = String(dt.getFullYear()).slice(2);
    var H  = String(dt.getHours()).padStart(2, '0');
    var M  = String(dt.getMinutes()).padStart(2, '0');
    return d + '-' + m + '-' + y + ' ' + H + ':' + M;
  }

  // Отображение даты в поле ввода: dd-mm-yy (всегда)
  function formatDateForInput(date) {
    var d = String(date.getDate()).padStart(2, '0');
    var m = String(date.getMonth() + 1).padStart(2, '0');
    var y = String(date.getFullYear()).slice(2);
    return d + '-' + m + '-' + y;
  }

  // Парсинг dd-mm-yy (или d-m-yy) → YYYY-MM-DD для API
  function parseDateToApi(str) {
    if (!str || typeof str !== 'string') return '';
    var parts = str.trim().split(/[-./\s]/);
    if (parts.length < 3) return '';
    var d = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10);
    var y = parseInt(parts[2], 10);
    if (isNaN(d) || isNaN(m) || isNaN(y)) return '';
    if (y >= 0 && y <= 99) y = 2000 + y;
    if (m < 1 || m > 12 || d < 1 || d > 31) return '';
    var date = new Date(y, m - 1, d);
    if (date.getFullYear() !== y || date.getMonth() !== m - 1 || date.getDate() !== d) return '';
    return String(y) + '-' + String(m).padStart(2, '0') + '-' + String(d).padStart(2, '0');
  }

  // Время в 24-часовом формате: HH:mm (поля Ч и М)
  function formatTimeForInput(date) {
    var H = String(date.getHours()).padStart(2, '0');
    var M = String(date.getMinutes()).padStart(2, '0');
    return H + ':' + M;
  }

  function getTime24(hId, mId) {
    var h = parseInt(document.getElementById(hId).value, 10);
    var m = parseInt(document.getElementById(mId).value, 10);
    if (isNaN(h) || isNaN(m) || h < 0 || h > 23 || m < 0 || m > 59) return '';
    return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
  }

  function setTime24(hId, mId, timeStr) {
    if (!timeStr || timeStr.indexOf(':') === -1) return;
    var parts = timeStr.split(':');
    document.getElementById(hId).value = parts[0] ? parseInt(parts[0], 10) : '';
    document.getElementById(mId).value = parts[1] ? parseInt(parts[1], 10) : '';
  }

  function todayStr() {
    return formatDateForInput(new Date());
  }

  // ── Обработчики событий ───────────────────────────────────────────────────
  function setupEventListeners() {
    document.getElementById('btnAddPrescription')
      ?.addEventListener('click', openAddPrescription);
    document.getElementById('btnAddIntake')
      ?.addEventListener('click', openAddIntake);

    document.getElementById('formPrescription')
      ?.addEventListener('submit', submitPrescription);
    document.getElementById('formAddIntake')
      ?.addEventListener('submit', submitAddIntake);
    document.getElementById('formEditIntake')
      ?.addEventListener('submit', submitEditIntake);

    document.getElementById('intakeSelectPrescription')
      ?.addEventListener('change', e => handleIntakePrescriptionChange(e.target.value));
    document.getElementById('intakeActualDose')
      ?.addEventListener('input', validateIntakeDose);
    document.getElementById('intakeNotes')
      ?.addEventListener('input', e => {
        document.getElementById('intakeNotesCount').textContent = e.target.value.length;
      });

    document.getElementById('btnEditPrescription')
      ?.addEventListener('click', () => {
        if (state.currentPrescription) openEditPrescription(state.currentPrescription);
      });
    document.getElementById('btnDeletePrescription')
      ?.addEventListener('click', () => {
        if (state.currentPrescription) confirmDeletePrescription(state.currentPrescription.id);
      });
  }

  // ── Экспорт для onclick в HTML ────────────────────────────────────────────
  window.openDetails              = openDetails;
  window.openEditIntake           = openEditIntake;
  window.confirmDeleteIntake      = confirmDeleteIntake;
  window.confirmDeletePrescription = confirmDeletePrescription;
  window.loadPrescriptions        = loadPrescriptions;
})();
