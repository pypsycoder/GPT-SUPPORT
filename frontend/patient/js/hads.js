(function () {
  let hadsQuestions = [];
  let currentIndex = 0;
  let answers = [];
  let isSubmitting = false;

  const questionContainer = document.getElementById('hads-question-container');
  const progressText = document.getElementById('hads-progress-text');
  const progressFill = document.getElementById('hads-progress-fill');
  const statusBanner = document.getElementById('hads-status');
  const resultBlock = document.getElementById('hads-result');

  function getPatientTokenFromPath() {
    if (window.PatientAuth) {
      return window.PatientAuth.getPatientToken();
    }
    const parts = window.location.pathname.split('/').filter(Boolean);
    const pIndex = parts.indexOf('p');
    if (pIndex !== -1 && parts.length > pIndex + 1) {
      return parts[pIndex + 1];
    }
    return null;
  }

  function showStatus(message, type = 'error') {
    if (!statusBanner) return;

    statusBanner.textContent = message;
    statusBanner.classList.remove('status-hidden', 'status-success', 'status-error');

    if (type === 'success') {
      statusBanner.classList.add('status-success');
    } else {
      statusBanner.classList.add('status-error');
    }
  }

  function clearStatus() {
    if (!statusBanner) return;
    statusBanner.textContent = '';
    statusBanner.classList.add('status-hidden');
    statusBanner.classList.remove('status-success', 'status-error');
  }

  function updateProgress() {
    if (!hadsQuestions.length) return;

    const currentNumber = Math.min(currentIndex + 1, hadsQuestions.length);
    progressText.textContent = `Вопрос ${currentNumber} из ${hadsQuestions.length}`;

    const percent = Math.min((currentIndex / hadsQuestions.length) * 100, 100);
    progressFill.style.width = `${percent}%`;
  }

  function renderQuestion() {
    clearStatus();

    if (!questionContainer) return;

    questionContainer.innerHTML = '';

    if (!hadsQuestions.length) {
      questionContainer.innerHTML = '<div class="hads-error-text">Не удалось загрузить вопросы. Попробуйте обновить страницу.</div>';
      return;
    }

    if (currentIndex >= hadsQuestions.length) {
      submitAnswers();
      return;
    }

    const question = hadsQuestions[currentIndex];
    updateProgress();

    const card = document.createElement('div');
    card.className = 'hads-question-card';

    const text = document.createElement('div');
    text.className = 'hads-question-text';
    text.textContent = question.text;

    const optionsWrapper = document.createElement('div');
    optionsWrapper.className = 'hads-options';

    question.options.forEach((opt) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'hads-option-btn';
      btn.textContent = opt.text;
      btn.dataset.optionId = opt.id;

      btn.addEventListener('click', () => {
        if (isSubmitting) return;

        answers.push({
          question_id: question.id,
          option_id: opt.id,
        });
        currentIndex += 1;
        renderQuestion();
      });

      optionsWrapper.appendChild(btn);
    });

    card.appendChild(text);
    card.appendChild(optionsWrapper);

    questionContainer.appendChild(card);
  }

  function buildAdvice(result) {
    const anxietyLevel = result?.ANX?.level || '';
    const depressionLevel = result?.DEP?.level || '';

    if (anxietyLevel === 'clinical' || depressionLevel === 'clinical') {
      return 'Рекомендуется обсудить результат с лечащим врачом.';
    }

    if (anxietyLevel === 'normal' && depressionLevel === 'normal') {
      return 'Выраженных признаков тревоги и депрессии по этой шкале сейчас не выявлено.';
    }

    return 'Обратите внимание на своё самочувствие и при необходимости обсудите результат со специалистом.';
  }

  function showResult(payload) {
    if (!resultBlock) return;

    const { result, measured_at: measuredAt } = payload || {};
    const anxiety = result?.ANX;
    const depression = result?.DEP;

    const advice = buildAdvice(result);
    const dashboardUrl = (() => {
      const token = getPatientTokenFromPath();
      return token
        ? `/patient/vitals`
        : '/frontend/patient/vitals.html';
    })();

    const measuredText = measuredAt ? `<div class="hads-helper-text">Время измерения: ${new Date(measuredAt).toLocaleString('ru-RU')}</div>` : '';

    resultBlock.innerHTML = `
      <h2>Результат по шкале HADS</h2>
      <div class="hads-score-row">Тревога: ${anxiety?.score ?? '—'} баллов — ${anxiety?.label ?? 'нет данных'}</div>
      <div class="hads-score-row">Депрессия: ${depression?.score ?? '—'} баллов — ${depression?.label ?? 'нет данных'}</div>
      ${measuredText}
      <div class="hads-advice">${advice}</div>
      <div class="hads-actions">
        <a class="secondary-button" href="${dashboardUrl}">↩️ Вернуться в кабинет</a>
      </div>
    `;

    progressText.textContent = 'Опрос завершён';
    progressFill.style.width = '100%';

    questionContainer.classList.add('hidden');
    resultBlock.classList.remove('hidden');
  }

  function submitAnswers() {
    if (isSubmitting) return;
    isSubmitting = true;

    progressText.textContent = 'Сохраняем ответы…';

    fetch('/api/v1/scales/HADS/submit', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ answers }),
    })
      .then(async (resp) => {
        if (!resp.ok) {
          const errorData = await resp.json().catch(() => ({}));
          const detail = errorData?.detail || 'Не удалось сохранить ответы. Попробуйте позже.';
          throw new Error(detail);
        }
        return resp.json();
      })
      .then((payload) => {
        clearStatus();
        showResult(payload);
      })
      .catch((err) => {
        showStatus(err.message || 'Ошибка отправки.');
        isSubmitting = false;
      });
  }

  function loadQuestions() {
    if (!questionContainer) return;

    questionContainer.innerHTML = '<div class="hads-loader">Загружаем вопросы…</div>';

    fetch('/api/v1/scales/HADS')
      .then((resp) => {
        if (!resp.ok) {
          throw new Error('Не удалось получить шкалу HADS.');
        }
        return resp.json();
      })
      .then((data) => {
        hadsQuestions = data?.questions || [];
        currentIndex = 0;
        answers = [];
        isSubmitting = false;

        if (!hadsQuestions.length) {
          throw new Error('Список вопросов пуст.');
        }

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
