/**
 * KDQOL-SF 1.3 — Wizard-style questionnaire
 *
 * Flow:
 *   1. GET /api/v1/patient/kdqol/pending
 *      → null  → waiting screen
 *      → point → load questions
 *   2. GET /api/v1/patient/kdqol/questions
 *   3. Build flat steps list (grids with ≥4 subitems → individual screens)
 *   4. Show start screen → step-by-step wizard with back button
 *   5. POST /api/v1/patient/kdqol/submit
 *   6. Show result / thanks screen
 *
 * Question types handled:
 *   single       – auto-advance on option click; back button below
 *   grid (<4)    – all subitems in table/stacked on one screen; nav row
 *   grid (≥4)    – each subitem = separate screen, auto-advance; back button
 *   scale        – 0-10 slider (Q17); nav row
 *   number       – numeric input (Q25a, Q26, Q27); nav row
 *   multiple     – checkboxes (Q28); nav row
 *   date         – date picker (Q29); nav row
 *   skip         – filtered out entirely (Q35)
 *
 * Special cases:
 *   Q20  optional: true  → show Пропустить button (only 2 subitems, not split)
 *   Q25a condition: "25 == 2" → show only when Q25 answered Да
 *   Q38  auto-fill today's date → added silently to submission
 */
(function () {
  'use strict';

  // ─── STATE ────────────────────────────────────────────────────────────────

  /** @type {{id: number, patient_id: number, point_type: string, activated_at: string, completed_at: string|null, is_completed: boolean}|null} */
  var pendingPoint = null;

  /** @type {Array<Object>} raw questions array from API */
  var allQuestions = [];

  /**
   * Flat step list. Grid questions with ≥ 4 subitems are expanded into
   * individual virtual steps: { _gridSubitem, _parentQ, _subitem, _subitemIndex, _totalSubitems }
   */
  var steps = [];

  /** Currently visible steps (conditions evaluated) */
  var effectiveSteps = [];

  var currentStep = 0;

  /**
   * Accumulated answers.
   * Key = question_id (single/scale/number/date/multiple) OR subitem id (grid).
   * Value = numeric answer value.
   */
  var answers = {};

  /**
   * For multiple-choice Q28: { optionValue: boolean }
   */
  var multiSelected = {};

  var isSubmitting = false;

  // ─── DOM ──────────────────────────────────────────────────────────────────

  var container    = document.getElementById('kdqol-container');
  var progressText = document.getElementById('kdqol-progress-text');
  var progressFill = document.getElementById('kdqol-progress-fill');
  var statusBanner = document.getElementById('kdqol-status');

  // ─── STATUS BANNER ────────────────────────────────────────────────────────

  function showStatus(msg, type) {
    if (!statusBanner) return;
    statusBanner.textContent = msg;
    statusBanner.className = 'status-banner status-' + (type || 'error');
  }

  function clearStatus() {
    if (!statusBanner) return;
    statusBanner.textContent = '';
    statusBanner.className = 'status-banner status-hidden';
  }

  // ─── PROGRESS BAR ─────────────────────────────────────────────────────────

  function updateProgress(current, total) {
    if (!progressText || !progressFill) return;
    progressText.textContent = total
      ? 'Вопрос ' + Math.min(current + 1, total) + ' из ' + total
      : 'Загружаем…';
    var pct = total ? Math.min((current / total) * 100, 100) : 0;
    progressFill.style.width = pct + '%';
  }

  // ─── LOCAL STORAGE ────────────────────────────────────────────────────────

  function storageKey() {
    return pendingPoint ? 'kdqol_progress_' + pendingPoint.id : null;
  }

  function saveProgress() {
    var key = storageKey();
    if (!key) return;
    try {
      localStorage.setItem(key, JSON.stringify({
        currentStep: currentStep,
        answers: answers,
        multiSelected: multiSelected,
      }));
    } catch (_) {}
  }

  function loadProgress() {
    var key = storageKey();
    if (!key) return;
    try {
      var raw = localStorage.getItem(key);
      if (!raw) return;
      var d = JSON.parse(raw);
      currentStep   = d.currentStep   || 0;
      answers       = d.answers       || {};
      multiSelected = d.multiSelected || {};
    } catch (_) {}
  }

  function clearProgress() {
    var key = storageKey();
    if (key) {
      try { localStorage.removeItem(key); } catch (_) {}
    }
  }

  // ─── STEPS ────────────────────────────────────────────────────────────────

  /**
   * Build flat step list from raw questions.
   * Grid questions with ≥ 4 subitems are expanded into individual virtual steps.
   */
  function buildSteps(questions) {
    var result = [];
    questions.forEach(function (q) {
      if (q.type === 'skip' || q.id === '38') return;

      if (q.type === 'grid' && (q.subitems || []).length >= 4) {
        var subitems = q.subitems;
        var chunkSize = 3;
        var totalChunks = Math.ceil(subitems.length / chunkSize);
        for (var ci = 0; ci < totalChunks; ci++) {
          result.push({
            _gridSubitem: true,
            _parentQ: q,
            _subitems: subitems.slice(ci * chunkSize, (ci + 1) * chunkSize),
          });
        }
      } else {
        result.push(q);
      }
    });
    return result;
  }

  function buildEffectiveSteps() {
    return steps.filter(function (step) {
      var q = step._gridSubitem ? step._parentQ : step;
      if (!q.condition) return true;
      // Format: "25 == 2"
      var parts = q.condition.split(' == ');
      return String(answers[parts[0]]) === parts[1];
    });
  }

  // ─── COLLECT RESPONSES FOR SUBMISSION ─────────────────────────────────────

  function buildResponses() {
    var responses = [];
    var seen = {};
    var eff = buildEffectiveSteps();

    eff.forEach(function (step) {
      if (step._gridSubitem) {
        (step._subitems || []).forEach(function (sub) {
          if (!seen[sub.id] && sub.id in answers) {
            responses.push({ question_id: sub.id, answer_value: answers[sub.id] });
            seen[sub.id] = true;
          }
        });
      } else if (step.type === 'grid') {
        // Compact grid (< 4 subitems) — iterate subitems
        (step.subitems || []).forEach(function (sub) {
          if (!seen[sub.id] && sub.id in answers) {
            responses.push({ question_id: sub.id, answer_value: answers[sub.id] });
            seen[sub.id] = true;
          }
        });
      } else if (step.type === 'multiple') {
        Object.keys(multiSelected).forEach(function (optVal) {
          if (multiSelected[optVal]) {
            responses.push({ question_id: step.id + '_' + optVal, answer_value: 1 });
          }
        });
      } else {
        // single, scale, number, date
        if (step.id in answers) {
          responses.push({ question_id: step.id, answer_value: answers[step.id] });
        }
      }
    });

    // Q38: auto-fill today's date as YYYYMMDD integer
    var now = new Date();
    var yyyymmdd = now.getFullYear() * 10000 + (now.getMonth() + 1) * 100 + now.getDate();
    responses.push({ question_id: '38', answer_value: yyyymmdd });

    return responses;
  }

  // ─── SUBMIT ───────────────────────────────────────────────────────────────

  function submitAnswers() {
    if (isSubmitting) return;
    isSubmitting = true;

    if (progressText) progressText.textContent = 'Отправляем ответы…';
    if (progressFill) progressFill.style.width = '100%';

    var body = {
      measurement_point_id: pendingPoint.id,
      responses: buildResponses(),
    };

    fetch('/api/v1/patient/kdqol/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(body),
    })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().catch(function () { return {}; }).then(function (err) {
            throw new Error(err.detail || 'Ошибка при отправке ответов.');
          });
        }
        return resp.json();
      })
      .then(function (data) {
        clearProgress();
        showResult(data);
      })
      .catch(function (err) {
        showStatus(err.message || 'Ошибка отправки. Попробуйте обновить страницу.');
        isSubmitting = false;
        if (progressText) progressText.textContent = 'Произошла ошибка';
      });
  }

  // ─── RESULT SCREEN ────────────────────────────────────────────────────────

  var FEEDBACK_LABELS = {
    physical_functioning:         'В разделе обучения есть материалы о физической реабилитации и активности при диализе.',
    energy_fatigue:               'Раздел «Усталость и бодрость» в образовательной программе может быть полезен.',
    sleep:                        'Рекомендуем ознакомиться с материалами о здоровом сне.',
    emotional_wellbeing:          'Раздел «Эмоциональное здоровье» поможет справляться с тревогой и подавленностью.',
    symptoms:                     'Обсудите беспокоящие симптомы с лечащим врачом при следующем визите.',
    effects_kidney:               'Узнайте больше о жизни с хроническим заболеванием почек в разделе обучения.',
    burden_kidney:                'Психологическая поддержка может помочь справиться с нагрузкой болезни.',
    social_functioning:           'Активное общение с близкими важно для Вашего самочувствия.',
    cognitive_function:           'Раздел «Когнитивное здоровье» содержит упражнения для памяти и концентрации.',
    quality_social_interaction:   'Обсудите трудности в общении со специалистом или психологом.',
    role_physical:                'Поговорите с врачом о реабилитационных возможностях.',
    role_emotional:               'Психологическая поддержка помогает справляться с эмоциональными трудностями.',
    pain:                         'Не терпите боль — обсудите методы обезболивания с Вашим врачом.',
    general_health:               'Ваши ощущения об общем здоровье важны — поделитесь ими с врачом.',
    dialysis_staff_encouragement: 'Задавайте персоналу диализного центра интересующие Вас вопросы.',
    patient_satisfaction:         'Ваши пожелания о лечении важны — обсудите их с врачом.',
    social_support:               'Поговорите с близкими или специалистом о вопросах поддержки.',
  };

  // ─── SUBSCALE SCORES (result screen) ─────────────────────────────────────

  var SUBSCALE_DISPLAY = [
    {
      key: 'symptoms',
      label: 'Симптомы / проблемы',
      interp: [
        { min: 75, text: 'Симптомы беспокоят вас незначительно — это хороший фон для работы над самочувствием.' },
        { min: 40, text: 'Некоторые симптомы заметно влияют на ваш день — раздел «Симптомы и осложнения» может помочь разобраться.' },
        { min: 0,  text: 'Симптомы сейчас ощущаются тяжело — важно обсудить это с вашим врачом на ближайшем визите.' },
      ],
    },
    {
      key: 'burden_kidney',
      label: 'Бремя болезни почек',
      interp: [
        { min: 75, text: 'Болезнь занимает немного места в вашей жизни — вы справляетесь.' },
        { min: 40, text: 'Ощущение, что болезнь многое определяет — модуль «Адаптация к болезни» написан именно для этого.' },
        { min: 0,  text: 'Сейчас болезнь ощущается как очень тяжёлая ноша — поговорите с психологом или врачом, это важно.' },
      ],
    },
    {
      key: 'quality_social_interaction',
      label: 'Качество социального взаимодействия',
      interp: [
        { min: 75, text: 'Общение с близкими остаётся важной частью вашей жизни.' },
        { min: 40, text: 'Диализ забирает время и силы на общение — это замечают многие пациенты.' },
        { min: 0,  text: 'Ощущение изоляции сейчас выражено — не оставайтесь с этим одни.' },
      ],
    },
    {
      key: 'dialysis_staff_encouragement',
      label: 'Поддержка персонала диализа',
      interp: [
        { min: 75, text: 'Вы чувствуете поддержку команды — это важный ресурс.' },
        { min: 40, text: 'Если чего-то не хватает в общении с персоналом — можно обсудить это открыто.' },
        { min: 0,  text: 'Поддержки от команды сейчас недостаточно — скажите об этом врачу или медсестре.' },
      ],
    },
    {
      key: 'emotional_wellbeing',
      label: 'Психическое здоровье',
      interp: [
        { min: 75, text: 'Эмоциональный фон сейчас стабильный.' },
        { min: 40, text: 'Тревога или подавленность присутствуют — раздел «Эмоции» и «Тревога» могут быть полезны.' },
        { min: 0,  text: 'Эмоциональное состояние сейчас тяжёлое — пожалуйста, поговорите с врачом или психологом.' },
      ],
    },
    {
      key: 'energy_fatigue',
      label: 'Жизнеспособность / энергия',
      interp: [
        { min: 75, text: 'Энергии достаточно для повседневных дел.' },
        { min: 40, text: 'Усталость заметна — модуль «Стресс» и раздел «Распорядок дня» помогут найти режим, который не истощает.' },
        { min: 0,  text: 'Сил сейчас очень мало — обсудите усталость с врачом, иногда за ней стоят корректируемые причины.' },
      ],
    },
  ];

  function _scoreInterp(interpArr, score) {
    for (var i = 0; i < interpArr.length; i++) {
      if (score >= interpArr[i].min) return interpArr[i].text;
    }
    return '';
  }

  function _scoreColor(score) {
    if (score >= 75) return '#16a34a';
    if (score >= 40) return '#ea580c';
    return '#dc2626';
  }

  function renderSubscaleScores(scores) {
    var block = document.getElementById('kdqol-scores-block');
    if (!block) return;

    var cards = '';
    SUBSCALE_DISPLAY.forEach(function (cfg) {
      var score = scores[cfg.key];
      if (score === null || score === undefined) return;
      var rounded = Math.round(score);
      var color = _scoreColor(rounded);
      cards +=
        '<div class="kdqol-score-card">' +
          '<div class="kdqol-score-name">' + cfg.label + '</div>' +
          '<div class="kdqol-score-bar-wrap">' +
            '<div class="kdqol-score-bar-fill" style="width:' + rounded + '%;background:' + color + ';"></div>' +
          '</div>' +
          '<div class="kdqol-score-value" style="color:' + color + ';">' + rounded + '\u00a0/ 100</div>' +
          '<div class="kdqol-score-interp">' + _scoreInterp(cfg.interp, rounded) + '</div>' +
        '</div>';
    });

    if (!cards) return;
    block.innerHTML =
      '<div class="kdqol-scores-section">' +
        '<div class="kdqol-scores-title">Ваши результаты</div>' +
        '<div class="kdqol-scores-grid">' + cards + '</div>' +
      '</div>';
  }

  function showResult(data) {
    var feedbackModule = data && data.feedback_module;
    var feedbackHtml = '';
    if (feedbackModule && FEEDBACK_LABELS[feedbackModule]) {
      feedbackHtml = '<div class="kdqol-advice">' + FEEDBACK_LABELS[feedbackModule] + '</div>';
    }

    if (container) {
      container.innerHTML =
        '<div class="kdqol-result">' +
          '<div class="kdqol-result-icon">&#10003;</div>' +
          '<h2>Спасибо! Опросник завершён.</h2>' +
          '<p class="kdqol-result-text">Ваши ответы записаны. Специалист ознакомится с результатами.</p>' +
          feedbackHtml +
          '<div class="hads-actions">' +
            '<a class="secondary-button" href="/patient/home">На главную</a>' +
          '</div>' +
        '</div>' +
        '<div id="kdqol-scores-block"></div>';
    }

    if (progressText) progressText.textContent = 'Опрос завершён';
    if (progressFill) progressFill.style.width = '100%';

    fetch('/api/v1/patient/kdqol/latest-scores', { credentials: 'include' })
      .then(function (resp) { return resp.ok ? resp.json() : null; })
      .then(function (result) {
        if (result && result.scores) renderSubscaleScores(result.scores);
      })
      .catch(function () {});
  }

  // ─── RENDER CURRENT STEP ──────────────────────────────────────────────────

  function renderCurrentStep() {
    clearStatus();
    effectiveSteps = buildEffectiveSteps();

    if (currentStep >= effectiveSteps.length) {
      submitAnswers();
      return;
    }

    updateProgress(currentStep, effectiveSteps.length);
    renderQuestion(effectiveSteps[currentStep]);
  }

  function renderQuestion(step) {
    if (!container) return;
    container.innerHTML = '';

    var card = document.createElement('div');
    card.className = 'hads-question-card';

    if (step._gridSubitem) {
      renderGridSubitem(card, step);
    } else if (step.type === 'single') {
      renderSingle(card, step);
    } else if (step.type === 'grid') {
      renderGrid(card, step);
    } else if (step.type === 'scale') {
      renderScale(card, step);
    } else if (step.type === 'number') {
      renderNumber(card, step);
    } else if (step.type === 'multiple') {
      renderMultiple(card, step);
    } else if (step.type === 'date') {
      renderDate(card, step);
    } else {
      // Fallback: skip unknown types
      currentStep++;
      saveProgress();
      renderCurrentStep();
      return;
    }

    container.appendChild(card);
  }

  // ─── SINGLE ───────────────────────────────────────────────────────────────

  function renderSingle(card, q) {
    card.appendChild(makeText(q.text));

    var opts = document.createElement('div');
    opts.className = 'hads-options';

    (q.options || []).forEach(function (opt) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'hads-option-btn';
      if (answers[q.id] === opt.value) btn.classList.add('kdqol-option-selected');
      btn.textContent = opt.label;
      btn.addEventListener('click', function () {
        answers[q.id] = opt.value;
        currentStep++;
        saveProgress();
        renderCurrentStep();
      });
      opts.appendChild(btn);
    });

    card.appendChild(opts);

    if (currentStep > 0) {
      card.appendChild(makeBackRow());
    }
  }

  // ─── GRID SUBITEM (chunk of 3 subitems per screen) ────────────────────────

  function renderGridSubitem(card, step) {
    var parentQ  = step._parentQ;
    var subitems = step._subitems || [];

    // Parent question text as group header
    var header = document.createElement('div');
    header.className = 'kdqol-sub-group-header';
    header.textContent = parentQ.text;
    card.appendChild(header);

    // Create nextBtn first so option click handlers can reference it
    var nextBtn = makeNextBtn(function () {
      currentStep++;
      saveProgress();
      renderCurrentStep();
    });
    nextBtn.disabled = !isChunkComplete(subitems);

    // Render each subitem as a mini-card
    subitems.forEach(function (sub) {
      var subCard = document.createElement('div');
      subCard.className = 'kdqol-subitem-card';

      var subText = document.createElement('div');
      subText.className = 'hads-question-text';
      subText.textContent = sub.text;
      subCard.appendChild(subText);

      var opts = document.createElement('div');
      opts.className = 'hads-options';

      (parentQ.options || []).forEach(function (opt) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'hads-option-btn';
        if (answers[sub.id] === opt.value) btn.classList.add('kdqol-option-selected');
        btn.textContent = opt.label;
        btn.addEventListener('click', function () {
          opts.querySelectorAll('.hads-option-btn').forEach(function (b) {
            b.classList.remove('kdqol-option-selected');
          });
          btn.classList.add('kdqol-option-selected');
          answers[sub.id] = opt.value;
          saveProgress();
          nextBtn.disabled = !isChunkComplete(subitems);
        });
        opts.appendChild(btn);
      });

      subCard.appendChild(opts);
      card.appendChild(subCard);
    });

    card.appendChild(makeNavRow(nextBtn));
  }

  function isChunkComplete(subitems) {
    return subitems.every(function (sub) { return sub.id in answers; });
  }

  // ─── GRID (compact — < 4 subitems, shown all at once) ─────────────────────

  function renderGrid(card, q) {
    card.appendChild(makeText(q.text));

    // Skip button for optional Q20
    if (q.optional) {
      var skipRow = document.createElement('div');
      skipRow.className = 'kdqol-skip-row';
      var skipBtn = document.createElement('button');
      skipBtn.type = 'button';
      skipBtn.className = 'kdqol-skip-btn';
      skipBtn.textContent = 'Пропустить этот вопрос';
      skipBtn.addEventListener('click', function () {
        (q.subitems || []).forEach(function (sub) { delete answers[sub.id]; });
        currentStep++;
        saveProgress();
        renderCurrentStep();
      });
      skipRow.appendChild(skipBtn);
      card.appendChild(skipRow);
    }

    var optCount = (q.options || []).length;

    var wrapper = document.createElement('div');
    wrapper.className = 'kdqol-grid-wrapper';

    if (optCount <= 4) {
      wrapper.appendChild(buildGridTable(q));
    } else {
      buildGridStacked(wrapper, q);
    }

    card.appendChild(wrapper);

    var nextBtn = makeNextBtn(function () {
      currentStep++;
      saveProgress();
      renderCurrentStep();
    });
    nextBtn.disabled = !isGridComplete(q);

    wrapper.addEventListener('change', function () {
      nextBtn.disabled = !isGridComplete(q);
    });

    card.appendChild(makeNavRow(nextBtn));
  }

  function buildGridTable(q) {
    var table = document.createElement('table');
    table.className = 'kdqol-grid-table';

    // Header
    var thead = document.createElement('thead');
    var headerRow = document.createElement('tr');
    var emptyTh = document.createElement('th');
    emptyTh.className = 'kdqol-th-label';
    headerRow.appendChild(emptyTh);
    (q.options || []).forEach(function (opt) {
      var th = document.createElement('th');
      th.className = 'kdqol-th-option';
      th.textContent = opt.label;
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    // Body
    var tbody = document.createElement('tbody');
    (q.subitems || []).forEach(function (sub, rowIdx) {
      var tr = document.createElement('tr');
      tr.className = rowIdx % 2 === 0 ? 'kdqol-tr-even' : 'kdqol-tr-odd';

      var tdLabel = document.createElement('td');
      tdLabel.className = 'kdqol-td-label';
      tdLabel.textContent = sub.text;
      tr.appendChild(tdLabel);

      (q.options || []).forEach(function (opt) {
        var td = document.createElement('td');
        td.className = 'kdqol-td-radio';

        var radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'kdqol-sub-' + sub.id;
        radio.value = opt.value;
        radio.className = 'kdqol-radio';
        if (answers[sub.id] === opt.value) radio.checked = true;
        radio.addEventListener('change', function () {
          answers[sub.id] = opt.value;
          saveProgress();
        });

        td.appendChild(radio);
        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    return table;
  }

  function buildGridStacked(wrapper, q) {
    (q.subitems || []).forEach(function (sub) {
      var subCard = document.createElement('div');
      subCard.className = 'kdqol-sub-card';

      var subText = document.createElement('div');
      subText.className = 'kdqol-sub-text';
      subText.textContent = sub.text;
      subCard.appendChild(subText);

      var subOpts = document.createElement('div');
      subOpts.className = 'kdqol-sub-options';

      (q.options || []).forEach(function (opt) {
        var label = document.createElement('label');
        label.className = 'kdqol-sub-opt-label';

        var radio = document.createElement('input');
        radio.type = 'radio';
        radio.name = 'kdqol-sub-' + sub.id;
        radio.value = opt.value;
        if (answers[sub.id] === opt.value) radio.checked = true;
        radio.addEventListener('change', function () {
          answers[sub.id] = opt.value;
          saveProgress();
        });

        label.appendChild(radio);
        label.appendChild(document.createTextNode('\u00a0' + opt.label));
        subOpts.appendChild(label);
      });

      subCard.appendChild(subOpts);
      wrapper.appendChild(subCard);
    });
  }

  function isGridComplete(q) {
    return (q.subitems || []).every(function (sub) {
      return sub.id in answers;
    });
  }

  // ─── SCALE (Q17) ──────────────────────────────────────────────────────────

  function renderScale(card, q) {
    card.appendChild(makeText(q.text));

    var wrapper = document.createElement('div');
    wrapper.className = 'kdqol-scale-wrapper';

    var initValue = q.id in answers ? answers[q.id] : 5;

    var valueDisplay = document.createElement('div');
    valueDisplay.className = 'kdqol-scale-value';
    valueDisplay.textContent = initValue;
    wrapper.appendChild(valueDisplay);

    var slider = document.createElement('input');
    slider.type = 'range';
    slider.min = q.min !== undefined ? q.min : 0;
    slider.max = q.max !== undefined ? q.max : 10;
    slider.step = 1;
    slider.value = initValue;
    slider.className = 'kdqol-slider';
    slider.setAttribute('aria-label', q.text);
    slider.addEventListener('input', function () {
      valueDisplay.textContent = slider.value;
      answers[q.id] = parseInt(slider.value, 10);
      saveProgress();
    });
    wrapper.appendChild(slider);

    var labelsRow = document.createElement('div');
    labelsRow.className = 'kdqol-scale-labels';
    var minSpan = document.createElement('span');
    minSpan.textContent = q.min_label || String(slider.min);
    var maxSpan = document.createElement('span');
    maxSpan.textContent = q.max_label || String(slider.max);
    labelsRow.appendChild(minSpan);
    labelsRow.appendChild(maxSpan);
    wrapper.appendChild(labelsRow);

    card.appendChild(wrapper);

    // Pre-save initial value so slider is never unanswered
    if (!(q.id in answers)) {
      answers[q.id] = initValue;
      saveProgress();
    }

    card.appendChild(makeNavRow(makeNextBtn(function () {
      currentStep++;
      saveProgress();
      renderCurrentStep();
    })));
  }

  // ─── NUMBER ───────────────────────────────────────────────────────────────

  function renderNumber(card, q) {
    card.appendChild(makeText(q.text));

    var input = document.createElement('input');
    input.type = 'number';
    input.min = 0;
    input.step = 1;
    input.className = 'kdqol-number-input';
    input.placeholder = '0';
    if (q.id in answers) input.value = answers[q.id];
    input.addEventListener('input', function () {
      var val = parseInt(input.value, 10);
      if (!isNaN(val) && val >= 0) {
        answers[q.id] = val;
        saveProgress();
      }
    });
    card.appendChild(input);

    card.appendChild(makeNavRow(makeNextBtn(function () {
      if (!(q.id in answers)) answers[q.id] = 0;
      currentStep++;
      saveProgress();
      renderCurrentStep();
    })));
  }

  // ─── MULTIPLE (Q28) ───────────────────────────────────────────────────────

  function renderMultiple(card, q) {
    card.appendChild(makeText(q.text));

    var hint = document.createElement('div');
    hint.className = 'hads-helper-text';
    hint.style.marginBottom = '0.75rem';
    hint.textContent = 'Можно выбрать несколько вариантов';
    card.appendChild(hint);

    var list = document.createElement('div');
    list.className = 'kdqol-checkboxes';

    (q.options || []).forEach(function (opt) {
      var label = document.createElement('label');
      label.className = 'kdqol-checkbox-label';

      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.className = 'kdqol-checkbox';
      cb.checked = !!multiSelected[opt.value];
      cb.addEventListener('change', function () {
        multiSelected[opt.value] = cb.checked;
        saveProgress();
      });

      label.appendChild(cb);
      label.appendChild(document.createTextNode('\u00a0' + opt.label));
      list.appendChild(label);
    });
    card.appendChild(list);

    card.appendChild(makeNavRow(makeNextBtn(function () {
      answers[q.id] = 1; // mark visited even if nothing selected
      currentStep++;
      saveProgress();
      renderCurrentStep();
    })));
  }

  // ─── DATE ─────────────────────────────────────────────────────────────────

  function renderDate(card, q) {
    card.appendChild(makeText(q.text));

    var input = document.createElement('input');
    input.type = 'date';
    input.className = 'kdqol-date-input';
    if (q.id in answers) {
      // Convert stored YYYYMMDD integer back to date string
      var stored = String(answers[q.id]);
      if (stored.length === 8) {
        input.value = stored.slice(0, 4) + '-' + stored.slice(4, 6) + '-' + stored.slice(6, 8);
      }
    }
    input.addEventListener('change', function () {
      if (input.value) {
        answers[q.id] = parseInt(input.value.replace(/-/g, ''), 10);
        saveProgress();
      }
    });
    card.appendChild(input);

    card.appendChild(makeNavRow(makeNextBtn(function () {
      if (!(q.id in answers)) answers[q.id] = 0;
      currentStep++;
      saveProgress();
      renderCurrentStep();
    })));
  }

  // ─── HELPERS ──────────────────────────────────────────────────────────────

  function makeText(text) {
    var el = document.createElement('div');
    el.className = 'hads-question-text';
    el.textContent = text;
    return el;
  }

  function makeNextBtn(onClick) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'kdqol-btn-primary kdqol-next-btn';
    btn.textContent = 'Далее \u2192';
    btn.addEventListener('click', onClick);
    return btn;
  }

  function makeBackBtn() {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'kdqol-back-btn';
    btn.textContent = '\u2190 Назад';
    btn.disabled = currentStep === 0;
    btn.addEventListener('click', function () {
      if (currentStep > 0) {
        currentStep--;
        saveProgress();
        renderCurrentStep();
      }
    });
    return btn;
  }

  /**
   * Navigation row: back button on the left, optional next button on the right.
   * If nextBtn is null, only the back button is shown (used by grid/auto-advance compacts).
   */
  function makeNavRow(nextBtn) {
    var row = document.createElement('div');
    row.className = 'kdqol-nav-row';
    row.appendChild(makeBackBtn());
    if (nextBtn) row.appendChild(nextBtn);
    return row;
  }

  /**
   * Back-only row for auto-advance question types (single, gridSubitem).
   * Not shown on step 0.
   */
  function makeBackRow() {
    var row = document.createElement('div');
    row.className = 'kdqol-nav-row kdqol-nav-row--back-only';
    row.appendChild(makeBackBtn());
    return row;
  }

  // ─── START SCREEN ─────────────────────────────────────────────────────────

  function showStartScreen() {
    var hasSaved = currentStep > 0 || Object.keys(answers).length > 0;
    var btnLabel = hasSaved ? 'Продолжить \u2192' : 'Начать опрос \u2192';
    var resumeNote = hasSaved
      ? '<p style="font-size:0.85rem;color:#6b7280">Обнаружены сохранённые ответы — продолжите с места остановки.</p>'
      : '';

    if (progressText) progressText.textContent = 'Готовы начать?';
    if (progressFill) progressFill.style.width = '0%';

    if (container) {
      container.innerHTML =
        '<div class="kdqol-start">' +
          '<div class="kdqol-start-icon">&#128203;</div>' +
          '<h2>Опросник KDQOL-SF\u00a01.3</h2>' +
          '<p>Данный опросник поможет оценить качество Вашей жизни с болезнью почек. ' +
             'Пожалуйста, отвечайте честно — здесь нет правильных или неправильных ответов.</p>' +
          '<p class="kdqol-start-meta">Время заполнения: около 20–25 минут.</p>' +
          resumeNote +
          '<button type="button" class="kdqol-btn-primary" id="kdqol-start-btn">' + btnLabel + '</button>' +
        '</div>';

      document.getElementById('kdqol-start-btn').addEventListener('click', function () {
        renderCurrentStep();
      });
    }
  }

  // ─── WAITING SCREEN ───────────────────────────────────────────────────────

  function showWaitingScreen() {
    if (progressText) progressText.textContent = 'Опрос не активирован';
    if (progressFill) progressFill.style.width = '0%';

    if (container) {
      container.innerHTML =
        '<div class="kdqol-waiting">' +
          '<div class="kdqol-waiting-icon">&#9203;</div>' +
          '<h2>Опрос ещё не начат</h2>' +
          '<p>Исследователь не активировал для Вас опрос. ' +
             'Когда придёт время — Вы сможете его пройти здесь.</p>' +
          '<a class="secondary-button" href="/patient/home">На главную</a>' +
        '</div>';
    }
  }

  // ─── INIT ─────────────────────────────────────────────────────────────────

  function init() {
    if (container) {
      container.innerHTML = '<div class="hads-loader">Загружаем данные…</div>';
    }

    fetch('/api/v1/patient/kdqol/pending', { credentials: 'include' })
      .then(function (resp) {
        if (!resp.ok) throw new Error('Ошибка проверки статуса опроса.');
        return resp.json();
      })
      .then(function (point) {
        pendingPoint = point;

        if (!pendingPoint) {
          showWaitingScreen();
          return;
        }

        return fetch('/api/v1/patient/kdqol/questions', { credentials: 'include' })
          .then(function (resp) {
            if (!resp.ok) throw new Error('Ошибка загрузки вопросов.');
            return resp.json();
          })
          .then(function (data) {
            allQuestions = data.questions || [];
            steps = buildSteps(allQuestions);
            loadProgress();
            showStartScreen();
          });
      })
      .catch(function (err) {
        if (container) {
          container.innerHTML = '<div class="hads-error-text">' + err.message + '</div>';
        }
        showStatus(err.message || 'Ошибка загрузки.', 'error');
      });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
