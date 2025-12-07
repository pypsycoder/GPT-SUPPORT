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

  function buildMiniBarChart(container, values) {
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
      const heightPct = Math.max(8, Math.round(((item.value || 0) / maxValue) * 100));
      bar.style.height = `${heightPct}%`;
      bar.title = `${item.value ?? '—'} • ${formatDateLabel(item.date)}`;
      container.appendChild(bar);
    });
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

  async function loadVitalsCard(config) {
    const {
      idPrefix,
      endpoint,
      formatValue,
      trendSuffix,
      chartMapper,
    } = config;
    const latestEl = document.getElementById(`${idPrefix}-latest`);
    const trendEl = document.getElementById(`${idPrefix}-trend`);
    const updatedAtEl = document.getElementById(`${idPrefix}-updated-at`);
    const chartEl = document.getElementById(`${idPrefix}-chart`);

    try {
      const data = await safeFetch(endpoint);
      if (!Array.isArray(data) || data.length === 0) {
        trendEl.textContent = 'Нет данных за неделю';
        buildMiniBarChart(chartEl, []);
        return;
      }

      const latest = data[0];
      const values = data.slice(0, 7).reverse();

      const mapped = values.map((item) => chartMapper(item));
      buildMiniBarChart(chartEl, mapped);

      const numericValues = mapped.map((m) => m.value || 0);
      const avg = numericValues.reduce((a, b) => a + b, 0) / numericValues.length;
      const lastValue = mapped[mapped.length - 1].value;

      if (latestEl) latestEl.textContent = formatValue(latest);
      if (trendEl) trendEl.textContent = trendText(lastValue, avg, trendSuffix);
      if (updatedAtEl) updatedAtEl.textContent = formatDateLabel(latest.measured_at);
    } catch (err) {
      console.warn(`Не удалось загрузить ${idPrefix}:`, err);
      trendEl.textContent = 'Нет данных за неделю';
      buildMiniBarChart(chartEl, []);
    }
  }

  async function loadVitals(patientToken) {
    if (!patientToken) return;

    await Promise.all([
      loadVitalsCard({
        idPrefix: 'bp',
        endpoint: `/api/v1/vitals/bp/by-token/${encodeURIComponent(patientToken)}?limit=7&order_by=measured_at desc`,
        formatValue: (item) => `${item.systolic ?? '—'} / ${item.diastolic ?? '—'}`,
        trendSuffix: '',
        chartMapper: (item) => ({ value: item.systolic || 0, date: item.measured_at }),
      }),
      loadVitalsCard({
        idPrefix: 'pulse',
        endpoint: `/api/v1/vitals/pulse/by-token/${encodeURIComponent(patientToken)}?limit=7&order_by=measured_at desc`,
        formatValue: (item) => `${item.bpm ?? '—'} уд/мин`,
        trendSuffix: '',
        chartMapper: (item) => ({ value: item.bpm || 0, date: item.measured_at }),
      }),
      loadVitalsCard({
        idPrefix: 'weight',
        endpoint: `/api/v1/vitals/weight/by-token/${encodeURIComponent(patientToken)}?limit=7&order_by=measured_at desc`,
        formatValue: (item) => `${item.weight ?? '—'} кг`,
        trendSuffix: '',
        chartMapper: (item) => ({ value: item.weight || 0, date: item.measured_at }),
      }),
      loadVitalsCard({
        idPrefix: 'water',
        endpoint: `/api/v1/vitals/water/by-token/${encodeURIComponent(patientToken)}?limit=7&order_by=measured_at desc`,
        formatValue: (item) => `${item.volume ?? '—'} мл`,
        trendSuffix: '',
        chartMapper: (item) => ({ value: item.volume || 0, date: item.measured_at }),
      }),
    ]);
  }

  async function loadScales(patientToken) {
    const selectEl = document.getElementById('scale-select');
    const scoreEl = document.getElementById('scale-main-score');
    const summaryEl = document.getElementById('scale-main-summary');
    const chartEl = document.getElementById('scale-chart');

    if (selectEl) {
      selectEl.addEventListener('click', (event) => event.stopPropagation());
    }

    try {
      const overview = await safeFetch('/api/v1/scales/overview');
      if (!Array.isArray(overview) || overview.length === 0) {
        selectEl.innerHTML = '<option>Нет шкал</option>';
        scoreEl.textContent = '—';
        summaryEl.textContent = 'Нет данных по шкале';
        buildMiniBarChart(chartEl, []);
        return;
      }

      overview.forEach((scale) => {
        const option = document.createElement('option');
        option.value = scale.scale_code || scale.code || '';
        option.textContent = scale.scale_name || scale.name || option.value;
        selectEl.appendChild(option);
      });

      const preferred = overview.find((s) => (s.scale_code || s.code) === 'HADS');
      selectEl.value = preferred
        ? (preferred.scale_code || preferred.code)
        : selectEl.options[0].value;

      async function updateSelectedScale() {
        const code = selectEl.value;
        try {
          const history = await safeFetch(`/api/v1/scales/${encodeURIComponent(code)}/history?limit=7${patientToken ? `&patient_token=${encodeURIComponent(patientToken)}` : ''}`);
          if (!Array.isArray(history) || history.length === 0) {
            scoreEl.textContent = '—';
            summaryEl.textContent = 'Нет данных по шкале';
            buildMiniBarChart(chartEl, []);
            return;
          }

          const latest = history[0];
          const mapped = history
            .slice(0, 7)
            .reverse()
            .map((item) => ({ value: item.total_score ?? item.score ?? 0, date: item.measured_at || item.created_at }));

          scoreEl.textContent = latest.total_score ?? latest.score ?? '—';
          summaryEl.textContent = latest.summary || latest.status || 'Обновлено';
          buildMiniBarChart(chartEl, mapped);
        } catch (err) {
          console.warn('Не удалось загрузить шкалу', err);
          scoreEl.textContent = '—';
          summaryEl.textContent = 'Нет данных по шкале';
          buildMiniBarChart(chartEl, []);
        }
      }

      selectEl.addEventListener('change', updateSelectedScale);
      await updateSelectedScale();
    } catch (err) {
      console.warn('Не удалось загрузить список шкал', err);
      if (selectEl) selectEl.innerHTML = '<option>Нет шкал</option>';
      scoreEl.textContent = '—';
      summaryEl.textContent = 'Нет данных по шкале';
      buildMiniBarChart(chartEl, []);
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
