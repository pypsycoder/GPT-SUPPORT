(function () {
  function initScaleButtons() {
    var scales = {
      hads:  '/patient/hads',
      kop25a: '/patient/kop25a',
      tobol: '/patient/tobol',
      psqi:  '/patient/psqi',
    };

    Object.keys(scales).forEach(function (code) {
      var btn = document.querySelector('[data-scale="' + code + '"]');
      if (btn && !btn.disabled) {
        btn.addEventListener('click', function () {
          window.location.href = scales[code];
        });
      }
    });
  }

  document.addEventListener('DOMContentLoaded', async function () {
    if (window.PatientAuth) {
      await window.PatientAuth.requireAuth();
    }
    initScaleButtons();
  });
})();
