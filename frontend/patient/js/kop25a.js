(function () {
  let questions = [];
  let currentIndex = 0;
  const answersMap = {};
  let isSubmitting = false;

  const container = document.getElementById('kop25a-container');
  const progressText = document.getElementById('kop25a-progress-text');
  const progressFill = document.getElementById('kop25a-progress-fill');
  const prevButton = document.getElementById('kop25a-prev');
  const nextButton = document.getElementById('kop25a-next');
  const submitButton = document.getElementById('submit-kop25a');
  const statusBanner = document.getElementById('kop25a-status');

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

  function interpretAdherence(value) {
    if (value < 50) {
      return {
        level: 'low',
        color: '#ff7518',
        boxClass: 'result-box-low',
        label: 'Низкая приверженность',
        text: 'Похоже, что сейчас выполнять рекомендации бывает непросто. Это нормальная ситуация — многие пациенты сталкиваются с похожими трудностями. Можно обсудить с врачом, как упростить лечение и подобрать более удобный режим.',
      };
    }

    if (value < 75) {
      return {
        level: 'moderate',
        color: '#fbbf24',
        boxClass: 'result-box-moderate',
        label: 'Умеренная приверженность',
        text: 'Вы в целом стараетесь следовать рекомендациям, но временами это сложно. Небольшие изменения в режиме лечения могут заметно облегчить выполнение рекомендаций.',
      };
    }

    return {
      level: 'high',
      color: '#22c55e',
      boxClass: 'result-box-high',
      label: 'Высокая приверженность',
      text: 'Вы хорошо справляетесь с выполнением рекомендаций. Это помогает поддерживать стабильное состояние. Продолжайте в комфортном для вас темпе.',
    };
  }

  function getMiniBoxHtml(value, title) {
  if (value == null || Number.isNaN(value)) {
    return '';
  }

  const info = interpretAdherence(value);

  return `
    <div class="result-mini-box ${info.boxClass}">
      <div class="mini-title">${title}</div>
      <div class="mini-value">${value.toFixed(1)}%</div>
    </div>
  `;
}

  async function initKop25a() {
    if (!container) return;

    container.innerHTML = '<div class="hads-loader">Загружаем вопросы…</div>';
    clearStatus();

    try {
      const response = await fetch('/api/v1/scales/KOP25A');
      if (!response.ok) {
        throw new Error('Не удалось получить шкалу КОП-25 А1.');
      }

      const definition = await response.json();
      questions = definition.questions || [];
      currentIndex = 0;

      renderCurrentQuestion();
      updateProgress();
      updateNavButtons();
    } catch (err) {
      container.innerHTML = `<div class="hads-error-text">${err.message}</div>`;
      showStatus(err.message || 'Ошибка загрузки.');
    }
  }

  function renderCurrentQuestion() {
    if (!container) return;

    container.innerHTML = '';

    const question = questions[currentIndex];
    if (!question) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'scale-question';

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

  function updateProgress() {
    const total = questions.length || 25;
    const current = currentIndex + 1;

    if (progressText) {
      progressText.textContent = `Вопрос ${current} из ${total}`;
    }

    if (progressFill) {
      progressFill.style.width = `${(current / total) * 100}%`;
    }
  }

  function updateNavButtons() {
    const lastIndex = questions.length - 1;

    if (!questions.length) return;

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
      submitButton.disabled = !answered;
    }
  }

  async function submitKop25a() {
    if (isSubmitting) return;

    const answers = Object.entries(answersMap).map(([question_id, option_id]) => ({
      question_id,
      option_id,
    }));

    try {
      isSubmitting = true;
      updateNextAndSubmitState();

      const response = await fetch('/api/v1/scales/KOP25A/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers }),
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
      showResultWindow(data);
    } catch (err) {
      alert(err.message || 'Ошибка при отправке данных.');
    } finally {
      isSubmitting = false;
    }
  }

  function showResultWindow(apiResult) {
    const resultBlock = document.getElementById('result-container');
    const progress = document.querySelector('.scale-progress');
    const nav = document.querySelector('.scale-nav');

    // прячем вопросы, прогресс и навигацию
    if (container) container.innerHTML = '';
    if (progress) progress.classList.add('hidden');
    if (nav) nav.classList.add('hidden');

    if (!resultBlock) return;

    resultBlock.classList.remove('hidden');

    const a = apiResult?.result?.adherence || {};
    const PL = a.PL ?? null;
    const PT = a.PT ?? null;
    const PS = a.PS ?? null;
    const PM = a.PM ?? null;

    const interp = PL != null ? interpretAdherence(PL) : null;

    resultBlock.innerHTML = `
      <div class="kop25a-result-window">
        <h2>Ваш результат</h2>
  
        ${
          interp
            ? `
        <div class="result-main ${interp.boxClass}">
          <div class="result-score">${PL.toFixed(1)}%</div>
          <div class="result-label" style="color: ${interp.color}">
            ${interp.label}
          </div>
          <div class="result-text">${interp.text}</div>
        </div>
        `
            : ''
        }
  
        <h3>Подробности по направлениям</h3>
        <div class="mini-grid">
          ${PT != null && PT.toFixed ? getMiniBoxHtml(PT, 'Лекарственная терапия') : ''}
          ${PS != null && PS.toFixed ? getMiniBoxHtml(PS, 'Медицинское сопровождение') : ''}
          ${PM != null && PM.toFixed ? getMiniBoxHtml(PM, 'Образ жизни') : ''}
        </div>
  
        <h3>Числовые значения</h3>
        <div class="result-line">Лекарственная терапия: ${PT?.toFixed ? PT.toFixed(1) : '-'}%</div>
        <div class="result-line">Медицинское сопровождение: ${PS?.toFixed ? PS.toFixed(1) : '-'}%</div>
        <div class="result-line">Образ жизни: ${PM?.toFixed ? PM.toFixed(1) : '-'}%</div>
      </div>
    `;
  }


  document.addEventListener('DOMContentLoaded', () => {
    initKop25a();

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

    submitButton?.addEventListener('click', submitKop25a);
  });
})();
