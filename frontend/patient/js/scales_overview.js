(function () {
  function getPatientTokenFromPath() {
    const parts = window.location.pathname.split('/').filter(Boolean);
    const pIndex = parts.indexOf('p');
    if (pIndex !== -1 && parts.length > pIndex + 1) {
      return parts[pIndex + 1];
    }
    return null;
  }

  function initScaleButtons() {
    const patientToken = getPatientTokenFromPath();

    const hadsButton = document.querySelector('[data-scale="hads"]');
    if (hadsButton) {
      hadsButton.addEventListener('click', () => {
        const target = patientToken
          ? `/p/${encodeURIComponent(patientToken)}/hads`
          : '/frontend/patient/hads.html';
        window.location.href = target;
      });
    }

    const kopButton = document.querySelector('[data-scale="kop25a"]');
    if (kopButton && !kopButton.disabled) {
      kopButton.addEventListener('click', () => {
        const target = patientToken
          ? `/p/${encodeURIComponent(patientToken)}/kop25a`
          : '/frontend/patient/kop25a.html';
        window.location.href = target;
      });
    }

    const tobolButton = document.querySelector('[data-scale="tobol"]');
    if (tobolButton && !tobolButton.disabled) {
      tobolButton.addEventListener('click', () => {
        const target = patientToken
          ? `/p/${encodeURIComponent(patientToken)}/tobol`
          : '/frontend/patient/tobol.html';
        window.location.href = target;
      });
    }
  }

  document.addEventListener('DOMContentLoaded', initScaleButtons);
})();
