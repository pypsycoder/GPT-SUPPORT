(function () {
  'use strict';

  var previewToken = null;
  var previewData = null;

  function showStep(stepId) {
    document.querySelectorAll('.r-import-step').forEach(function (el) {
      el.style.display = el.id === stepId ? '' : 'none';
    });
  }

  function formatWeekdays(weekdays) {
    if (!weekdays || !weekdays.length) return '—';
    var names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    return (weekdays.map(function (d) { return names[d - 1] || d; })).join('/');
  }

  function shiftLabel(s) {
    if (s === 'morning') return 'утро';
    if (s === 'afternoon') return 'день';
    if (s === 'evening') return 'вечер';
    return s;
  }

  document.getElementById('import-upload-btn').addEventListener('click', async function () {
    var input = document.getElementById('import-file');
    if (!input.files || !input.files[0]) {
      alert('Выберите файл CSV');
      return;
    }
    var btn = document.getElementById('import-upload-btn');
    btn.disabled = true;
    btn.textContent = 'Проверка...';
    try {
      var form = new FormData();
      form.append('file', input.files[0]);
      var resp = await fetch('/api/v1/import/schedules', {
        method: 'POST',
        credentials: 'include',
        body: form,
      });
      if (!resp.ok) {
        alert('Ошибка загрузки');
        btn.disabled = false;
        btn.textContent = 'Загрузить и проверить';
        return;
      }
      var data = await resp.json();
      previewToken = data.preview_token;
      previewData = { ready: data.ready || [], conflicts: data.conflicts || [], errors: data.errors || [] };

      document.getElementById('preview-ready-count').textContent = previewData.ready.length;
      document.getElementById('preview-conflicts-count').textContent = previewData.conflicts.length;
      document.getElementById('preview-errors-count').textContent = previewData.errors.length;

      var conflictTable = document.getElementById('preview-conflicts-table');
      if (previewData.conflicts.length === 0) {
        conflictTable.innerHTML = '';
      } else {
        var headers = '<tr><th>Пациент ID</th><th>Текущее расписание</th><th>Новое расписание</th><th>Решение</th></tr>';
        var rows = previewData.conflicts.map(function (c, i) {
          var ex = c.existing_schedule || {};
          var nu = c.new_schedule || {};
          var pid = (nu.patient_id != null ? nu.patient_id : (ex.patient_id != null ? ex.patient_id : '—'));
          var exStr = formatWeekdays(ex.weekdays) + ' ' + shiftLabel(ex.shift);
          var nuStr = formatWeekdays(nu.weekdays) + ' ' + shiftLabel(nu.shift);
          return '<tr>' +
            '<td>' + pid + '</td>' +
            '<td>' + exStr + '</td>' +
            '<td>' + nuStr + '</td>' +
            '<td><select class="r-conflict-action" data-patient-id="' + pid + '"><option value="apply">Применить</option><option value="skip">Пропустить</option></select></td>' +
            '</tr>';
        });
        conflictTable.innerHTML = '<table class="r-table"><thead>' + headers + '</thead><tbody>' + rows.join('') + '</tbody></table>';
      }

      var errList = document.getElementById('preview-errors-list');
      if (previewData.errors.length === 0) {
        errList.innerHTML = '';
      } else {
        errList.innerHTML = '<p class="r-schedule-section-title">Ошибки (не будут импортированы)</p><ul>' +
          previewData.errors.map(function (e) {
            return '<li>Строка ' + (e.row_index || '?') + ': ' + (e.error_message || e) + '</li>';
          }).join('') + '</ul>';
      }

      showStep('step2');
    } catch (e) {
      alert('Ошибка соединения');
    }
    btn.disabled = false;
    btn.textContent = 'Загрузить и проверить';
  });

  document.getElementById('import-apply-btn').addEventListener('click', async function () {
    if (!previewToken || !previewData) {
      alert('Нет данных для применения');
      return;
    }
    var resolveConflicts = [];
    document.querySelectorAll('.r-conflict-action').forEach(function (sel) {
      var pid = parseInt(sel.dataset.patientId, 10);
      if (!isNaN(pid)) resolveConflicts.push({ patient_id: pid, action: sel.value });
    });
    var btn = document.getElementById('import-apply-btn');
    btn.disabled = true;
    btn.textContent = 'Применение...';
    try {
      var resp = await fetch('/api/v1/import/schedules/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          preview_token: previewToken,
          apply_ready: true,
          resolve_conflicts: resolveConflicts,
        }),
      });
      var data = await resp.json().catch(function () { return {}; });
      if (!resp.ok) {
        alert(data.detail || 'Ошибка применения импорта');
        btn.disabled = false;
        btn.textContent = 'Применить импорт';
        return;
      }
      document.getElementById('result-applied').textContent = data.applied != null ? data.applied : 0;
      document.getElementById('result-skipped').textContent = data.skipped != null ? data.skipped : 0;
      document.getElementById('result-errors').textContent = (data.errors && data.errors.length) ? data.errors.length : 0;
      var errList = document.getElementById('result-errors-list');
      if (data.errors && data.errors.length > 0) {
        errList.innerHTML = '<ul>' + data.errors.map(function (e) {
          return '<li>' + (e.message || e.patient_id || JSON.stringify(e)) + '</li>';
        }).join('') + '</ul>';
      } else {
        errList.innerHTML = '';
      }
      showStep('step3');
    } catch (e) {
      alert('Ошибка соединения');
    }
    btn.disabled = false;
    btn.textContent = 'Применить импорт';
  });

  document.getElementById('result-back-btn').addEventListener('click', function () {
    previewToken = null;
    previewData = null;
    document.getElementById('import-file').value = '';
    showStep('step1');
  });

  document.getElementById('r-logout-btn').addEventListener('click', function () {
    if (window.ResearcherAuth) window.ResearcherAuth.logout();
  });

  document.addEventListener('DOMContentLoaded', async function () {
    if (!window.ResearcherAuth) return;
    var researcher = await window.ResearcherAuth.requireAuth();
    var nameEl = document.getElementById('r-user-name');
    if (nameEl) nameEl.textContent = researcher.full_name || researcher.username;
  });
})();
