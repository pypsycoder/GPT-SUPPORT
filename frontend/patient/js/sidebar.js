(function () {
  // # навигация: session-based URLs (/patient/...) с fallback на legacy (/p/{token}/...)
  var NAV_MAP = {
    dashboard:       '/patient/home',
    vitals:          '/patient/vitals',
    sleep_tracker:   '/patient/sleep_tracker',
    education:       '/patient/education_overview',
    hads:            '/patient/hads',
    scales_overview: '/patient/scales',
    profile:         '/patient/profile',
  };

  // # стартовое состояние: на маленьких экранах — узкий, на больших — широкий
  function sidebarApplyInitialState() {
    const isMobile = window.innerWidth < 768;
    if (isMobile) {
      document.body.classList.add('sidebar-collapsed');
    } else {
      document.body.classList.remove('sidebar-collapsed');
    }
  }

  // # переключение режимов по кнопке
  function sidebarToggleMode() {
    document.body.classList.toggle('sidebar-collapsed');
  }

  // # навигация по клику на пункты
  function sidebarInitNav(root) {
    const bodyPage = document.body.getAttribute('data-page') || '';
    const normalizedPage =
      bodyPage === 'education_test'
        ? 'education'
        : bodyPage === 'hads'
          ? 'scales_overview'
          : bodyPage;

    const items = root.querySelectorAll('.sidebar-item[data-section]');

    items.forEach((item) => {
      const section = item.getAttribute('data-section');

      if (section === normalizedPage || (section === 'dashboard' && normalizedPage === 'home')) {
        item.classList.add('active');
      }

      item.addEventListener('click', () => {
        var targetUrl = NAV_MAP[section] || null;
        if (targetUrl && targetUrl !== window.location.pathname) {
          window.location.href = targetUrl;
        }
      });
    });
  }

  // # инициализация кнопки сворачивания
  function sidebarInitCollapse(root) {
    const toggleBtn = root.querySelector('.sidebar-toggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', (event) => {
        event.preventDefault();
        sidebarToggleMode();
      });
    }

    // на ресайзе пересчитываем дефолтное состояние
    window.addEventListener('resize', () => {
      sidebarApplyInitialState();
    });
  }

  // # загрузка sidebar.html в контейнер
  function sidebarInit() {
    const rootContainer = document.getElementById('sidebar-container');
    if (!rootContainer) return;

    fetch('/frontend/patient/components/sidebar.html')
      .then((resp) => {
        if (!resp.ok) {
          throw new Error('Sidebar HTML load error: ' + resp.status);
        }
        return resp.text();
      })
      .then((html) => {
        rootContainer.innerHTML = html;

        const sidebarRoot = rootContainer.querySelector('.sidebar');
        if (!sidebarRoot) return;

        sidebarApplyInitialState();
        sidebarInitNav(rootContainer);
        sidebarInitCollapse(sidebarRoot);
      })
      .catch((err) => {
        console.error('Не удалось инициализировать сайдбар:', err);
      });
  }

  document.addEventListener('DOMContentLoaded', sidebarInit);
})();
