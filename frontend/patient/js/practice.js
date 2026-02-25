(function () {
  // ============================================================
  //  Утилиты
  // ============================================================

  async function apiFetch(url, method, body) {
    method = method || 'GET';
    var opts = { method: method, credentials: 'include', headers: {} };
    if (body) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    var res = await fetch(url, opts);
    if (!res.ok) {
      var err = await res.json().catch(function () { return { detail: 'HTTP ' + res.status }; });
      throw new Error(err.detail || 'Ошибка сервера');
    }
    if (res.status === 204) return null;
    return res.json();
  }

  function showToast(message, type) {
    var container = document.getElementById('toast-container');
    if (!container) return;
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + (type || 'info');
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(function () {
      toast.classList.add('toast-hide');
      setTimeout(function () { toast.remove(); }, 400);
    }, 2500);
  }

  function formatTime(seconds) {
    var m = Math.floor(seconds / 60);
    var s = seconds % 60;
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }

  // ============================================================
  //  Состояние
  // ============================================================

  var practiceId = null;
  var practice = null;
  var timerTotal = 0;
  var timerRemaining = 0;
  var timerInterval = null;
  var timerRunning = false;
  var completionDone = false;

  // ============================================================
  //  Таймер
  // ============================================================

  function updateTimerDisplay() {
    var display = document.getElementById('timer-display');
    var bar = document.getElementById('timer-progress-bar');
    if (display) display.textContent = formatTime(timerRemaining);
    if (bar && timerTotal > 0) {
      var pct = ((timerTotal - timerRemaining) / timerTotal) * 100;
      bar.style.width = pct.toFixed(1) + '%';
    }
  }

  function startTimer() {
    if (timerRunning || timerRemaining <= 0) return;
    timerRunning = true;
    document.getElementById('btn-timer-start').style.display = 'none';
    document.getElementById('btn-timer-pause').style.display = '';
    timerInterval = setInterval(function () {
      timerRemaining -= 1;
      updateTimerDisplay();
      if (timerRemaining <= 0) {
        clearInterval(timerInterval);
        timerRunning = false;
        document.getElementById('btn-timer-pause').style.display = 'none';
        document.getElementById('btn-timer-start').style.display = '';
        document.getElementById('btn-timer-start').disabled = true;
        document.getElementById('btn-timer-start').textContent = 'Готово';
      }
    }, 1000);
  }

  function pauseTimer() {
    if (!timerRunning) return;
    clearInterval(timerInterval);
    timerRunning = false;
    document.getElementById('btn-timer-pause').style.display = 'none';
    document.getElementById('btn-timer-start').style.display = '';
  }

  function resetTimer() {
    clearInterval(timerInterval);
    timerRunning = false;
    timerRemaining = timerTotal;
    updateTimerDisplay();
    var btnStart = document.getElementById('btn-timer-start');
    var btnPause = document.getElementById('btn-timer-pause');
    if (btnStart) {
      btnStart.style.display = '';
      btnStart.disabled = false;
      btnStart.textContent = 'Старт';
    }
    if (btnPause) btnPause.style.display = 'none';
  }

  // ============================================================
  //  Завершение практики
  // ============================================================

  async function submitComplete(mood) {
    if (completionDone) return;
    completionDone = true;

    try {
      await apiFetch('/api/practices/' + practiceId + '/complete', 'POST', {
        mood_after: mood || null,
      });
      showToast('Отмечено ✓', 'success');
    } catch (e) {
      showToast('Ошибка: ' + e.message, 'error');
      completionDone = false;
      return;
    }

    setTimeout(function () { history.back(); }, 1200);
  }

  // ============================================================
  //  Рендер практики
  // ============================================================

  function renderPractice(p) {
    practice = p;
    practiceId = p.id;

    document.title = p.title + ' — GPT Health Support';

    var titleEl = document.getElementById('practice-title');
    var taglineEl = document.getElementById('practice-tagline');
    var instrEl = document.getElementById('practice-instruction');
    var timerBlock = document.getElementById('timer-block');
    var promptEl = document.getElementById('completion-prompt');

    if (titleEl) titleEl.textContent = p.title;

    if (taglineEl) {
      taglineEl.textContent = p.tagline || '';
      taglineEl.style.display = p.tagline ? '' : 'none';
    }

    if (instrEl) {
      instrEl.innerHTML = '';
      (p.instruction || []).forEach(function (step) {
        var li = document.createElement('li');
        li.textContent = step;
        instrEl.appendChild(li);
      });
    }

    if (timerBlock && p.duration_seconds > 0) {
      timerTotal = p.duration_seconds;
      timerRemaining = p.duration_seconds;
      updateTimerDisplay();
      timerBlock.style.display = '';
    }

    if (promptEl) {
      promptEl.textContent = p.completion_prompt || 'Как вы себя чувствуете?';
    }

    document.getElementById('practice-content').style.display = '';
  }

  // ============================================================
  //  Инициализация
  // ============================================================

  async function init() {
    // Получаем practice_id из URL (?id=p01_breathing_478)
    var params = new URLSearchParams(window.location.search);
    practiceId = params.get('id');

    var errorEl = document.getElementById('practice-error');
    var contentEl = document.getElementById('practice-content');

    if (!practiceId) {
      if (errorEl) errorEl.style.display = '';
      return;
    }

    try {
      var p = await apiFetch('/api/practices/' + practiceId);
      renderPractice(p);
    } catch (e) {
      if (errorEl) errorEl.style.display = '';
      console.error('Не удалось загрузить практику:', e);
      return;
    }

    // Кнопка назад
    var btnBack = document.getElementById('btn-back');
    if (btnBack) {
      btnBack.addEventListener('click', function () { history.back(); });
    }

    // Таймер: Старт
    var btnStart = document.getElementById('btn-timer-start');
    if (btnStart) btnStart.addEventListener('click', startTimer);

    // Таймер: Пауза
    var btnPause = document.getElementById('btn-timer-pause');
    if (btnPause) btnPause.addEventListener('click', pauseTimer);

    // Таймер: Сброс
    var btnReset = document.getElementById('btn-timer-reset');
    if (btnReset) btnReset.addEventListener('click', resetTimer);

    // Кнопка ВЫПОЛНЕНО
    var btnComplete = document.getElementById('btn-complete');
    if (btnComplete) {
      btnComplete.addEventListener('click', function () {
        btnComplete.style.display = 'none';
        var moodBlock = document.getElementById('mood-block');
        if (moodBlock) moodBlock.style.display = '';
      });
    }

    // Кнопки настроения
    var moodBtns = document.querySelectorAll('.mood-btn');
    moodBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var mood = parseInt(btn.getAttribute('data-mood'), 10);
        submitComplete(mood);
      });
    });

    // Пропустить
    var btnSkip = document.getElementById('btn-skip');
    if (btnSkip) {
      btnSkip.addEventListener('click', function () { submitComplete(null); });
    }
  }

  document.addEventListener('DOMContentLoaded', async function () {
    if (window.PatientAuth) {
      await window.PatientAuth.requireAuth();
    }
    await init();
  });
})();
