(function () {
  'use strict';

  var patients = [];
  var transcript = [];

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

  function ensureSessionId() {
    var input = byId('dbg-session');
    if (!input.value.trim()) {
      input.value = 'researcher-debug-' + Date.now();
    }
    return input.value.trim();
  }

  function updateSessionPill() {
    var sessionId = ensureSessionId();
    var threadId = byId('dbg-thread').value.trim() || 'main';
    byId('dbg-session-pill').textContent = 'session: ' + sessionId + ' / thread: ' + threadId;
  }

  function selectedPatientId() {
    return Number(byId('dbg-patient').value || 0);
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

  function renderTranscript() {
    var root = byId('dbg-chat');
    if (!transcript.length) {
      root.innerHTML = '<div class="r-debug-empty">Здесь появится диалог исследователя с моделью от имени выбранного пациента.</div>';
      return;
    }
    root.innerHTML = transcript.map(function (item) {
      var meta = [];
      if (item.domain) meta.push('domain: ' + item.domain);
      if (item.request_type) meta.push('type: ' + item.request_type);
      if (item.model) meta.push('model: ' + item.model);
      if (item.actual_model_tier) meta.push('tier: ' + item.actual_model_tier);
      if (item.requested_model_tier && item.requested_model_tier !== item.actual_model_tier) {
        meta.push('requested: ' + item.requested_model_tier);
      }
      if (item.account_id) meta.push('account: ' + item.account_id);
      if (item.tokens_used != null) meta.push('tokens: ' + item.tokens_used);
      return (
        '<div class="r-debug-msg ' + item.role + '">' +
          escHtml(item.content) +
          (meta.length ? '<div class="r-debug-meta">' + escHtml(meta.join(' · ')) + '</div>' : '') +
        '</div>'
      );
    }).join('');
    root.scrollTop = root.scrollHeight;
  }

  function renderTrace(payload) {
    var root = byId('dbg-trace');
    var sections = payload.human_trace || [];
    var memoryBefore = payload.memory_before || [];
    var memoryAfter = payload.memory_after || [];
    var extras = '';

    if (memoryBefore.length || memoryAfter.length) {
      sections = sections.slice();
      sections.push({
        title: 'Снимок памяти',
        items: [
          'До ответа в ST-memory было записей: ' + memoryBefore.length + '.',
          'После ответа в ST-memory стало записей: ' + memoryAfter.length + '.'
        ],
      });
    }

    if (!sections.length) {
      root.innerHTML = '<div class="r-debug-empty">По этому ответу не пришёл trace.</div>';
      return;
    }

    if (payload.diagnostics_json) {
      extras =
        '<details>' +
          '<summary style="cursor:pointer;color:#1d4ed8;font-weight:600;">Показать raw diagnostics</summary>' +
          '<pre class="r-trace-json">' + escHtml(JSON.stringify(payload.diagnostics_json, null, 2)) + '</pre>' +
        '</details>';
    }

    root.innerHTML = sections.map(function (section) {
      var items = (section.items || []).map(function (item) {
        return '<li>' + escHtml(item) + '</li>';
      }).join('');
      return (
        '<div class="r-trace-section">' +
          '<div class="r-trace-title">' + escHtml(section.title || 'Trace') + '</div>' +
          '<ul class="r-trace-list">' + items + '</ul>' +
        '</div>'
      );
    }).join('') + extras;
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
        }),
      });
      var data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || 'Ошибка debug-чата');
      }
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
      renderTranscript();
      renderTrace(data);
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
      transcript = [];
      renderTranscript();
      byId('dbg-trace').innerHTML = '<div class="r-debug-empty">После отправки сообщения здесь появится разбор: что система поняла, какие агенты вызвала и что записала в память.</div>';
    });
    byId('dbg-session').addEventListener('input', updateSessionPill);
    byId('dbg-thread').addEventListener('input', updateSessionPill);
    byId('dbg-patient').addEventListener('change', updateSessionPill);
    await loadPatients();
    updateSessionPill();
  }

  init();
})();
