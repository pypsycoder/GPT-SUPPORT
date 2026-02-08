(function () {
  let psqiConfig = null;
  let currentBlockIndex = 0;
  let answers = {};       // question_id -> value
  let isSubmitting = false;

  const blockContainer = document.getElementById('psqi-block-container');
  const progressText = document.getElementById('psqi-progress-text');
  const progressFill = document.getElementById('psqi-progress-fill');
  const statusBanner = document.getElementById('psqi-status');
  const resultBlock = document.getElementById('psqi-result');
  const navPanel = document.getElementById('psqi-nav');
  const prevBtn = document.getElementById('psqi-prev');
  const nextBtn = document.getElementById('psqi-next');
  const submitBtn = document.getElementById('psqi-submit');

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

  /* ---------- helpers ---------- */

  function getVisibleBlocks() {
    if (!psqiConfig) return [];
    return psqiConfig.blocks.filter(function (block) {
      if (!block.conditional) return true;
      var dep = block.conditional.depends_on;
      var val = answers[dep];
      if (val === undefined || val === null) return false;
      return block.conditional.show_if.indexOf(Number(val)) !== -1;
    });
  }

  function updateProgress() {
    var blocks = getVisibleBlocks();
    if (!blocks.length) return;
    var num = Math.min(currentBlockIndex + 1, blocks.length);
    progressText.textContent = 'Блок ' + num + ' из ' + blocks.length;
    var pct = Math.min((currentBlockIndex / blocks.length) * 100, 100);
    progressFill.style.width = pct + '%';
  }

  function updateNav() {
    var blocks = getVisibleBlocks();
    var isLast = currentBlockIndex >= blocks.length - 1;

    prevBtn.disabled = currentBlockIndex === 0;
    nextBtn.style.display = isLast ? 'none' : '';
    submitBtn.style.display = isLast ? '' : 'none';

    var valid = validateCurrentBlock();
    nextBtn.disabled = !valid;
    submitBtn.disabled = !valid;
  }

  /* ---------- validation ---------- */

  function validateCurrentBlock() {
    var blocks = getVisibleBlocks();
    if (currentBlockIndex >= blocks.length) return false;
    var block = blocks[currentBlockIndex];
    var questions = block.questions || [];

    for (var i = 0; i < questions.length; i++) {
      var q = questions[i];
      if (q.required === false) continue;

      // Skip optional text fields
      if (q.has_text_field) continue;

      var val = answers[q.id];
      if (val === undefined || val === null || val === '') return false;

      // time validation
      if (q.type === 'time') {
        if (!/^\d{1,2}:\d{2}$/.test(String(val))) return false;
      }
      // number validation
      if (q.type === 'number') {
        if (isNaN(Number(val))) return false;
      }
    }

    // matrix blocks: each question needs an answer
    if (block.type === 'matrix') {
      for (var j = 0; j < questions.length; j++) {
        var qm = questions[j];
        var vm = answers[qm.id];
        if (vm === undefined || vm === null || vm === '') return false;
      }
    }

    return true;
  }

  /* ---------- render ---------- */

  function renderBlock() {
    clearStatus();
    if (!blockContainer) return;
    blockContainer.innerHTML = '';

    var blocks = getVisibleBlocks();
    if (!blocks.length) {
      blockContainer.innerHTML = '<div class="psqi-error">Не удалось загрузить блоки.</div>';
      return;
    }

    if (currentBlockIndex >= blocks.length) {
      submitAnswers();
      return;
    }

    var block = blocks[currentBlockIndex];
    updateProgress();
    navPanel.style.display = '';

    var wrapper = document.createElement('div');
    wrapper.className = 'psqi-block';

    // block title
    var title = document.createElement('h3');
    title.className = 'psqi-block-title';
    title.textContent = block.title;
    wrapper.appendChild(title);

    // instruction
    if (block.instruction) {
      var instr = document.createElement('p');
      instr.className = 'psqi-block-instruction';
      instr.textContent = block.instruction;
      wrapper.appendChild(instr);
    }

    if (block.type === 'matrix') {
      renderMatrixBlock(wrapper, block);
    } else {
      renderQuestionsBlock(wrapper, block);
    }

    blockContainer.appendChild(wrapper);
    updateNav();
  }

  function renderQuestionsBlock(wrapper, block) {
    var questions = block.questions || [];
    for (var i = 0; i < questions.length; i++) {
      var q = questions[i];
      var qDiv = document.createElement('div');
      qDiv.className = 'psqi-question';

      var label = document.createElement('label');
      label.className = 'psqi-question-text';
      label.textContent = q.text;
      label.setAttribute('for', 'input-' + q.id);
      qDiv.appendChild(label);

      if (q.help_text) {
        var help = document.createElement('div');
        help.className = 'psqi-help-text';
        help.textContent = q.help_text;
        qDiv.appendChild(help);
      }

      if (q.type === 'time') {
        var inp = document.createElement('input');
        inp.type = 'text';
        inp.id = 'input-' + q.id;
        inp.className = 'psqi-input psqi-time-input';
        inp.placeholder = q.placeholder || 'ЧЧ:ММ';
        inp.maxLength = 5;
        inp.value = answers[q.id] || '';
        inp.dataset.qid = q.id;
        inp.addEventListener('input', handleTimeInput);
        inp.addEventListener('change', handleInputChange);
        qDiv.appendChild(inp);
      } else if (q.type === 'number') {
        var numInp = document.createElement('input');
        numInp.type = 'number';
        numInp.id = 'input-' + q.id;
        numInp.className = 'psqi-input psqi-number-input';
        numInp.placeholder = q.placeholder || '';
        numInp.min = q.min != null ? q.min : '';
        numInp.max = q.max != null ? q.max : '';
        numInp.step = q.step || 1;
        numInp.value = answers[q.id] != null ? answers[q.id] : '';
        numInp.dataset.qid = q.id;
        numInp.addEventListener('input', handleInputChange);
        qDiv.appendChild(numInp);
      } else if (q.type === 'single_choice') {
        var opts = q.options || [];
        var optsDiv = document.createElement('div');
        optsDiv.className = 'psqi-radio-group';
        for (var j = 0; j < opts.length; j++) {
          var opt = opts[j];
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'psqi-radio-btn';
          if (answers[q.id] !== undefined && Number(answers[q.id]) === opt.value) {
            btn.classList.add('selected');
          }
          btn.textContent = opt.label;
          btn.dataset.qid = q.id;
          btn.dataset.val = opt.value;
          btn.addEventListener('click', handleRadioClick);
          optsDiv.appendChild(btn);
        }
        qDiv.appendChild(optsDiv);

        // Add text field if has_text_field is true
        if (q.has_text_field) {
          var tfDiv = document.createElement('div');
          tfDiv.className = 'psqi-text-field-row';
          var tfLabel = document.createElement('label');
          tfLabel.className = 'psqi-text-field-label';
          tfLabel.textContent = q.text_field_label || 'Опишите';
          tfLabel.setAttribute('for', 'input-' + q.text_field_id);
          var tf = document.createElement('input');
          tf.type = 'text';
          tf.id = 'input-' + q.text_field_id;
          tf.className = 'psqi-input psqi-text-field';
          tf.placeholder = q.text_field_label || '';
          tf.value = answers[q.text_field_id] || '';
          tf.dataset.qid = q.text_field_id;
          tf.addEventListener('input', handleInputChange);
          tfDiv.appendChild(tfLabel);
          tfDiv.appendChild(tf);
          qDiv.appendChild(tfDiv);
        }
      }

      wrapper.appendChild(qDiv);
    }
  }

  function renderMatrixBlock(wrapper, block) {
    var questions = block.questions || [];
    var options = block.options || [];

    var table = document.createElement('div');
    table.className = 'psqi-matrix';

    for (var i = 0; i < questions.length; i++) {
      var q = questions[i];

      var row = document.createElement('div');
      row.className = 'psqi-matrix-row';

      var labelCell = document.createElement('div');
      labelCell.className = 'psqi-matrix-label';
      labelCell.textContent = q.text;
      row.appendChild(labelCell);

      var optionsCell = document.createElement('div');
      optionsCell.className = 'psqi-matrix-options';

      for (var j = 0; j < options.length; j++) {
        var opt = options[j];
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'psqi-matrix-btn';
        if (answers[q.id] !== undefined && Number(answers[q.id]) === opt.value) {
          btn.classList.add('selected');
        }
        btn.textContent = opt.label;
        btn.dataset.qid = q.id;
        btn.dataset.val = opt.value;
        btn.addEventListener('click', handleRadioClick);
        optionsCell.appendChild(btn);
      }

      row.appendChild(optionsCell);
      table.appendChild(row);

      // text field for "other" items
      if (q.has_text_field) {
        var tfDiv = document.createElement('div');
        tfDiv.className = 'psqi-text-field-row';
        var tfLabel = document.createElement('label');
        tfLabel.className = 'psqi-text-field-label';
        tfLabel.textContent = q.text_field_label || 'Опишите';
        tfLabel.setAttribute('for', 'input-' + q.text_field_id);
        var tf = document.createElement('input');
        tf.type = 'text';
        tf.id = 'input-' + q.text_field_id;
        tf.className = 'psqi-input psqi-text-field';
        tf.placeholder = q.text_field_label || '';
        tf.value = answers[q.text_field_id] || '';
        tf.dataset.qid = q.text_field_id;
        tf.addEventListener('input', handleInputChange);
        tfDiv.appendChild(tfLabel);
        tfDiv.appendChild(tf);
        table.appendChild(tfDiv);
      }
    }

    wrapper.appendChild(table);
  }

  /* ---------- event handlers ---------- */

  function handleTimeInput(e) {
    var val = e.target.value.replace(/[^\d:]/g, '');
    // auto-insert colon after 2 digits
    if (val.length === 2 && !val.includes(':')) {
      val = val + ':';
    }
    if (val.length > 5) val = val.slice(0, 5);
    e.target.value = val;
    answers[e.target.dataset.qid] = val;
    updateNav();
  }

  function handleInputChange(e) {
    answers[e.target.dataset.qid] = e.target.value;
    updateNav();
  }

  function handleRadioClick(e) {
    var qid = e.target.dataset.qid;
    var val = Number(e.target.dataset.val);
    answers[qid] = val;

    // update visual selection
    var siblings = e.target.parentElement.querySelectorAll('button');
    for (var i = 0; i < siblings.length; i++) {
      siblings[i].classList.remove('selected');
    }
    e.target.classList.add('selected');

    // if q10 changed, re-evaluate visible blocks
    if (qid === 'q10') {
      updateNav();
    } else {
      updateNav();
    }
  }

  /* ---------- navigation ---------- */

  function goNext() {
    if (!validateCurrentBlock()) return;
    var blocks = getVisibleBlocks();
    if (currentBlockIndex < blocks.length - 1) {
      currentBlockIndex++;
      renderBlock();
      window.scrollTo(0, 0);
    }
  }

  function goPrev() {
    if (currentBlockIndex > 0) {
      currentBlockIndex--;
      renderBlock();
      window.scrollTo(0, 0);
    }
  }

  /* ---------- submit ---------- */

  function submitAnswers() {
    if (isSubmitting) return;
    isSubmitting = true;
    progressText.textContent = 'Сохраняем ответы...';
    navPanel.style.display = 'none';

    // build answers array
    var answersArr = [];
    var keys = Object.keys(answers);
    for (var i = 0; i < keys.length; i++) {
      answersArr.push({ question_id: keys[i], value: answers[keys[i]] });
    }

    fetch('/api/v1/scales/PSQI/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers: answersArr }),
    })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().catch(function () { return {}; }).then(function (d) {
            throw new Error(d.detail || 'Не удалось сохранить ответы.');
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
        navPanel.style.display = '';
        isSubmitting = false;
      });
  }

  /* ---------- result ---------- */

  function getInterpretation(score) {
    if (score <= 5)  return { level: 'normal',      label: 'Нормальное качество сна',    cls: 'result-box-high' };
    if (score <= 10) return { level: 'moderate',     label: 'Умеренные нарушения сна',    cls: 'result-box-moderate' };
    if (score <= 15) return { level: 'significant',  label: 'Значительные нарушения сна', cls: 'result-box-low' };
    return               { level: 'severe',       label: 'Выраженные нарушения сна',  cls: 'result-box-low' };
  }

  function getMessage(score) {
    if (score <= 5) return 'Ваше качество сна находится в пределах нормы. Продолжайте следовать здоровым привычкам сна.';
    if (score <= 10) return 'У вас есть умеренные нарушения сна, которые могут влиять на ваше самочувствие и эффективность лечения. Рекомендуем обсудить это с врачом и обратить внимание на гигиену сна.';
    if (score <= 15) return 'У вас значительные нарушения сна. Это важно обсудить с лечащим врачом, так как качество сна напрямую связано с эффективностью диализа и вашим общим состоянием.';
    return 'У вас выраженные нарушения сна, которые требуют медицинского внимания. Пожалуйста, обязательно сообщите об этом вашему лечащему врачу или нефрологу.';
  }

  function componentLabel(key) {
    var map = {
      C1_subjective_quality:  'Субъективное качество сна',
      C2_sleep_latency:       'Латентность сна',
      C3_sleep_duration:      'Длительность сна',
      C4_sleep_efficiency:    'Эффективность сна',
      C5_sleep_disturbances:  'Нарушения сна',
      C6_sleep_medication:    'Использование снотворных',
      C7_daytime_dysfunction: 'Дневная дисфункция',
    };
    return map[key] || key;
  }

  function showResult(payload) {
    if (!resultBlock) return;

    var result = payload.result || {};
    var score = result.total_score;
    var interp = getInterpretation(score);
    var msg = getMessage(score);
    var measuredAt = payload.measured_at;
    var components = result.components || {};
    var details = result.details || {};
    var flags = result.clinical_flags || [];

    var token = getPatientTokenFromPath();
    var backUrl = token ? '/patient/scales' : '/';

    // components mini cards
    var compHtml = '';
    var compKeys = Object.keys(components);
    for (var i = 0; i < compKeys.length; i++) {
      compHtml += '<div class="result-mini-box ' + interp.cls + '">'
        + '<div class="mini-title">' + componentLabel(compKeys[i]) + '</div>'
        + '<div class="mini-value">' + components[compKeys[i]] + ' / 3</div>'
        + '</div>';
    }

    // clinical flags
    var flagsHtml = '';
    if (flags.length > 0) {
      flagsHtml = '<div class="psqi-flags"><h4>Клинические маркеры</h4>';
      for (var f = 0; f < flags.length; f++) {
        flagsHtml += '<div class="psqi-flag-item">'
          + '<strong>' + flags[f].name + '</strong>'
          + '<div>' + flags[f].recommendation + '</div>'
          + '</div>';
      }
      flagsHtml += '</div>';
    }

    var measuredText = measuredAt
      ? '<div class="psqi-helper-text">Время измерения: ' + new Date(measuredAt).toLocaleString('ru-RU') + '</div>'
      : '';

    resultBlock.innerHTML =
      '<div class="kop25a-result-window">'
      + '<h2>Результат PSQI</h2>'
      + '<div class="result-main ' + interp.cls + '">'
      + '  <div class="result-score">' + score + ' <span style="font-size:1rem;font-weight:400">/ 21</span></div>'
      + '  <div class="result-text"><strong>' + interp.label + '</strong></div>'
      + '  <div class="result-text">' + msg + '</div>'
      + '</div>'
      + measuredText
      + '<div class="psqi-details">'
      + '  <div class="result-line">Время в постели: ' + details.time_in_bed_hours + ' ч</div>'
      + '  <div class="result-line">Эффективность сна: ' + details.sleep_efficiency_pct + '%</div>'
      + '</div>'
      + '<h4 style="margin-top:16px;">Компоненты</h4>'
      + '<div class="mini-grid">' + compHtml + '</div>'
      + flagsHtml
      + '<div style="margin-top:20px;text-align:center;">'
      + '  <a class="secondary-button" href="' + backUrl + '">Вернуться к шкалам</a>'
      + '</div>'
      + '</div>';

    progressText.textContent = 'Опрос завершён';
    progressFill.style.width = '100%';

    blockContainer.classList.add('hidden');
    resultBlock.classList.remove('hidden');
  }

  /* ---------- init ---------- */

  function loadConfig() {
    if (!blockContainer) return;
    blockContainer.innerHTML = '<div class="psqi-loader">Загружаем опросник...</div>';

    fetch('/api/v1/scales/PSQI')
      .then(function (resp) {
        if (!resp.ok) throw new Error('Не удалось загрузить опросник PSQI.');
        return resp.json();
      })
      .then(function (data) {
        psqiConfig = data;
        currentBlockIndex = 0;
        answers = {};
        isSubmitting = false;

        prevBtn.addEventListener('click', goPrev);
        nextBtn.addEventListener('click', goNext);
        submitBtn.addEventListener('click', submitAnswers);

        renderBlock();
      })
      .catch(function (err) {
        blockContainer.innerHTML = '<div class="psqi-error">' + err.message + '</div>';
        showStatus(err.message, 'error');
      });
  }

  document.addEventListener('DOMContentLoaded', loadConfig);
})();
