(function () {
    function ensureFavicons() {
        const icons = [
            { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/frontend/patient/img/favicon-32.png' },
            { rel: 'icon', type: 'image/png', sizes: '16x16', href: '/frontend/patient/img/favicon-16.png' },
            { rel: 'apple-touch-icon', href: '/frontend/patient/img/apple-touch-icon.png' },
        ];
        icons.forEach(spec => {
            const sel = spec.sizes
                ? `link[rel="${spec.rel}"][sizes="${spec.sizes}"]`
                : `link[rel="${spec.rel}"]`;
            if (document.head.querySelector(sel)) return;
            const link = document.createElement('link');
            Object.entries(spec).forEach(([k, v]) => link.setAttribute(k, v));
            document.head.appendChild(link);
        });
    }

    function initGlobalHeader() {
        ensureFavicons();

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
