/* ═══════════════════════════════════════════════════════════════
   Healthcare — Main JavaScript
   ═══════════════════════════════════════════════════════════════ */

// ─── Mobile Sidebar Toggle ────────────────────────────────────
function toggleSidebar() {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');
    if (!sidebar) return;

    var isOpen = sidebar.classList.contains('open');

    if (isOpen) {
        sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('active');
        document.body.style.overflow = '';
    } else {
        sidebar.classList.add('open');
        if (overlay) overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

// Close sidebar on outside click (mobile)
document.addEventListener('click', function(e) {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');
    if (!sidebar || !sidebar.classList.contains('open')) return;

    // Don't close if clicking inside sidebar
    if (sidebar.contains(e.target)) return;

    // Don't close if clicking the hamburger button
    var toggleBtn = e.target.closest('.menu-toggle');
    if (toggleBtn) return;

    // Close sidebar
    sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
    document.body.style.overflow = '';
});

// Close sidebar on window resize (if desktop)
window.addEventListener('resize', function() {
    if (window.innerWidth > 768) {
        var sidebar = document.getElementById('sidebar');
        var overlay = document.getElementById('sidebarOverlay');
        if (sidebar) sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('active');
        document.body.style.overflow = '';
    }
});

// ─── Auto-dismiss alerts after 5 seconds ──────────────────────
document.addEventListener('DOMContentLoaded', function() {
    var alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-8px)';
            alert.style.transition = 'all 0.3s ease';
            setTimeout(function() {
                alert.style.display = 'none';
            }, 300);
        }, 5000);
    });

    // ─── Animate stat cards on scroll ─────────────────────────
    var statCards = document.querySelectorAll('.stat-card');
    statCards.forEach(function(card, index) {
        card.style.animationDelay = (index * 80) + 'ms';
    });

    // ─── Active menu item highlight ───────────────────────────
    var currentPath = window.location.pathname;
    var menuItems = document.querySelectorAll('.menu-item');
    menuItems.forEach(function(item) {
        if (item.getAttribute('href') === currentPath) {
            item.classList.add('active');
        }
    });

    // ─── Smooth scroll for anchor links ───────────────────────
    document.querySelectorAll('a[href^="#"]').forEach(function(anchor) {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            var target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

    // ─── Table row click to view details (if data-href) ──────
    var clickableRows = document.querySelectorAll('tr[data-href]');
    clickableRows.forEach(function(row) {
        row.style.cursor = 'pointer';
        row.addEventListener('click', function() {
            window.location.href = this.getAttribute('data-href');
        });
    });

    // ─── Form validation styling ──────────────────────────────
    var formControls = document.querySelectorAll('.form-control');
    formControls.forEach(function(control) {
        control.addEventListener('blur', function() {
            if (this.value.trim() !== '') {
                this.style.borderColor = 'var(--primary-300)';
            }
        });
        control.addEventListener('focus', function() {
            this.style.borderColor = 'var(--primary-500)';
        });
    });

    // ─── Confirm before dangerous actions ─────────────────────
    var dangerButtons = document.querySelectorAll('[data-confirm]');
    dangerButtons.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            var message = this.getAttribute('data-confirm') || 'Are you sure?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });

    // ─── Notification bell animation ──────────────────────────
    var notifBell = document.querySelector('.notification-bell .dot');
    if (notifBell) {
        setInterval(function() {
            notifBell.style.animation = 'pulse 2s infinite';
        }, 100);
    }
});

// ─── Utility: Format currency ─────────────────────────────────
function formatCurrency(amount, currency) {
    currency = currency || 'PKR';
    return currency + ' ' + parseFloat(amount).toLocaleString('en-PK', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
    });
}

// ─── Utility: Format date ─────────────────────────────────────
function formatDate(dateStr) {
    var date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

// ─── Utility: Time ago ────────────────────────────────────────
function timeAgo(dateStr) {
    var date = new Date(dateStr);
    var now = new Date();
    var diff = Math.floor((now - date) / 1000);

    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + ' min ago';
    if (diff < 86400) return Math.floor(diff / 3600) + ' hr ago';
    if (diff < 604800) return Math.floor(diff / 86400) + ' days ago';
    return formatDate(dateStr);
}

// ─── Print functionality ──────────────────────────────────────
function printPage() {
    window.print();
}

// ─── Close sidebar on outside click (mobile) ─────────────────
document.addEventListener('click', function(e) {
    var sidebar = document.getElementById('sidebar');
    var toggle = document.querySelector('.menu-toggle');
    var overlay = document.getElementById('sidebarOverlay');

    if (sidebar && sidebar.classList.contains('open')) {
        if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {
            sidebar.classList.remove('open');
            if (overlay) overlay.classList.remove('active');
        }
    }
});

// ─── Keyboard shortcuts ───────────────────────────────────────
document.addEventListener('keydown', function(e) {
    // Escape to close sidebar
    if (e.key === 'Escape') {
        var sidebar = document.getElementById('sidebar');
        var overlay = document.getElementById('sidebarOverlay');
        if (sidebar) sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('active');
    }
});


// ─── Dark Mode Toggle ──────────────────────────────────────────
function toggleTheme() {
    var html = document.documentElement;
    var icon = document.getElementById('themeIcon');
    var currentTheme = html.getAttribute('data-theme');
    var newTheme = currentTheme === 'dark' ? 'light' : 'dark';

    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('healthcare-theme', newTheme);

    if (icon) {
        icon.className = newTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }
}

// Apply saved theme on page load
(function() {
    var savedTheme = localStorage.getItem('healthcare-theme');
    if (savedTheme) {
        document.documentElement.setAttribute('data-theme', savedTheme);
        var icon = document.getElementById('themeIcon');
        if (icon) {
            icon.className = savedTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
        }
    }
})();
