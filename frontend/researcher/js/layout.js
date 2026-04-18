(function () {
  "use strict";

  var BUG_REPORTS_URL = "https://docs.google.com/forms/d/1qZi20ChV8GG_HDKbE8y9Rj4CkARoPLunacBhKaJ8wl8/edit#responses";

  function navLink(href, label, isActive, extraAttrs) {
    return '<a href="' + href + '" class="r-nav-btn' + (isActive ? ' active' : '') + '"' + (extraAttrs || "") + ">" + label + "</a>";
  }

  function navButton(tab, label, isActive) {
    return '<button type="button" class="r-nav-btn' + (isActive ? ' active' : '') + '" data-tab="' + tab + '">' + label + "</button>";
  }

  function renderDashboardNav(activeTab) {
    return [
      navButton("dashboard", "Обзор", activeTab === "dashboard"),
      navButton("patients", "Пациенты", activeTab === "patients"),
      navLink("/researcher/centers", "Центры", false),
      navLink("/researcher/import/schedules", "Импорт расписаний", false),
      navLink("/researcher/chat-monitor", "Мониторинг чатов", false),
      navLink("/researcher/chat-debug", "Отладочный чат", false),
      navLink(BUG_REPORTS_URL, "Bug Reports", false, ' target="_blank" rel="noopener noreferrer"'),
    ].join("");
  }

  function renderStandardNav(activePage) {
    return [
      navLink("/researcher/dashboard", "Обзор", false),
      navLink("/researcher/dashboard#patients", "Пациенты", false),
      navLink("/researcher/centers", "Центры", activePage === "centers"),
      navLink("/researcher/import/schedules", "Импорт расписаний", activePage === "import_schedules"),
      navLink("/researcher/chat-monitor", "Мониторинг чатов", activePage === "chat_monitor"),
      navLink("/researcher/chat-debug", "Отладочный чат", activePage === "chat_debug"),
      navLink(BUG_REPORTS_URL, "Bug Reports", false, ' target="_blank" rel="noopener noreferrer"'),
    ].join("");
  }

  function renderResearcherNav() {
    var root = document.getElementById("r-shared-nav");
    if (!root) {
      return;
    }

    var page = root.dataset.page || "";
    var activeTab = root.dataset.activeTab || "dashboard";
    var html = page === "dashboard" ? renderDashboardNav(activeTab) : renderStandardNav(page);
    root.innerHTML = '<div class="r-nav">' + html + "</div>";
  }

  window.ResearcherLayout = {
    renderNav: renderResearcherNav,
  };

  renderResearcherNav();
})();
