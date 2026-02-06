(function () {
  function getPatientToken() {
    const parts = window.location.pathname.split('/').filter(Boolean);
    const pIndex = parts.indexOf('p');
    if (pIndex !== -1 && parts.length > pIndex + 1) {
      return parts[pIndex + 1];
    }
    return null;
  }

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

    // Определяем диапазон значений
    const allValues = values.flatMap(v => [v.systolic || 0, v.diastolic || 0]);
    const minVal = 40; // Фиксированная нижняя граница для лучшей видимости низких значений
    const maxVal = Math.max(...allValues, 200);
    const range = maxVal - minVal || 1;

    // Цвета для уровней
    // Индексы: -3, -2, -1, 0, 1, 2, 3
    const colors = [
      '#1e40af', // -3: Гипотония III (темно-синий)
      '#3b82f6', // -2: Гипотония II (синий)
      '#60a5fa', // -1: Гипотония I (светло-синий)
      '#22c55e', //  0: Норма (зеленый)
      '#eab308', //  1: Гипертония 1 ст. (желтый)
      '#f97316', //  2: Гипертония 2 ст. (оранжевый)
      '#ef4444'  //  3: Гипертония 3 ст. (красный)
    ];

    // Создаем SVG
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    svg.setAttribute('viewBox', `0 0 ${values.length * 20} 100`);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.style.overflow = 'visible';

    // Рисуем коридоры нормы (пунктирные линии)
    const normRanges = [
      { value: 120, label: 'САД мин' },
      { value: 130, label: 'САД макс' },
      { value: 80, label: 'ДАД мин' },
      { value: 85, label: 'ДАД макс' }
    ];

    normRanges.forEach(norm => {
      const y = 100 - ((norm.value - minVal) / range * 100);
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', '0');
      line.setAttribute('x2', values.length * 20);
      line.setAttribute('y1', y);
      line.setAttribute('y2', y);
      line.setAttribute('stroke', '#94a3b8');
      line.setAttribute('stroke-width', '1.5');
      line.setAttribute('stroke-dasharray', '4,3');
      line.setAttribute('opacity', '0.8');
      svg.appendChild(line);
    });

    // Рисуем линии для каждого измерения
    values.forEach((item, index) => {
      const sys = item.systolic || 0;
      const dia = item.diastolic || 0;
      const level = getBPLevel(sys, dia);
      const color = colors[level + 3]; // Сдвигаем индекс: -3 -> 0, 0 -> 3, 3 -> 6

      const x = index * 20 + 10;
      const y1 = 100 - ((sys - minVal) / range * 100);
      const y2 = 100 - ((dia - minVal) / range * 100);

      // Вертикальная линия от диастолического до систолического
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', x);
      line.setAttribute('x2', x);
      line.setAttribute('y1', y1);
      line.setAttribute('y2', y2);
      line.setAttribute('stroke', color);
      line.setAttribute('stroke-width', '8');
      line.setAttribute('stroke-linecap', 'round');
      line.setAttribute('class', 'bp-range-line');

      // Tooltip
      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = `${sys}/${dia} • ${formatDateLabel(item.date)}`;
      line.appendChild(title);

      svg.appendChild(line);

      // Точки на концах для лучшей видимости
      [y1, y2].forEach(y => {
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', x);
        circle.setAttribute('cy', y);
        circle.setAttribute('r', '4');
        circle.setAttribute('fill', color);
        svg.appendChild(circle);
      });
    });

    container.appendChild(svg);
  }


  function trendText(last, avg, suffix = '') {
    if (last === null || last === undefined || avg === null || avg === undefined) {
      return 'Нет данных за неделю';
    }
    const diff = last - avg;
    if (Math.abs(diff) < 0.5) return 'Стабильно';
    return diff > 0 ? `Есть рост${suffix}` : `Снижение${suffix}`;
  }

  function updateHeaderToken(token) {
    const el = document.getElementById('header-token');
    if (el && token) {
      el.textContent = `Токен пациента: ${token}`;
    }
  }

  function safeFetch(url) {
    return fetch(url).then((resp) => {
      if (!resp.ok) throw new Error(`Request failed ${resp.status}`);
      return resp.json();
    });
  }

  async function loadDailyWaterTotal(patientToken) {
    try {
      const data = await safeFetch(`/vitals/water/daily-total/by-token/${encodeURIComponent(patientToken)}`);
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
      const values = data.slice(0, 7).reverse();

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

  async function loadWaterCard(patientToken) {
    if (!patientToken) return;

    const chartEl = document.getElementById('water-chart');
    const latestEl = document.getElementById('water-latest');
    const trendEl = document.getElementById('water-trend');
    const updatedAtEl = document.getElementById('water-updated-at');

    try {
      const data = await safeFetch(`/vitals/water/by-token/${encodeURIComponent(patientToken)}?limit=200&order_by=measured_at desc`);

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

  async function loadVitals(patientToken) {
    if (!patientToken) return;

    await Promise.all([
      loadVitalsCard({
        idPrefix: 'bp',
        endpoint: `/vitals/bp/by-token/${encodeURIComponent(patientToken)}?limit=7&order_by=measured_at desc`,
        formatValue: (item) => `${item.systolic ?? '—'} / ${item.diastolic ?? '—'}`,
        trendSuffix: '',
        chartMapper: (item) => ({
          systolic: item.systolic || 0,
          diastolic: item.diastolic || 0,
          date: item.measured_at
        }),
        customChartBuilder: buildBPRangeChart,
      }),
      loadVitalsCard({
        idPrefix: 'pulse',
        endpoint: `/vitals/pulse/by-token/${encodeURIComponent(patientToken)}?limit=7&order_by=measured_at desc`,
        formatValue: (item) => `${item.bpm ?? '—'} уд/мин`,
        trendSuffix: '',
        chartMapper: (item) => ({ value: item.bpm || 0, date: item.measured_at }),
        colorClassifier: getPulseLevel,
      }),
      loadVitalsCard({
        idPrefix: 'weight',
        endpoint: `/vitals/weight/by-token/${encodeURIComponent(patientToken)}?limit=7&order_by=measured_at desc`,
        formatValue: (item) => `${item.weight ?? '—'} кг`,
        trendSuffix: '',
        chartMapper: (item) => ({ value: item.weight || 0, date: item.measured_at }),
      }),

      loadWaterCard(patientToken),

    ]);
  }

  async function loadScales(patientToken) {
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
        `/api/v1/scales/${encodeURIComponent(code)}/history?limit=7` +
        (patientToken ? `&patient_token=${encodeURIComponent(patientToken)}` : '');

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

    if (!patientToken) {
      setEmptyState();
      return;
    }

    try {
      const overviewUrl =
        `/api/v1/scales/overview` +
        (patientToken ? `?patient_token=${encodeURIComponent(patientToken)}` : '');

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

  async function loadEducation(patientToken) {
    const fillEl = document.getElementById('education-progress-fill');
    const labelEl = document.getElementById('education-progress-label');
    const titleEl = document.getElementById('education-last-title');
    const captionEl = document.getElementById('education-last-caption');

    if (!patientToken) {
      labelEl.textContent = 'Нет данных';
      titleEl.textContent = 'Недоступно';
      captionEl.textContent = 'Авторизуйтесь по токену пациента.';
      return;
    }

    try {
      const blocks = await safeFetch(`/api/v1/education/lessons/overview?patient_token=${encodeURIComponent(patientToken)}`);
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

  function initNavigation(patientToken) {
    const vitalsCards = ['card-bp', 'card-pulse', 'card-weight', 'card-water'];
    vitalsCards.forEach((id) => {
      const card = document.getElementById(id);
      if (card) {
        card.addEventListener('click', () => {
          const target = patientToken
            ? `/p/${encodeURIComponent(patientToken)}/vitals`
            : '/frontend/patient/vitals.html';
          window.location.href = target;
        });
      }
    });

    const scalesCard = document.getElementById('card-scales');
    if (scalesCard) {
      scalesCard.addEventListener('click', () => {
        const target = patientToken
          ? `/p/${encodeURIComponent(patientToken)}/scales`
          : '/frontend/patient/scales_overview.html';
        window.location.href = target;
      });
    }

    const eduCard = document.getElementById('card-education');
    if (eduCard) {
      eduCard.addEventListener('click', () => {
        const target = patientToken
          ? `/p/${encodeURIComponent(patientToken)}/education_overview`
          : '/frontend/patient/education_overview.html';
        window.location.href = target;
      });
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const patientToken = getPatientToken();
    updateHeaderToken(patientToken);

    await Promise.all([
      loadVitals(patientToken),
      loadScales(patientToken),
      loadEducation(patientToken),
    ]);

    initNavigation(patientToken);
  });
})();
