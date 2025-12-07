(function () {
  const container = document.getElementById('kop25a-container');
  const submitButton = document.getElementById('submit-kop25a');
  const statusBanner = document.getElementById('kop25a-status');
  const resultContainer = document.getElementById('result-container');
  const progressText = document.getElementById('kop25a-progress-text');
  const progressFill = document.getElementById('kop25a-progress-fill');
  const prevButton = document.getElementById('kop25a-prev');
  const nextButton = document.getElementById('kop25a-next');

  let definition = null;
  let questions = [];
  let currentIndex = 0;
  const answersMap = {};
  let isSubmitting = false;

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
    const current = currentIndex + 1;
    const total = questions.length || 25;

    if (progressText) {
      progressText.textContent = `Вопрос ${current} из ${total}`;
    }

    if (progressFill) {
      const percent = (current / total) * 100;
      progressFill.style.width = `${percent}%`;
    }
  }

  function updateNavButtons() {
    if (!questions.length) return;

    const lastIndex = questions.length - 1;

    if (prevButton) {
      prevButton.disabled = currentIndex === 0;
    }

    if (nextButton) {
      nextButton.style.display = currentIndex === lastIndex ? 'none' : 'inline-flex';
    }

    if (submitButton) {
      submitButton.style.display = currentIndex === lastIndex ? 'inline-flex' : 'none';
      submitButton.disabled = !answersMap[questions[currentIndex].id];
    }
  }

  function updateNextButtonState() {
    const q = questions[currentIndex];
    const answered = !!answersMap[q.id];

    if (nextButton && nextButton.style.display !== 'none') {
      nextButton.disabled = !answered;
    }

    if (submitButton && submitButton.style.display !== 'none') {
      submitButton.disabled = !answered;
    }
  }

  function renderCurrentQuestion() {
    if (!container) return;

    container.innerHTML = '';

    const question = questions[currentIndex];
    if (!question) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'scale-question';

    const title = document.createElement('div');
    title.className = 'question-title';
    title.textContent = `Вопрос ${currentIndex + 1}`;

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

        updateNextButtonState();
      });

      options.appendChild(btn);
    });

    wrapper.appendChild(title);
    wrapper.appendChild(qText);
    wrapper.appendChild(options);
    container.appendChild(wrapper);

    updateNextButtonState();
  }

  function formatPercent(value) {
    if (value === undefined || value === null || Number.isNaN(value)) return '—';
    return `${value}%`;
  }

  function showResult(payload) {
    if (!resultContainer) return;

    const { result, measured_at: measuredAt } = payload || {};
    const adherence = result?.adherence || {};
    const main = formatPercent(adherence.PL);
    const pt = formatPercent(adherence.PT);
    const ps = formatPercent(adherence.PS);
    const pm = formatPercent(adherence.PM);

    const measuredText = measuredAt
      ? `<div class="hads-helper-text">Измерение: ${new Date(measuredAt).toLocaleString('ru-RU')}</div>`
      : '';

    resultContainer.innerHTML = `
      <h3>Ваши результаты</h3>
      <div class="result-main">Приверженность лечению: ${main}</div>
      <ul>
        <li>Лекарственная терапия (PT): ${pt}</li>
        <li>Медицинское сопровождение (PS): ${ps}</li>
        <li>Образ жизни (PM): ${pm}</li>
      </ul>
      ${measuredText}
    `;

    resultContainer.classList.remove('hidden');
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = 'Готово';
    }
  }

  function collectAnswers() {
    return Object.entries(answersMap).map(([question_id, option_id]) => ({
      question_id,
      option_id,
    }));
  }

  function submitAnswers() {
    if (isSubmitting) return;
    if (!definition) return;

    clearStatus();
    const answers = collectAnswers();

    if (!answers.length || answers.length !== (definition.questions || []).length) {
      showStatus('Ответьте на все вопросы, прежде чем завершить.');
      return;
    }

    isSubmitting = true;
    submitButton.disabled = true;
    submitButton.textContent = 'Сохраняем…';

    fetch('/api/v1/scales/KOP25A/submit', {
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
        submitButton.disabled = false;
        submitButton.textContent = 'Завершить';
        isSubmitting = false;
        showStatus(err.message || 'Ошибка отправки.');
      });
  }

  function loadDefinition() {
    if (!container) return;

    container.innerHTML = '<div class="hads-loader">Загружаем вопросы…</div>';

    fetch('/api/v1/scales/KOP25A')
      .then((resp) => {
        if (!resp.ok) {
          throw new Error('Не удалось получить шкалу КОП-25 А1.');
        }
        return resp.json();
      })
      .then((data) => {
        definition = data;
        questions = data?.questions || [];
        currentIndex = 0;
        renderCurrentQuestion();
        updateProgress();
        updateNavButtons();
        clearStatus();
      })
      .catch((err) => {
        container.innerHTML = `<div class="hads-error-text">${err.message}</div>`;
        showStatus(err.message || 'Ошибка загрузки.');
      });
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadDefinition();

    if (submitButton) {
      submitButton.addEventListener('click', submitAnswers);
    }

    if (prevButton) {
      prevButton.addEventListener('click', () => {
        if (currentIndex > 0) {
          currentIndex -= 1;
          renderCurrentQuestion();
          updateProgress();
          updateNavButtons();
        }
      });
    }

    if (nextButton) {
      nextButton.addEventListener('click', () => {
        if (currentIndex < questions.length - 1) {
          currentIndex += 1;
          renderCurrentQuestion();
          updateProgress();
          updateNavButtons();
        }
      });
    }
  });
})();
