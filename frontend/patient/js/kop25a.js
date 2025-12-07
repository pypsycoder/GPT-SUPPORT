(function () {
  const container = document.getElementById('kop25a-container');
  const submitButton = document.getElementById('submit-kop25a');
  const statusBanner = document.getElementById('kop25a-status');
  const resultContainer = document.getElementById('result-container');

  let definition = null;
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

  function renderQuestions(scaleDefinition) {
    if (!container) return;

    container.innerHTML = '';

    const questions = scaleDefinition?.questions || [];
    if (!questions.length) {
      container.innerHTML = '<div class="hads-error-text">Не удалось загрузить вопросы.</div>';
      return;
    }

    questions.forEach((question, index) => {
      const block = document.createElement('div');
      block.className = 'scale-question';

      const title = document.createElement('div');
      title.className = 'question-title';
      title.textContent = `Вопрос ${index + 1}`;

      const text = document.createElement('div');
      text.className = 'question-text';
      text.textContent = question.text;

      const optionsWrap = document.createElement('div');
      optionsWrap.className = 'scale-options';

      question.options.forEach((opt) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'scale-option';
        btn.textContent = opt.text;
        btn.dataset.questionId = question.id;
        btn.dataset.optionId = opt.id;

        btn.addEventListener('click', () => {
          if (isSubmitting) return;

          const siblings = optionsWrap.querySelectorAll('.scale-option');
          siblings.forEach((el) => el.classList.remove('selected'));
          btn.classList.add('selected');
        });

        optionsWrap.appendChild(btn);
      });

      block.appendChild(title);
      block.appendChild(text);
      block.appendChild(optionsWrap);

      container.appendChild(block);
    });
  }

  function collectAnswers() {
    return [...document.querySelectorAll('.scale-option.selected')].map((btn) => ({
      question_id: btn.dataset.questionId,
      option_id: btn.dataset.optionId,
    }));
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
        renderQuestions(definition);
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
  });
})();
