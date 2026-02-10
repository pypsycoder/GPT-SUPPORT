(function () {
  'use strict';

  var centersBody = document.getElementById('r-centers-tbody');
  var addModal = document.getElementById('modal-add-center');
  var addForm = document.getElementById('form-add-center');
  var errorEl = document.getElementById('center-error');

  function hideError() {
    errorEl.textContent = '';
    errorEl.classList.remove('visible');
  }

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.classList.add('visible');
  }

  function renderCenters(centers) {
    if (!centers || centers.length === 0) {
      centersBody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#9ca3af;padding:2rem;">Нет центров</td></tr>';
      return;
    }
    centersBody.innerHTML = centers.map(function (c) {
      return '<tr>' +
        '<td><strong>' + (c.name || '—') + '</strong></td>' +
        '<td>' + (c.city || '—') + '</td>' +
        '<td>' + (c.timezone || '—') + '</td>' +
        '<td>—</td>' +
        '</tr>';
    }).join('');
  }

  async function loadCenters() {
    try {
      var resp = await fetch('/api/v1/centers', { credentials: 'include' });
      if (!resp.ok) {
        centersBody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#dc2626;">Ошибка загрузки</td></tr>';
        return;
      }
      var data = await resp.json();
      renderCenters(data);
    } catch (e) {
      console.warn('Failed to load centers', e);
      centersBody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#dc2626;">Ошибка соединения</td></tr>';
    }
  }

  document.getElementById('r-add-center-btn').addEventListener('click', function () {
    addForm.reset();
    hideError();
    addModal.classList.add('visible');
  });

  document.getElementById('center-cancel').addEventListener('click', function () {
    addModal.classList.remove('visible');
  });

  addForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    hideError();
    var submitBtn = document.getElementById('center-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Сохранение...';
    try {
      var resp = await fetch('/api/v1/centers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: document.getElementById('center-name').value.trim(),
          city: document.getElementById('center-city').value.trim() || null,
          timezone: document.getElementById('center-timezone').value,
        }),
      });
      var data = await resp.json().catch(function () { return {}; });
      if (!resp.ok) {
        showError(data.detail || (typeof data.detail === 'string' ? data.detail : 'Ошибка создания центра'));
        submitBtn.disabled = false;
        submitBtn.textContent = 'Сохранить';
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
