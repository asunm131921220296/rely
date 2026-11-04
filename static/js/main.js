document.addEventListener('DOMContentLoaded', () => {
  const toasts = document.querySelectorAll('.toast');
  toasts.forEach((toast) => {
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-4px)';
      toast.style.transition = 'all 0.25s ease';
    }, 2800);
  });

  const confirmTargets = document.querySelectorAll('[data-confirm="logout"]');
  confirmTargets.forEach((button) => {
    button.addEventListener('click', (event) => {
      const confirmed = window.confirm('Are you sure you want to log out?');
      if (!confirmed) {
        event.preventDefault();
      }
    });
  });
});
