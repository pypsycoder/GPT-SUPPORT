(function () {
  var ACTIVITY_DEFS = {
    physical: { icon: '🚶', main: 'Физическая активность', sub: 'Прогулка, зарядка, упражнения' },
    household: { icon: '🏠', main: 'Домашние дела', sub: 'Уборка, готовка, покупки' },
    work: { icon: '💼', main: 'Работа / подработка', sub: 'Любая трудовая деятельность' },
    leisure: { icon: '🎨', main: 'Досуг и хобби', sub: 'Книги, сад, рукоделие, ТВ' },
    social: { icon: '👥', main: 'Общение с людьми', sub: 'Встречи, звонки, мессенджеры' },
    self_care: { icon: '🧴', main: 'Самообслуживание', sub: 'Гигиена, внешний вид' },
    diet: { icon: '🥗', main: 'Диета и питьевой режим', sub: 'Соблюдение ограничений' }
  };

  var DURATION_LABELS = {
    '15min': '15 мин',
    '30min': '30 мин',
    '1h': '1 час',
    '1h_plus': '> 1 часа'
  };

  var statusEl = document.getElementById('routine-status');

  function showStatus(msg, type) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.className = 'routine-status ' + (type === 'success' ? 'success' : 'error');
    statusEl.classList.remove('routine-status-hidden');
  }

  function clearStatus() {
    if (!statusEl) return;
    statusEl.textContent = '';
    statusEl.className = 'routine-status routine-status-hidden';
  }

  // --- Табы ---
  function initTabs() {
    var tabs = document.querySelectorAll('.routine-tab');
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        var target = tab.getAttribute('data-tab');
        tabs.forEach(function (t) { t.classList.remove('active'); });
        tab.classList.add('active');

        document.querySelectorAll('.routine-section').forEach(function (section) {
          section.classList.add('routine-hidden');
        });
        var sectionId = target === 'baseline'
          ? 'routine-baseline'
          : target === 'planner'
            ? 'routine-planner'
            : 'routine-verification';
        var sec = document.getElementById(sectionId);
        if (sec) sec.classList.remove('routine-hidden');
      });
    });
  }

  // --- Baseline: 4 шага ---
  var baselineState = {
    step: 1,
    activity_pool: [],
    dialysis_day_template: [],
    non_dialysis_day_template: [],
    planning_time: null
  };

  function toggleActivityIn(list, value) {
    var idx = list.indexOf(value);
    if (idx === -1) list.push(value);
    else list.splice(idx, 1);
  }

  function buildBaselineCards(containerId, sourceList, stateList) {
    var root = document.getElementById(containerId);
    if (!root) return;
    root.innerHTML = '';
    sourceList.forEach(function (code) {
      var def = ACTIVITY_DEFS[code];
      if (!def) return;
      var card = document.createElement('button');
      card.type = 'button';
      card.className = 'routine-activity-card';
      card.setAttribute('data-code', code);

      var icon = document.createElement('span');
      icon.className = 'routine-activity-icon';
      icon.textContent = def.icon;
      card.appendChild(icon);

      var label = document.createElement('span');
      label.className = 'routine-activity-label';
      var main = document.createElement('span');
      main.className = 'routine-activity-label-main';
      main.textContent = def.main;
      label.appendChild(main);
      if (code === 'self_care') {
        var sub1 = document.createElement('span');
        sub1.className = 'routine-activity-label-sub';
        sub1.textContent = 'Гигиена,';
        var sub2 = document.createElement('span');
        sub2.className = 'routine-activity-label-sub';
        sub2.textContent = 'внешний вид';
        label.appendChild(sub1);
        label.appendChild(sub2);
      } else {
        var sub = document.createElement('span');
        sub.className = 'routine-activity-label-sub';
        sub.textContent = def.sub;
        label.appendChild(sub);
      }
      card.appendChild(label);

      if (stateList.indexOf(code) !== -1) card.classList.add('active');

      card.addEventListener('click', function () {
        toggleActivityIn(stateList, code);
        card.classList.toggle('active');
      });

      root.appendChild(card);
    });
  }

  function updateBaselineStepHeader() {
    var titleEl = document.getElementById('routine-baseline-step-title');
    var subtitleEl = document.getElementById('routine-baseline-step-subtitle');
    if (!titleEl || !subtitleEl) return;
    var t = baselineState.step;
    titleEl.textContent = 'Шаг ' + t + ' из 4';
    if (t === 1) {
      subtitleEl.textContent = 'Отметьте занятия, которые есть в вашей обычной жизни.';
    } else if (t === 2) {
      subtitleEl.textContent = 'В день диализа — что из этого вы обычно делаете?';
    } else if (t === 3) {
      subtitleEl.textContent = 'В обычный день без диализа — что из этого вы обычно делаете?';
    } else {
      subtitleEl.textContent = 'Когда вам удобнее планировать день?';
    }
  }

  function showBaselineStep(step) {
    baselineState.step = step;
    updateBaselineStepHeader();
    ['baseline-step-1', 'baseline-step-2', 'baseline-step-3', 'baseline-step-4'].forEach(function (id, idx) {
      var el = document.getElementById(id);
      if (!el) return;
      el.classList.toggle('routine-hidden', idx + 1 !== step);
    });

    var backBtn = document.getElementById('baseline-prev');
    var nextBtn = document.getElementById('baseline-next');
    if (backBtn) backBtn.disabled = step === 1;
    if (nextBtn) nextBtn.textContent = step === 4 ? 'Сохранить' : 'Далее';
  }

  function validateBaselineStep(step) {
    if (step === 1) {
      return baselineState.activity_pool.length > 0;
    }
    if (step === 4) {
      return !!baselineState.planning_time;
    }
    return true;
  }

  function initBaseline() {
    var poolCodes = Object.keys(ACTIVITY_DEFS);
    baselineState.activity_pool = [];
    baselineState.dialysis_day_template = [];
    baselineState.non_dialysis_day_template = [];
    baselineState.planning_time = null;

    buildBaselineCards('baseline-activity-pool', poolCodes, baselineState.activity_pool);

    var nextBtn = document.getElementById('baseline-next');
    var prevBtn = document.getElementById('baseline-prev');
    if (nextBtn) {
      nextBtn.addEventListener('click', function () {
        clearStatus();
        var current = baselineState.step;
        if (!validateBaselineStep(current)) {
          showStatus('Пожалуйста, заполните этот шаг.', 'error');
          return;
        }
        if (current < 4) {
          if (current === 1) {
            buildBaselineCards('baseline-dialysis-template', baselineState.activity_pool, baselineState.dialysis_day_template);
            buildBaselineCards('baseline-non-dialysis-template', baselineState.activity_pool, baselineState.non_dialysis_day_template);
          }
          showBaselineStep(current + 1);
        } else {
          saveBaseline();
        }
      });
    }
    if (prevBtn) {
      prevBtn.addEventListener('click', function () {
        clearStatus();
        if (baselineState.step > 1) {
          showBaselineStep(baselineState.step - 1);
        }
      });
    }

    document.querySelectorAll('.routine-planning-time .routine-chip').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var value = btn.getAttribute('data-planning-time');
        baselineState.planning_time = value;
        document.querySelectorAll('.routine-planning-time .routine-chip').forEach(function (b) {
          b.classList.toggle('active', b === btn);
        });
      });
    });

    // Попробуем подгрузить существующий baseline и предзаполнить состояние
    fetch('/api/v1/routine/baseline', { credentials: 'include' })
      .then(function (res) {
        if (res.status === 404) return null;
        if (!res.ok) throw new Error(res.statusText);
        return res.json();
      })
      .then(function (body) {
        if (!body) return;
        baselineState.activity_pool = body.activity_pool || [];
        baselineState.dialysis_day_template = body.dialysis_day_template || [];
        baselineState.non_dialysis_day_template = body.non_dialysis_day_template || [];
        baselineState.planning_time = body.planning_time || null;

        buildBaselineCards('baseline-activity-pool', poolCodes, baselineState.activity_pool);
        buildBaselineCards('baseline-dialysis-template', baselineState.activity_pool, baselineState.dialysis_day_template);
        buildBaselineCards('baseline-non-dialysis-template', baselineState.activity_pool, baselineState.non_dialysis_day_template);
        document.querySelectorAll('.routine-planning-time .routine-chip').forEach(function (b) {
          var value = b.getAttribute('data-planning-time');
          b.classList.toggle('active', value === baselineState.planning_time);
        });
      })
      .catch(function () {
        // тихо игнорируем, baseline можно заполнить с нуля
      });

    showBaselineStep(1);
  }

  function saveBaseline() {
    var payload = {
      activity_pool: baselineState.activity_pool,
      dialysis_day_template: baselineState.dialysis_day_template,
      non_dialysis_day_template: baselineState.non_dialysis_day_template,
      planning_time: baselineState.planning_time
    };
    var btn = document.getElementById('baseline-next');
    if (btn) btn.disabled = true;
    fetch('/api/v1/routine/baseline', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload)
    })
      .then(function (res) {
        if (!res.ok) return res.json().then(function (j) { throw new Error(j.detail || res.statusText); });
        return res.json();
      })
      .then(function () {
        showStatus('Шаблон сохранён.', 'success');
      })
      .catch(function (err) {
        showStatus(err.message || 'Ошибка сохранения шаблона.', 'error');
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  }

  // --- Планер ---
  var plannerState = {
    date: null,
    dialysis_day: null,
    template_activities: {},
    added_from_pool: {},
    custom_activities: [null, null, null, null, null]
  };

  function toTodayISO() {
    var d = new Date();
    var y = d.getFullYear();
    var m = d.getMonth() + 1;
    var day = d.getDate();
    return y + '-' + (m < 10 ? '0' + m : m) + '-' + (day < 10 ? '0' + day : day);
  }

  function buildPlannerFromPlan(plan) {
    plannerState.dialysis_day = plan.dialysis_day;
    plannerState.template_activities = plan.template_activities || {};
    plannerState.added_from_pool = plan.added_from_pool || {};
    plannerState.custom_activities = plan.custom_activities || [null, null, null, null, null];

    var dialysisBadge = document.getElementById('planner-dialysis-badge');
    if (dialysisBadge) {
      if (plannerState.dialysis_day) dialysisBadge.classList.remove('routine-hidden');
      else dialysisBadge.classList.add('routine-hidden');
    }

    var tmplRoot = document.getElementById('planner-template-activities');
    var poolRoot = document.getElementById('planner-pool-activities');
    var customRoot = document.getElementById('planner-custom-activities');
    if (tmplRoot) tmplRoot.innerHTML = '';
    if (poolRoot) poolRoot.innerHTML = '';
    if (customRoot) customRoot.innerHTML = '';

    function createPlannedRow(code, item, isTemplate) {
      var row = document.createElement('div');
      row.className = 'routine-activity-row';
      row.setAttribute('data-code', code);
      row.setAttribute('data-block', isTemplate ? 'template' : 'pool');

      var checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = !!item.planned;
      checkbox.style.minWidth = '18px';
      row.appendChild(checkbox);

      var name = document.createElement('div');
      name.className = 'routine-activity-name';
      var def = ACTIVITY_DEFS[code] || { main: code, icon: '' };
      name.textContent = def.main;
      row.appendChild(name);

      var durationGroup = document.createElement('div');
      durationGroup.className = 'routine-duration-group';
      durationGroup.setAttribute('data-role', 'duration-group');

      if (code === 'diet') {
        var dietHint = document.createElement('span');
        dietHint.className = 'routine-duration-hint';
        dietHint.textContent = '(длительность не указывается)';
        durationGroup.appendChild(dietHint);
      }

      Object.keys(DURATION_LABELS).forEach(function (dur) {
        if (code === 'diet') return;
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'routine-duration-chip';
        btn.textContent = DURATION_LABELS[dur];
        btn.setAttribute('data-duration', dur);
        if (item.planned_duration === dur) btn.classList.add('active');
        btn.addEventListener('click', function () {
          if (!checkbox.checked) return;
          var block = row.getAttribute('data-block');
          var target = block === 'template' ? plannerState.template_activities : plannerState.added_from_pool;
          Object.keys(DURATION_LABELS).forEach(function (d) {
            var chips = durationGroup.querySelectorAll('[data-duration="' + d + '"]');
            chips.forEach(function (c) { c.classList.remove('active'); });
          });
          btn.classList.add('active');
          if (!target[code]) target[code] = { planned: true, planned_duration: null };
          target[code].planned_duration = dur;
        });
        durationGroup.appendChild(btn);
      });

      if (!checkbox.checked) {
        durationGroup.style.display = 'none';
      }
      checkbox.addEventListener('change', function () {
        var block = row.getAttribute('data-block');
        var target = block === 'template' ? plannerState.template_activities : plannerState.added_from_pool;
        if (!target[code]) target[code] = { planned: false, planned_duration: null };
        target[code].planned = checkbox.checked;
        if (code === 'diet') {
          durationGroup.style.display = 'none';
        } else {
          durationGroup.style.display = checkbox.checked ? 'flex' : 'none';
        }
      });

      row.appendChild(durationGroup);
      return row;
    }

    if (tmplRoot) {
      Object.keys(plannerState.template_activities).forEach(function (code) {
        var item = plannerState.template_activities[code] || { planned: true, planned_duration: null };
        tmplRoot.appendChild(createPlannedRow(code, item, true));
      });
    }

    if (poolRoot) {
      Object.keys(plannerState.added_from_pool).forEach(function (code) {
        var item = plannerState.added_from_pool[code] || { planned: false, planned_duration: null };
        poolRoot.appendChild(createPlannedRow(code, item, false));
      });
    }

    if (customRoot) {
      for (var i = 0; i < 5; i++) {
        (function (index) {
          var row = document.createElement('div');
          row.className = 'routine-custom-row';
          var input = document.createElement('input');
          input.type = 'text';
          input.className = 'routine-input';
          input.placeholder = 'Например, позвонить врачу';

          var durGroup = document.createElement('div');
          durGroup.className = 'routine-duration-group';

          Object.keys(DURATION_LABELS).forEach(function (dur) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'routine-duration-chip';
            btn.textContent = DURATION_LABELS[dur];
            btn.setAttribute('data-duration', dur);
            btn.addEventListener('click', function () {
              if (!input.value) return;
              var current = plannerState.custom_activities[index] || { text: input.value, planned_duration: null };
              current.text = input.value;
              current.planned_duration = dur;
              plannerState.custom_activities[index] = current;
              durGroup.querySelectorAll('.routine-duration-chip').forEach(function (c) { c.classList.remove('active'); });
              btn.classList.add('active');
            });
            durGroup.appendChild(btn);
          });

          input.addEventListener('input', function () {
            if (!input.value) {
              plannerState.custom_activities[index] = null;
              durGroup.querySelectorAll('.routine-duration-chip').forEach(function (c) { c.classList.remove('active'); });
              return;
            }
            var current = plannerState.custom_activities[index] || { text: input.value, planned_duration: null };
            current.text = input.value;
            plannerState.custom_activities[index] = current;
          });

          var existing = plannerState.custom_activities[index];
          if (existing && existing.text) {
            input.value = existing.text;
            if (existing.planned_duration) {
              var activeBtn = durGroup.querySelector('[data-duration="' + existing.planned_duration + '"]');
              if (activeBtn) activeBtn.classList.add('active');
            }
          }

          row.appendChild(input);
          row.appendChild(durGroup);
          customRoot.appendChild(row);
        })(i);
      }
    }
  }

  function loadPlanForDate(dateStr) {
    plannerState.date = dateStr;
    clearStatus();
    fetch('/api/v1/routine/plan?date=' + encodeURIComponent(dateStr), { credentials: 'include' })
      .then(function (res) {
        if (res.status === 404) {
          showStatus('Сначала заполните вкладку «Мой обычный день».', 'error');
          buildPlannerFromPlan({
            dialysis_day: null,
            template_activities: {},
            added_from_pool: {},
            custom_activities: [null, null, null, null, null]
          });
          return null;
        }
        if (!res.ok) return res.json().then(function (j) { throw new Error(j.detail || res.statusText); });
        return res.json();
      })
      .then(function (body) {
        // #region agent log
        if (body) {
          var _ta = body.template_activities ? Object.keys(body.template_activities) : [];
          var _ap = body.added_from_pool ? Object.keys(body.added_from_pool) : [];
          fetch('http://127.0.0.1:7243/ingest/fb06d002-78a5-4e63-9c2e-8526884849e3', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'routine.js:loadPlanForDate', message: 'plan body received', data: { template_keys: _ta, added_keys: _ap }, hypothesisId: 'H2,H5', timestamp: Date.now() }) }).catch(function () {});
        }
        // #endregion
        if (body) buildPlannerFromPlan(body);
      })
      .catch(function (err) {
        showStatus(err.message || 'Не удалось загрузить план.', 'error');
      });
  }

  function initPlanner() {
    var dateInput = document.getElementById('planner-date');
    if (!dateInput) return;
    var today = toTodayISO();
    dateInput.value = today;
    plannerState.date = today;
    dateInput.addEventListener('change', function () {
      loadPlanForDate(dateInput.value);
    });

    loadPlanForDate(today);

    var sliderDayLabel = document.getElementById('planner-day-label');
    if (sliderDayLabel) sliderDayLabel.textContent = 'Ваш план на сегодня';

    var saveBtn = document.getElementById('planner-save');
    if (saveBtn) {
      saveBtn.addEventListener('click', function () {
        if (!plannerState.date) return;
        clearStatus();
        saveBtn.disabled = true;
        // #region agent log
        var _ta = plannerState.template_activities ? Object.keys(plannerState.template_activities) : [];
        var _ap = plannerState.added_from_pool ? Object.keys(plannerState.added_from_pool) : [];
        fetch('http://127.0.0.1:7243/ingest/fb06d002-78a5-4e63-9c2e-8526884849e3', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ location: 'routine.js:planner save', message: 'payload before send', data: { template_keys: _ta, added_keys: _ap }, hypothesisId: 'H3', timestamp: Date.now() }) }).catch(function () {});
        // #endregion
        var payload = {
          plan_date: plannerState.date,
          dialysis_day: plannerState.dialysis_day,
          template_activities: plannerState.template_activities,
          added_from_pool: plannerState.added_from_pool,
          custom_activities: plannerState.custom_activities
        };
        fetch('/api/v1/routine/plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(payload)
        })
          .then(function (res) {
            if (!res.ok) return res.json().then(function (j) { throw new Error(j.detail || res.statusText); });
            return res.json();
          })
          .then(function () {
            showStatus('План сохранён.', 'success');
          })
          .catch(function (err) {
            showStatus(err.message || 'Ошибка сохранения плана.', 'error');
          })
          .finally(function () {
            saveBtn.disabled = false;
          });
      });
    }
  }

  // --- Верификация ---
  var verificationState = {
    date: null,
    template_executed: {},
    pool_added_executed: {},
    custom_executed: {},
    unplanned_executed: [],
    custom_unplanned: '',
    custom_unplanned_items: [],
    day_control_score: 5
  };

  function initVerificationSlider() {
    var slider = document.getElementById('verification-day-control');
    var label = document.getElementById('verification-day-control-value');
    if (!slider || !label) return;
    slider.value = '5';
    label.textContent = '5 / 10';
    slider.addEventListener('input', function () {
      label.textContent = slider.value + ' / 10';
      verificationState.day_control_score = parseInt(slider.value, 10);
    });
  }

  function buildVerificationFromPlanAndData(plan, ver) {
    var fromPlanSection = document.getElementById('verification-from-plan');
    var listRoot = document.getElementById('verification-planned-list');
    var unplannedRoot = document.getElementById('verification-unplanned-list');
    if (listRoot) listRoot.innerHTML = '';
    if (unplannedRoot) unplannedRoot.innerHTML = '';

    var dialysisBadge = document.getElementById('verification-dialysis-badge');
    if (dialysisBadge) {
      if (plan && plan.dialysis_day) dialysisBadge.classList.remove('routine-hidden');
      else dialysisBadge.classList.add('routine-hidden');
    }

    verificationState.template_executed = ver && ver.template_executed ? ver.template_executed : {};
    verificationState.pool_added_executed = ver && ver.pool_added_executed ? ver.pool_added_executed : {};
    verificationState.custom_executed = ver && ver.custom_executed ? ver.custom_executed : {};
    verificationState.unplanned_executed = ver && ver.unplanned_executed ? ver.unplanned_executed : [];
    verificationState.custom_unplanned = ver && ver.custom_unplanned ? ver.custom_unplanned : '';
    verificationState.custom_unplanned_items = [];
    if (verificationState.custom_unplanned) {
      verificationState.custom_unplanned.split(';').forEach(function (raw) {
        var text = (raw || '').trim();
        if (text) {
          verificationState.custom_unplanned_items.push({ text: text, done: true });
        }
      });
    }
    verificationState.day_control_score = ver && typeof ver.day_control_score === 'number' ? ver.day_control_score : 5;

    var slider = document.getElementById('verification-day-control');
    var sliderLabel = document.getElementById('verification-day-control-value');
    if (slider && sliderLabel) {
      slider.value = String(verificationState.day_control_score);
      sliderLabel.textContent = verificationState.day_control_score + ' / 10';
    }

    function createExecRow(label, key, blockType, isDiet) {
      var row = document.createElement('div');
      row.className = 'routine-activity-row';
      row.setAttribute('data-key', key);
      row.setAttribute('data-block', blockType);

      var name = document.createElement('div');
      name.className = 'routine-activity-name';
      name.textContent = label;
      row.appendChild(name);

      if (isDiet) {
        var dietGroup = document.createElement('div');
        dietGroup.className = 'routine-duration-group';
        var options = [
          { value: 'fully', label: 'Полностью' },
          { value: 'partly', label: 'Частично' },
          { value: 'no', label: 'Нет' }
        ];
        options.forEach(function (opt) {
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'routine-duration-chip';
          btn.textContent = opt.label;
          btn.setAttribute('data-diet', opt.value);
          if (verificationState.template_executed[key] && verificationState.template_executed[key].done === opt.value) {
            btn.classList.add('active');
          }
          btn.addEventListener('click', function () {
            verificationState.template_executed[key] = verificationState.template_executed[key] || {};
            verificationState.template_executed[key].done = opt.value;
            dietGroup.querySelectorAll('.routine-duration-chip').forEach(function (c) { c.classList.remove('active'); });
            btn.classList.add('active');
          });
          dietGroup.appendChild(btn);
        });
        var dietHint = document.createElement('span');
        dietHint.className = 'routine-duration-hint';
        dietHint.textContent = '(длительность не указывается)';
        dietGroup.appendChild(dietHint);
        row.appendChild(dietGroup);
      } else {
        var yesNoGroup = document.createElement('div');
        yesNoGroup.className = 'routine-duration-group';
        ['yes', 'no'].forEach(function (val) {
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'routine-duration-chip';
          btn.textContent = val === 'yes' ? 'Да' : 'Нет';
          btn.setAttribute('data-done', val);
          var block = blockType === 'template' ? verificationState.template_executed
            : blockType === 'pool' ? verificationState.pool_added_executed
              : verificationState.custom_executed;
          if (block[key] && block[key].done === val) btn.classList.add('active');
          btn.addEventListener('click', function () {
            var b = block;
            b[key] = b[key] || {};
            b[key].done = val;
            yesNoGroup.querySelectorAll('.routine-duration-chip').forEach(function (c) { c.classList.remove('active'); });
            btn.classList.add('active');
          });
          yesNoGroup.appendChild(btn);
        });
        row.appendChild(yesNoGroup);
      }

      return row;
    }

    if (plan && listRoot) {
      if (plan.template_activities) {
        Object.keys(plan.template_activities).forEach(function (code) {
          var def = ACTIVITY_DEFS[code] || { main: code };
          var isDiet = code === 'diet';
          listRoot.appendChild(createExecRow(def.main, code, 'template', isDiet));
        });
      }
      if (plan.added_from_pool) {
        Object.keys(plan.added_from_pool).forEach(function (code) {
          var def = ACTIVITY_DEFS[code] || { main: code };
          listRoot.appendChild(createExecRow(def.main, code, 'pool', false));
        });
      }
      if (plan.custom_activities) {
        plan.custom_activities.forEach(function (item) {
          if (!item || !item.text) return;
          listRoot.appendChild(createExecRow(item.text, item.text, 'custom', false));
        });
      }
      if (fromPlanSection) {
        fromPlanSection.classList.remove('routine-hidden');
      }
    } else {
      if (fromPlanSection) {
        fromPlanSection.classList.remove('routine-hidden');
      }
      if (listRoot) {
        listRoot.innerHTML = '';
        var emptyMsg = document.createElement('p');
        emptyMsg.className = 'routine-duration-hint';
        emptyMsg.textContent = 'Нет запланированных активностей на эту дату.';
        listRoot.appendChild(emptyMsg);
      }
    }

    var unplannedCategories = ['physical', 'household', 'work', 'leisure', 'social', 'self_care', 'diet'];
    if (unplannedRoot) {
      unplannedCategories.forEach(function (code) {
        var def = ACTIVITY_DEFS[code] || { main: code };
        var row = document.createElement('div');
        row.className = 'routine-activity-row';
        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = verificationState.unplanned_executed.indexOf(code) !== -1;
        checkbox.addEventListener('change', function () {
          var idx = verificationState.unplanned_executed.indexOf(code);
          if (checkbox.checked && idx === -1) verificationState.unplanned_executed.push(code);
          if (!checkbox.checked && idx !== -1) verificationState.unplanned_executed.splice(idx, 1);
        });
        var name = document.createElement('div');
        name.className = 'routine-activity-name';
        name.textContent = def.main;
        row.appendChild(checkbox);
        row.appendChild(name);
        unplannedRoot.appendChild(row);
      });

      if (verificationState.custom_unplanned_items && verificationState.custom_unplanned_items.length) {
        verificationState.custom_unplanned_items.forEach(function (item) {
          var row = document.createElement('div');
          row.className = 'routine-activity-row';
          var cb = document.createElement('input');
          cb.type = 'checkbox';
          cb.checked = item.done !== false;
          cb.addEventListener('change', function () {
            item.done = cb.checked;
          });
          var name = document.createElement('div');
          name.className = 'routine-activity-name';
          name.textContent = item.text;
          row.appendChild(cb);
          row.appendChild(name);
          unplannedRoot.appendChild(row);
        });
      }
    }

    var customUnplanned = document.getElementById('verification-custom-unplanned');
    if (customUnplanned) {
      customUnplanned.value = '';
      var addBtn = document.getElementById('verification-add-custom-unplanned');
      if (addBtn && unplannedRoot) {
        addBtn.addEventListener('click', function () {
          var text = (customUnplanned.value || '').trim();
          if (!text) return;
          var item = { text: text, done: true };
          if (!verificationState.custom_unplanned_items) {
            verificationState.custom_unplanned_items = [];
          }
          verificationState.custom_unplanned_items.push(item);

          var row = document.createElement('div');
          row.className = 'routine-activity-row';
          var cb = document.createElement('input');
          cb.type = 'checkbox';
          cb.checked = true;
          cb.addEventListener('change', function () {
            item.done = cb.checked;
          });
          var name = document.createElement('div');
          name.className = 'routine-activity-name';
          name.textContent = text;
          row.appendChild(cb);
          row.appendChild(name);
          unplannedRoot.appendChild(row);

          customUnplanned.value = '';
        });
      }
    }
  }

  function loadVerificationForDate(dateStr) {
    verificationState.date = dateStr;
    clearStatus();
    var dateObj = new Date(dateStr + 'T00:00:00');
    var dialysisFlag = null;

    fetch('/api/v1/routine/verification?date=' + encodeURIComponent(dateStr), { credentials: 'include' })
      .then(function (res) {
        if (res.status === 404) return null;
        if (!res.ok) return res.json().then(function (j) { throw new Error(j.detail || res.statusText); });
        return res.json();
      })
      .then(function (verBody) {
        return fetch('/api/v1/routine/plan?date=' + encodeURIComponent(dateStr), { credentials: 'include' })
          .then(function (res) {
            if (!res.ok) {
              if (res.status === 404) return null;
              return res.json().then(function (j) { throw new Error(j.detail || res.statusText); });
            }
            return res.json();
          })
          .then(function (planBody) {
            buildVerificationFromPlanAndData(planBody, verBody);
          });
      })
      .catch(function (err) {
        showStatus(err.message || 'Ошибка загрузки верификации.', 'error');
      });
  }

  function initVerification() {
    initVerificationSlider();
    var dateInput = document.getElementById('verification-date');
    if (!dateInput) return;
    var today = toTodayISO();
    dateInput.value = today;
    loadVerificationForDate(today);
    dateInput.addEventListener('change', function () {
      loadVerificationForDate(dateInput.value);
    });

    var saveBtn = document.getElementById('verification-save');
    if (saveBtn) {
      saveBtn.addEventListener('click', function () {
        if (!verificationState.date) return;
        clearStatus();
        saveBtn.disabled = true;
        var customJoined = '';
        if (verificationState.custom_unplanned_items && verificationState.custom_unplanned_items.length) {
          var texts = verificationState.custom_unplanned_items
            .filter(function (it) { return it && it.done !== false && it.text && it.text.trim(); })
            .map(function (it) { return it.text.trim(); });
          if (texts.length) {
            customJoined = texts.join('; ');
          }
        } else if (verificationState.custom_unplanned) {
          customJoined = verificationState.custom_unplanned;
        }
        var payload = {
          verification_date: verificationState.date,
          dialysis_day: null,
          template_executed: verificationState.template_executed,
          pool_added_executed: verificationState.pool_added_executed,
          custom_executed: verificationState.custom_executed,
          unplanned_executed: verificationState.unplanned_executed,
          custom_unplanned: customJoined || null,
          day_control_score: verificationState.day_control_score
        };
        fetch('/api/v1/routine/verification', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(payload)
        })
          .then(function (res) {
            if (!res.ok) return res.json().then(function (j) { throw new Error(j.detail || res.statusText); });
            return res.json();
          })
          .then(function () {
            showStatus('Ответ сохранён.', 'success');
          })
          .catch(function (err) {
            showStatus(err.message || 'Ошибка сохранения.', 'error');
          })
          .finally(function () {
            saveBtn.disabled = false;
          });
      });
    }
  }

  // --- Навешиваем обработчики после загрузки DOM ---
  document.addEventListener('DOMContentLoaded', function () {
    initTabs();
    initBaseline();
    initPlanner();
    initVerification();
  });
})();

