/**
 * KITT Web UI — Alpine.js components and HTMX configuration
 */

// Auto-scroll log panels to bottom
document.addEventListener('htmx:sseMessage', function(evt) {
    const logStream = document.getElementById('log-stream');
    if (logStream) {
        logStream.scrollTop = logStream.scrollHeight;
    }
});

// HTMX error handling
document.addEventListener('htmx:responseError', function(evt) {
    console.error('HTMX request failed:', evt.detail);
});

// Toast notification helper
function showToast(message, type) {
    type = type || 'info';
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'rounded-md p-3 text-sm mb-2 transition-opacity duration-500';

    if (type === 'error') {
        toast.className += ' bg-red-900/50 text-red-200 border border-red-700';
    } else if (type === 'success') {
        toast.className += ' bg-green-900/50 text-green-200 border border-green-700';
    } else {
        toast.className += ' bg-blue-900/50 text-blue-200 border border-blue-700';
    }

    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(function() {
        toast.style.opacity = '0';
        setTimeout(function() { toast.remove(); }, 500);
    }, 4000);
}
