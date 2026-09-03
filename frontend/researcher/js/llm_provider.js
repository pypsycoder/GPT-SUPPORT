/**
 * Переключатель LLM-провайдера (Сбер ↔ Cloud.ru) для researcher-панели.
 *
 * Любой контейнер с атрибутом data-llm-provider на странице подхватывается
 * автоматически на DOMContentLoaded. Меняет активного провайдера чат-контура
 * на живой системе (эндпоинт /api/v1/researcher/llm-provider, значение
 * переживает рестарт через public.app_settings).
 */
(function () {
  'use strict';

  var API = '/api/v1/researcher/llm-provider';
  var LABELS = { sber: 'Сбер', cloudru: 'Cloud.ru' };

  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      if (k === 'class') el.className = attrs[k];
      else if (k === 'text') el.textContent = attrs[k];
      else el.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { el.appendChild(c); });
    return el;
  }

  function fmtWhen(iso) {
    if (!iso) return '';
    try {
      var d = new Date(iso);
      return d.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' });
    } catch (e) { return ''; }
  }

  function render(box, state, opts) {
    box.innerHTML = '';
    var configured = state.configured || [];
    var title = h('div', { class: 'llmp-title', text: opts.title || 'LLM-провайдер чата' });

    var seg = h('div', { class: 'llmp-seg' });
    ['sber', 'cloudru'].forEach(function (p) {
      var isActive = state.active === p;
      var isConfigured = configured.indexOf(p) !== -1;
      var btn = h('button', {
        type: 'button',
        class: 'llmp-btn' + (isActive ? ' is-active' : '') + (isConfigured ? '' : ' is-disabled'),
        text: LABELS[p] || p,
        title: isConfigured ? '' : 'нет ключа для ' + p,
      });
      if (isConfigured && !isActive) {
        btn.addEventListener('click', function () { switchTo(box, p, opts); });
      } else {
        btn.disabled = true;
      }
      seg.appendChild(btn);
    });

    var srcParts = [];
    srcParts.push(state.db_override ? 'сохранено в БД' : 'из окружения (' + state.env_default + ')');
    if (state.updated_by) {
      srcParts.push('менял: ' + state.updated_by + (state.updated_at ? ' · ' + fmtWhen(state.updated_at) : ''));
    }
    var meta = h('div', { class: 'llmp-meta', text: srcParts.join(' · ') });

    var msg = h('div', { class: 'llmp-msg', id: 'llmp-msg' });

    box.appendChild(title);
    box.appendChild(seg);
    box.appendChild(meta);
    box.appendChild(msg);
  }

  function flash(box, text, isError) {
    var msg = box.querySelector('#llmp-msg');
    if (!msg) return;
    msg.textContent = text;
    msg.className = 'llmp-msg' + (isError ? ' is-error' : ' is-ok');
    if (!isError) setTimeout(function () { if (msg) { msg.textContent = ''; msg.className = 'llmp-msg'; } }, 4000);
  }

  async function load(box, opts) {
    try {
      var resp = await fetch(API, { credentials: 'include' });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      render(box, await resp.json(), opts);
    } catch (e) {
      box.innerHTML = '';
      box.appendChild(h('div', { class: 'llmp-msg is-error', text: 'не удалось загрузить статус провайдера' }));
    }
  }

  async function switchTo(box, provider, opts) {
    if (!window.confirm('Переключить LLM-провайдера чата на «' + (LABELS[provider] || provider) + '»?')) return;
    flash(box, 'переключаю…', false);
    try {
      var resp = await fetch(API, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: provider }),
      });
      var data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || ('HTTP ' + resp.status));
      render(box, data, opts);
      flash(box, 'активен: ' + (LABELS[data.active] || data.active), false);
    } catch (e) {
      flash(box, 'ошибка: ' + e.message, true);
    }
  }

  function init() {
    var boxes = document.querySelectorAll('[data-llm-provider]');
    Array.prototype.forEach.call(boxes, function (box) {
      var opts = { title: box.getAttribute('data-title') || '' };
      box.classList.add('llmp-box');
      load(box, opts);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.LlmProvider = { reload: function () { init(); } };
})();
