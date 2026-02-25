(function () {
  function formatDateLabel(dateString) {
    if (!dateString) return '—';
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', { month: 'short', day: 'numeric' });
  }

  function getPulseLevel(bpm) {
    // Классификация пульса:
    // 0 - норма (60-100 уд/мин)
    // 1 - повышенный (> 100 уд/мин)
    // -1 - пониженный (< 60 уд/мин)
    if (bpm > 100) return 1;
    if (bpm < 60) return -1;
    return 0;
  }

  function buildMiniBarChart(container, values, colorClassifier) {
    if (!container) return;
    container.innerHTML = '';

    if (!values || values.length === 0) {
      const emptyBar = document.createElement('div');
      emptyBar.className = 'chart-bar chart-bar-empty';
      emptyBar.style.height = '12px';
      container.appendChild(emptyBar);
      return;
    }

    const maxValue = Math.max(...values.map((v) => v.value || 0)) || 1;

    values.forEach((item) => {
      const bar = document.createElement('div');
      bar.className = 'chart-bar';
      const heightPct = Math.max(
        8,
        Math.round(((item.value || 0) / maxValue) * 100),
      );
      bar.style.height = `${heightPct}%`;
      bar.title = `${item.value ?? '—'} • ${formatDateLabel(item.date)}`;

      // Применяем цвет, если есть функция классификации
      if (colorClassifier && typeof colorClassifier === 'function') {
        const level = colorClassifier(item.value);
        if (level === 0) {
          bar.style.setProperty('background', '#22c55e', 'important'); // Зеленый - норма
        } else if (level === 1) {
          bar.style.setProperty('background', '#f97316', 'important'); // Оранжевый - повышенный
        } else if (level === -1) {
          bar.style.setProperty('background', '#60a5fa', 'important'); // Синий - пониженный
        }
      }

      container.appendChild(bar);
    });
  }

  function getBPLevel(systolic, diastolic) {
    // Возвращает уровень АД:
    // Гипотония: -3 (тяжелая), -2 (средняя), -1 (легкая)
    // 0 - норма
    // Гипертония: 1 (1 степень), 2 (2 степень), 3 (3 степень)

    // Сначала проверяем гипотонию (низкое давление)
    let hypoLevel = 0;

    // Проверяем по САД
    if (systolic < 70) hypoLevel = Math.min(hypoLevel, -3);
    else if (systolic < 100) hypoLevel = Math.min(hypoLevel, -2);
    else if (systolic < 115) hypoLevel = Math.min(hypoLevel, -1);

    // Проверяем по ДАД
    if (diastolic < 60) hypoLevel = Math.min(hypoLevel, -3);
    else if (diastolic < 70) hypoLevel = Math.min(hypoLevel, -2);
    else if (diastolic < 75) hypoLevel = Math.min(hypoLevel, -1);

    // Если есть гипотония, возвращаем её
    if (hypoLevel < 0) return hypoLevel;

    // Проверяем гипертонию (высокое давление)
    let hyperLevel = 0;

    // Проверяем САД
    if (systolic >= 180) hyperLevel = Math.max(hyperLevel, 3);
    else if (systolic >= 160) hyperLevel = Math.max(hyperLevel, 2);
    else if (systolic >= 140) hyperLevel = Math.max(hyperLevel, 1);

    // Проверяем ДАД
    if (diastolic >= 110) hyperLevel = Math.max(hyperLevel, 3);
    else if (diastolic >= 100) hyperLevel = Math.max(hyperLevel, 2);
    else if (diastolic >= 90) hyperLevel = Math.max(hyperLevel, 1);

    return hyperLevel;
  }

  function buildWaterStackChart(container, daysData) {
    if (!container) return;
    container.innerHTML = '';

    if (!daysData || daysData.length === 0) {
      const emptyBar = document.createElement('div');
      emptyBar.className = 'chart-bar chart-bar-empty';
      emptyBar.style.height = '12px';
      container.appendChild(emptyBar);
      return;
    }

    // 1. Находим максимум суточного потребления для масштаба
    const dailyTotals = daysData.map(d => d.portions.reduce((a, b) => a + b, 0));
    const maxTotal = Math.max(...dailyTotals, 1); // минимум 1, чтобы не делить на 0

    daysData.forEach((dayItem) => {
      // Контейнер для столбика дня
      const barWrapper = document.createElement('div');
      barWrapper.className = 'chart-bar-wrapper';
      // Стили для обертки, чтобы она вела себя как столбик в общем графике
      barWrapper.style.display = 'flex';
      barWrapper.style.flexDirection = 'column-reverse'; // Стекируем снизу вверх
      barWrapper.style.alignItems = 'center';
      barWrapper.style.width = '12%'; // Ширина как у обычных баров
      barWrapper.style.height = '100%';
      barWrapper.style.justifyContent = 'flex-end'; // Прижимаем к низу

      const totalVolume = dayItem.portions.reduce((a, b) => a + b, 0);
      const totalHeightPct = Math.max(8, Math.round((totalVolume / maxTotal) * 100));

      // Сам "столбик", состоящий из сегментов
      const barStack = document.createElement('div');
      barStack.style.width = '100%';
      barStack.style.height = `${totalHeightPct}%`;
      barStack.style.display = 'flex';
      barStack.style.flexDirection = 'column-reverse'; // Сегменты снизу вверх
      barStack.style.overflow = 'hidden'; // Скругление углов бар-контейнера обрежет сегменты
      barStack.className = 'chart-bar'; // Используем базовый класс для скруглений и фона
      barStack.style.background = 'transparent'; // Фон будет у сегментов
      barStack.title = `${totalVolume} мл • ${formatDateLabel(dayItem.date)} (${dayItem.portions.length} порций)`;

      // Добавляем сегменты
      dayItem.portions.forEach((portion, idx) => {
        const segment = document.createElement('div');
        // Высота сегмента пропорциональна его доле в дневном объеме
        const segmentHeightPct = (portion / totalVolume) * 100;
        segment.style.height = `${segmentHeightPct}%`;
        segment.style.width = '100%';
        segment.style.backgroundColor = '#3b82f6'; // Основной цвет воды

        // Добавляем разделитель (белую полоску), если это не верхний сегмент
        // Так как column-reverse, первый в DOM это нижний. Верхний - последний.
        if (idx < dayItem.portions.length - 1) {
          segment.style.borderTop = '3px solid rgba(250, 249, 249, 0.93)';
        }

        segment.title = `${portion} мл`; // Тултип для конкретной порции (хотя общий на баре перекроет)
        barStack.appendChild(segment);
      });

      barWrapper.appendChild(barStack);
      container.appendChild(barWrapper);
    });
  }

  function buildBPRangeChart(container, values) {
    if (!container) return;
    container.innerHTML = '';

    if (!values || values.length === 0) {
      const emptyBar = document.createElement('div');
      emptyBar.className = 'chart-bar chart-bar-empty';
      emptyBar.style.height = '12px';
      container.appendChild(emptyBar);
      return;
    }

    const allValues = values.flatMap(v => [v.systolic || 0, v.diastolic || 0]);
    const minVal = 40;
    const maxVal = Math.max(...allValues, 200);
    const range = maxVal - minVal || 1;

    const colors = [
      '#1e40af', '#3b82f6', '#60a5fa',
      '#22c55e',
      '#eab308', '#f97316', '#ef4444'
    ];

    // Fixed coordinate space
    const VW = 100;
    const VH = 100;
    const padTop = 8;
    const padBottom = 4;
    const drawH = VH - padTop - padBottom;

    // Y helper — clamps inside padded area
    const toY = val =>
      padTop + drawH - Math.min(Math.max((val - minVal) / range, 0), 1) * drawH;

    // Dynamic bar width: fills full width for any 1–9 points
    const n = values.length;
    const slotW = VW / n;
    const barW = Math.max(4, slotW * 0.4);

    // SVG wrapper — takes all available width, labels column is separate
    const svgWrapper = document.createElement('div');
    svgWrapper.style.cssText = 'flex:1;min-width:0;position:relative;height:100%;overflow:hidden;';

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    svg.setAttribute('viewBox', `0 0 ${VW} ${VH}`);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.style.display = 'block';
    svg.style.overflow = 'hidden';

    // Normal zone bands (soft green fill)
    const zones = [
      { lo: 120, hi: 130 },  // systolic
      { lo: 80,  hi: 85  }   // diastolic
    ];
    zones.forEach(({ lo, hi }) => {
      const yTop = toY(hi);
      const yBot = toY(lo);
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', '0');
      rect.setAttribute('y', String(yTop));
      rect.setAttribute('width', String(VW));
      rect.setAttribute('height', String(yBot - yTop));
      rect.setAttribute('fill', '#22c55e');
      rect.setAttribute('opacity', '0.10');
      svg.appendChild(rect);
    });

    // Reference lines at 120 and 80
    [120, 80].forEach(val => {
      const y = toY(val);
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', '0');
      line.setAttribute('x2', String(VW));
      line.setAttribute('y1', String(y));
      line.setAttribute('y2', String(y));
      line.setAttribute('stroke', '#e2e8f0');
      line.setAttribute('stroke-width', '0.8');
      svg.appendChild(line);
    });

    // Data bars
    values.forEach((item, index) => {
      const sys = item.systolic || 0;
      const dia = item.diastolic || 0;
      const level = getBPLevel(sys, dia);
      const color = colors[level + 3];

      const x = slotW * index + slotW / 2;
      const y1 = toY(sys);
      const y2 = toY(dia);

      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', String(x));
      line.setAttribute('x2', String(x));
      line.setAttribute('y1', String(y1));
      line.setAttribute('y2', String(y2));
      line.setAttribute('stroke', color);
      line.setAttribute('stroke-width', String(barW));
      line.setAttribute('stroke-linecap', 'round');
      line.setAttribute('class', 'bp-range-line');
      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = `${sys}/${dia} • ${formatDateLabel(item.date)}`;
      line.appendChild(title);
      svg.appendChild(line);
    });

    svgWrapper.appendChild(svg);
    container.appendChild(svgWrapper);

    // Labels column (120 / 80) to the right of the chart
    const labelsCol = document.createElement('div');
    labelsCol.style.cssText = 'width:22px;flex-shrink:0;position:relative;';

    // container 110px − 4px top padding − 4px bottom padding = 102px content height
    const svgContentH = 102;
    [{ val: 120 }, { val: 80 }].forEach(({ val }) => {
      const topPx = (toY(val) / VH) * svgContentH;
      const el = document.createElement('span');
      el.textContent = String(val);
      el.style.cssText = `position:absolute;left:2px;top:${Math.round(topPx - 7)}px;font-size:10px;font-weight:500;color:#94a3b8;font-family:system-ui,sans-serif;pointer-events:none;line-height:1;`;
      labelsCol.appendChild(el);
    });

    container.appendChild(labelsCol);
  }


  function trendText(last, avg, suffix = '') {
    if (last === null || last === undefined || avg === null || avg === undefined) {
      return 'Нет данных за неделю';
    }
    const diff = last - avg;
    if (Math.abs(diff) < 0.5) return 'Стабильно';
    return diff > 0 ? `Есть рост${suffix}` : `Снижение${suffix}`;
  }

  function safeFetch(url) {
    return fetch(url, {
      credentials: 'include'
    }).then((resp) => {
      if (!resp.ok) throw new Error(`Request failed ${resp.status}`);
      return resp.json();
    });
  }

  async function loadDailyWaterTotal() {
    try {
      const data = await safeFetch('/api/v1/vitals/water/daily-total/me');
      const latestEl = document.getElementById('water-latest');
      const trendEl = document.getElementById('water-trend');

      if (latestEl) latestEl.textContent = `${data.total_ml} мл`;
      if (trendEl) trendEl.textContent = `За сегодня (${data.entries_count} записей)`;
    } catch (err) {
      console.warn('Не удалось загрузить суточное потребление воды:', err);
    }
  }

  async function loadVitalsCard(config) {
    const {
      idPrefix,
      endpoint,
      formatValue,
      trendSuffix,
      chartMapper,
      customChartBuilder,
      colorClassifier,
      chartLimit,
    } = config;
    const latestEl = document.getElementById(`${idPrefix}-latest`);
    const trendEl = document.getElementById(`${idPrefix}-trend`);
    const updatedAtEl = document.getElementById(`${idPrefix}-updated-at`);
    const chartEl = document.getElementById(`${idPrefix}-chart`);

    try {
      const data = await safeFetch(endpoint);
      if (!Array.isArray(data) || data.length === 0) {
        trendEl.textContent = 'Нет данных за неделю';
        (customChartBuilder || buildMiniBarChart)(chartEl, []);
        return;
      }

      const latest = data[0];
      const values = data.slice(0, chartLimit ?? 7).reverse();

      const mapped = values.map((item) => chartMapper(item));
      const chartBuilder = customChartBuilder || buildMiniBarChart;
      if (customChartBuilder) {
        chartBuilder(chartEl, mapped);
      } else {
        chartBuilder(chartEl, mapped, colorClassifier);
      }

      // Для графиков с единичным значением вычисляем тренд
      if (!customChartBuilder) {
        const numericValues = mapped.map((m) => m.value || 0);
        const avg = numericValues.reduce((a, b) => a + b, 0) / numericValues.length;
        const lastValue = mapped[mapped.length - 1].value;
        if (trendEl) trendEl.textContent = trendText(lastValue, avg, trendSuffix);
      } else {
        // Для BP показываем упрощенный тренд
        if (trendEl) trendEl.textContent = 'За 7 дней';
      }

      if (latestEl) latestEl.textContent = formatValue(latest);
      if (updatedAtEl) updatedAtEl.textContent = formatDateLabel(latest.measured_at);
    } catch (err) {
      console.warn(`Не удалось загрузить ${idPrefix}:`, err);
      trendEl.textContent = 'Нет данных за неделю';
      (customChartBuilder || buildMiniBarChart)(chartEl, []);
    }
  }

  async function loadWaterCard() {
    const chartEl = document.getElementById('water-chart');
    const latestEl = document.getElementById('water-latest');
    const trendEl = document.getElementById('water-trend');
    const updatedAtEl = document.getElementById('water-updated-at');

    try {
      const data = await safeFetch('/api/v1/vitals/water/me?limit=200&order_by=measured_at desc');

      if (!Array.isArray(data) || data.length === 0) {
        if (latestEl) latestEl.textContent = '—';
        if (trendEl) trendEl.textContent = 'Нет данных за неделю';
        if (chartEl && typeof buildWaterStackChart === 'function') buildWaterStackChart(chartEl, []);
        return;
      }

      // 2. Агрегация по дням, сохраняя порции
      const dailyMap = {};
      data.forEach(item => {
        if (!item.measured_at) return;
        const localDate = new Date(item.measured_at).toLocaleDateString('en-CA');
        if (!dailyMap[localDate]) {
          dailyMap[localDate] = [];
        }
        dailyMap[localDate].push(item.volume_ml || 0);
      });

      // 3. Формируем массив последних 7 дней
      const sortedDays = Object.keys(dailyMap).sort();
      const last7Days = sortedDays.slice(-7);

      const chartValues = last7Days.map(dateStr => ({
        date: dateStr,
        portions: dailyMap[dateStr] // Массив порций
      }));

      // 4. Отображаем стековый график
      buildWaterStackChart(chartEl, chartValues);

      // 5. Отображаем "Сегодня"
      const todayStr = new Date().toLocaleDateString('en-CA');
      const todayPortions = dailyMap[todayStr] || [];
      const todaySum = todayPortions.reduce((a, b) => a + b, 0);

      if (latestEl) latestEl.textContent = `${todaySum} мл`;

      if (trendEl) {
        const count = todayPortions.length;
        if (count > 0) {
          trendEl.textContent = `За сегодня (${count} порций)`;
        } else {
          trendEl.textContent = 'Нет данных за сегодня';
        }
      }

      if (updatedAtEl && data[0]) {
        updatedAtEl.textContent = formatDateLabel(data[0].measured_at);
      }

    } catch (err) {
      console.warn('Не удалось загрузить данные воды:', err);
      if (trendEl) trendEl.textContent = 'Ошибка загрузки';
      if (chartEl && typeof buildWaterStackChart === 'function') buildWaterStackChart(chartEl, []);
    }
  }

  async function loadVitals() {
    await Promise.all([
      loadVitalsCard({
        idPrefix: 'bp',
        endpoint: '/api/v1/vitals/bp/me?limit=9&order_by=measured_at desc',
        formatValue: (item) => `${item.systolic ?? '—'} / ${item.diastolic ?? '—'}`,
        trendSuffix: '',
        chartMapper: (item) => ({
          systolic: item.systolic || 0,
          diastolic: item.diastolic || 0,
          date: item.measured_at
        }),
        customChartBuilder: buildBPRangeChart,
        chartLimit: 9,
      }),
      loadVitalsCard({
        idPrefix: 'pulse',
        endpoint: '/api/v1/vitals/pulse/me?limit=7&order_by=measured_at desc',
        formatValue: (item) => `${item.bpm ?? '—'} уд/мин`,
        trendSuffix: '',
        chartMapper: (item) => ({ value: item.bpm || 0, date: item.measured_at }),
        colorClassifier: getPulseLevel,
      }),
      loadVitalsCard({
        idPrefix: 'weight',
        endpoint: '/api/v1/vitals/weight/me?limit=7&order_by=measured_at desc',
        formatValue: (item) => `${item.weight ?? '—'} кг`,
        trendSuffix: '',
        chartMapper: (item) => ({ value: item.weight || 0, date: item.measured_at }),
      }),

      loadWaterCard(),

    ]);
  }

  async function loadScales() {
    const selectEl = document.getElementById('scale-select');
    const scoreEl = document.getElementById('scale-main-score');
    const summaryEl = document.getElementById('scale-main-summary');
    const chartEl = document.getElementById('scale-chart');

    const formatScore = (value) => {
      if (value === null || value === undefined) return '—';
      if (typeof value === 'number') {
        return Number.isInteger(value) ? value : value.toFixed(1);
      }
      return value;
    };

    const setEmptyState = () => {
      if (selectEl) selectEl.innerHTML = '<option>Нет шкал</option>';
      if (scoreEl) scoreEl.textContent = '—';
      if (summaryEl) summaryEl.textContent = 'Нет данных по шкале';
      buildMiniBarChart(chartEl, []);
    };

    const updateSelectedScale = async () => {
      const code = selectEl?.value;
      if (!code) {
        setEmptyState();
        return;
      }

      const historyUrl =
        `/api/v1/scales/${encodeURIComponent(code)}/history?limit=7`;

      try {
        const history = await safeFetch(historyUrl);

        if (!Array.isArray(history) || history.length === 0) {
          if (scoreEl) scoreEl.textContent = '—';
          if (summaryEl) summaryEl.textContent = 'Нет данных по шкале';
          buildMiniBarChart(chartEl, []);
          return;
        }

        const latest = history[0];
        const mapped = history
          .slice(0, 7)
          .reverse()
          .map((item) => ({
            value: item.total_score ?? item.score ?? 0,
            date: item.measured_at || item.created_at,
          }));

        const summaryText =
          typeof latest.summary === 'string'
            ? latest.summary
            : latest.summary != null
              ? JSON.stringify(latest.summary)
              : 'Нет данных по шкале';

        if (scoreEl) scoreEl.textContent = formatScore(latest.total_score ?? latest.score);
        if (summaryEl) summaryEl.textContent = summaryText || 'Нет данных по шкале';
        buildMiniBarChart(chartEl, mapped);
      } catch (err) {
        console.warn('Не удалось загрузить шкалу', err);
        if (scoreEl) scoreEl.textContent = '—';
        if (summaryEl) summaryEl.textContent = 'Нет данных по шкале';
        buildMiniBarChart(chartEl, []);
      }
    };

    if (selectEl) {
      selectEl.addEventListener('click', (event) => event.stopPropagation());
      selectEl.addEventListener('change', updateSelectedScale);
    }

    try {
      const overviewUrl = '/api/v1/scales/overview';

      const overview = await safeFetch(overviewUrl);

      if (!Array.isArray(overview) || overview.length === 0) {
        setEmptyState();
        return;
      }

      selectEl.innerHTML = '';
      overview.forEach((scale) => {
        const option = document.createElement('option');
        option.value = scale.scale_code;
        option.textContent = scale.scale_name || scale.scale_code;
        selectEl.appendChild(option);
      });

      const preferred = overview.find((s) => s.scale_code === 'HADS');
      selectEl.value = preferred ? 'HADS' : selectEl.options[0]?.value;

      await updateSelectedScale();
    } catch (err) {
      console.warn('Не удалось загрузить список шкал', err);
      setEmptyState();
    }
  }

  async function loadEducation() {
    const fillEl = document.getElementById('education-progress-fill');
    const labelEl = document.getElementById('education-progress-label');
    const titleEl = document.getElementById('education-last-title');
    const captionEl = document.getElementById('education-last-caption');

    try {
      const blocks = await safeFetch(`/api/v1/education/lessons/overview`);
      if (!Array.isArray(blocks) || blocks.length === 0) {
        labelEl.textContent = 'Нет данных';
        titleEl.textContent = 'Нет активных тем';
        captionEl.textContent = 'Все доступные темы пройдены.';
        return;
      }

      let lessonsTotal = 0;
      let testsPassed = 0;
      let pendingLesson = null;

      blocks.forEach((block) => {
        const progress = block.progress || {};
        lessonsTotal += progress.lessons_total || 0;
        testsPassed += progress.tests_passed || 0;

        if (!pendingLesson && Array.isArray(block.lessons)) {
          pendingLesson = block.lessons.find((lesson) => !lesson.is_test_passed);
        }
      });

      const percent = lessonsTotal > 0 ? Math.round((testsPassed / lessonsTotal) * 100) : 0;
      fillEl.style.width = `${percent}%`;
      labelEl.textContent = `${percent}% завершено`;

      if (pendingLesson) {
        titleEl.textContent = pendingLesson.title || pendingLesson.lesson_code || 'Тема обучения';
        captionEl.textContent = pendingLesson.is_read ? 'Следующий шаг: пройти тест' : 'Прочитать урок';
      } else {
        titleEl.textContent = 'Все темы пройдены';
        captionEl.textContent = 'Можно вернуться к материалам в любое время.';
      }
    } catch (err) {
      console.warn('Не удалось загрузить обучение', err);
      labelEl.textContent = 'Нет данных';
      titleEl.textContent = 'Ошибка загрузки';
      captionEl.textContent = 'Попробуйте обновить страницу позже.';
    }
  }

  function initNavigation() {
    const vitalsCardToTab = {
      'card-bp': 'bp',
      'card-pulse': 'pulse',
      'card-weight': 'weight',
      'card-water': 'water',
    };
    Object.keys(vitalsCardToTab).forEach((id) => {
      const card = document.getElementById(id);
      const tab = vitalsCardToTab[id];
      if (card && tab) {
        card.addEventListener('click', () => {
          window.location.href = '/patient/vitals#' + tab;
        });
      }
    });

    const scalesCard = document.getElementById('card-scales');
    if (scalesCard) {
      scalesCard.addEventListener('click', () => {
        window.location.href = '/patient/scales';
      });
    }

    const eduCard = document.getElementById('card-education');
    if (eduCard) {
      eduCard.addEventListener('click', () => {
        window.location.href = '/patient/education_overview';
      });
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    // Use session-based auth; redirects to /login if not authenticated
    if (window.PatientAuth) {
      await window.PatientAuth.requireAuth();
    }

    await Promise.all([
      loadVitals(),
      loadScales(),
      loadEducation(),
    ]);

    initNavigation();
  });
})();
