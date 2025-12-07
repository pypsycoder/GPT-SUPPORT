(function () {
  // # получаем patient_token из URL (/p/{token}/...)
  function sidebarGetPatientTokenFromPath() {
    const parts = window.location.pathname.split('/').filter(Boolean);
    const pIndex = parts.indexOf('p');
    if (pIndex !== -1 && parts.length > pIndex + 1) {
      return parts[pIndex + 1];
    }
    return null;
  }

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
      bodyPage === 'education_test' ? 'education' : bodyPage;

    const items = root.querySelectorAll('.sidebar-item[data-section]');
    const patientToken = sidebarGetPatientTokenFromPath();

    items.forEach((item) => {
      const section = item.getAttribute('data-section');

      if (section === normalizedPage) {
        item.classList.add('active');
      }

      item.addEventListener('click', () => {
        let targetUrl = null;

        if (section === 'vitals') {
          targetUrl = patientToken
            ? `/p/${encodeURIComponent(patientToken)}/vitals`
            : '/frontend/patient/vitals.html';
        }
        else if (section === 'education') {
          // ✅ Обновлено: "Обучение" ведёт на навигатор education_overview
          targetUrl = patientToken
            ? `/p/${encodeURIComponent(patientToken)}/education_overview`
            : '/frontend/patient/education_overview.html';
        }

        if (targetUrl && targetUrl !== window.location.pathname + window.location.search) {
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
