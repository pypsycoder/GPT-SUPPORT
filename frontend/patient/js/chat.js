/**
 * chat.js — Chat Drawer Widget
 *
 * Sliding drawer поверх layout, открывается из sidebar.
 * Не требует подключения на каждой странице — загружается динамически из sidebar.js.
 *
 * Зависимости:
 *   - window.PatientAuth (из auth.js) — для получения patient_id
 *   - window.ChatDrawer.open() / close() — публичное API
 */
(function () {
  'use strict';

  // ============================================================
  // STATE
  // ============================================================

  var state = {
    patientId: null,
    historyLoaded: false,
    loading: false,
  };

  // Кэши DOM-ссылок
  var els = {
    backdrop: null,
    drawer: null,
    messages: null,
    textarea: null,
    sendBtn: null,
    quickActions: null,
  };

  var typingEl = null;

  // ============================================================
  // API HELPERS
  // ============================================================

  function apiFetch(url, method, body) {
    var opts = {
      method: method || 'GET',
      credentials: 'include',
      headers: {},
    };
    if (body) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(function (res) {
      if (!res.ok) {
        return res
          .json()
          .catch(function () { return { detail: 'HTTP ' + res.status }; })
          .then(function (err) { throw new Error(err.detail || 'Ошибка сервера'); });
      }
      if (res.status === 204) return null;
      return res.json();
    });
  }

  async function getPatientId() {
    if (state.patientId) return state.patientId;
    // Используем кэшированный результат из auth.js если доступен
    if (window.PatientAuth) {
      var user = await window.PatientAuth.fetchCurrentUser();
      if (user && user.id) {
        state.patientId = user.id;
        return state.patientId;
      }
    }
    // Fallback: прямой запрос
    var data = await apiFetch('/api/v1/auth/patient/me', 'GET');
    state.patientId = data.id;
    return state.patientId;
  }

  // ============================================================
  // DOM CREATION
  // ============================================================

  function createDrawer() {
    // --- Backdrop ---
    var backdrop = document.createElement('div');
    backdrop.id = 'chat-backdrop';
    backdrop.addEventListener('click', closeChatDrawer);
    document.body.appendChild(backdrop);

    // --- Drawer ---
    var drawer = document.createElement('div');
    drawer.id = 'chat-drawer';
    drawer.setAttribute('role', 'dialog');
    drawer.setAttribute('aria-modal', 'true');
    drawer.setAttribute('aria-label', 'Чат поддержки');

    drawer.innerHTML =
      '<div class="chat-drag-handle">' +
        '<div class="chat-drag-handle-bar"></div>' +
      '</div>' +

      '<div class="chat-header">' +
        '<div class="chat-header-title">🤖 Поддержка</div>' +
        '<button class="chat-close-btn" aria-label="Закрыть чат">×</button>' +
      '</div>' +

      '<div class="chat-messages" id="chat-messages"></div>' +

      '<div class="chat-quick-actions" id="chat-quick-actions">' +
        '<button class="chat-quick-btn" data-text="Как я себя чувствую">Как я себя чувствую</button>' +
        '<button class="chat-quick-btn" data-text="Сон">Сон</button>' +
        '<button class="chat-quick-btn" data-text="Таблетки">Таблетки</button>' +
        '<button class="chat-quick-btn" data-text="Давление">Давление</button>' +
        '<button class="chat-quick-btn" data-text="Настроение">Настроение</button>' +
      '</div>' +

      '<div class="chat-input-area">' +
        '<textarea' +
          ' class="chat-textarea"' +
          ' id="chat-textarea"' +
          ' placeholder="Напишите сообщение..."' +
          ' rows="1"' +
          ' aria-label="Сообщение"' +
        '></textarea>' +
        '<button class="chat-send-btn" id="chat-send-btn" aria-label="Отправить">' +
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"' +
            ' stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
            '<line x1="22" y1="2" x2="11" y2="13"></line>' +
            '<polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>' +
          '</svg>' +
        '</button>' +
      '</div>';

    document.body.appendChild(drawer);

    // --- Cache references ---
    els.backdrop = backdrop;
    els.drawer = drawer;
    els.messages = drawer.querySelector('#chat-messages');
    els.textarea = drawer.querySelector('#chat-textarea');
    els.sendBtn = drawer.querySelector('#chat-send-btn');
    els.quickActions = drawer.querySelector('#chat-quick-actions');

    // --- Events ---
    drawer.querySelector('.chat-close-btn').addEventListener('click', closeChatDrawer);

    els.sendBtn.addEventListener('click', function () {
      handleSend(els.textarea.value.trim(), 'text');
    });

    els.textarea.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend(els.textarea.value.trim(), 'text');
      }
    });

    els.textarea.addEventListener('input', function () {
      // Auto-resize: 1-3 строки
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 80) + 'px';
    });

    els.quickActions.querySelectorAll('.chat-quick-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        handleSend(this.getAttribute('data-text'), 'button');
      });
    });

    // Закрытие по Escape
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && drawer.classList.contains('chat-drawer--open')) {
        closeChatDrawer();
      }
    });
  }

  // ============================================================
  // UI HELPERS
  // ============================================================

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function appendMessage(role, text) {
    var div = document.createElement('div');
    div.className = 'chat-msg chat-msg--' + role;

    var bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    // \n → <br>, эмодзи отображаются как есть (текст не эскейпится для эмодзи)
    bubble.innerHTML = escapeHtml(text).replace(/\n/g, '<br>');

    div.appendChild(bubble);
    els.messages.appendChild(div);
    scrollToBottom();
    return div;
  }

  function showTyping() {
    if (typingEl) return;
    typingEl = document.createElement('div');
    typingEl.className = 'chat-msg chat-msg--assistant chat-typing-row';
    typingEl.innerHTML =
      '<div class="chat-typing">' +
        '<div class="chat-typing-dot"></div>' +
        '<div class="chat-typing-dot"></div>' +
        '<div class="chat-typing-dot"></div>' +
      '</div>';
    els.messages.appendChild(typingEl);
    scrollToBottom();
  }

  function hideTyping() {
    if (typingEl) {
      typingEl.remove();
      typingEl = null;
    }
  }

  function scrollToBottom() {
    els.messages.scrollTop = els.messages.scrollHeight;
  }

  function setDisabled(disabled) {
    state.loading = disabled;
    els.textarea.disabled = disabled;
    els.sendBtn.disabled = disabled;
    els.quickActions.querySelectorAll('.chat-quick-btn').forEach(function (btn) {
      btn.disabled = disabled;
    });
  }

  // ============================================================
  // CORE LOGIC
  // ============================================================

  async function handleSend(text, source) {
    if (!text || state.loading) return;

    // Очистить поле и сбросить высоту
    els.textarea.value = '';
    els.textarea.style.height = 'auto';

    // Сразу показать сообщение пользователя
    appendMessage('user', text);
    setDisabled(true);
    showTyping();

    try {
      var patientId = await getPatientId();
      var data = await apiFetch('/api/chat/message', 'POST', {
        patient_id: patientId,
        message: text,
        source: source,
      });
      hideTyping();
      appendMessage('assistant', data.response);
    } catch (err) {
      hideTyping();
      appendMessage('assistant', 'Что-то пошло не так, попробуй позже 🙏');
    } finally {
      setDisabled(false);
      els.textarea.focus();
    }
  }

  async function loadHistory() {
    if (state.historyLoaded) return;

    try {
      var patientId = await getPatientId();
      var messages = await apiFetch(
        '/api/chat/history/' + patientId + '?limit=20',
        'GET'
      );
      if (messages && messages.length > 0) {
        messages.forEach(function (m) {
          appendMessage(m.role, m.content);
        });
      }
    } catch (err) {
      // История — некритично, просто логируем
      console.warn('[ChatDrawer] History load failed:', err.message);
    } finally {
      // Не повторять загрузку даже при ошибке
      state.historyLoaded = true;
    }
  }

  // ============================================================
  // OPEN / CLOSE
  // ============================================================

  async function openChatDrawer() {
    if (!els.drawer) return;

    els.backdrop.classList.add('chat-backdrop--visible');
    els.drawer.classList.add('chat-drawer--open');

    // Блокируем скролл body на мобиле
    document.body.style.overflow = 'hidden';

    // Загружаем историю при первом открытии
    await loadHistory();

    // Фокус на поле ввода после анимации
    setTimeout(function () {
      if (els.textarea && !els.textarea.disabled) {
        els.textarea.focus();
      }
    }, 320);
  }

  function closeChatDrawer() {
    if (!els.drawer) return;

    els.backdrop.classList.remove('chat-backdrop--visible');
    els.drawer.classList.remove('chat-drawer--open');
    document.body.style.overflow = '';
  }

  // ============================================================
  // INIT
  // ============================================================

  function init() {
    // Не создавать повторно если уже инициализирован
    if (document.getElementById('chat-drawer')) return;

    createDrawer();

    // Публичное API
    window.ChatDrawer = {
      open: openChatDrawer,
      close: closeChatDrawer,
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
