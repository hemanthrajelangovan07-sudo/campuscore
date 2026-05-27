// ─── Mobile sidebar toggle ────────────────────────────────────────────────────
const menuToggle = document.getElementById('menuToggle');
const sidebar = document.getElementById('sidebar');

if (menuToggle && sidebar) {
  menuToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });
  document.addEventListener('click', (e) => {
    if (!sidebar.contains(e.target) && !menuToggle.contains(e.target)) {
      sidebar.classList.remove('open');
    }
  });
}

// ─── Notifications ────────────────────────────────────────────────────────────
const notifBtn = document.getElementById('notifBtn');
const notifWrapper = document.querySelector('.notif-wrapper');
const notifList = document.getElementById('notifList');
const notifCount = document.getElementById('notifCount');

if (notifBtn) {
  notifBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    notifWrapper.classList.toggle('open');
    if (notifWrapper.classList.contains('open')) {
      loadNotifications();
    }
  });
  document.addEventListener('click', () => {
    notifWrapper?.classList.remove('open');
  });
}

async function loadNotifications() {
  try {
    const res = await fetch('/api/notifications');
    const notes = await res.json();
    if (notifList) {
      if (notes.length === 0) {
        notifList.innerHTML = '<p class="notif-empty">No new notifications</p>';
      } else {
        notifList.innerHTML = notes.map(n =>
          `<div class="notif-item ${n.type}">${n.msg}</div>`
        ).join('');
        notifCount.textContent = notes.length;
        notifCount.style.display = notes.length > 0 ? 'flex' : 'none';
      }
    }
  } catch (e) {
    if (notifList) notifList.innerHTML = '<p class="notif-empty">Could not load notifications</p>';
  }
}

// ─── Auto-dismiss flash messages ─────────────────────────────────────────────
document.querySelectorAll('.flash').forEach(el => {
  setTimeout(() => {
    el.style.transition = 'opacity 0.5s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 500);
  }, 5000);
});

// ─── Form validation ──────────────────────────────────────────────────────────
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', (e) => {
    const required = form.querySelectorAll('[required]');
    const errors = [];
    const errorContainer = document.getElementById('form-errors');
    const errorList = document.getElementById('error-list');

    if (errorContainer) errorContainer.style.display = 'none';
    if (errorList) errorList.innerHTML = '';

    required.forEach(field => {
      if (field.offsetParent === null) return;
      field.style.borderColor = '';
    });

    let valid = true;
    required.forEach(field => {
      if (field.offsetParent === null) return;
      if (!field.value.trim()) {
        field.style.borderColor = '#dc2626';
        valid = false;
        const label = field.closest('.form-group')?.querySelector('label')?.textContent?.replace(' *', '') || field.name;
        const msg = `${label} is required.`;
        if (!errors.includes(msg)) errors.push(msg);
        field.addEventListener('input', () => {
          field.style.borderColor = '';
        }, { once: true });
      }
    });

    if (!valid) {
      e.preventDefault();
      if (errorContainer && errorList) {
        errorList.innerHTML = errors.map(e => `<li>${e}</li>`).join('');
        errorContainer.style.display = 'block';
        errorContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });
});

// ─── Animate stat cards ───────────────────────────────────────────────────────
document.querySelectorAll('.stat-value').forEach(el => {
  const target = parseInt(el.textContent) || 0;
  if (target === 0) return;
  let current = 0;
  const step = Math.max(1, Math.floor(target / 40));
  const timer = setInterval(() => {
    current = Math.min(current + step, target);
    el.textContent = current;
    if (current >= target) clearInterval(timer);
  }, 30);
});
