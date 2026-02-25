(function () {
  // ============================================
  // WCQ (Лазарус) — Опросник совладающего поведения
  // ============================================
  // Навигация: клик по варианту → авто-переход вперёд.
  // «← Назад» — всегда виден, недоступен на первом вопросе.
  // «Вперёд →» — активен только если вопрос уже был отвечен (есть сохранённый ответ).
  // answers[i] хранит ответ на i-й вопрос; переход назад не затирает сохранённый выбор.

  let wcqQuestions = [];
  let currentIndex = 0;
  // answers — массив той же длины, что вопросы; answers[i] = {question_id, option_id} | null
  let answers = [];
  let isSubmitting = false;

  const questionContainer = document.getElementById('wcq-question-container');
  const progressText      = document.getElementById('wcq-progress-text');
  const progressFill      = document.getElementById('wcq-progress-fill');
  const statusBanner      = document.getElementById('wcq-status');
  const resultBlock       = document.getElementById('wcq-result');
  const periodLabel       = document.getElementById('wcq-period-label');

  // ── Статус-баннер ──────────────────────────────────────────
  function showStatus(message, type = 'error') {
    if (!statusBanner) return;
    statusBanner.textContent = message;
    statusBanner.classList.remove('status-hidden', 'status-success', 'status-error');
    statusBanner.classList.add(type === 'success' ? 'status-success' : 'status-error');
  }

  function clearStatus() {
    if (!statusBanner) return;
    statusBanner.textContent = '';
    statusBanner.classList.add('status-hidden');
    statusBanner.classList.remove('status-success', 'status-error');
  }

  // ── Прогресс ───────────────────────────────────────────────
  function updateProgress() {
    if (!wcqQuestions.length) return;
    progressText.textContent = `Вопрос ${currentIndex + 1} из ${wcqQuestions.length}`;
    const pct = (currentIndex / wcqQuestions.length) * 100;
    progressFill.style.width = `${pct}%`;
  }

  // ── Переход вперёд (если есть сохранённый ответ) ──────────
  function goForward() {
    if (isSubmitting || !answers[currentIndex]) return;
    currentIndex += 1;
    if (currentIndex >= wcqQuestions.length) {
      submitAnswers();
    } else {
      renderQuestion();
    }
  }

  // ── Переход назад ──────────────────────────────────────────
  function goBack() {
    if (currentIndex === 0 || isSubmitting) return;
    currentIndex -= 1;
    renderQuestion();
  }

  // ── Рендер вопроса ─────────────────────────────────────────
  function renderQuestion() {
    clearStatus();
    if (!questionContainer) return;
    questionContainer.innerHTML = '';

    if (!wcqQuestions.length) {
      questionContainer.innerHTML = '<div class="hads-error-text">Не удалось загрузить вопросы. Попробуйте обновить страницу.</div>';
      return;
    }

    if (currentIndex >= wcqQuestions.length) {
      submitAnswers();
      return;
    }

    const question        = wcqQuestions[currentIndex];
    const savedAnswer     = answers[currentIndex];   // null или {question_id, option_id}
    const hasForward      = savedAnswer !== null;

    updateProgress();

    const card = document.createElement('div');
    card.className = 'hads-question-card';

    // Текст вопроса
    const text = document.createElement('div');
    text.className = 'hads-question-text';
    text.textContent = question.text;

    // Варианты ответа
    const optionsWrapper = document.createElement('div');
    optionsWrapper.className = 'hads-options';

    question.options.forEach((opt) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'hads-option-btn';

      // Подсветка ранее выбранного варианта
      if (savedAnswer && savedAnswer.option_id === opt.id) {
        btn.classList.add('wcq-option-selected');
      }

      btn.textContent = opt.text;
      btn.dataset.optionId = opt.id;

      btn.addEventListener('click', () => {
        if (isSubmitting) return;
        // Записываем/перезаписываем ответ и сразу двигаемся вперёд
        answers[currentIndex] = { question_id: question.id, option_id: opt.id };
        currentIndex += 1;
        if (currentIndex >= wcqQuestions.length) {
          submitAnswers();
        } else {
          renderQuestion();
        }
      });

      optionsWrapper.appendChild(btn);
    });

    // Панель навигации: «← Назад» слева, «Вперёд →» справа
    const nav = document.createElement('div');
    nav.className = 'wcq-nav';

    const backBtn = document.createElement('button');
    backBtn.type = 'button';
    backBtn.className = 'wcq-back-btn';
    backBtn.textContent = '← Назад';
    backBtn.disabled = currentIndex === 0;
    backBtn.addEventListener('click', goBack);

    const fwdBtn = document.createElement('button');
    fwdBtn.type = 'button';
    fwdBtn.className = 'wcq-forward-btn';
    fwdBtn.textContent = 'Вперёд →';
    fwdBtn.disabled = !hasForward;
    fwdBtn.addEventListener('click', goForward);

    nav.appendChild(backBtn);
    nav.appendChild(fwdBtn);

    card.appendChild(text);
    card.appendChild(optionsWrapper);
    card.appendChild(nav);
    questionContainer.appendChild(card);
  }

  // ── Отображение результатов ────────────────────────────────
  function buildProfileHtml(result) {
    const subscales = result?.subscales || {};
    const order     = result?.subscale_order || Object.keys(subscales);
    const message   = result?.patient_message || 'Спасибо за прохождение опросника.';

    const levelMeta = {
      very_low:  'wcq-level-very-low',
      low:       'wcq-level-low',
      medium:    'wcq-level-medium',
      high:      'wcq-level-high',
      very_high: 'wcq-level-very-high',
    };

    const rows = order.map((subId) => {
      const sub = subscales[subId];
      if (!sub) return '';
      const css = levelMeta[sub.level] || '';
      return `
        <tr>
          <td class="wcq-profile-name">${sub.name}</td>
          <td><span class="wcq-level-badge ${css}">${sub.level_label || '—'}</span></td>
        </tr>`;
    }).join('');

    return `
      <div class="wcq-thank-you"><p>${message}</p></div>
      <div class="wcq-profile">
        <div class="wcq-profile-title">Ваш профиль совладания</div>
        <table class="wcq-profile-table">
          <thead>
            <tr><th>Стратегия</th><th>Уровень использования</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
        <p class="wcq-profile-note">
          Уровень показывает, как часто вы используете эту стратегию по сравнению с общей популяцией.
          Одна и та же стратегия может помогать или мешать в зависимости от ситуации.
        </p>
      </div>
      <div class="hads-actions">
        <a class="secondary-button" href="/patient/vitals">↩ Вернуться в кабинет</a>
      </div>`;
  }

  function showResult(payload) {
    if (!resultBlock) return;
    resultBlock.innerHTML = buildProfileHtml(payload?.result);
    progressText.textContent = 'Опрос завершён';
    progressFill.style.width = '100%';
    if (periodLabel) periodLabel.hidden = true;
    questionContainer.classList.add('hidden');
    resultBlock.classList.remove('hidden');
  }

  // ── Отправка ───────────────────────────────────────────────
  function submitAnswers() {
    if (isSubmitting) return;
    isSubmitting = true;
    progressText.textContent = 'Сохраняем ответы…';

    // Фильтруем пустые ячейки на случай нелинейной навигации (не должно быть, но страховка)
    const payload = answers.filter(Boolean);

    fetch('/api/v1/scales/WCQ_LAZARUS/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ answers: payload }),
    })
      .then(async (resp) => {
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err?.detail || 'Не удалось сохранить ответы. Попробуйте позже.');
        }
        return resp.json();
      })
      .then((data) => { clearStatus(); showResult(data); })
      .catch((err) => { showStatus(err.message || 'Ошибка отправки.'); isSubmitting = false; });
  }

  // ── Загрузка вопросов ──────────────────────────────────────
  function loadQuestions() {
    if (!questionContainer) return;
    questionContainer.innerHTML = '<div class="hads-loader">Загружаем вопросы…</div>';

    fetch('/api/v1/scales/WCQ_LAZARUS', { credentials: 'include' })
      .then((resp) => {
        if (!resp.ok) throw new Error('Не удалось получить опросник WCQ.');
        return resp.json();
      })
      .then((data) => {
        wcqQuestions = data?.questions || [];
        if (!wcqQuestions.length) throw new Error('Список вопросов пуст.');

        // Инициализируем массив ответов (все null)
        answers = new Array(wcqQuestions.length).fill(null);
        currentIndex = 0;
        isSubmitting = false;

        if (periodLabel) periodLabel.hidden = false;
        updateProgress();
        renderQuestion();
      })
      .catch((err) => {
        questionContainer.innerHTML = `<div class="hads-error-text">${err.message}</div>`;
        showStatus(err.message || 'Ошибка загрузки.', 'error');
      });
  }

  document.addEventListener('DOMContentLoaded', loadQuestions);
})();
