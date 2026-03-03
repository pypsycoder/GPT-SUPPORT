/**
 * profile.js — Скрипт страницы профиля пациента
 *
 * Загружает данные профиля, отображает их и позволяет редактировать
 * личную информацию (ФИО, возраст, пол).
 */
(function () {
  'use strict';

  // ========================================
  // Утилиты
  // ========================================

  /**
   * API запросы используют session cookies для авторизации
   * (не нужно передавать токен в URL или заголовках)
   */

  /**
   * Форматирование даты в читаемый вид
   */
  function formatDate(dateString) {
    if (!dateString) return '—';
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  /**
   * Форматирование даты без времени
   */
  function formatDateShort(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'short',
    });
  }

  /**
   * Перевод пола на русский
   */
  function formatGender(gender) {
    if (gender === 'male') return 'Мужской';
    if (gender === 'female') return 'Женский';
    return 'Не указан';
  }

  /**
   * Перевод смены диализа на русский
   */
  function formatShift(shift) {
    if (shift === 'morning') return 'Утренняя';
    if (shift === 'afternoon') return 'Дневная';
    if (shift === 'evening') return 'Вечерняя';
    return shift || '—';
  }

  /**
   * Перевод дней недели (ISO 1–7) в строку
   */
  function formatWeekdays(weekdays) {
    if (!weekdays || weekdays.length === 0) return '—';
    const names = { 1: 'Пн', 2: 'Вт', 3: 'Ср', 4: 'Чт', 5: 'Пт', 6: 'Сб', 7: 'Вс' };
    return weekdays.map((d) => names[d] || d).join(', ');
  }

  // ========================================
  // Статусная плашка
  // ========================================

  function setStatus(type, message) {
    const banner = document.getElementById('status-banner');
    if (!banner) return;

    banner.textContent = message || '';
    banner.classList.remove('status-hidden', 'status-success', 'status-error');

    if (type === 'success') {
      banner.classList.add('status-success');
      // Автоскрытие через 3 секунды
      setTimeout(() => {
        banner.classList.add('status-hidden');
      }, 3000);
    } else if (type === 'error') {
      banner.classList.add('status-error');
    } else {
      banner.classList.add('status-hidden');
    }
  }

  // ========================================
  // Достижения — конфигурация
  // ========================================

  const LEVEL_COLORS     = ['gray', 'blue', 'green', 'green', 'gold'];
  const LEVEL_DOT_CLASSES = ['dot-gray', 'dot-blue', 'dot-green', 'dot-green', 'dot-gold'];
  const PAST_COLORS      = ['gray', 'blue', 'green', 'green', 'gold'];

  const TRACKER_DATA = {
    medications: {
      icon: '💊',
      levels: [
        { name: 'Начало',        desc: 'Первая отметка' },
        { name: 'Неделя',        desc: '5 из 7 дней' },
        { name: 'Две недели',    desc: '10 из 14 дней' },
        { name: 'Три недели',    desc: '15 из 21 дня' },
        { name: 'Надёжная рука', desc: '22 из 30 дней' },
      ],
    },
    sleep: {
      icon: '😴',
      levels: [
        { name: 'Первая запись', desc: 'Начало пути' },
        { name: 'Неделя',        desc: '5 из 7 дней' },
        { name: 'Две недели',    desc: '10 из 14 дней' },
        { name: 'Три недели',    desc: '15 из 21 дня' },
        { name: 'Знаю свой сон', desc: '22 из 30 дней' },
      ],
    },
    vitals: {
      icon: '📊',
      levels: [
        { name: 'Первый замер',          desc: 'Первая запись' },
        { name: 'Неделя',                desc: '5 из 7 дней' },
        { name: 'Две недели',            desc: '10 из 14 дней' },
        { name: 'Три недели',            desc: '15 из 21 дня' },
        { name: 'Держу руку на пульсе',  desc: '22 из 30 дней' },
      ],
    },
    practices: {
      icon: '🧘',
      levels: [
        { name: 'Первая практика', desc: 'Начало' },
        { name: 'Неделя',          desc: '5 из 7 дней' },
        { name: 'Две недели',      desc: '10 из 14 дней' },
        { name: 'Три недели',      desc: '15 из 21 дня' },
        { name: 'Моя опора',       desc: '22 из 30 дней' },
      ],
    },
    scales: {
      icon: '🤝',
      levels: [
        { name: 'Этап T0', desc: 'Первичные шкалы' },
        { name: 'Этап T1', desc: 'Промежуточные шкалы' },
        { name: 'Этап T2', desc: 'Итоговые шкалы' },
      ],
    },
  };

  // Правильные пути фронтенда (из sidebar.js и роутеров)
  const TRACKER_URLS = {
    medications: '/patient/medications',
    sleep:       '/patient/sleep_tracker',
    vitals:      '/patient/vitals',
    practices:   '/patient/education_overview',
    scales:      '/patient/scales',
  };

  const TRACKER_STREAK_NAMES = {
    medications: '💊 Лекарств',
    sleep:       '😴 Сон',
    vitals:      '📊 Показатели',
    practices:   '🧘 Практик',
  };

  // Конфигурация модалок (трекеры + бонусы)
  const MODALS = {
    medications: {
      icon: '💊', name: 'Лекарства',
      steps: [
        { label: 'Первая отметка', key: 'med_start' },
        { label: '5 из 7 дней',   key: 'med_week' },
        { label: '10 из 14 дней', key: 'med_2weeks' },
        { label: '15 из 21 дня',  key: 'med_3weeks' },
        { label: '22 из 30 дней', key: 'med_month' },
      ],
    },
    sleep: {
      icon: '😴', name: 'Сон',
      steps: [
        { label: 'Первая запись', key: 'sleep_start' },
        { label: '5 из 7 дней',  key: 'sleep_week' },
        { label: '10 из 14 дней',key: 'sleep_2weeks' },
        { label: '15 из 21 дня', key: 'sleep_3weeks' },
        { label: '22 из 30 дней',key: 'sleep_month' },
      ],
    },
    vitals: {
      icon: '📊', name: 'Показатели',
      steps: [
        { label: 'Первый замер', key: 'vitals_start' },
        { label: '5 из 7 дней', key: 'vitals_week' },
        { label: '10 из 14 дней',key: 'vitals_2weeks' },
        { label: '15 из 21 дня', key: 'vitals_3weeks' },
        { label: '22 из 30 дней',key: 'vitals_month' },
      ],
    },
    practices: {
      icon: '🧘', name: 'Практики',
      steps: [
        { label: 'Первая практика',key: 'practice_start' },
        { label: '5 из 7 дней',   key: 'practice_week' },
        { label: '10 из 14 дней', key: 'practice_2weeks' },
        { label: '15 из 21 дня',  key: 'practice_3weeks' },
        { label: '22 из 30 дней', key: 'practice_month' },
      ],
    },
    scales: {
      icon: '🤝', name: 'Шкалы исследования',
      desc: 'Этапы оценки состояния',
      steps: [
        { label: 'T0 — первичные шкалы',     key: 'scale_t0' },
        { label: 'T1 — промежуточные шкалы', key: 'scale_t1' },
        { label: 'T2 — итоговые шкалы',      key: 'scale_t2' },
      ],
    },
    vitals_full: {
      icon: '💡', name: 'Полная картина',
      desc: 'Все 4 показателя за один день',
      steps: [{ label: 'Внести АД, пульс, воду и вес в один день', key: 'vitals_full' }],
    },
    practice_5: {
      icon: '🧘', name: 'Пробую',
      desc: 'Выполнено 5 разных практик',
      steps: [{ label: 'Выполнить 5 разных практик', key: 'practice_5' }],
    },
    practice_all: {
      icon: '⭐', name: 'Исследователь',
      desc: 'Выполнены все 9 практик',
      steps: [{ label: 'Выполнить все 9 доступных практик', key: 'practice_all' }],
    },
  };

  // Бейджи обучения с текстом оверлея и цветом для earned-состояния
  const EDUCATION_BADGES = [
    { key: 'lesson_first', icon: '📖', name: 'Хочу понимать',
      color: 'blue',  desc: 'Первый урок пройден',
      overlayText: 'Пройдите первый образовательный урок' },
    { key: 'psych_block',  icon: '🧠', name: 'Психологический блок',
      color: 'green', desc: 'Все 9 модулей блока А',
      overlayText: 'Пройдите все 9 уроков блока «Здоровый ум»' },
    { key: 'nephro_block', icon: '🫀', name: 'Жизнь с диализом',
      color: 'green', desc: 'Все 9 модулей блока Б',
      overlayText: 'Пройдите все 9 уроков блока «Жизнь с диализом»' },
    { key: 'all_lessons',  icon: '⭐', name: 'Всё прочитал',
      color: 'gold',  desc: 'Все 18 модулей пройдены',
      overlayText: 'Пройдите все 18 образовательных модулей' },
  ];

  // Особые бонусные бейджи
  const SPECIAL_BADGES = [
    { key: 'vitals_full',   icon: '💡', name: 'Полная картина' },
    { key: 'practice_5',    icon: '🧘', name: 'Пробую' },
    { key: 'practice_all',  icon: '⭐', name: 'Исследователь' },
  ];

  // ========================================
  // Модалка трекера / бонусного бейджа
  // ========================================

  function openModal(tracker) {
    const cfg = MODALS[tracker];
    if (!cfg) return;
    const earnedKeys = window._earnedBadgeKeys || [];

    let stepsHtml = '';
    if (cfg.steps && cfg.steps.length) {
      stepsHtml = cfg.steps.map((step, i) => {
        const done = earnedKeys.includes(step.key);
        const prevDone = cfg.steps.slice(0, i).every(s => earnedKeys.includes(s.key));
        const isNext = !done && prevDone;
        const cls  = done ? 'done' : isNext ? 'next' : 'locked-step';
        const icon = done ? '✅' : isNext ? '→' : '⬜';
        return `<li class="badge-modal-step ${cls}">
          <span class="step-icon">${icon}</span>
          <span>${step.label}</span>
        </li>`;
      }).join('');
    }

    const overlay = document.createElement('div');
    overlay.className = 'badge-modal-overlay';
    overlay.innerHTML = `<div class="badge-modal">
      <div class="badge-modal-icon">${cfg.icon}</div>
      <div class="badge-modal-name">${cfg.name}</div>
      ${cfg.desc ? `<div class="badge-modal-desc">${cfg.desc}</div>` : ''}
      ${stepsHtml ? `<ul class="badge-modal-steps">${stepsHtml}</ul>` : ''}
      <button class="badge-modal-close"
              onclick="this.closest('.badge-modal-overlay').remove()">
        Закрыть
      </button>
    </div>`;
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
  }

  // Простая модалка для бейджа обучения (earned)
  function openEducationBadgeModal(key) {
    const defn = EDUCATION_BADGES.find(b => b.key === key);
    if (!defn) return;
    const overlay = document.createElement('div');
    overlay.className = 'badge-modal-overlay';
    overlay.innerHTML = `<div class="badge-modal">
      <div class="badge-modal-icon">${defn.icon}</div>
      <div class="badge-modal-name">${defn.name}</div>
      <div class="badge-modal-desc">${defn.desc}</div>
      <button class="badge-modal-close"
              onclick="this.closest('.badge-modal-overlay').remove()">
        Закрыть
      </button>
    </div>`;
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
  }

  window._openModal = openModal;
  window._openEduModal = openEducationBadgeModal;

  // ========================================
  // Рендер стопки (5 уровней)
  // ========================================

  function renderStack(tracker, currentLevel) {
    const data = TRACKER_DATA[tracker];
    const displayLevel = Math.max(currentLevel, 1);
    const levelData = data.levels[displayLevel - 1];
    const color = currentLevel === 0 ? 'gray' : LEVEL_COLORS[displayLevel - 1];

    const futureCount = 5 - displayLevel;
    const pastCount   = displayLevel - 1;

    let futureHtml = '';
    for (let i = futureCount; i >= 1; i--) {
      futureHtml += `<div class="stack-future sf-${i}"></div>`;
    }

    let pastHtml = '';
    for (let i = 1; i <= pastCount; i++) {
      const pastColor = PAST_COLORS[displayLevel - 1 - i];
      pastHtml += `<div class="stack-past sp-${i}" data-color="${pastColor}"></div>`;
    }

    const dotsHtml = Array.from({ length: 5 }, (_, i) => {
      const filled = currentLevel > 0 && i < displayLevel;
      const cls = filled ? `dot ${LEVEL_DOT_CLASSES[i]}` : 'dot';
      return `<div class="${cls}"></div>`;
    }).join('');

    return `
      <div class="stack-wrapper" onclick="window._openModal('${tracker}')">
        ${futureHtml}
        <div class="stack-card" data-color="${color}">
          <span class="card-icon">${data.icon}</span>
          <div class="card-name">${levelData.name}</div>
          <div class="card-desc">${levelData.desc}</div>
          <div class="card-dots">${dotsHtml}</div>
        </div>
        ${pastHtml}
      </div>`;
  }

  // ========================================
  // Рендер стопки шкал (3 уровня)
  // ========================================

  const SCALES_LEVEL_COLORS = ['blue', 'green', 'gold'];
  const SCALES_DOT_CLASSES   = ['dot-blue', 'dot-green', 'dot-gold'];
  const SCALES_PAST_COLORS   = ['blue', 'green', 'gold'];

  function renderScalesStack(currentLevel) {
    const data = TRACKER_DATA['scales'];
    const displayLevel = Math.max(currentLevel, 1);
    const levelData = data.levels[displayLevel - 1];
    const color = currentLevel === 0 ? 'gray' : SCALES_LEVEL_COLORS[displayLevel - 1];

    const futureCount = 3 - displayLevel;
    const pastCount   = displayLevel - 1;

    let futureHtml = '';
    for (let i = futureCount; i >= 1; i--) {
      futureHtml += `<div class="stack-future sf-${i}"></div>`;
    }

    let pastHtml = '';
    for (let i = 1; i <= pastCount; i++) {
      const pastColor = SCALES_PAST_COLORS[displayLevel - 1 - i];
      pastHtml += `<div class="stack-past sp-${i}" data-color="${pastColor}"></div>`;
    }

    const dotsHtml = Array.from({ length: 3 }, (_, i) => {
      const filled = currentLevel > 0 && i < displayLevel;
      const cls = filled ? `dot ${SCALES_DOT_CLASSES[i]}` : 'dot';
      return `<div class="${cls}"></div>`;
    }).join('');

    return `
      <div class="stack-wrapper" onclick="window._openModal('scales')">
        ${futureHtml}
        <div class="stack-card" data-color="${color}">
          <span class="card-icon">${data.icon}</span>
          <div class="card-name">${levelData.name}</div>
          <div class="card-desc">${levelData.desc}</div>
          <div class="card-dots">${dotsHtml}</div>
        </div>
        ${pastHtml}
      </div>`;
  }

  // ========================================
  // Рендер достижений
  // ========================================

  function renderAchievements(data) {
    const earnedKeys = (data.badges || []).map(b => b.key);
    window._earnedBadgeKeys = earnedKeys;

    // 1. Серии — кликабельные ссылки
    const streaksGrid = document.getElementById('streaks-grid');
    if (streaksGrid) {
      const trackers = ['medications', 'sleep', 'vitals', 'practices'];
      streaksGrid.innerHTML = trackers.map(t => {
        const s = (data.streaks || {})[t] || { current: 0, best: 0 };
        const url = TRACKER_URLS[t] || '#';
        return `<a href="${url}" class="streak-item streak-link">
          <span class="streak-line1">${TRACKER_STREAK_NAMES[t]} <b>${s.current}</b> дн.</span>
          <span class="streak-line2">Рекорд ${s.best} дн.</span>
        </a>`;
      }).join('');
    }

    // 2. Стопки трекеров (без бонусных бейджей — они в отдельной секции)
    const stacksRow = document.getElementById('stacks-row');
    if (stacksRow) {
      const trackerOrder = ['medications', 'sleep', 'vitals', 'practices'];
      const tl = data.tracker_levels || {};
      stacksRow.innerHTML = trackerOrder.map(tracker => {
        const level = tl[tracker] || 0;
        return `<div class="stack-col">${renderStack(tracker, level)}</div>`;
      }).join('');
    }

    // 3. Бейджи обучения: locked по умолчанию, цвет/рамка — если earned
    const eduContainer = document.getElementById('badges-education');
    if (eduContainer) {
      eduContainer.innerHTML = EDUCATION_BADGES.map(defn => {
        const earned = earnedKeys.includes(defn.key);
        const dataColor = earned ? `data-color="${defn.color}"` : 'data-color=""';
        const clickAttr = earned ? `onclick="window._openEduModal('${defn.key}')"` : '';
        const overlayHtml = !earned ? `
          <div class="badge-overlay">
            <div class="badge-overlay-icon">🔒</div>
            <div class="badge-overlay-text">${defn.overlayText}</div>
          </div>` : '';
        return `<div class="badge-single ${earned ? 'earned' : 'locked'}" ${dataColor} ${clickAttr}>
          <div class="badge-single-icon">${defn.icon}</div>
          <div class="badge-single-name">${defn.name}</div>
          ${overlayHtml}
        </div>`;
      }).join('');
    }

    // 4. Стопка шкал
    const scalesRow = document.getElementById('scales-stack-row');
    if (scalesRow) {
      const scalesLevel = data.scales_level || 0;
      scalesRow.innerHTML = `<div class="stack-col" style="max-width:110px;">
        ${renderScalesStack(scalesLevel)}
      </div>`;
    }

    // 5. Особые бонусные бейджи
    const specialRow = document.getElementById('special-badges-row');
    if (specialRow) {
      specialRow.innerHTML = SPECIAL_BADGES.map(defn => {
        const earned = earnedKeys.includes(defn.key);
        const clickAttr = earned ? `onclick="window._openModal('${defn.key}')"` : '';
        return `<div class="badge-bonus ${earned ? 'earned' : 'locked'}" ${clickAttr}>
          <span class="badge-bonus-icon">${defn.icon}</span>
          <span class="badge-bonus-name">${defn.name}</span>
        </div>`;
      }).join('');
    }

    // 6. Прогресс-бары
    const progressSection = document.getElementById('progress-section');
    if (progressSection && data.progress) {
      const p = data.progress;
      const lp = p.lessons_total > 0 ? Math.round(p.lessons_done / p.lessons_total * 100) : 0;
      const pp = p.practices_total > 0 ? Math.round(p.practices_done / p.practices_total * 100) : 0;
      progressSection.innerHTML = `
        <div class="progress-bar-item">
          <div class="progress-bar-header">
            <span>📚 Уроки</span>
            <span>${p.lessons_done} / ${p.lessons_total}</span>
          </div>
          <div class="progress-bar-track">
            <div class="progress-bar-fill" style="width:${lp}%"></div>
          </div>
        </div>
        <div class="progress-bar-item">
          <div class="progress-bar-header">
            <span>🧘 Практики</span>
            <span>${p.practices_done} / ${p.practices_total}</span>
          </div>
          <div class="progress-bar-track">
            <div class="progress-bar-fill" style="width:${pp}%"></div>
          </div>
        </div>`;
    }
  }

  async function fetchAchievements() {
    const res = await fetch('/api/v1/profile/achievements', { credentials: 'include' });
    if (!res.ok) throw new Error(`achievements: ${res.status}`);
    return res.json();
  }

  // ========================================
  // API запросы
  // ========================================

  async function fetchProfileSummary() {
    const url = `/api/v1/profile/summary`;
    const response = await fetch(url, {
      credentials: 'include', // Включить cookies для авторизации
    });
    if (!response.ok) {
      throw new Error(`Ошибка загрузки профиля: ${response.status}`);
    }
    return response.json();
  }

  async function updateProfile(data) {
    const url = `/api/v1/profile/update`;
    const response = await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include', // Включить cookies для авторизации
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      throw new Error(`Ошибка сохранения: ${response.status}`);
    }
    return response.json();
  }

  async function revokeConsent(revokePersonalData, revokeBotUse) {
    const url = `/api/v1/consent/revoke`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        revoke_personal_data: revokePersonalData,
        revoke_bot_use: revokeBotUse,
      }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Ошибка отзыва: ${response.status}`);
    }
    return response.json();
  }

  // ========================================
  // Отрисовка данных
  // ========================================

  function renderPersonalData(profile) {
    const fullnameEl = document.getElementById('view-fullname');
    const ageEl = document.getElementById('view-age');
    const genderEl = document.getElementById('view-gender');

    if (fullnameEl) fullnameEl.textContent = profile.full_name || 'Не указано';
    if (ageEl) ageEl.textContent = profile.age ? `${profile.age} лет` : 'Не указан';
    if (genderEl) genderEl.textContent = formatGender(profile.gender);

    // Заполняем форму редактирования текущими значениями
    const editFullname = document.getElementById('edit-fullname');
    const editAge = document.getElementById('edit-age');
    const editGender = document.getElementById('edit-gender');

    if (editFullname) editFullname.value = profile.full_name || '';
    if (editAge) editAge.value = profile.age || '';
    if (editGender) editGender.value = profile.gender || '';
  }

  function renderConsents(profile) {
    const personalIcon = document.getElementById('consent-personal-icon');
    const botIcon = document.getElementById('consent-bot-icon');
    const revokePersonalBtn = document.getElementById('revoke-personal-btn');
    const revokeBotBtn = document.getElementById('revoke-bot-btn');

    if (personalIcon) {
      personalIcon.textContent = profile.consent_personal_data ? '✅' : '❌';
      personalIcon.classList.toggle('consent-yes', profile.consent_personal_data);
      personalIcon.classList.toggle('consent-no', !profile.consent_personal_data);
    }
    if (revokePersonalBtn) {
      revokePersonalBtn.style.display = profile.consent_personal_data ? '' : 'none';
    }

    if (botIcon) {
      botIcon.textContent = profile.consent_bot_use ? '✅' : '❌';
      botIcon.classList.toggle('consent-yes', profile.consent_bot_use);
      botIcon.classList.toggle('consent-no', !profile.consent_bot_use);
    }
    if (revokeBotBtn) {
      revokeBotBtn.style.display = profile.consent_bot_use ? '' : 'none';
    }
  }

  function renderVitals(vitals) {
    const bpEl = document.getElementById('vitals-bp');
    const bpDateEl = document.getElementById('vitals-bp-date');
    const pulseEl = document.getElementById('vitals-pulse');
    const pulseDateEl = document.getElementById('vitals-pulse-date');
    const weightEl = document.getElementById('vitals-weight');
    const weightDateEl = document.getElementById('vitals-weight-date');
    const waterEl = document.getElementById('vitals-water');

    if (bpEl) {
      if (vitals.last_bp) {
        bpEl.textContent = `${vitals.last_bp.systolic}/${vitals.last_bp.diastolic}`;
        if (bpDateEl) bpDateEl.textContent = formatDateShort(vitals.last_bp.measured_at);
      } else {
        bpEl.textContent = '—';
        if (bpDateEl) bpDateEl.textContent = '';
      }
    }

    if (pulseEl) {
      if (vitals.last_pulse) {
        pulseEl.textContent = `${vitals.last_pulse.bpm} уд/мин`;
        if (pulseDateEl) pulseDateEl.textContent = formatDateShort(vitals.last_pulse.measured_at);
      } else {
        pulseEl.textContent = '—';
        if (pulseDateEl) pulseDateEl.textContent = '';
      }
    }

    if (weightEl) {
      if (vitals.last_weight) {
        weightEl.textContent = `${vitals.last_weight.weight} кг`;
        if (weightDateEl) weightDateEl.textContent = formatDateShort(vitals.last_weight.measured_at);
      } else {
        weightEl.textContent = '—';
        if (weightDateEl) weightDateEl.textContent = '';
      }
    }

    if (waterEl) {
      if (vitals.last_water_today_ml !== null && vitals.last_water_today_ml !== undefined) {
        waterEl.textContent = `${vitals.last_water_today_ml} мл`;
      } else {
        waterEl.textContent = '—';
      }
    }
  }

  function renderEducation(education) {
    const lessonsEl = document.getElementById('edu-lessons');
    const testsEl = document.getElementById('edu-tests');
    const practicesEl = document.getElementById('edu-practices');
    const lastActivityEl = document.getElementById('edu-last-activity');

    if (lessonsEl) {
      lessonsEl.textContent = `${education.lessons_completed} / ${education.lessons_total}`;
    }
    if (testsEl) testsEl.textContent = education.tests_passed || '0';
    if (practicesEl) practicesEl.textContent = education.practices_done || '0';
    if (lastActivityEl) {
      lastActivityEl.textContent = education.last_activity_at
        ? formatDate(education.last_activity_at)
        : 'Нет данных';
    }
  }

  function renderDialysis(dialysis) {
    const centerEl = document.getElementById('dialysis-center');
    const shiftEl = document.getElementById('dialysis-shift');
    const daysEl = document.getElementById('dialysis-days');

    if (!dialysis) {
      if (centerEl) centerEl.textContent = '—';
      if (shiftEl) shiftEl.textContent = '—';
      if (daysEl) daysEl.textContent = '—';
      return;
    }

    const centerStr = dialysis.center_city
      ? `${dialysis.center_name} (${dialysis.center_city})`
      : dialysis.center_name || '—';

    if (centerEl) centerEl.textContent = centerStr;
    if (shiftEl) shiftEl.textContent = formatShift(dialysis.shift);
    if (daysEl) daysEl.textContent = formatWeekdays(dialysis.weekdays);
  }

  function renderScales(scales) {
    const passedEl = document.getElementById('scales-passed');
    const availableEl = document.getElementById('scales-available');
    const lastEl = document.getElementById('scales-last');

    if (passedEl) passedEl.textContent = scales.scales_passed || '0';
    if (availableEl) availableEl.textContent = scales.scales_available || '0';
    if (lastEl) {
      if (scales.last_scale) {
        lastEl.textContent = `${scales.last_scale.name} (${formatDateShort(scales.last_scale.measured_at)})`;
      } else {
        lastEl.textContent = 'Нет данных';
      }
    }
  }

  // ========================================
  // Редактирование профиля
  // ========================================

  let isEditing = false;

  function toggleEditMode(enable) {
    isEditing = enable;

    const viewEl = document.getElementById('personal-view');
    const formEl = document.getElementById('personal-form');
    const editBtn = document.getElementById('edit-personal-btn');

    if (enable) {
      viewEl?.classList.add('hidden');
      formEl?.classList.remove('hidden');
      if (editBtn) editBtn.textContent = 'Отмена';
    } else {
      viewEl?.classList.remove('hidden');
      formEl?.classList.add('hidden');
      if (editBtn) editBtn.textContent = 'Редактировать';
    }
  }

  function initEditControls(reloadProfile) {
    const editBtn = document.getElementById('edit-personal-btn');
    const cancelBtn = document.getElementById('cancel-edit-btn');
    const form = document.getElementById('personal-form');

    if (editBtn) {
      editBtn.addEventListener('click', () => {
        toggleEditMode(!isEditing);
      });
    }

    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        toggleEditMode(false);
        reloadProfile(); // Восстановить значения из сервера
      });
    }

    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        setStatus('none', '');

        const fullName = document.getElementById('edit-fullname')?.value?.trim() || null;
        const ageStr = document.getElementById('edit-age')?.value;
        const age = ageStr ? parseInt(ageStr, 10) : null;
        const gender = document.getElementById('edit-gender')?.value || null;

        const data = {};
        if (fullName !== null) data.full_name = fullName;
        if (age !== null && !isNaN(age)) data.age = age;
        if (gender) data.gender = gender;

        try {
          await updateProfile(data);
          setStatus('success', 'Профиль успешно сохранён!');
          toggleEditMode(false);
          reloadProfile();
        } catch (err) {
          console.error('Ошибка сохранения профиля:', err);
          setStatus('error', 'Не удалось сохранить изменения. Попробуйте ещё раз.');
        }
      });
    }
  }

  // ========================================
  // Копирование токена
  // ========================================

  // ========================================
  // Инициализация страницы
  // ========================================

  async function loadAndRenderProfile() {
    try {
      const [profile, achievements] = await Promise.all([
        fetchProfileSummary(),
        fetchAchievements().catch(() => null),
      ]);

      renderPersonalData(profile);
      renderDialysis(profile.dialysis);
      renderConsents(profile);
      renderVitals(profile.vitals);
      renderEducation(profile.education);
      renderScales(profile.scales);
      if (achievements) renderAchievements(achievements);
    } catch (err) {
      console.error('Ошибка загрузки профиля:', err);
      setStatus('error', 'Не удалось загрузить данные профиля. Обновите страницу.');
    }
  }

  function initRevokeButtons(reloadProfile) {
    const revokePersonalBtn = document.getElementById('revoke-personal-btn');
    const revokeBotBtn = document.getElementById('revoke-bot-btn');

    function doRevoke(revokePersonal, revokeBot, label) {
      if (!confirm(`Вы уверены, что хотите отозвать ${label}? После отзыва соответствующие возможности сервиса могут быть ограничены.`)) {
        return;
      }
      setStatus('none', '');
      revokeConsent(revokePersonal, revokeBot)
        .then(() => {
          setStatus('success', 'Доступ отозван.');
          reloadProfile();
        })
        .catch((err) => {
          console.error('Ошибка отзыва согласия:', err);
          setStatus('error', err.message || 'Не удалось отозвать доступ.');
        });
    }

    if (revokePersonalBtn) {
      revokePersonalBtn.addEventListener('click', () => {
        doRevoke(true, false, 'согласие на обработку персональных данных');
      });
    }
    if (revokeBotBtn) {
      revokeBotBtn.addEventListener('click', () => {
        doRevoke(false, true, 'согласие на использование бота');
      });
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    // Авторизация происходит через session cookies
    // Загрузка данных профиля
    const reloadProfile = () => loadAndRenderProfile();
    reloadProfile();

    // Инициализация управления
    initEditControls(reloadProfile);
    initRevokeButtons(reloadProfile);
  });
})();
