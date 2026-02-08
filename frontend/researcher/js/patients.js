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
