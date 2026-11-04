document.addEventListener('DOMContentLoaded', () => {
  const metricBox = document.querySelector('.metric-box');
  const completedInput = document.querySelector('#completed_deliveries');
  const returnsInput = document.querySelector('#returns');

  if (!document.body.classList.contains('route-loader-initialized')) {
    const overlay = document.createElement('div');
    overlay.className = 'ride-loader-overlay';
    overlay.innerHTML = `
      <div class="ride-loader-card">
        <div class="ride-loader-scene" aria-hidden="true">
          <div class="road-line"></div>
          <div class="bike-ride">
            <div class="wheel wheel-left"></div>
            <div class="wheel wheel-right"></div>
            <div class="frame-part frame-body"></div>
            <div class="frame-part frame-seat"></div>
            <div class="frame-part frame-handle"></div>
            <div class="frame-part frame-pedal"></div>
          </div>
        </div>
        <p>Preparing delivery route...</p>
      </div>
    `;
    document.body.appendChild(overlay);
    document.body.classList.add('route-loader-initialized');

    window.addEventListener('load', () => {
      setTimeout(() => {
        overlay.classList.add('hidden');
      }, 700);
    }, { once: true });
  }

  const updateMetric = () => {
    const completed = Number(completedInput?.value || 0);
    const returns = Number(returnsInput?.value || 0);
    const amount = (completed + returns) * 15;
    if (metricBox) metricBox.textContent = `₹${amount.toFixed(2)}`;
  };

  completedInput?.addEventListener('input', updateMetric);
  returnsInput?.addEventListener('input', updateMetric);
  updateMetric();
});
