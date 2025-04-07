// Dashboard.js - JavaScript for the dashboard page

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Fetch new emails button animation
    const fetchButton = document.querySelector('a[href*="fetch-emails"]');
    if (fetchButton) {
        fetchButton.addEventListener('click', function() {
            // Show loading state
            const originalText = this.innerHTML;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Fetching...';
            this.classList.add('disabled');
            
            // Restore after 3 seconds (in case page doesn't reload)
            setTimeout(function() {
                if (document.body.contains(fetchButton)) {
                    fetchButton.innerHTML = originalText;
                    fetchButton.classList.remove('disabled');
                }
            }, 3000);
        });
    }
    
    // Handle chart resizing when window size changes
    window.addEventListener('resize', function() {
        if (typeof Chart !== 'undefined') {
            Chart.instances.forEach(chart => {
                chart.resize();
            });
        }
    });
});

// Function to update dashboard data dynamically
function refreshDashboardData() {
    fetch('/statistics')
        .then(response => response.json())
        .then(data => {
            // Update email count display
            const totalEmailsElement = document.querySelector('[aria-valuenow]');
            if (totalEmailsElement && data.read_status) {
                const total = data.read_status.read + data.read_status.unread;
                const percentage = total > 0 ? (data.read_status.read / total * 100) : 0;
                
                totalEmailsElement.setAttribute('aria-valuenow', percentage);
                totalEmailsElement.style.width = percentage + '%';
                totalEmailsElement.textContent = Math.round(percentage) + '%';
            }
            
            // Refresh charts if they exist
            if (window.timelineChart && data.email_timeline) {
                window.timelineChart.data.labels = data.email_timeline.dates;
                window.timelineChart.data.datasets[0].data = data.email_timeline.counts;
                window.timelineChart.update();
            }
            
            if (window.readUnreadChart && data.read_status) {
                window.readUnreadChart.data.datasets[0].data = [
                    data.read_status.read,
                    data.read_status.unread
                ];
                window.readUnreadChart.update();
            }
        })
        .catch(error => console.error('Error refreshing dashboard data:', error));
}

// Set up auto-refresh every 60 seconds if on dashboard page
if (window.location.pathname.includes('dashboard')) {
    setInterval(refreshDashboardData, 60000);
}
