(function () {
  'use strict';

  var checkPd = document.getElementById('consent-pd');
  var checkBot = document.getElementById('consent-bot');
  var consentBtn = document.getElementById('consent-btn');
  var errorDiv = document.getElementById('consent-error');

  function updateButton() {
    consentBtn.disabled = !(checkPd.checked && checkBot.checked);
  }

  checkPd.addEventListener('change', updateButton);
  checkBot.addEventListener('change', updateButton);

  // Make the entire row clickable
  document.getElementById('consent-row-pd').addEventListener('click', function (e) {
    if (e.target !== checkPd) {
      checkPd.checked = !checkPd.checked;
      updateButton();
    }
  });
  document.getElementById('consent-row-bot').addEventListener('click', function (e) {
    if (e.target !== checkBot) {
      checkBot.checked = !checkBot.checked;
      updateButton();
    }
  });

  consentBtn.addEventListener('click', async function () {
    errorDiv.classList.remove('visible');
    consentBtn.disabled = true;
    consentBtn.textContent = 'Сохранение...';

    try {
      var resp = await fetch('/api/v1/consent/accept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          consent_personal_data: true,
          consent_bot_use: true,
        }),
      });

      if (!resp.ok) {
        var data = await resp.json();
        errorDiv.textContent = data.detail || 'Ошибка сохранения';
        errorDiv.classList.add('visible');
        consentBtn.disabled = false;
        consentBtn.textContent = 'Продолжить';
        return;
      }

      var me = await fetch('/api/v1/auth/patient/me').then(function (r) { return r.json(); });
      window.location.href = me.is_onboarded ? '/patient/home' : '/patient/onboarding';
    } catch (err) {
      errorDiv.textContent = 'Ошибка соединения. Попробуйте позже.';
      errorDiv.classList.add('visible');
      consentBtn.disabled = false;
      consentBtn.textContent = 'Продолжить';
    }
  });
})();
