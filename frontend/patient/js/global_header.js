(function () {
    function initGlobalHeader() {
        const container = document.getElementById('global-header');
        if (!container) return;

        fetch('/frontend/patient/components/global_header.html')
            .then(r => r.text())
            .then(html => {
                container.innerHTML = html;
            })
            .catch(err =>
                console.error('Global header load failed:', err)
            );
    }

    document.addEventListener('DOMContentLoaded', initGlobalHeader);
})();
