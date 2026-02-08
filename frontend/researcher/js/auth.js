(function () {
  'use strict';

  // --- Login form (only on /researcher/login page) ---
  var form = document.getElementById('r-login-form');
  if (form) {
    var usernameInput = document.getElementById('r-username');
    var passwordInput = document.getElementById('r-password');
    var loginBtn = document.getElementById('r-login-btn');
    var errorDiv = document.getElementById('r-login-error');

    form.addEventListener('submit', async function (e) {
      e.preventDefault();

      errorDiv.classList.remove('visible');
      loginBtn.disabled = true;
      loginBtn.textContent = 'Вход...';

      try {
        var resp = await fetch('/api/v1/auth/researcher/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            username: usernameInput.value.trim(),
            password: passwordInput.value,
          }),
        });

        var data = await resp.json();

        if (!resp.ok) {
          errorDiv.textContent = data.error || 'Ошибка входа';
          errorDiv.classList.add('visible');
          loginBtn.disabled = false;
          loginBtn.textContent = 'Войти';
          return;
        }

        window.location.href = '/researcher/dashboard';
      } catch (err) {
        console.error('[auth] Login error:', err);
        errorDiv.textContent = 'Ошибка соединения';
        errorDiv.classList.add('visible');
        loginBtn.disabled = false;
        loginBtn.textContent = 'Войти';
      }
    });
  }

  // --- Auth check helper for researcher pages ---
  window.ResearcherAuth = {
    requireAuth: async function () {
      try {
        var resp = await fetch('/api/v1/auth/researcher/me', {
          credentials: 'include',
        });
        if (!resp.ok) {
          window.location.href = '/researcher/login';
          return new Promise(function () {});
        }
        return await resp.json();
      } catch (e) {
        console.error('[auth] Error checking auth:', e);
        window.location.href = '/researcher/login';
        return new Promise(function () {});
      }
    },

    logout: async function () {
      await fetch('/api/v1/auth/researcher/logout', {
        method: 'POST',
        credentials: 'include',
      });
      window.location.href = '/researcher/login';
    },
  };
})();
