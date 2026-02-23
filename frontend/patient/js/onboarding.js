(function () {
  'use strict';

  var startBtn = document.getElementById('start-btn');
  var titleEl = document.getElementById('onboarding-title');
  var errorDiv = document.getElementById('onboarding-error');

  function showError(msg) {
    errorDiv.textContent = msg;
    errorDiv.classList.add('visible');
  }

  async function init() {
    // Auth guard (manual — avoid requireAuth loop since is_onboarded = false)
    var resp = await fetch('/api/v1/auth/patient/me');
    if (!resp.ok) {
      window.location.href = '/login';
      return;
    }
    var user = await resp.json();
    if (!user.consent_personal_data) {
      window.location.href = '/consent';
      return;
    }

    // If already onboarded, go straight to home
    if (user.is_onboarded) {
      window.location.href = '/patient/home';
      return;
    }

    // Personalise heading
    var firstName = (user.full_name || '').split(' ')[0];
    if (firstName) {
      titleEl.textContent = 'Добро пожаловать, ' + firstName + '!';
    }
  }

  startBtn.addEventListener('click', async function () {
    startBtn.disabled = true;
    startBtn.textContent = 'Загрузка...';
    errorDiv.classList.remove('visible');

    try {
      var resp = await fetch('/api/v1/auth/patient/onboarding/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!resp.ok) {
        showError('Не удалось сохранить. Попробуйте ещё раз.');
        startBtn.disabled = false;
        startBtn.textContent = 'Начать';
        return;
      }

      window.location.href = '/patient/home';
    } catch (err) {
      showError('Ошибка соединения. Попробуйте позже.');
      startBtn.disabled = false;
      startBtn.textContent = 'Начать';
    }
  });

  init();
})();
