(function () {
  function initScaleButtons() {
    var scales = {
      hads:        '/patient/hads',
      kop25a:      '/patient/kop25a',
      psqi:        '/patient/psqi',
      kdqol:       '/patient/kdqol',
      pss10:       '/patient/pss10',
      wcq_lazarus: '/patient/wcq_lazarus',
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
