(function () {
  'use strict';

  const form = document.getElementById('login-form');
  const numberInput = document.getElementById('patient-number');
  const pinInput = document.getElementById('pin-code');
  const loginBtn = document.getElementById('login-btn');
  const errorDiv = document.getElementById('login-error');

  function showError(msg) {
    errorDiv.textContent = msg;
    errorDiv.classList.add('visible');
  }

  function hideError() {
    errorDiv.classList.remove('visible');
  }

  // Only allow digits in both fields
  [numberInput, pinInput].forEach(function (input) {
    input.addEventListener('input', function () {
      this.value = this.value.replace(/\D/g, '');
    });
  });

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    hideError();

    var patientNumber = numberInput.value.trim();
    var pin = pinInput.value.trim();

    if (!patientNumber || !pin) {
      showError('Введите номер пациента и PIN-код');
      return;
    }

    loginBtn.disabled = true;
    loginBtn.textContent = 'Вход...';

    try {
      var resp = await fetch('/api/v1/auth/patient/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_number: parseInt(patientNumber, 10),
          pin: pin,
        }),
      });

      var data = await resp.json();

      if (!resp.ok) {
        showError(data.error || 'Ошибка входа');
        loginBtn.disabled = false;
        loginBtn.textContent = 'Войти';
        return;
      }

      // Success — redirect based on consent / onboarding status
      if (data.needs_consent) {
        window.location.href = '/consent';
      } else if (data.needs_onboarding) {
        window.location.href = '/patient/onboarding';
      } else {
        window.location.href = '/patient/home';
      }
    } catch (err) {
      showError('Ошибка соединения. Попробуйте позже.');
      loginBtn.disabled = false;
      loginBtn.textContent = 'Войти';
    }
  });
})();
