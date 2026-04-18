(function () {
  'use strict';

  var patients = [];
  var transcript = [];
  var currentSupervisorState = null;
  var turnSnapshots = [];

  function escHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function chatPlaceholderHtml() {
    return '<div class="r-debug-empty">Здесь появится поток ходов: фраза пациента, state до и после рядом, pipeline и затем фраза бота.</div>';
  }

  function ensureSessionId() {
    var input = byId('dbg-session');
    if (!input.value.trim()) {
      input.value = 'researcher-debug-' + Date.now();
    }
    return input.value.trim();
  }

  function assignFreshSessionId() {
    byId('dbg-session').value = 'researcher-debug-' + Date.now();
    updateSessionPill();
  }

  function updateSessionPill() {
    var sessionId = ensureSessionId();
    var threadId = byId('dbg-thread').value.trim() || 'main';
    byId('dbg-session-pill').textContent = 'session: ' + sessionId + ' / thread: ' + threadId;
  }

  function updateStateBadge(seedWasUsed) {
    var badge = byId('dbg-state-badge');
    if (!badge) return;
    if (seedWasUsed) {
      badge.className = 'r-debug-state-badge continued';
      badge.textContent = 'state continued';
      return;
    }
    badge.className = 'r-debug-state-badge fresh';
    badge.textContent = 'fresh state';
  }

  function selectedPatientId() {
    return Number(byId('dbg-patient').value || 0);
  }

  function selectedPatientLabel() {
    var select = byId('dbg-patient');
    if (!select || select.selectedIndex < 0) {
      return '';
    }
    return String(select.options[select.selectedIndex].text || '').trim();
  }

  function cloneJson(value) {
    return value ? JSON.parse(JSON.stringify(value)) : null;
  }

  function resetSupervisorState() {
    currentSupervisorState = null;
  }

  function resetDebugSession() {
    transcript = [];
    turnSnapshots = [];
    resetSupervisorState();
    renderTranscript();
    assignFreshSessionId();
    updateStateBadge(false);
  }

  function renderPatients() {
    var select = byId('dbg-patient');
    if (!patients.length) {
      select.innerHTML = '<option value="">Нет пациентов</option>';
      return;
    }
    select.innerHTML = patients.map(function (p) {
      var label = '#' + (p.patient_number || p.id) + ' ' + (p.full_name || 'Без имени');
      return '<option value="' + p.id + '">' + escHtml(label) + '</option>';
    }).join('');
  }

  function normalizeExportNumbers(rawValue) {
    var input = String(rawValue || '').trim();
    if (!input) {
      throw new Error('Укажите номера ходов для экспорта.');
    }

    var selected = {};

    input.split(',').forEach(function (chunk) {
      var token = String(chunk || '').trim();
      var rangeMatch;
      var start;
      var end;
      var step;
      var value;

      if (!token) return;

      rangeMatch = token.match(/^(\d+)\s*-\s*(\d+)$/);
      if (rangeMatch) {
        start = Number(rangeMatch[1]);
        end = Number(rangeMatch[2]);
        if (start < 1 || end < 1) {
          throw new Error('Номера ходов должны быть положительными.');
        }
        if (end < start) {
          throw new Error('В диапазоне конец не может быть меньше начала.');
        }
        for (step = start; step <= end; step += 1) {
          selected[step] = true;
        }
        return;
      }

      if (!/^\d+$/.test(token)) {
        throw new Error('Формат номеров должен быть таким: 1-2, 5, 8.');
      }

      value = Number(token);
      if (value < 1) {
        throw new Error('Номера ходов должны быть положительными.');
      }
      selected[value] = true;
    });

    return Object.keys(selected).map(function (item) {
      return Number(item);
    }).sort(function (left, right) {
      return left - right;
    });
  }

  function buildExportPayload(turnNumbers) {
    var selectedTurns = turnNumbers.map(function (turnNumber) {
      var turn = turnSnapshots[turnNumber - 1];
      if (!turn) {
        throw new Error('Ход ' + turnNumber + ' отсутствует в текущем логе.');
      }
      return {
        turn_number: turnNumber,
        user_message: turn.userMessage,
        assistant_reply: turn.assistantReply,
        domain: turn.domain || null,
        request_type: turn.requestType || null,
        model: turn.model || null,
        requested_model_tier: turn.requestedModelTier || null,
        actual_model_tier: turn.actualModelTier || null,
        account_id: turn.accountId || null,
        tokens_used: turn.tokensUsed,
        state_before: cloneJson(turn.stateBefore) || {},
        state_after: cloneJson(turn.stateAfter) || {},
        human_trace: cloneJson(turn.humanTrace) || [],
        diagnostics_json: cloneJson(turn.diagnosticsJson) || null,
        raw_debug_response: cloneJson(turn.rawDebugResponse) || null,
      };
    });

    return {
      exported_at: new Date().toISOString(),
      export_scope: turnNumbers.length === turnSnapshots.length ? 'all' : 'selected',
      selected_turns: turnNumbers,
      patient_id: selectedPatientId(),
      patient_label: selectedPatientLabel(),
      session_id: ensureSessionId(),
      thread_id: byId('dbg-thread').value.trim() || 'main',
      forced_model_tier: byId('dbg-tier').value || null,
      persist_messages: Boolean(byId('dbg-persist').checked),
      current_supervisor_state: cloneJson(currentSupervisorState),
      transcript: cloneJson(transcript) || [],
      turns: selectedTurns,
    };
  }

  function resolveTurnNumbers(mode) {
    if (!turnSnapshots.length) {
      throw new Error('Пока нечего экспортировать: в чате нет завершенных ходов.');
    }

    if (mode === 'selected') {
      return normalizeExportNumbers(byId('dbg-export-turns').value);
    }

    return turnSnapshots.map(function (_turn, index) {
      return index + 1;
    });
  }

  function downloadExportPayload(payload) {
    var sessionId = ensureSessionId().replace(/[^a-zA-Z0-9_-]+/g, '_');
    var turnsLabel = payload.export_scope === 'all'
      ? 'all'
      : payload.selected_turns.join('-');
    var fileName = 'researcher-chat-debug-' + sessionId + '-turns-' + turnsLabel + '.json';
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');

    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  async function readResponsePayload(resp) {
    var rawText = await resp.text();
    var trimmed = String(rawText || '').trim();

    if (!trimmed) {
      return {};
    }

    try {
      return JSON.parse(trimmed);
    } catch (_err) {
      return { detail: trimmed };
    }
  }

  function buildErrorMessage(data) {
    if (!data) return 'Ошибка debug-чата';
    if (typeof data.detail === 'string' && data.detail.trim()) return data.detail.trim();
    if (typeof data.error === 'string' && data.error.trim()) return data.error.trim();
    if (typeof data.message === 'string' && data.message.trim()) return data.message.trim();
    return 'Ошибка debug-чата';
  }

  async function saveExportPayloadToProject(payload) {
    var resp = await fetch('/api/v1/researcher/chat-debug/save-report', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_data: payload,
      }),
    });
    var data = await readResponsePayload(resp);

    if (!resp.ok) {
      throw new Error(data.detail || data.error || 'Не удалось сохранить отчет в проект.');
    }

    return data;
  }

  function exportTurns(mode) {
    var turnNumbers;
    var payload;
    try {
      turnNumbers = resolveTurnNumbers(mode);
      payload = buildExportPayload(turnNumbers);
      downloadExportPayload(payload);
    } catch (err) {
      window.alert(err && err.message ? err.message : String(err));
    }
  }

  async function saveTurnsToProject(mode) {
    var turnNumbers;
    var payload;
    var result;

    try {
      turnNumbers = resolveTurnNumbers(mode);
      payload = buildExportPayload(turnNumbers);
      result = await saveExportPayloadToProject(payload);
      window.alert('Лог сохранен в проект: ' + result.relative_path);
    } catch (err) {
      window.alert(err && err.message ? err.message : String(err));
    }
  }

  function stringifyMeta(turn) {
    var meta = [];
    if (turn.domain) meta.push('domain: ' + turn.domain);
    if (turn.requestType) meta.push('type: ' + turn.requestType);
    if (turn.model) meta.push('model: ' + turn.model);
    if (turn.actualModelTier) meta.push('tier: ' + turn.actualModelTier);
    if (turn.requestedModelTier && turn.requestedModelTier !== turn.actualModelTier) {
      meta.push('requested: ' + turn.requestedModelTier);
    }
    if (turn.accountId) meta.push('account: ' + turn.accountId);
    if (turn.tokensUsed != null) meta.push('tokens: ' + turn.tokensUsed);
    return meta;
  }

  function getRouterCard(diagnosticsJson) {
    var diagnostics = diagnosticsJson || {};
    var supervisor = diagnostics.supervisor || {};
    var goalAnalysis = supervisor.goal_analysis || {};
    return goalAnalysis.router_card || null;
  }

  function getGraphPath(diagnosticsJson) {
    var diagnostics = diagnosticsJson || {};
    var supervisor = diagnostics.supervisor || {};
    var graphPath = supervisor.graph_path || [];
    return Array.isArray(graphPath) ? graphPath : [];
  }

  function formatLlmDebugLines(title, payload) {
    var block = payload || {};
    var llm = block.llm || {};
    var lines = [];
    var failures = Array.isArray(llm.failures) ? llm.failures : [];

    if (!Object.keys(llm).length) {
      return lines;
    }

    lines.push('<div><strong>' + escHtml(title + ' attempts:') + '</strong> ' + escHtml(String(llm.attempts_total || '-')) + '</div>');
    if (llm.succeeded_on_attempt) {
      lines.push('<div><strong>' + escHtml(title + ' succeeded on:') + '</strong> ' + escHtml(String(llm.succeeded_on_attempt)) + '</div>');
    }
    if (failures.length) {
      lines.push('<div><strong>' + escHtml(title + ' retries:') + '</strong> ' + escHtml(String(failures.length)) + '</div>');
    }
    failures.forEach(function (failure) {
      var text = (failure.error_type || 'Error') + (failure.error_message ? ' - ' + failure.error_message : '');
      if (failure.raw_excerpt) {
        text += ' | raw: ' + failure.raw_excerpt;
      }
      lines.push(
        '<div><strong>' + escHtml(title + ' error #' + (failure.attempt || '?') + ':') + '</strong> ' +
        escHtml(text) +
        '</div>'
      );
    });
    return lines;
  }

  function renderRouterCard(turn) {
    var diagnostics = turn.diagnosticsJson || {};
    var routerCard = getRouterCard(diagnostics);
    var graphPath = getGraphPath(diagnostics);
    var supervisor = diagnostics.supervisor || {};
    var selectedAgents = supervisor.selected_agents || [];
    var summary = [];
    var details = [];

    if (!routerCard && !graphPath.length) {
      return '';
    }

    if (routerCard && routerCard.phase) summary.push('фаза: ' + routerCard.phase);
    if (routerCard && routerCard.status) summary.push('статус: ' + routerCard.status);
    if (routerCard && routerCard.next_action) summary.push('действие: ' + routerCard.next_action);
    if (selectedAgents.length) summary.push('агенты: ' + selectedAgents.join(', '));
    if (!summary.length && graphPath.length) summary.push('graph path: ' + graphPath.join(' -> '));

    if (routerCard) {
      if (routerCard.problem) details.push('<div><strong>Проблема:</strong> ' + escHtml(routerCard.problem) + '</div>');
      if (routerCard.context) details.push('<div><strong>Контекст:</strong> ' + escHtml(routerCard.context) + '</div>');
      if (routerCard.intention) details.push('<div><strong>Намерение:</strong> ' + escHtml(routerCard.intention) + '</div>');
      if (routerCard.phase) details.push('<div><strong>Фаза:</strong> ' + escHtml(routerCard.phase) + '</div>');
      if (routerCard.status) details.push('<div><strong>Статус:</strong> ' + escHtml(routerCard.status) + '</div>');
      if (routerCard.next_action) details.push('<div><strong>Следующее действие:</strong> ' + escHtml(routerCard.next_action) + '</div>');
      if (routerCard.needs_clarification) details.push('<div><strong>Нужны уточнения:</strong> ' + escHtml(routerCard.needs_clarification) + '</div>');
      if (routerCard.needs_another_cycle) details.push('<div><strong>Нужен еще цикл:</strong> ' + escHtml(routerCard.needs_another_cycle) + '</div>');
      if (routerCard.rationale) details.push('<div><strong>Обоснование:</strong> ' + escHtml(routerCard.rationale) + '</div>');
      if (Array.isArray(routerCard.experts) && routerCard.experts.length) {
        details.push(
          '<div><strong>Эксперты:</strong><div class="r-router-experts">' +
          routerCard.experts.map(function (expert) {
            return (
              '<div class="r-router-expert">' +
                '<div><strong>' + escHtml(expert.expert || '-') + '</strong></div>' +
                '<div>задача: ' + escHtml(expert.task || '-') + '</div>' +
                '<div>контекст: ' + escHtml(expert.context || '-') + '</div>' +
              '</div>'
            );
          }).join('') +
          '</div></div>'
        );
      }
    }

    if (graphPath.length) {
      details.push('<div><strong>Graph path:</strong> ' + escHtml(graphPath.join(' -> ')) + '</div>');
    }

    return (
      '<details class="r-router-card" open>' +
        '<summary>Graph: ' + escHtml(summary.join(' | ')) + '</summary>' +
        '<div class="r-router-card-body">' + details.join('') + '</div>' +
      '</details>'
    );
  }

  function renderTranscript() {
    var root = byId('dbg-chat');
    var completedTurns = turnSnapshots.length;
    var pendingOnlyMessages = transcript.slice(completedTurns * 2);

    if (!completedTurns && !pendingOnlyMessages.length) {
      root.innerHTML = chatPlaceholderHtml();
      return;
    }

    root.innerHTML =
      turnSnapshots.map(function (turn, index) {
        var traceHtml = renderTraceSections(turn.humanTrace || [], turn.diagnosticsJson || {});
        var meta = stringifyMeta(turn);
        var routerCardHtml = renderRouterCard(turn);

        return (
          '<div class="r-turn-card">' +
            '<div class="r-turn-title">Ход ' + escHtml(String(index + 1)) + '</div>' +
            '<div class="r-debug-msg user">' + escHtml(turn.userMessage || '') + '</div>' +
            routerCardHtml +
            '<div class="r-turn-details">' +
              '<details class="r-collapsible">' +
                '<summary>State diff</summary>' +
                '<div class="r-collapsible-body">' +
                  renderStateDiffTable(turn.stateBefore || {}, turn.stateAfter || {}) +
                '</div>' +
              '</details>' +
              '<details class="r-collapsible">' +
                '<summary>Pipeline</summary>' +
                '<div class="r-collapsible-body">' +
                  traceHtml +
                '</div>' +
              '</details>' +
            '</div>' +
            '<div class="r-debug-msg assistant">' +
              escHtml(turn.assistantReply || '') +
              (meta.length ? '<div class="r-debug-meta">' + escHtml(meta.join(' В· ')) + '</div>' : '') +
            '</div>' +
          '</div>'
        );
      }).join('') +
      pendingOnlyMessages.map(function (item) {
        return '<div class="r-debug-msg ' + item.role + '">' + escHtml(item.content) + '</div>';
      }).join('');

    root.scrollTop = root.scrollHeight;
  }

  function collectChangedKeys(beforeState, afterState) {
    var keys = {};
    var allKeys = {};

    Object.keys(beforeState || {}).forEach(function (key) {
      allKeys[key] = true;
    });
    Object.keys(afterState || {}).forEach(function (key) {
      allKeys[key] = true;
    });

    Object.keys(allKeys).forEach(function (key) {
      var beforeValue = beforeState ? beforeState[key] : undefined;
      var afterValue = afterState ? afterState[key] : undefined;
      if (JSON.stringify(beforeValue) !== JSON.stringify(afterValue)) {
        keys[key] = true;
      }
    });

    return keys;
  }

  function valueLines(value) {
    if (value == null) {
      return ['-'];
    }
    if (Array.isArray(value)) {
      if (!value.length) {
        return ['[]'];
      }
      return value.map(function (item) {
        return stringifyScalar(item);
      });
    }
    if (typeof value === 'object') {
      var keys = Object.keys(value);
      if (!keys.length) {
        return ['{}'];
      }
      return keys.map(function (key) {
        return key + ': ' + stringifyScalar(value[key]);
      });
    }
    return [String(value)];
  }

  function stringifyScalar(value) {
    if (value == null) {
      return '-';
    }
    if (Array.isArray(value) || typeof value === 'object') {
      return JSON.stringify(value);
    }
    return String(value);
  }

  function flattenState(value, prefix, rows) {
    rows = rows || {};
    prefix = prefix || '';

    if (value == null || typeof value !== 'object' || Array.isArray(value)) {
      rows[prefix || 'value'] = valueLines(value);
      return rows;
    }

    var keys = Object.keys(value);
    if (!keys.length) {
      rows[prefix || 'value'] = ['{}'];
      return rows;
    }

    keys.forEach(function (key) {
      var nextPrefix = prefix ? prefix + '.' + key : key;
      var item = value[key];

      if (item != null && typeof item === 'object' && !Array.isArray(item)) {
        flattenState(item, nextPrefix, rows);
        return;
      }

      rows[nextPrefix] = valueLines(item);
    });

    return rows;
  }

  function renderStateDiffTable(beforeState, afterState) {
    var beforeRows = flattenState(beforeState || {});
    var afterRows = flattenState(afterState || {});
    var changedKeys = collectChangedKeys(beforeRows, afterRows);
    var allKeys = {};

    Object.keys(beforeRows).forEach(function (key) { allKeys[key] = true; });
    Object.keys(afterRows).forEach(function (key) { allKeys[key] = true; });

    var rowHtml = Object.keys(allKeys).sort().map(function (key) {
      var beforeLines = beforeRows[key] || ['-'];
      var afterLines = afterRows[key] || ['-'];
      var maxLines = Math.max(beforeLines.length, afterLines.length);
      var parts = [];

      for (var index = 0; index < maxLines; index += 1) {
        var beforeLine = beforeLines[index] != null ? beforeLines[index] : '';
        var afterLine = afterLines[index] != null ? afterLines[index] : '';
        var changedBefore = beforeLine !== afterLine;
        var changedAfter = beforeLine !== afterLine;

        parts.push(
          '<tr>' +
            '<td class="r-state-key' + (index > 0 ? ' continuation' : '') + '">' + escHtml(index === 0 ? key : 'в†і') + '</td>' +
            '<td class="r-state-value' + (changedBefore ? ' changed' : '') + '">' + escHtml(beforeLine || '-') + '</td>' +
            '<td class="r-state-value' + (changedAfter ? ' changed' : '') + '">' + escHtml(afterLine || '-') + '</td>' +
          '</tr>'
        );
      }

      return parts.join('');
    }).join('');

    return (
      '<table class="r-state-table">' +
        '<thead>' +
          '<tr>' +
            '<th class="r-state-key">Field</th>' +
            '<th class="r-state-value">State до</th>' +
            '<th class="r-state-value">State после</th>' +
          '</tr>' +
        '</thead>' +
        '<tbody>' + rowHtml + '</tbody>' +
      '</table>'
    );
  }

  function buildPipelineStages(diagnosticsJson) {
    var diagnostics = diagnosticsJson || {};
    var canonicalOrder = [
      'boundary_guard',
      'classification',
      'supervisor',
      'context',
      'intake',
      'orchestration',
      'validation',
      'memory_write'
    ];
    var stageByName = {};

    (diagnostics.stages || []).forEach(function (stage) {
      stageByName[String(stage.name || '')] = stage || {};
    });

    function effectiveStatus(name) {
      var stage = stageByName[name] || {};
      if (String(stage.status || '') === 'error') {
        return { label: 'error', className: 'error' };
      }
      if (name === 'context' && diagnostics.patient_context && diagnostics.patient_context.skipped) {
        return { label: 'skipped', className: 'skipped' };
      }
      if (name === 'intake' && diagnostics.intake && diagnostics.intake.skipped) {
        return { label: 'skipped', className: 'skipped' };
      }
      if (name === 'orchestration' && diagnostics.orchestration && diagnostics.orchestration.skipped) {
        return { label: 'skipped', className: 'skipped' };
      }
      if (name === 'validation' && diagnostics.validation && String(diagnostics.validation.status || '').indexOf('skipped') === 0) {
        return { label: 'skipped', className: 'skipped' };
      }
      if (Object.prototype.hasOwnProperty.call(stageByName, name)) {
        return { label: 'ok', className: 'active' };
      }
      return { label: 'not_run', className: 'skipped' };
    }

    return canonicalOrder.map(function (name) {
      var info = effectiveStatus(name);
      return {
        name: name,
        label: info.label,
        className: info.className,
      };
    });
  }

  function renderPipelineChain(diagnosticsJson) {
    var stages = buildPipelineStages(diagnosticsJson);
    return (
      '<div class="r-pipeline-chain">' +
        stages.map(function (stage, index) {
          var arrow = index < stages.length - 1 ? '<span class="r-pipeline-arrow">в†’</span>' : '';
          return (
            '<span class="r-pipeline-stage ' + escHtml(stage.className) + '">' +
              escHtml(stage.name) + ': ' + escHtml(stage.label) +
            '</span>' +
            arrow
          );
        }).join('') +
      '</div>'
    );
  }

  function renderTraceSections(sections, diagnosticsJson) {
    var visibleSections = (sections || []).filter(function (section) {
      var title = String((section && section.title) || '');
      return title !== 'Пайплайн' && title !== 'Понимание запроса';
    });

    var pipelineChain = renderPipelineChain(diagnosticsJson || {});
    if (!visibleSections.length) {
      return pipelineChain;
    }

    return pipelineChain + visibleSections.map(function (section) {
      var items = (section.items || []).map(function (item) {
        return '<li>' + escHtml(item) + '</li>';
      }).join('');

      return (
        '<div class="r-trace-section">' +
          '<div class="r-trace-title">' + escHtml(section.title || 'Trace') + '</div>' +
          '<ul class="r-trace-list">' + items + '</ul>' +
        '</div>'
      );
    }).join('');
  }

  // Graph v2 overrides. These definitions intentionally shadow legacy helpers above.
  function getRouterCard(diagnosticsJson) {
    var diagnostics = diagnosticsJson || {};
    var supervisor = diagnostics.supervisor || {};
    return supervisor || null;
  }

  function getGraphPath(diagnosticsJson) {
    var diagnostics = diagnosticsJson || {};
    var supervisor = diagnostics.supervisor || {};
    var graphPath = supervisor.graph_path || [];
    return Array.isArray(graphPath) ? graphPath : [];
  }

  function renderRouterCard(turn) {
    var diagnostics = turn.diagnosticsJson || {};
    var supervisor = getRouterCard(diagnostics) || {};
    var graphPath = getGraphPath(diagnostics);
    var intake = supervisor.intake || {};
    var delegation = supervisor.delegation || {};
    var expert = supervisor.expert || {};
    var intakeCard = intake.card || null;
    var delegationCard = delegation.card || null;
    var expertCard = expert.card || null;
    var selectedAgents = supervisor.selected_agents || [];
    var summary = [];
    var details = [];

    if (!intakeCard && !delegationCard && !expertCard && !graphPath.length) {
      return '';
    }

    if (intakeCard && intakeCard.problem) summary.push('проблема: ' + intakeCard.problem);
    if (intakeCard && intakeCard.needs_clarification) summary.push('уточнение: ' + intakeCard.needs_clarification);
    if (intakeCard && intakeCard.ready_to_delegate) summary.push('передать: ' + intakeCard.ready_to_delegate);
    if (delegationCard && delegationCard.expert) summary.push('эксперт: ' + delegationCard.expert);
    if (selectedAgents.length) summary.push('агенты: ' + selectedAgents.join(', '));
    if (!summary.length && graphPath.length) summary.push('graph path: ' + graphPath.join(' -> '));

    if (intakeCard) {
      if (intakeCard.problem) details.push('<div><strong>Проблема:</strong> ' + escHtml(intakeCard.problem) + '</div>');
      if (intakeCard.context) details.push('<div><strong>Контекст:</strong> ' + escHtml(intakeCard.context) + '</div>');
      if (intakeCard.needs_clarification) details.push('<div><strong>Нужно уточнение:</strong> ' + escHtml(intakeCard.needs_clarification) + '</div>');
      if (intakeCard.question) details.push('<div><strong>Вопрос:</strong> ' + escHtml(intakeCard.question) + '</div>');
      if (intakeCard.ready_to_delegate) details.push('<div><strong>Готово к передаче:</strong> ' + escHtml(intakeCard.ready_to_delegate) + '</div>');
      if (intakeCard.rationale) details.push('<div><strong>Обоснование:</strong> ' + escHtml(intakeCard.rationale) + '</div>');
      details = details.concat(formatLlmDebugLines('Intake', intake));
    }

    if (delegationCard) {
      details.push('<hr>');
      if (delegationCard.expert) details.push('<div><strong>Эксперт:</strong> ' + escHtml(delegationCard.expert) + '</div>');
      if (delegationCard.task) details.push('<div><strong>Задача:</strong> ' + escHtml(delegationCard.task) + '</div>');
      if (delegationCard.rationale) details.push('<div><strong>Обоснование делегации:</strong> ' + escHtml(delegationCard.rationale) + '</div>');
      details = details.concat(formatLlmDebugLines('Delegation', delegation));
    }

    if (expertCard) {
      details.push('<hr>');
      if (expertCard.support) details.push('<div><strong>Поддержка:</strong> ' + escHtml(expertCard.support) + '</div>');
      if (expertCard.step_now) details.push('<div><strong>Шаг сейчас:</strong> ' + escHtml(expertCard.step_now) + '</div>');
      if (expertCard.follow_up) details.push('<div><strong>Уточнение после помощи:</strong> ' + escHtml(expertCard.follow_up) + '</div>');
      if (expertCard.needs_more_info) details.push('<div><strong>Нужно ли уточнение:</strong> ' + escHtml(expertCard.needs_more_info) + '</div>');
      if (expertCard.rationale) details.push('<div><strong>Обоснование эксперта:</strong> ' + escHtml(expertCard.rationale) + '</div>');
      details = details.concat(formatLlmDebugLines('Expert', expert));
    }

    if (graphPath.length) {
      details.push('<div><strong>Graph path:</strong> ' + escHtml(graphPath.join(' -> ')) + '</div>');
    }

    return (
      '<details class="r-router-card" open>' +
        '<summary>Graph: ' + escHtml(summary.join(' | ')) + '</summary>' +
        '<div class="r-router-card-body">' + details.join('') + '</div>' +
      '</details>'
    );
  }

  function isPlainEnter(event) {
    var isEnter = event.key === 'Enter' || event.code === 'Enter' || event.keyCode === 13;
    if (!isEnter) return false;
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return false;
    if (event.isComposing) return false;
    return true;
  }

  async function loadPatients() {
    var resp = await fetch('/api/v1/researcher/patients', { credentials: 'include' });
    if (!resp.ok) {
      throw new Error('Не удалось загрузить пациентов');
    }
    patients = await resp.json();
    renderPatients();
  }

  async function sendMessage() {
    var messageEl = byId('dbg-message');
    var message = messageEl.value.trim();
    var stateBefore = cloneJson(currentSupervisorState) || {};

    if (!message) return;

    updateSessionPill();
    var sessionId = ensureSessionId();
    var threadId = byId('dbg-thread').value.trim() || 'main';
    var patientId = selectedPatientId();
    var persistMessages = byId('dbg-persist').checked;
    var forcedModelTier = byId('dbg-tier').value || null;
    var sendBtn = byId('dbg-send');

    transcript.push({ role: 'user', content: message });
    renderTranscript();
    messageEl.value = '';
    sendBtn.disabled = true;
    sendBtn.textContent = 'Отправка...';

    try {
      var resp = await fetch('/api/v1/researcher/chat-debug/message', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_id: patientId,
          message: message,
          forced_model_tier: forcedModelTier,
          session_id: sessionId,
          thread_id: threadId,
          persist_messages: persistMessages,
          supervisor_state: currentSupervisorState,
        }),
      });
      var data = await readResponsePayload(resp);

      if (!resp.ok) {
        var errorMessage = buildErrorMessage(data);
        currentSupervisorState = data.supervisor_state || currentSupervisorState || null;

        transcript.push({
          role: 'assistant',
          content: data.response || ('Ошибка debug-чата: ' + errorMessage),
        });

        turnSnapshots.push({
          userMessage: message,
          assistantReply: data.response || ('Ошибка debug-чата: ' + errorMessage),
          domain: data.domain || null,
          requestType: data.request_type || null,
          model: data.model || null,
          requestedModelTier: data.requested_model_tier || null,
          actualModelTier: data.actual_model_tier || null,
          accountId: data.account_id || null,
          tokensUsed: data.tokens_used || 0,
          stateBefore: stateBefore,
          stateAfter: cloneJson(data.supervisor_state) || cloneJson(stateBefore) || {},
          humanTrace: cloneJson(data.human_trace) || [],
          diagnosticsJson: cloneJson(data.diagnostics_json) || null,
          rawDebugResponse: cloneJson(data) || null,
        });

        renderTranscript();
        return;
      }

      currentSupervisorState = data.supervisor_state || null;
      updateStateBadge(Boolean(
        data &&
        data.diagnostics_json &&
        data.diagnostics_json.classify &&
        data.diagnostics_json.classify.supervisor_state_seeded
      ));

      transcript.push({
        role: 'assistant',
        content: data.response,
        domain: data.domain,
        request_type: data.request_type,
        model: data.model,
        requested_model_tier: data.requested_model_tier,
        actual_model_tier: data.actual_model_tier,
        account_id: data.account_id,
        tokens_used: data.tokens_used,
      });

      turnSnapshots.push({
        userMessage: message,
        assistantReply: data.response,
        domain: data.domain,
        requestType: data.request_type,
        model: data.model,
        requestedModelTier: data.requested_model_tier,
        actualModelTier: data.actual_model_tier,
        accountId: data.account_id,
        tokensUsed: data.tokens_used,
        stateBefore: stateBefore,
        stateAfter: cloneJson(data.supervisor_state) || {},
        humanTrace: cloneJson(data.human_trace) || [],
        diagnosticsJson: cloneJson(data.diagnostics_json) || null,
        rawDebugResponse: cloneJson(data) || null,
      });

      renderTranscript();
    } catch (err) {
      transcript.push({
        role: 'assistant',
        content: 'Ошибка debug-чата: ' + (err && err.message ? err.message : String(err)),
      });
      renderTranscript();
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = 'Отправить';
    }
  }

  async function init() {
    var me = await window.ResearcherAuth.requireAuth();
    byId('r-user-name').textContent = me.full_name || me.username || 'Исследователь';
    byId('r-logout-btn').addEventListener('click', function () {
      window.ResearcherAuth.logout();
    });
    byId('dbg-send').addEventListener('click', sendMessage);
    byId('dbg-clear').addEventListener('click', function () {
      resetDebugSession();
    });
    byId('dbg-export-all-btn').addEventListener('click', function () {
      byId('dbg-export-all').checked = true;
      exportTurns('all');
    });
    byId('dbg-export-selected-btn').addEventListener('click', function () {
      byId('dbg-export-selected').checked = true;
      exportTurns('selected');
    });
    byId('dbg-save-all-btn').addEventListener('click', function () {
      byId('dbg-export-all').checked = true;
      saveTurnsToProject('all');
    });
    byId('dbg-save-selected-btn').addEventListener('click', function () {
      byId('dbg-export-selected').checked = true;
      saveTurnsToProject('selected');
    });
    byId('dbg-export-turns').addEventListener('focus', function () {
      byId('dbg-export-selected').checked = true;
    });
    byId('dbg-session').addEventListener('input', function () {
      resetSupervisorState();
      turnSnapshots = [];
      renderTranscript();
      updateSessionPill();
      updateStateBadge(false);
    });
    byId('dbg-thread').addEventListener('input', function () {
      resetSupervisorState();
      turnSnapshots = [];
      renderTranscript();
      updateSessionPill();
      updateStateBadge(false);
    });
    byId('dbg-patient').addEventListener('change', function () {
      resetDebugSession();
      updateSessionPill();
    });
    byId('dbg-message').addEventListener('keydown', function (event) {
      if (!isPlainEnter(event)) return;
      event.preventDefault();
      event.stopPropagation();
      sendMessage();
    });

    await loadPatients();
    renderTranscript();
    updateStateBadge(false);
    updateSessionPill();
  }

  init();
})();

