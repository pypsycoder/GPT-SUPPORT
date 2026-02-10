(function () {
  var WEEKDAY = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
  var MONTH_GENITIVE = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];

  function formatSleepDateLabel(d) {
    return WEEKDAY[d.getDay()] + ', ' + d.getDate() + ' ' + MONTH_GENITIVE[d.getMonth()];
  }

  function toYYYYMMDD(d) {
    var y = d.getFullYear();
    var m = (d.getMonth() + 1);
    var day = d.getDate();
    return y + '-' + (m < 10 ? '0' : '') + m + '-' + (day < 10 ? '0' : '') + day;
  }

  function parseHHMM(s) {
    if (!s || s.length < 5) return { h: '', m: '' };
    var parts = s.split(':');
    var h = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10);
    if (isNaN(h) || isNaN(m)) return { h: '', m: '' };
    return { h: h, m: m };
  }

  var nightScreen = document.getElementById('sleep-night-screen');
  var nightOptions = document.getElementById('sleep-night-options');
  var nightContinue = document.getElementById('sleep-night-continue');
  var duplicateDialog = document.getElementById('sleep-duplicate-dialog');
  var duplicateEdit = document.getElementById('sleep-duplicate-edit');
  var duplicateCancel = document.getElementById('sleep-duplicate-cancel');
  var formWrap = document.getElementById('sleep-form-wrap');
  var form = document.getElementById('sleep-form');
  var statusEl = document.getElementById('sleep-status');
  var tibWarning = document.getElementById('tib-warning');
  var tibConfirm = document.getElementById('tib-confirm');
  var seWarning = document.getElementById('se-warning');
  var seDisplay = document.getElementById('se-display');
  var submitBtn = document.getElementById('sleep-submit');

  var state = {
    sleep_date: null,
    sleep_onset: '',
    wake_time: '',
    tst_hours: null,
    night_awakenings: '',
    sleep_latency: '',
    morning_wellbeing: '',
    daytime_nap: '',
    disturbances: [],
    tibWarningConfirmed: false,
    editRecordId: null,
    existingRecord: null
  };

  function showStatus(message, type) {
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = 'sleep-status ' + (type === 'success' ? 'success' : 'error');
    statusEl.classList.remove('sleep-status-hidden');
  }

  function clearStatus() {
    if (!statusEl) return;
    statusEl.textContent = '';
    statusEl.className = 'sleep-status sleep-status-hidden';
  }

  function showScreen(screen) {
    if (screen === 'night') {
      nightScreen.classList.remove('sleep-hidden');
      duplicateDialog.classList.add('sleep-hidden');
      formWrap.classList.add('sleep-hidden');
    } else if (screen === 'duplicate') {
      nightScreen.classList.add('sleep-hidden');
      duplicateDialog.classList.remove('sleep-hidden');
      formWrap.classList.add('sleep-hidden');
    } else {
      nightScreen.classList.add('sleep-hidden');
      duplicateDialog.classList.add('sleep-hidden');
      formWrap.classList.remove('sleep-hidden');
    }
  }

  function buildNightOptions() {
    var today = new Date();
    today.setHours(0, 0, 0, 0);
    var options = [];
    for (var i = 1; i <= 4; i++) {
      var d = new Date(today);
      d.setDate(d.getDate() - i);
      options.push({ date: d, label: formatSleepDateLabel(d), value: toYYYYMMDD(d) });
    }
    nightOptions.innerHTML = '';
    options.forEach(function (opt, index) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'sleep-night-option' + (index === 0 ? ' selected' : '');
      btn.setAttribute('data-sleep-date', opt.value);
      btn.textContent = opt.label;
      btn.addEventListener('click', function () {
        nightOptions.querySelectorAll('.sleep-night-option').forEach(function (b) { b.classList.remove('selected'); });
        btn.classList.add('selected');
      });
      nightOptions.appendChild(btn);
    });
  }

  function getSelectedSleepDate() {
    var selected = nightOptions.querySelector('.sleep-night-option.selected');
    return selected ? selected.getAttribute('data-sleep-date') : null;
  }

  function getTimeFromInputs(hId, mId) {
    var hEl = document.getElementById(hId);
    var mEl = document.getElementById(mId);
    if (!hEl || !mEl) return null;
    var h = parseInt(hEl.value, 10);
    var m = parseInt(mEl.value, 10);
    if (isNaN(h) || isNaN(m) || h < 0 || h > 23 || m < 0 || m > 59) return null;
    return h * 60 + m;
  }

  function getTimeStrFromInputs(hId, mId) {
    var hEl = document.getElementById(hId);
    var mEl = document.getElementById(mId);
    if (!hEl || !mEl) return '';
    var h = parseInt(hEl.value, 10);
    var m = parseInt(mEl.value, 10);
    if (isNaN(h) || isNaN(m) || h < 0 || h > 23 || m < 0 || m > 59) return '';
    return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
  }

  function parseTime(str) {
    if (!str || str.length < 5) return null;
    var parts = str.split(':');
    var h = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10);
    if (isNaN(h) || isNaN(m)) return null;
    return h * 60 + m;
  }

  function computeTibMinutes(onsetStr, wakeStr) {
    var onset = parseTime(onsetStr);
    var wake = parseTime(wakeStr);
    if (onset === null || wake === null) return null;
    var startM = onset;
    var endM = wake;
    if (endM <= startM) endM += 24 * 60;
    return endM - startM;
  }

  function updateTibWarning() {
    var tib = computeTibMinutes(state.sleep_onset, state.wake_time);
    if (tib === null) {
      tibWarning.classList.add('sleep-warning-hidden');
      return;
    }
    if (state.tibWarningConfirmed) {
      tibWarning.classList.add('sleep-warning-hidden');
      return;
    }
    if (tib < 2 * 60 || tib > 14 * 60) {
      tibWarning.classList.remove('sleep-warning-hidden');
    } else {
      tibWarning.classList.add('sleep-warning-hidden');
    }
  }

  tibConfirm.addEventListener('click', function () {
    state.tibWarningConfirmed = true;
    tibWarning.classList.add('sleep-warning-hidden');
    updateSubmitButton();
  });

  function updateSeDisplay() {
    var tib = computeTibMinutes(state.sleep_onset, state.wake_time);
    var tst = state.tst_hours !== null ? Math.round(state.tst_hours * 60) : null;
    seDisplay.textContent = '';
    seWarning.classList.add('sleep-warning-hidden');
    if (tib === null || tib === 0 || tst === null) return;
    if (tst > tib) {
      seWarning.classList.remove('sleep-warning-hidden');
      return;
    }
    var se = Math.round(1000 * tst / tib) / 10;
    seDisplay.textContent = 'Эффективность сна: ' + se + '%';
  }

  function updateSubmitButton() {
    var required = (
      state.sleep_onset &&
      state.wake_time &&
      state.tst_hours !== null && state.tst_hours !== '' &&
      state.night_awakenings &&
      state.sleep_latency &&
      state.morning_wellbeing
    );
    var tib = computeTibMinutes(state.sleep_onset, state.wake_time);
    var tstM = state.tst_hours !== null ? Math.round(state.tst_hours * 60) : 0;
    var noSeError = (tib === null || tib === 0 || tstM <= tib);
    submitBtn.disabled = !required || !noSeError;
  }

  function syncTimeState() {
    state.sleep_onset = getTimeStrFromInputs('sleep_onset_h', 'sleep_onset_m');
    state.wake_time = getTimeStrFromInputs('wake_time_h', 'wake_time_m');
    state.tibWarningConfirmed = false;
    updateTibWarning();
    updateSeDisplay();
    updateSubmitButton();
  }

  function resetForm() {
    form.reset();
    state.sleep_onset = '';
    state.wake_time = '';
    state.tst_hours = null;
    state.night_awakenings = '';
    state.sleep_latency = '';
    state.morning_wellbeing = '';
    state.daytime_nap = '';
    state.disturbances = [];
    state.tibWarningConfirmed = false;
    state.editRecordId = null;
    state.existingRecord = null;
    ['sleep_onset_h', 'sleep_onset_m', 'wake_time_h', 'wake_time_m'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.value = '';
    });
    document.querySelectorAll('.sleep-btn').forEach(function (b) { b.classList.remove('selected'); });
    document.querySelectorAll('.sleep-check input[name="disturbance"]').forEach(function (c) { c.checked = false; });
    submitBtn.textContent = 'Отправить';
    updateSubmitButton();
  }

  function fillFormFromRecord(record) {
    var onset = parseHHMM(record.sleep_onset);
    var wake = parseHHMM(record.wake_time);
    document.getElementById('sleep_onset_h').value = onset.h !== '' ? onset.h : '';
    document.getElementById('sleep_onset_m').value = onset.m !== '' ? onset.m : '';
    document.getElementById('wake_time_h').value = wake.h !== '' ? wake.h : '';
    document.getElementById('wake_time_m').value = wake.m !== '' ? wake.m : '';
    document.getElementById('tst_hours').value = record.tst_minutes / 60;

    state.sleep_onset = record.sleep_onset;
    state.wake_time = record.wake_time;
    state.tst_hours = record.tst_minutes / 60;
    state.night_awakenings = record.night_awakenings || '';
    state.sleep_latency = record.sleep_latency || '';
    state.morning_wellbeing = record.morning_wellbeing || '';
    state.daytime_nap = record.daytime_nap || '';
    state.disturbances = record.sleep_disturbances && record.sleep_disturbances.length ? record.sleep_disturbances.slice() : [];

    document.querySelectorAll('.sleep-btn').forEach(function (b) {
      var name = b.getAttribute('data-name');
      var value = b.getAttribute('data-value');
      if (state[name] === value) b.classList.add('selected');
      else b.classList.remove('selected');
    });
    document.querySelectorAll('.sleep-check input[name="disturbance"]').forEach(function (c) {
      c.checked = state.disturbances.indexOf(c.value) !== -1;
    });
    updateTibWarning();
    updateSeDisplay();
    updateSubmitButton();
  }

  nightContinue.addEventListener('click', function () {
    var sleepDate = getSelectedSleepDate();
    if (!sleepDate) return;
    state.sleep_date = sleepDate;
    clearStatus();
    nightContinue.disabled = true;
    fetch('/api/v1/sleep/me/by-date?date=' + encodeURIComponent(sleepDate), { credentials: 'include' })
      .then(function (res) {
        if (res.status === 404) {
          showScreen('form');
          resetForm();
          state.sleep_date = sleepDate;
          nightContinue.disabled = false;
          return;
        }
        if (!res.ok) throw new Error(res.statusText);
        return res.json();
      })
      .then(function (body) {
        if (!body) return;
        state.existingRecord = body;
        showScreen('duplicate');
        nightContinue.disabled = false;
      })
      .catch(function () {
        showStatus('Ошибка проверки данных. Попробуйте снова.', 'error');
        nightContinue.disabled = false;
      });
  });

  duplicateCancel.addEventListener('click', function () {
    showScreen('night');
    state.existingRecord = null;
    state.sleep_date = null;
  });

  duplicateEdit.addEventListener('click', function () {
    if (!state.existingRecord) return;
    state.editRecordId = state.existingRecord.record_id;
    fillFormFromRecord(state.existingRecord);
    submitBtn.textContent = 'Сохранить изменения';
    showScreen('form');
  });

  ['sleep_onset_h', 'sleep_onset_m', 'wake_time_h', 'wake_time_m'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', syncTimeState);
  });

  document.getElementById('tst_hours').addEventListener('input', function () {
    var v = this.value === '' ? null : parseFloat(this.value);
    if (v !== null && (isNaN(v) || v < 0 || v > 12)) v = null;
    state.tst_hours = v;
    updateSeDisplay();
    updateSubmitButton();
  });

  document.querySelectorAll('.sleep-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var name = this.getAttribute('data-name');
      var value = this.getAttribute('data-value');
      var group = this.closest('.sleep-btn-group');
      if (!group) return;
      group.querySelectorAll('.sleep-btn').forEach(function (b) { b.classList.remove('selected'); });
      this.classList.add('selected');
      state[name] = value;
      updateSubmitButton();
    });
  });

  var noneCheck = document.querySelector('.sleep-check-none input');
  document.querySelectorAll('.sleep-check input[name="disturbance"]').forEach(function (cb) {
    cb.addEventListener('change', function () {
      var val = this.value;
      if (val === 'none') {
        if (this.checked) {
          document.querySelectorAll('.sleep-check input[name="disturbance"]').forEach(function (c) {
            if (c !== cb) c.checked = false;
          });
          state.disturbances = ['none'];
        } else {
          state.disturbances = [];
        }
      } else {
        if (noneCheck && noneCheck.checked) noneCheck.checked = false;
        var checked = [];
        document.querySelectorAll('.sleep-check input[name="disturbance"]:checked').forEach(function (c) {
          checked.push(c.value);
        });
        state.disturbances = checked.indexOf('none') >= 0 ? ['none'] : checked;
      }
    });
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    clearStatus();
    var tib = computeTibMinutes(state.sleep_onset, state.wake_time);
    var tstM = state.tst_hours !== null ? Math.round(state.tst_hours * 60) : 0;
    if (tib !== null && tstM > tib) {
      showStatus('Время сна не может быть больше времени в кровати.', 'error');
      return;
    }

    var payload = {
      sleep_onset: state.sleep_onset,
      wake_time: state.wake_time,
      tst_hours: state.tst_hours,
      night_awakenings: state.night_awakenings,
      sleep_latency: state.sleep_latency,
      morning_wellbeing: state.morning_wellbeing,
      daytime_nap: state.daytime_nap || null,
      sleep_disturbances: state.disturbances.length ? state.disturbances : null
    };

    submitBtn.disabled = true;

    if (state.editRecordId) {
      fetch('/api/v1/sleep/me/' + state.editRecordId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload)
      })
        .then(function (res) {
          if (!res.ok) return res.json().then(function (j) { throw new Error(j.detail || res.statusText); });
          return res.json();
        })
        .then(function () {
          showStatus('Изменения сохранены.', 'success');
          showScreen('night');
          resetForm();
          state.sleep_date = null;
          submitBtn.disabled = false;
        })
        .catch(function (err) {
          showStatus(err.message || 'Ошибка сохранения.', 'error');
          submitBtn.disabled = false;
        });
    } else {
      payload.sleep_date = state.sleep_date;
      fetch('/api/v1/sleep/me', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload)
      })
        .then(function (res) {
          if (!res.ok) return res.json().then(function (j) { throw new Error(j.detail || res.statusText); });
          return res.json();
        })
        .then(function () {
          showStatus('Запись сохранена.', 'success');
          showScreen('night');
          resetForm();
          state.sleep_date = null;
          submitBtn.disabled = false;
        })
        .catch(function (err) {
          showStatus(err.message || 'Ошибка отправки. Проверьте сеть и попробуйте снова.', 'error');
          submitBtn.disabled = false;
        });
    }
  });

  buildNightOptions();
  showScreen('night');
  updateSubmitButton();
})();
