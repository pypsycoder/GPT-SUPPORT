(function () {
    function initGlobalHeader() {
        const container = document.getElementById('global-header');
        if (!container) return;

        fetch('/frontend/patient/components/global_header.html')
            .then(r => r.text())
            .then(html => {
                container.innerHTML = html;
                initReportModal();
            })
            .catch(err =>
                console.error('Global header load failed:', err)
            );
    }

    function initReportModal() {
        const overlay = document.getElementById('reportModal');
        if (!overlay) return;

        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closeReportModal();
        });
    }

    document.addEventListener('DOMContentLoaded', initGlobalHeader);
})();

function openReportModal() {
    document.getElementById('reportModal').classList.add('gh-modal-open');
    document.body.style.overflow = 'hidden';
}

function closeReportModal() {
    document.getElementById('reportModal').classList.remove('gh-modal-open');
    document.body.style.overflow = '';
}
