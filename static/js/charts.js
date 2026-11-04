document.addEventListener('DOMContentLoaded', () => {
  if (!window.chartData || !window.Chart) return;

  const data = window.chartData;

  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        labels: { usePointStyle: true, boxWidth: 8, color: '#49382D' }
      }
    },
    scales: {
      x: { ticks: { color: '#49382D' }, grid: { display: false } },
      y: { ticks: { color: '#49382D' }, grid: { color: 'rgba(73, 56, 45, 0.08)' } }
    }
  };

  const dailyCtx = document.getElementById('dailyDeliveriesChart');
  if (dailyCtx) {
    new Chart(dailyCtx, {
      type: 'line',
      data: {
        labels: data.daily_labels || [],
        datasets: [{
          label: 'Completed deliveries',
          data: data.daily_deliveries || [],
          borderColor: '#C77B55',
          backgroundColor: 'rgba(199, 123, 85, 0.18)',
          borderWidth: 3,
          tension: 0.34,
          fill: true
        }]
      },
      options: commonOptions
    });
  }

  const weeklyCtx = document.getElementById('weeklyDeliveryChart');
  if (weeklyCtx) {
    new Chart(weeklyCtx, {
      type: 'bar',
      data: {
        labels: data.daily_labels || [],
        datasets: [{
          label: 'Deliveries',
          data: data.daily_deliveries || [],
          backgroundColor: ['#D6AD70', '#C77B55', '#D6AD70', '#C77B55', '#D6AD70', '#C77B55', '#D6AD70'],
          borderRadius: 10
        }]
      },
      options: commonOptions
    });
  }

  const monthlyCtx = document.getElementById('monthlyEarningsChart');
  if (monthlyCtx) {
    new Chart(monthlyCtx, {
      type: 'line',
      data: {
        labels: data.monthly_labels && data.monthly_labels.length ? data.monthly_labels : ['No data'],
        datasets: [{
          label: 'Monthly revenue',
          data: data.monthly_earnings && data.monthly_earnings.length ? data.monthly_earnings : [0],
          borderColor: '#49382D',
          backgroundColor: 'rgba(73, 56, 45, 0.12)',
          fill: true,
          borderWidth: 2,
          tension: 0.32
        }]
      },
      options: commonOptions
    });
  }

  const attendanceCtx = document.getElementById('attendanceChart');
  if (attendanceCtx) {
    new Chart(attendanceCtx, {
      type: 'doughnut',
      data: {
        labels: data.attendance_labels || ['Present', 'Off Duty'],
        datasets: [{
          data: data.attendance_values || [0, 0],
          backgroundColor: ['#C77B55', '#D6AD70']
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '65%',
        plugins: { legend: { position: 'bottom', labels: { color: '#49382D' } } }
      }
    });
  }

  const comparisonCtx = document.getElementById('comparisonChart');
  if (comparisonCtx) {
    new Chart(comparisonCtx, {
      type: 'bar',
      data: {
        labels: data.comparison_labels || ['Pickups', 'Completed'],
        datasets: [{
          label: 'Counts',
          data: data.comparison_values || [0, 0],
          backgroundColor: ['#D6AD70', '#C77B55'],
          borderRadius: 12
        }]
      },
      options: commonOptions
    });
  }
});
