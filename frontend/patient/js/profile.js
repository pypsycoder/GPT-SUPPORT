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

    if (personalIcon) {
      personalIcon.textContent = profile.consent_personal_data ? '✅' : '❌';
      personalIcon.classList.toggle('consent-yes', profile.consent_personal_data);
      personalIcon.classList.toggle('consent-no', !profile.consent_personal_data);
    }

    if (botIcon) {
      botIcon.textContent = profile.consent_bot_use ? '✅' : '❌';
      botIcon.classList.toggle('consent-yes', profile.consent_bot_use);
      botIcon.classList.toggle('consent-no', !profile.consent_bot_use);
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
      const profile = await fetchProfileSummary();

      renderPersonalData(profile);
      renderConsents(profile);
      renderVitals(profile.vitals);
      renderEducation(profile.education);
      renderScales(profile.scales);
    } catch (err) {
      console.error('Ошибка загрузки профиля:', err);
      setStatus('error', 'Не удалось загрузить данные профиля. Обновите страницу.');
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    // Авторизация происходит через session cookies
    // Загрузка данных профиля
    const reloadProfile = () => loadAndRenderProfile();
    reloadProfile();

    // Инициализация управления
    initEditControls(reloadProfile);
  });
})();
