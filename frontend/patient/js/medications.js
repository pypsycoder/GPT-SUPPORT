/**
 * Модуль управления препаратами
 * API: /api/v1/medications (список препаратов, приёмы)
 * - Загрузка и отображение активных назначений (medications)
 * - Отметка факта приёма
 * - Просмотр истории приёмов
 * - Редактирование/удаление: UI готов, бэкенд пока не поддерживает
 */

(function () {
  "use strict";

  const API_BASE = "/api/v1/medications";
  const ENDPOINTS = {
    list: API_BASE + "?active_only=true",
    prescriptions: API_BASE,
    medicationById: function (id) { return API_BASE + "/" + id; },
    intake: API_BASE + "/intake",
    intakeHistory: API_BASE + "/intake/history",
    intakeById: function (id) { return API_BASE + "/intake/" + id; },
  };

  let activePrescriptions = [];
  let currentPrescription = null;
  let currentIntake = null;

  function fetchWithAuth(url, options) {
    const opts = Object.assign({ credentials: "include" }, options);
    return fetch(url, opts);
  }

  document.addEventListener("DOMContentLoaded", async function () {
    try {
      await loadActivePrescriptions();
      setupEventListeners();
    } catch (err) {
      console.error("Ошибка инициализации модуля препаратов:", err);
      showToast("Ошибка загрузки страницы", "error");
    }
  });

  async function loadActivePrescriptions() {
    const container = document.getElementById("prescriptionsContainer");
    const emptyState = document.getElementById("emptyState");
    if (!container) return;

    try {
      container.innerHTML = '<div class="loading-spinner">Загрузка назначений...</div>';
      emptyState.style.display = "none";

      const response = await fetchWithAuth(ENDPOINTS.list);
      if (!response.ok) throw new Error("HTTP " + response.status + ": " + response.statusText);

      const data = await response.json();
      const items = data.items || [];
      activePrescriptions = items.map(function (m) {
        const times = m.times_of_day || [];
        return {
          id: m.id,
          medication_name: m.display_name || "",
          dose: m.dose || "",
          dose_unit: "ед.",
          frequency_times_per_day: times.length || 1,
          times_of_day: m.times_of_day || [],
          route: formatFoodRelation(m.relation_to_food),
          start_date: m.created_at,
          end_date: null,
          indication: m.notes || "",
          adherence_rate: 0,
          prescribed_by: m.prescribed_by != null ? m.prescribed_by : null,
        };
      });

      if (activePrescriptions.length === 0) {
        container.innerHTML = "";
        emptyState.style.display = "block";
      } else {
        emptyState.style.display = "none";
        renderPrescriptions(activePrescriptions);
      }
    } catch (err) {
      console.error("Ошибка загрузки назначений:", err);
      container.innerHTML =
        '<div class="error-state">' +
        '<i class="icon-alert-circle"></i>' +
        "<p>Не удалось загрузить назначения</p>" +
        '<button class="btn btn-secondary" type="button" id="retryPrescriptions">Повторить попытку</button>' +
        "</div>";
      showToast("Ошибка загрузки назначений", "error");
      document.getElementById("retryPrescriptions")?.addEventListener("click", loadActivePrescriptions);
    }
  }

  /** Генерация времени приёма по количеству раз в день (для API: daily + times_of_day) */
  function generateTimesOfDay(timesPerDay) {
    var n = Math.max(1, Math.min(10, parseInt(timesPerDay, 10) || 1));
    var out = [];
    for (var i = 0; i < n; i++) {
      var hour = n === 1 ? 12 : 8 + Math.round((12 * (i + 1)) / (n + 1));
      if (hour > 23) hour = 23;
      out.push(String(hour).padStart(2, "0") + ":00:00");
    }
    return out.sort();
  }

  function formatFoodRelation(relation) {
    const map = {
      before: "до еды",
      with: "во время еды",
      after: "после еды",
      none: "",
    };
    return relation ? map[relation] || "" : "";
  }

  function renderPrescriptions(prescriptions) {
    const container = document.getElementById("prescriptionsContainer");
    if (!container) return;
    container.innerHTML = "";
    prescriptions.forEach(function (p) {
      container.appendChild(createPrescriptionCard(p));
    });
  }

  function createPrescriptionCard(prescription) {
    const card = document.createElement("div");
    card.className = "prescription-card";
    if (!prescription.prescribed_by) card.classList.add("self-prescribed");
    card.dataset.prescriptionId = prescription.id;

    const adherenceRate = prescription.adherence_rate || 0;
    const adherenceColor = getAdherenceColor(adherenceRate);
    const adherencePercent = Math.round(adherenceRate * 100);
    const startDate = formatDate(prescription.start_date);
    const endDate = prescription.end_date ? formatDate(prescription.end_date) : "постоянно";

    card.innerHTML =
      '<div class="card-header">' +
      '<div class="card-title-group">' +
      '<h3 class="card-title">' + escapeHtml(prescription.medication_name) + "</h3>" +
      (!prescription.prescribed_by ? '<span class="badge-self-prescribed">Самостоятельно</span>' : "") +
      "</div>" +
      '<span class="adherence-badge" style="background-color:' + adherenceColor + '">' + adherencePercent + "%</span>" +
      "</div>" +
      '<div class="card-body">' +
      '<div class="card-info-row"><span class="info-label">Доза:</span><span class="info-value">' +
      escapeHtml(prescription.dose) +
      " " +
      prescription.dose_unit +
      "</span></div>" +
      '<div class="card-info-row"><span class="info-label">Частота:</span><span class="info-value">' +
      prescription.frequency_times_per_day +
      "×/день</span></div>" +
      (prescription.route
        ? '<div class="card-info-row"><span class="info-label">Способ приёма:</span><span class="info-value">' +
          escapeHtml(prescription.route) +
          "</span></div>"
        : "") +
      '<div class="card-info-row"><span class="info-label">Период:</span><span class="info-value">' +
      startDate +
      " — " +
      endDate +
      "</span></div>" +
      (prescription.indication
        ? '<div class="card-info-row"><span class="info-label">Показания:</span><span class="info-value">' +
          escapeHtml(prescription.indication) +
          "</span></div>"
        : "") +
      "</div>" +
      '<div class="card-footer">' +
      '<button type="button" class="btn btn-link" data-action="details" data-id="' +
      escapeHtml(String(prescription.id)) +
      '"><i class="icon-info"></i> Подробнее</button>' +
      "</div>";

    card.querySelector('[data-action="details"]').addEventListener("click", function () {
      showPrescriptionDetails(prescription.id);
    });
    return card;
  }

  function getAdherenceColor(rate) {
    if (rate >= 0.8) return "#4caf50";
    if (rate >= 0.5) return "#ff9800";
    return "#f44336";
  }

  function openAddPrescriptionModal() {
    var modal = document.getElementById("modalAddPrescription");
    var form = document.getElementById("formAddPrescription");
    if (!modal || !form) return;
    form.reset();
    delete document.getElementById("btnSubmitPrescription").dataset.prescriptionId;
    var titleEl = modal.querySelector(".modal-title");
    if (titleEl) titleEl.textContent = "Добавить препарат";
    var submitBtn = document.getElementById("btnSubmitPrescription");
    if (submitBtn) submitBtn.innerHTML = '<i class="icon-check"></i> Добавить препарат';
    var today = new Date();
    var startInput = document.getElementById("newStartDate");
    if (startInput) {
      startInput.value = formatDateForInput(today);
      startInput.max = formatDateForInput(today);
      startInput.removeAttribute("readonly");
    }
    var nameInput = document.getElementById("newMedicationName");
    if (nameInput) nameInput.removeAttribute("readonly");
    showModal(modal);
  }

  async function submitAddPrescription(event) {
    event.preventDefault();
    var submitBtn = document.getElementById("btnSubmitPrescription");
    var prescriptionId = submitBtn && submitBtn.dataset.prescriptionId;
    var isUpdate = !!prescriptionId;
    var method = isUpdate ? "PATCH" : "POST";
    var url = isUpdate ? ENDPOINTS.medicationById(prescriptionId) : ENDPOINTS.prescriptions;

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<i class="icon-loader"></i> Сохранение...';
    }

    try {
      var nameVal = document.getElementById("newMedicationName").value.trim();
      var doseNum = parseFloat(document.getElementById("newDose").value);
      var doseUnit = document.getElementById("newDoseUnit").value;
      var freq = parseInt(document.getElementById("newFrequency").value, 10);
      var route = document.getElementById("newRoute").value;
      var startDate = document.getElementById("newStartDate").value;
      var endDateEl = document.getElementById("newEndDate");
      var endDate = endDateEl && endDateEl.value ? endDateEl.value : null;
      var indication = document.getElementById("newIndication").value.trim();
      var instructions = document.getElementById("newInstructions").value.trim();

      if (!nameVal || isNaN(doseNum) || doseNum <= 0 || isNaN(freq) || freq < 1 || freq > 10 || !route || !startDate) {
        throw new Error("Пожалуйста, заполните все обязательные поля корректно");
      }
      if (endDate && endDate < startDate) {
        throw new Error("Дата окончания не может быть раньше даты начала");
      }

      var notesParts = ["Способ: " + route];
      if (indication) notesParts.push("Для чего: " + indication);
      if (instructions) notesParts.push(instructions);
      if (startDate) notesParts.push("Начало: " + startDate);
      if (endDate) notesParts.push("Окончание: " + endDate);
      var notes = notesParts.join(". ") || null;

      var doseStr = doseNum + " " + doseUnit;
      var timesOfDay = generateTimesOfDay(freq);

      if (isUpdate) {
        var payload = {
          dose: doseStr,
          frequency_type: "daily",
          times_of_day: timesOfDay,
          notes: notes,
        };
        var response = await fetchWithAuth(url, {
          method: method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } else {
        var payload = {
          reference_id: null,
          custom_name: nameVal,
          dose: doseStr,
          frequency_type: "daily",
          days_of_week: null,
          times_of_day: timesOfDay,
          relation_to_food: null,
          notes: notes,
        };
        var response = await fetchWithAuth(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }

      if (!response.ok) {
        var errBody = await response.json().catch(function () { return {}; });
        var msg = errBody.detail;
        if (Array.isArray(msg) && msg[0] && msg[0].msg) msg = msg[0].msg;
        if (typeof msg !== "string") msg = "Ошибка при сохранении";
        throw new Error(msg);
      }

      showToast(isUpdate ? "Препарат обновлён" : "Препарат успешно добавлен", "success");
      closeModal(document.getElementById("modalAddPrescription"));
      if (submitBtn) {
        delete submitBtn.dataset.prescriptionId;
        submitBtn.innerHTML = '<i class="icon-check"></i> Добавить препарат';
      }
      var titleEl = document.querySelector("#modalAddPrescription .modal-title");
      if (titleEl) titleEl.textContent = "Добавить препарат";
      await loadActivePrescriptions();
    } catch (err) {
      console.error("Ошибка при сохранении препарата:", err);
      showToast(err.message || "Ошибка при сохранении", "error");
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = submitBtn.dataset.prescriptionId
          ? '<i class="icon-check"></i> Сохранить изменения'
          : '<i class="icon-check"></i> Добавить препарат';
      }
    }
  }

  function openAddIntakeModal() {
    const modal = document.getElementById("modalAddIntake");
    const select = document.getElementById("selectPrescription");
    const dateInput = document.getElementById("intakeDate");
    const timeInput = document.getElementById("intakeTime");
    if (!modal || !select) return;

    select.innerHTML = '<option value="">-- Выберите препарат --</option>';
    activePrescriptions.forEach(function (p) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.medication_name + " (" + p.dose + " " + p.dose_unit + ")";
      opt.dataset.dose = p.dose;
      opt.dataset.unit = p.dose_unit;
      select.appendChild(opt);
    });

    var now = new Date();
    dateInput.value = formatDateForInput(now);
    timeInput.value = formatTimeForInput(now);
    var minDate = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    dateInput.min = formatDateForInput(minDate);
    dateInput.max = formatDateForInput(now);

    document.getElementById("formAddIntake").reset();
    document.getElementById("actualDose").value = "";
    document.getElementById("intakeNotes").value = "";
    var hint = document.getElementById("prescribedDoseHint");
    if (hint) hint.textContent = "Назначено: --";
    var warn = document.getElementById("doseWarning");
    if (warn) warn.style.display = "none";
    var countEl = document.getElementById("notesCharCount");
    if (countEl) countEl.textContent = "0";

    dateInput.value = formatDateForInput(now);
    timeInput.value = formatTimeForInput(now);

    showModal(modal);
  }

  function handlePrescriptionSelect(prescriptionId) {
    var select = document.getElementById("selectPrescription");
    var option = null;
    if (select && prescriptionId) {
      for (var i = 0; i < select.options.length; i++) {
        if (select.options[i].value === String(prescriptionId)) {
          option = select.options[i];
          break;
        }
      }
    }
    var doseInput = document.getElementById("actualDose");
    var doseUnit = document.getElementById("doseUnit");
    var hint = document.getElementById("prescribedDoseHint");
    if (!option || !option.dataset.dose) {
      if (doseInput) doseInput.value = "";
      if (doseUnit) doseUnit.textContent = "";
      if (hint) hint.textContent = "Назначено: --";
      return;
    }
    var prescribedDose = option.dataset.dose;
    var unit = option.dataset.unit || "ед.";
    if (doseInput) doseInput.value = prescribedDose;
    if (doseUnit) doseUnit.textContent = unit;
    if (hint) hint.textContent = "Назначено: " + prescribedDose + " " + unit;
    var warning = document.getElementById("doseWarning");
    if (warning) warning.style.display = "none";
  }

  function validateDose() {
    var select = document.getElementById("selectPrescription");
    var option = select && select.options[select.selectedIndex];
    var doseInput = document.getElementById("actualDose");
    var warning = document.getElementById("doseWarning");
    if (!option || !option.dataset.dose || !warning) return;
    var prescribedStr = option.dataset.dose;
    var prescribedDose = parseFloat(prescribedStr);
    if (isNaN(prescribedDose)) return;
    var actualDose = parseFloat(doseInput.value);
    if (isNaN(actualDose) || actualDose <= 0) {
      warning.style.display = "none";
      return;
    }
    var deviation = Math.abs(actualDose - prescribedDose) / prescribedDose;
    warning.style.display = deviation > 0.5 ? "flex" : "none";
  }

  async function submitAddIntake(event) {
    event.preventDefault();
    var submitBtn = document.getElementById("btnSubmitIntake");
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<i class="icon-loader"></i> Сохранение...';
    }

    try {
      var prescriptionId = document.getElementById("selectPrescription").value;
      var date = document.getElementById("intakeDate").value;
      var time = document.getElementById("intakeTime").value;
      var notes = (document.getElementById("intakeNotes") && document.getElementById("intakeNotes").value) || "";
      if (!prescriptionId || !date || !time) {
        throw new Error("Пожалуйста, заполните все обязательные поля");
      }
      var timePart = time.length === 5 ? time + ":00" : time;
      var takenAt = date + "T" + timePart;
      var payload = {
        medication_id: prescriptionId,
        scheduled_date: date,
        scheduled_time: timePart,
        status: "taken",
        taken_at: takenAt,
      };

      var response = await fetchWithAuth(ENDPOINTS.intake, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        var errBody = await response.json().catch(function () { return {}; });
        throw new Error(errBody.detail || "Ошибка при сохранении приёма");
      }

      showToast("Приём успешно отмечен", "success");
      closeModal(document.getElementById("modalAddIntake"));
      await loadActivePrescriptions();
    } catch (err) {
      console.error("Ошибка при добавлении приёма:", err);
      showToast(err.message || "Ошибка при сохранении", "error");
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="icon-check"></i> Сохранить';
      }
    }
  }

  async function showPrescriptionDetails(prescriptionId) {
    var modal = document.getElementById("modalPrescriptionDetails");
    var content = document.getElementById("detailsContent");
    var titleEl = document.getElementById("detailsTitle");
    if (!modal || !content) return;

    var prescription = activePrescriptions.filter(function (p) { return String(p.id) === String(prescriptionId); })[0];
    if (!prescription) {
      showToast("Назначение не найдено", "error");
      return;
    }
    currentPrescription = prescription;

    if (titleEl) titleEl.textContent = prescription.medication_name;
    content.innerHTML = '<div class="loading-spinner">Загрузка данных...</div>';
    showModal(modal);

    try {
      var url = ENDPOINTS.intakeHistory + "?medication_id=" + encodeURIComponent(prescriptionId);
      var response = await fetchWithAuth(url);
      if (!response.ok) throw new Error("Не удалось загрузить историю");
      var intakes = await response.json();
      content.innerHTML = renderPrescriptionDetails(prescription, intakes || []);
    } catch (err) {
      console.error("Ошибка загрузки деталей:", err);
      content.innerHTML =
        '<div class="error-state"><i class="icon-alert-circle"></i><p>Не удалось загрузить данные</p></div>';
      showToast("Ошибка загрузки деталей", "error");
    }
  }

  function renderPrescriptionDetails(prescription, intakes) {
    var adherencePercent = Math.round((prescription.adherence_rate || 0) * 100);
    var adherenceColor = getAdherenceColor(prescription.adherence_rate || 0);
    var startDate = formatDate(prescription.start_date);
    var endDate = prescription.end_date ? formatDate(prescription.end_date) : "постоянно";
    var selfPrescribed = !prescription.prescribed_by;
    var idAttr = escapeHtml(String(prescription.id));

    var html =
      '<div class="prescription-details">' +
      '<div class="details-header">' +
      "<h3>" + escapeHtml(prescription.medication_name) + "</h3>" +
      '<div class="details-actions">' +
      '<span class="adherence-badge-large" style="background-color:' + adherenceColor + '">Соблюдение: ' + adherencePercent + "%</span>" +
      (selfPrescribed
        ? '<div class="dropdown-menu">' +
          '<button type="button" class="btn btn-icon" data-action="edit-prescription" data-id="' + idAttr + '" title="Редактировать"><i class="icon-edit"></i></button>' +
          '<button type="button" class="btn btn-icon btn-danger" data-action="delete-prescription" data-id="' + idAttr + '" title="Удалить"><i class="icon-trash"></i></button>' +
          "</div>"
        : "") +
      "</div></div>" +
      (selfPrescribed
        ? '<div class="alert alert-info"><i class="icon-info-circle"></i> Это препарат, добавленный вами самостоятельно. Обязательно сообщите о нём врачу на приёме.</div>'
        : "") +
      '<div class="details-grid">' +
      '<div class="detail-item"><span class="detail-label">Доза:</span><span class="detail-value">' +
      escapeHtml(prescription.dose) +
      " " +
      prescription.dose_unit +
      "</span></div>" +
      '<div class="detail-item"><span class="detail-label">Частота:</span><span class="detail-value">' +
      prescription.frequency_times_per_day +
      "×/день</span></div>" +
      (prescription.route
        ? '<div class="detail-item"><span class="detail-label">Способ приёма:</span><span class="detail-value">' +
          escapeHtml(prescription.route) +
          "</span></div>"
        : "") +
      '<div class="detail-item"><span class="detail-label">Период:</span><span class="detail-value">' +
      startDate + " — " + endDate +
      "</span></div>" +
      (prescription.indication
        ? '<div class="detail-item detail-item-full"><span class="detail-label">Показания:</span><span class="detail-value">' +
          escapeHtml(prescription.indication) +
          "</span></div>"
        : "") +
      "</div>" +
      '</div><hr class="divider">' +
      '<div class="intakes-history"><h4>История приёмов</h4>';

    if (!intakes.length) {
      html += '<div class="empty-state-small"><i class="icon-info-circle"></i><p>Приёмов ещё не отмечено</p></div>';
    } else {
      html += '<div class="intakes-table-wrapper"><table class="intakes-table">' +
        "<thead><tr><th>Дата и время</th><th>Статус</th><th class=\"actions-col\">Действия</th></tr></thead><tbody>";
      intakes.forEach(function (intake) {
        var dt = intake.taken_at || (intake.scheduled_date && intake.scheduled_time ? intake.scheduled_date + "T" + intake.scheduled_time : intake.created_at);
        var statusText = intake.status === "taken" ? "Принято" : "Пропущено";
        html +=
          '<tr data-intake-id="' + escapeHtml(String(intake.id)) + '">' +
          "<td>" + formatDateTime(dt) + "</td>" +
          "<td>" + escapeHtml(statusText) + "</td>" +
          '<td class="actions-cell">' +
          '<button type="button" class="btn-icon" data-action="edit-intake" data-id="' + escapeHtml(String(intake.id)) + '" title="Редактировать"><i class="icon-edit"></i></button>' +
          '<button type="button" class="btn-icon btn-danger" data-action="delete-intake" data-id="' + escapeHtml(String(intake.id)) + '" title="Удалить"><i class="icon-trash"></i></button>' +
          "</td></tr>";
      });
      html += "</tbody></table></div>";
    }
    html += "</div>";
    return html;
  }

  function onDetailsContentClick(e) {
    var target = e.target.closest("[data-action]");
    if (!target) return;
    var action = target.getAttribute("data-action");
    var id = target.getAttribute("data-id");
    if (action === "edit-intake" && id) editIntake(id);
    if (action === "delete-intake" && id) confirmDeleteIntake(id);
    if (action === "edit-prescription" && id) editPrescription(id);
    if (action === "delete-prescription" && id) confirmDeletePrescription(id);
  }

  function editIntake(intakeId) {
    // Модалка редактирования и форма есть в HTML; вызов API PUT — когда бэкенд добавит эндпоинт
    showToast("Редактирование записей о приёме пока недоступно", "info");
  }

  function confirmDeleteIntake(intakeId) {
    if (!confirm("Вы уверены, что хотите удалить эту запись о приёме? Это действие нельзя отменить.")) {
      return;
    }
    deleteIntake(intakeId);
  }

  async function deleteIntake(intakeId) {
    try {
      var url = typeof ENDPOINTS.intakeById === "function" ? ENDPOINTS.intakeById(intakeId) : API_BASE + "/intake/" + intakeId;
      var response = await fetchWithAuth(url, { method: "DELETE" });
      if (!response.ok) {
        throw new Error(response.status === 404 || response.status === 405 ? "Удаление приёмов пока не поддерживается сервером" : "Не удалось удалить приём");
      }
      showToast("Запись удалена", "success");
      if (currentPrescription) {
        await showPrescriptionDetails(currentPrescription.id);
      }
      await loadActivePrescriptions();
    } catch (err) {
      console.error("Ошибка при удалении приёма:", err);
      showToast(err.message || "Ошибка при удалении", "error");
    }
  }

  function editPrescription(prescriptionId) {
    var prescription = activePrescriptions.filter(function (p) { return String(p.id) === String(prescriptionId); })[0];
    if (!prescription) {
      showToast("Назначение не найдено", "error");
      return;
    }
    if (prescription.prescribed_by) {
      showToast("Можно редактировать только самостоятельно добавленные препараты", "error");
      return;
    }
    var nameInput = document.getElementById("newMedicationName");
    var doseInput = document.getElementById("newDose");
    var unitSelect = document.getElementById("newDoseUnit");
    if (nameInput) nameInput.value = prescription.medication_name;
    if (nameInput) nameInput.setAttribute("readonly", "readonly");
    var doseStr = prescription.dose || "";
    var doseMatch = /^(\d+(?:[.,]\d+)?)\s*(.*)$/.exec(doseStr.replace(",", "."));
    if (doseMatch) {
      if (doseInput) doseInput.value = parseFloat(doseMatch[1]) || "";
      var unit = (doseMatch[2] || "").trim();
      if (unitSelect) {
        var opt = Array.prototype.find.call(unitSelect.options, function (o) { return o.value === unit; });
        unitSelect.value = opt ? opt.value : (unitSelect.options[0] ? unitSelect.options[0].value : "мг");
      }
    } else {
      if (doseInput) doseInput.value = doseStr;
      if (unitSelect) unitSelect.value = "ед.";
    }
    document.getElementById("newFrequency").value = prescription.frequency_times_per_day || 1;
    var routeSelect = document.getElementById("newRoute");
    if (routeSelect) {
      var routeVal = prescription.route || "";
      var routeOpt = Array.prototype.find.call(routeSelect.options, function (o) { return o.value === routeVal || (routeVal && o.text.indexOf(routeVal) >= 0); });
      routeSelect.value = routeOpt ? routeOpt.value : (routeSelect.options[1] ? routeSelect.options[1].value : "");
    }
    var startInput = document.getElementById("newStartDate");
    if (startInput) {
      startInput.value = prescription.start_date ? (prescription.start_date.slice ? prescription.start_date.slice(0, 10) : formatDateForInput(new Date(prescription.start_date))) : "";
      startInput.removeAttribute("readonly");
    }
    var endInput = document.getElementById("newEndDate");
    if (endInput) endInput.value = prescription.end_date ? (prescription.end_date.slice ? prescription.end_date.slice(0, 10) : "") : "";
    document.getElementById("newIndication").value = prescription.indication || "";
    document.getElementById("newInstructions").value = prescription.instructions || "";
    var modal = document.getElementById("modalAddPrescription");
    var titleEl = modal && modal.querySelector(".modal-title");
    if (titleEl) titleEl.textContent = "Редактировать препарат";
    var submitBtn = document.getElementById("btnSubmitPrescription");
    if (submitBtn) {
      submitBtn.dataset.prescriptionId = String(prescription.id);
      submitBtn.innerHTML = '<i class="icon-check"></i> Сохранить изменения';
    }
    closeModal(document.getElementById("modalPrescriptionDetails"));
    showModal(modal);
  }

  function confirmDeletePrescription(prescriptionId) {
    if (!confirm("Вы уверены, что хотите удалить этот препарат? Это действие нельзя отменить. Все записи о приёмах также будут удалены.")) return;
    deletePrescription(prescriptionId);
  }

  async function deletePrescription(prescriptionId) {
    try {
      var response = await fetchWithAuth(ENDPOINTS.medicationById(prescriptionId), { method: "DELETE" });
      if (!response.ok) throw new Error("Не удалось удалить препарат");
      showToast("Препарат удалён", "success");
      closeModal(document.getElementById("modalPrescriptionDetails"));
      await loadActivePrescriptions();
    } catch (err) {
      console.error("Ошибка при удалении препарата:", err);
      showToast(err.message || "Ошибка при удалении", "error");
    }
  }

  function setupEventListeners() {
    var btnAddPrescription = document.getElementById("btnAddPrescription");
    if (btnAddPrescription) btnAddPrescription.addEventListener("click", openAddPrescriptionModal);
    var formAddPrescription = document.getElementById("formAddPrescription");
    if (formAddPrescription) formAddPrescription.addEventListener("submit", submitAddPrescription);
    var btnCancelAddPrescription = document.getElementById("btnCancelAddPrescription");
    if (btnCancelAddPrescription) btnCancelAddPrescription.addEventListener("click", function () { closeModal(document.getElementById("modalAddPrescription")); });

    var btnAdd = document.getElementById("btnAddIntake");
    if (btnAdd) btnAdd.addEventListener("click", openAddIntakeModal);

    var formAdd = document.getElementById("formAddIntake");
    if (formAdd) formAdd.addEventListener("submit", submitAddIntake);

    var btnCancel = document.getElementById("btnCancelIntake");
    if (btnCancel) btnCancel.addEventListener("click", function () { closeModal(document.getElementById("modalAddIntake")); });

    var selectPrescription = document.getElementById("selectPrescription");
    if (selectPrescription) selectPrescription.addEventListener("change", function () { handlePrescriptionSelect(this.value); });

    var actualDose = document.getElementById("actualDose");
    if (actualDose) actualDose.addEventListener("input", validateDose);

    var intakeNotes = document.getElementById("intakeNotes");
    if (intakeNotes) {
      intakeNotes.addEventListener("input", function () {
        var countEl = document.getElementById("notesCharCount");
        if (countEl) countEl.textContent = this.value.length;
      });
    }

    var detailsContent = document.getElementById("detailsContent");
    if (detailsContent) detailsContent.addEventListener("click", onDetailsContentClick);

    var btnCloseDetails = document.getElementById("btnCloseDetails");
    if (btnCloseDetails) btnCloseDetails.addEventListener("click", function () { closeModal(document.getElementById("modalPrescriptionDetails")); });

    document.querySelectorAll(".modal-close").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var modal = this.closest(".modal");
        if (modal) closeModal(modal);
      });
    });
    document.querySelectorAll(".modal-backdrop").forEach(function (backdrop) {
      backdrop.addEventListener("click", function () {
        var modal = this.closest(".modal");
        if (modal) closeModal(modal);
      });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        var openModal = document.querySelector(".modal[style*='display: block']");
        if (openModal) closeModal(openModal);
      }
    });
  }

  function showModal(modal) {
    if (!modal) return;
    modal.style.display = "block";
    document.body.style.overflow = "hidden";
    modal.setAttribute("aria-hidden", "false");
  }

  function closeModal(modal) {
    if (!modal) return;
    modal.style.display = "none";
    document.body.style.overflow = "";
    modal.setAttribute("aria-hidden", "true");
  }

  function showToast(message, type) {
    type = type || "info";
    var container = document.getElementById("toastContainer");
    if (!container) return;
    var toast = document.createElement("div");
    toast.className = "toast toast-" + type;
    var iconMap = { success: "icon-check-circle", error: "icon-alert-circle", warning: "icon-alert-triangle", info: "icon-info-circle" };
    var icon = iconMap[type] || "icon-info-circle";
    toast.innerHTML =
      '<i class="' + icon + '"></i>' +
      "<span>" + escapeHtml(message) + "</span>" +
      '<button type="button" class="toast-close" aria-label="Закрыть"><i class="icon-close"></i></button>';
    toast.querySelector(".toast-close").addEventListener("click", function () { toast.remove(); });
    container.appendChild(toast);
    setTimeout(function () {
      toast.style.animation = "toast-slideOut 0.3s ease";
      setTimeout(function () { toast.remove(); }, 300);
    }, 5000);
  }

  function formatDate(dateStr) {
    if (!dateStr) return "";
    var date = new Date(dateStr);
    var d = String(date.getDate()).padStart(2, "0");
    var m = String(date.getMonth() + 1).padStart(2, "0");
    var y = date.getFullYear();
    return d + "." + m + "." + y;
  }

  function formatDateTime(datetimeStr) {
    if (!datetimeStr) return "";
    var date = new Date(datetimeStr);
    var d = String(date.getDate()).padStart(2, "0");
    var m = String(date.getMonth() + 1).padStart(2, "0");
    var y = date.getFullYear();
    var h = String(date.getHours()).padStart(2, "0");
    var min = String(date.getMinutes()).padStart(2, "0");
    return d + "." + m + "." + y + " " + h + ":" + min;
  }

  function formatDateForInput(date) {
    var y = date.getFullYear();
    var m = String(date.getMonth() + 1).padStart(2, "0");
    var d = String(date.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + d;
  }

  function formatTimeForInput(date) {
    var h = String(date.getHours()).padStart(2, "0");
    var min = String(date.getMinutes()).padStart(2, "0");
    return h + ":" + min;
  }

  function escapeHtml(text) {
    if (text == null) return "";
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  window.showPrescriptionDetails = showPrescriptionDetails;
  window.editIntake = editIntake;
  window.confirmDeleteIntake = confirmDeleteIntake;
  window.editPrescription = editPrescription;
  window.confirmDeletePrescription = confirmDeletePrescription;
  window.deletePrescription = deletePrescription;
})();
