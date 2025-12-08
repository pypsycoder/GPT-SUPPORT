(function () {
  let blocks = [];
  let currentBlockIndex = 0;
  const answersByBlock = {};
  const questionOptionMap = {};
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

  function buildBlocks(questions = []) {
    const bySection = new Map();
    questionOptionMap && Object.keys(questionOptionMap).forEach((key) => delete questionOptionMap[key]);

    questions.forEach((q) => {
      if (!bySection.has(q.section)) {
        bySection.set(q.section, { code: q.section, title: q.section_title || '', items: [] });
      }
      const section = bySection.get(q.section);
      section.items.push({ id: q.id, text: q.text });

      if (Array.isArray(q.options) && q.options.length) {
        questionOptionMap[q.id] = q.options[0].id ?? '1';
      }
    });

    blocks = Array.from(bySection.values());
    currentBlockIndex = 0;
    Object.keys(answersByBlock).forEach((key) => delete answersByBlock[key]);
  }

  function updateProgress() {
    const total = blocks.length || 0;
    const current = currentBlockIndex + 1;

    if (progressText) {
      progressText.textContent = total ? `Блок ${current} из ${total}` : 'Загружаем блоки…';
    }

    if (progressFill) {
      const percent = total ? (current / total) * 100 : 0;
      progressFill.style.width = `${percent}%`;
    }
  }

  function updateNavButtons() {
    const lastIndex = blocks.length - 1;

    if (prevButton) {
      prevButton.disabled = currentBlockIndex === 0;
    }

    if (nextButton && submitButton) {
      if (currentBlockIndex === lastIndex) {
        nextButton.style.display = 'none';
        submitButton.style.display = 'inline-flex';
      } else {
        nextButton.style.display = 'inline-flex';
        submitButton.style.display = 'none';
      }
    }

    updateSubmitState();
  }

  function updateSubmitState() {
    if (!submitButton) return;
    const isLastBlock = currentBlockIndex === blocks.length - 1;
    submitButton.disabled = !isLastBlock || isSubmitting;
  }

  function renderCurrentBlock() {
    clearStatus();

    if (!container) return;
    container.innerHTML = '';

    const block = blocks[currentBlockIndex];
    if (!block) {
      container.innerHTML = '<div class="hads-error-text">Не удалось загрузить блок.</div>';
      return;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'scale-question';

    const sectionLabel = document.createElement('div');
    sectionLabel.className = 'scale-progress-text';
    sectionLabel.textContent = `Блок ${block.code}. ${block.title || ''}`.trim();
    wrapper.appendChild(sectionLabel);

    const hint = document.createElement('div');
    hint.className = 'scale-question-text';
    hint.textContent = 'Выберите не более двух утверждений. Можно ничего не выбирать, если ни одно не подходит.';
    wrapper.appendChild(hint);

    const options = document.createElement('div');
    options.className = 'scale-options';

    const selectedIds = new Set(answersByBlock[block.code] || []);

    block.items.forEach((item) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'scale-option';
      btn.textContent = item.text;

      if (selectedIds.has(item.id)) {
        btn.classList.add('selected');
      }

      btn.addEventListener('click', () => {
        const currentSelections = new Set(answersByBlock[block.code] || []);

        if (currentSelections.has(item.id)) {
          currentSelections.delete(item.id);
          btn.classList.remove('selected');
          clearStatus();
        } else {
          if (currentSelections.size >= 2) {
            showStatus('Можно выбрать не более двух утверждений в одном блоке.');
            return;
          }
          currentSelections.add(item.id);
          btn.classList.add('selected');
          clearStatus();
        }

        answersByBlock[block.code] = Array.from(currentSelections);
      });

      options.appendChild(btn);
    });

    wrapper.appendChild(options);
    container.appendChild(wrapper);
  }

  async function submitTobol() {
    if (isSubmitting) return;

    const answers = [];
    blocks.forEach((block) => {
      const selectedIds = answersByBlock[block.code] || [];
      selectedIds.forEach((question_id) => {
        answers.push({
          question_id,
          option_id: questionOptionMap[question_id] || '1',
        });
      });
    });

    const patientToken = getPatientTokenFromPath();
    if (!patientToken) {
      showStatus('Не найден токен пациента в адресе.');
      return;
    }

    if (!answers.length) {
      showStatus('Выберите хотя бы одно утверждение перед отправкой.');
      return;
    }

    try {
      isSubmitting = true;
      updateSubmitState();

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
      updateSubmitState();
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
      const questions = definition.questions || [];

      if (!questions.length) {
        throw new Error('Список вопросов пуст.');
      }

      buildBlocks(questions);
      renderCurrentBlock();
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
      if (currentBlockIndex > 0) {
        currentBlockIndex -= 1;
        renderCurrentBlock();
        updateProgress();
        updateNavButtons();
      }
    });

    nextButton?.addEventListener('click', () => {
      if (currentBlockIndex < blocks.length - 1) {
        currentBlockIndex += 1;
        renderCurrentBlock();
        updateProgress();
        updateNavButtons();
      }
    });

    submitButton?.addEventListener('click', submitTobol);
  });
})();
