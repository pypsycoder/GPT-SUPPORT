(function () {
  let questions = [];
  let currentIndex = 0;
  const answersMap = {};
  let isSubmitting = false;

  const container = document.getElementById('tobol-container');
  const progressText = document.getElementById('tobol-progress-text');
  const progressFill = document.getElementById('tobol-progress-fill');
  const prevButton = document.getElementById('tobol-prev');
  const nextButton = document.getElementById('tobol-next');
  const submitButton = document.getElementById('tobol-submit');
  const statusBanner = document.getElementById('tobol-status');
  const resultBlock = document.getElementById('tobol-result');

  function getPatientTokenFromPath() {
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
    statusBanner.classList.remove('status-hidden', 'status-error', 'status-success');
    statusBanner.classList.add(type === 'success' ? 'status-success' : 'status-error');
  }

  function clearStatus() {
    if (!statusBanner) return;

    statusBanner.textContent = '';
    statusBanner.classList.add('status-hidden');
    statusBanner.classList.remove('status-error', 'status-success');
  }

  function updateProgress() {
    const total = questions.length || 0;
    const current = currentIndex + 1;

    if (progressText) {
      progressText.textContent = total
        ? `Вопрос ${current} из ${total}`
        : 'Загружаем вопросы…';
    }

    if (progressFill) {
      const percent = total ? (current / total) * 100 : 0;
      progressFill.style.width = `${percent}%`;
    }
  }

  function updateNavButtons() {
    const lastIndex = questions.length - 1;

    if (prevButton) {
      prevButton.disabled = currentIndex === 0;
    }

    if (nextButton && submitButton) {
      if (currentIndex === lastIndex) {
        nextButton.style.display = 'none';
        submitButton.style.display = 'inline-flex';
      } else {
        nextButton.style.display = 'inline-flex';
        submitButton.style.display = 'none';
      }
    }

    updateNextAndSubmitState();
  }

  function updateNextAndSubmitState() {
    const q = questions[currentIndex];
    const answered = q ? !!answersMap[q.id] : false;

    if (nextButton && nextButton.style.display !== 'none') {
      nextButton.disabled = !answered;
    }
    if (submitButton && submitButton.style.display !== 'none') {
      submitButton.disabled = !answered || isSubmitting;
    }
  }

  function renderCurrentQuestion() {
    clearStatus();

    if (!container) return;
    container.innerHTML = '';

    const question = questions[currentIndex];
    if (!question) {
      container.innerHTML = '<div class="hads-error-text">Не удалось загрузить вопрос.</div>';
      return;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'scale-question';

    const section = question.section_title;
    if (section) {
      const sectionLabel = document.createElement('div');
      sectionLabel.className = 'scale-progress-text';
      sectionLabel.textContent = section;
      wrapper.appendChild(sectionLabel);
    }

    const qText = document.createElement('div');
    qText.className = 'scale-question-text';
    qText.textContent = question.text;

    const options = document.createElement('div');
    options.className = 'scale-options';

    question.options.forEach((opt) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'scale-option';
      btn.textContent = opt.text;
      btn.dataset.questionId = question.id;
      btn.dataset.optionId = opt.id;

      if (answersMap[question.id] === opt.id) {
        btn.classList.add('selected');
      }

      btn.addEventListener('click', () => {
        if (isSubmitting) return;

        answersMap[question.id] = opt.id;

        [...options.children].forEach((c) => c.classList.remove('selected'));
        btn.classList.add('selected');

        updateNextAndSubmitState();
      });

      options.appendChild(btn);
    });

    wrapper.appendChild(qText);
    wrapper.appendChild(options);
    container.appendChild(wrapper);

    updateNextAndSubmitState();
  }

  async function submitTobol() {
    if (isSubmitting) return;

    const answers = Object.entries(answersMap).map(([question_id, option_id]) => ({
      question_id,
      option_id,
    }));

    const patientToken = getPatientTokenFromPath();
    if (!patientToken) {
      showStatus('Не найден токен пациента в адресе.');
      return;
    }

    try {
      isSubmitting = true;
      updateNextAndSubmitState();

      const response = await fetch('/api/v1/scales/TOBOL/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patient_token: patientToken, answers }),
      });

      if (!response.ok) {
        let errText = 'Ошибка при отправке данных.';
        try {
          const err = await response.json();
          if (err.detail) errText = err.detail;
        } catch (e) {
          // ignore
        }
        throw new Error(errText);
      }

      const data = await response.json();
      showResult(data);
      showStatus('Результаты получены.', 'success');
    } catch (err) {
      showStatus(err.message || 'Ошибка при отправке данных.');
    } finally {
      isSubmitting = false;
      updateNextAndSubmitState();
    }
  }

  function showResult(data) {
    if (container) {
      container.innerHTML = '';
    }

    document.querySelector('.scale-progress')?.classList.add('hidden');
    document.querySelector('.scale-nav')?.classList.add('hidden');

    if (!resultBlock) return;

    resultBlock.classList.remove('hidden');

    const result = data?.result || {};
    const summary = result.summary || 'Результат получен.';
    const totalScore = result.total_score;
    const measuredAt = data?.measured_at;

    resultBlock.innerHTML = `
      <h2>Результаты ТОБОЛ</h2>
      <div class="result-text">${summary}</div>
      ${totalScore != null ? `<div class="result-line">Максимальный балл среди типов: ${totalScore}</div>` : ''}
      ${
        measuredAt
          ? `<div class="result-line">Дата измерения: ${new Date(measuredAt).toLocaleString('ru-RU')}</div>`
          : ''
      }
      <div class="result-text" style="margin-top: 12px;">Сохраните результат, чтобы обсудить его с врачом.</div>
    `;
  }

  async function loadQuestions() {
    if (!container) return;

    container.innerHTML = '<div class="hads-loader">Загружаем вопросы…</div>';
    clearStatus();

    try {
      const response = await fetch('/api/v1/scales/TOBOL');
      if (!response.ok) {
        throw new Error('Не удалось получить шкалу ТОБОЛ.');
      }

      const definition = await response.json();
      questions = definition.questions || [];
      currentIndex = 0;
      Object.keys(answersMap).forEach((key) => delete answersMap[key]);

      if (!questions.length) {
        throw new Error('Список вопросов пуст.');
      }

      renderCurrentQuestion();
      updateProgress();
      updateNavButtons();
    } catch (err) {
      container.innerHTML = `<div class="hads-error-text">${err.message}</div>`;
      showStatus(err.message || 'Ошибка загрузки.');
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadQuestions();

    prevButton?.addEventListener('click', () => {
      if (currentIndex > 0) {
        currentIndex -= 1;
        renderCurrentQuestion();
        updateProgress();
        updateNavButtons();
      }
    });

    nextButton?.addEventListener('click', () => {
      if (currentIndex < questions.length - 1) {
        currentIndex += 1;
        renderCurrentQuestion();
        updateProgress();
        updateNavButtons();
      }
    });

    submitButton?.addEventListener('click', submitTobol);
  });
})();
