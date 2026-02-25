(function () {
  let pss10Questions = [];
  let currentIndex = 0;
  let answers = [];
  let isSubmitting = false;

  const questionContainer = document.getElementById('pss10-question-container');
  const progressText = document.getElementById('pss10-progress-text');
  const progressFill = document.getElementById('pss10-progress-fill');
  const statusBanner = document.getElementById('pss10-status');
  const resultBlock = document.getElementById('pss10-result');

  function showStatus(message, type) {
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

  function updateProgress() {
    if (!pss10Questions.length) return;
    const currentNumber = Math.min(currentIndex + 1, pss10Questions.length);
    progressText.textContent = 'Вопрос ' + currentNumber + ' из ' + pss10Questions.length;
    const percent = Math.min((currentIndex / pss10Questions.length) * 100, 100);
    progressFill.style.width = percent + '%';
  }

  function renderQuestion() {
    clearStatus();
    if (!questionContainer) return;

    questionContainer.innerHTML = '';

    if (!pss10Questions.length) {
      questionContainer.innerHTML = '<div class="hads-error-text">Не удалось загрузить вопросы. Попробуйте обновить страницу.</div>';
      return;
    }

    if (currentIndex >= pss10Questions.length) {
      submitAnswers();
      return;
    }

    const question = pss10Questions[currentIndex];
    updateProgress();

    const card = document.createElement('div');
    card.className = 'hads-question-card';

    const text = document.createElement('div');
    text.className = 'hads-question-text';
    text.textContent = question.text;

    const optionsWrapper = document.createElement('div');
    optionsWrapper.className = 'hads-options';

    question.options.forEach(function (opt) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'hads-option-btn';
      btn.textContent = opt.text;
      btn.dataset.optionId = opt.id;

      btn.addEventListener('click', function () {
        if (isSubmitting) return;
        answers.push({ question_id: question.id, option_id: opt.id });
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
    var level = result && result.level;
    if (level === 'high') {
      return result.patient_advice || 'Уровень стресса сейчас высокий. Важно обсудить это с врачом.';
    }
    if (level === 'low') {
      return result.patient_advice || 'Уровень стресса сейчас невысокий — вы справляетесь с нагрузками.';
    }
    return result && result.patient_advice
      ? result.patient_advice
      : 'Обратите внимание на своё самочувствие.';
  }

  function showResult(payload) {
    if (!resultBlock) return;

    var result = payload && payload.result;
    var measuredAt = payload && payload.measured_at;
    var totalScore = result && result.total_score !== undefined ? result.total_score : '—';
    var label = (result && result.label) || '—';
    var subscales = (result && result.subscales) || {};
    var stressScore = subscales.perceived_stress && subscales.perceived_stress.score !== undefined
      ? subscales.perceived_stress.score : '—';
    var copingScore = subscales.perceived_coping && subscales.perceived_coping.score !== undefined
      ? subscales.perceived_coping.score : '—';
    var advice = buildAdvice(result);
    var dashboardUrl = '/patient/vitals';

    var measuredText = measuredAt
      ? '<div class="hads-helper-text">Время измерения: ' + new Date(measuredAt).toLocaleString('ru-RU') + '</div>'
      : '';

    resultBlock.innerHTML = [
      '<h2>Результат по шкале ШВС-10</h2>',
      '<div class="hads-score-row">Общий балл: <strong>' + totalScore + '</strong> — ' + label + '</div>',
      '<div class="hads-score-row pss10-subscale">Воспринимаемый стресс: ' + stressScore + ' баллов</div>',
      '<div class="hads-score-row pss10-subscale">Воспринимаемый контроль: ' + copingScore + ' баллов</div>',
      measuredText,
      '<div class="hads-advice">' + advice + '</div>',
      '<div class="hads-actions">',
      '  <a class="secondary-button" href="' + dashboardUrl + '">↩️ Вернуться в кабинет</a>',
      '</div>',
    ].join('');

    progressText.textContent = 'Опрос завершён';
    progressFill.style.width = '100%';

    questionContainer.classList.add('hidden');
    resultBlock.classList.remove('hidden');
  }

  function submitAnswers() {
    if (isSubmitting) return;
    isSubmitting = true;

    progressText.textContent = 'Сохраняем ответы…';

    fetch('/api/v1/scales/PSS10/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ answers: answers }),
    })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().catch(function () { return {}; }).then(function (errorData) {
            throw new Error(errorData.detail || 'Не удалось сохранить ответы. Попробуйте позже.');
          });
        }
        return resp.json();
      })
      .then(function (payload) {
        clearStatus();
        showResult(payload);
      })
      .catch(function (err) {
        showStatus(err.message || 'Ошибка отправки.', 'error');
        isSubmitting = false;
      });
  }

  function loadQuestions() {
    if (!questionContainer) return;

    questionContainer.innerHTML = '<div class="hads-loader">Загружаем вопросы…</div>';

    fetch('/api/v1/scales/PSS10', { credentials: 'include' })
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error('Не удалось получить шкалу ШВС-10.');
        }
        return resp.json();
      })
      .then(function (data) {
        pss10Questions = (data && data.questions) || [];
        currentIndex = 0;
        answers = [];
        isSubmitting = false;

        if (!pss10Questions.length) {
          throw new Error('Список вопросов пуст.');
        }

        updateProgress();
        renderQuestion();
      })
      .catch(function (err) {
        questionContainer.innerHTML = '<div class="hads-error-text">' + err.message + '</div>';
        showStatus(err.message || 'Ошибка загрузки.', 'error');
      });
  }

  document.addEventListener('DOMContentLoaded', loadQuestions);
})();
