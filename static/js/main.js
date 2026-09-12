// ===== Scan Device =====
function scanDevice(deviceId) {
    if (!confirm('Start scanning this device?')) return;
    
    fetch(`/api/scan/device/${deviceId}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'}
    })
    .then(response => response.json())
    .then(data => {
        showToast('Scan started! Data will be updated shortly.', 'success');
        // Refresh after delay
        setTimeout(() => location.reload(), 5000);
    })
    .catch(error => {
        showToast('Error starting scan: ' + error, 'danger');
    });
}

// ===== Scan All Devices =====
function scanAllDevices() {
    if (!confirm('Scan ALL devices? This may take several minutes.')) return;
    
    fetch('/api/scan/all', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'}
    })
    .then(response => response.json())
    .then(data => {
        showToast('Full network scan started! Please wait...', 'success');
        setTimeout(() => location.reload(), 15000);
    })
    .catch(error => {
        showToast('Error: ' + error, 'danger');
    });
}

// ===== Delete Device =====
function deleteDevice(deviceId) {
    if (!confirm('Are you sure you want to delete this device and ALL its data?')) return;
    
    fetch(`/api/device/${deviceId}/delete`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'}
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            showToast('Device deleted successfully', 'success');
            setTimeout(() => location.href = '/', 1000);
        } else {
            showToast('Error: ' + data.message, 'danger');
        }
    })
    .catch(error => {
        showToast('Error: ' + error, 'danger');
    });
}

// ===== Toast Notification =====
function showToast(message, type) {
    const container = document.querySelector('.container-fluid.mt-5');
    if (!container) return;
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    container.prepend(alert);
    
    setTimeout(() => {
        alert.classList.remove('show');
        setTimeout(() => alert.remove(), 300);
    }, 5000);
}

// ===== Auto-refresh status =====
function autoRefreshStatus() {
    fetch('/api/stats')
    .then(response => response.json())
    .then(data => {
        // Update stats if elements exist
        const el = document.querySelector('[data-stat="total"]');
        if (el) el.textContent = data.total_devices;
    })
    .catch(() => {});
}

// Refresh every 30 seconds
// setInterval(autoRefreshStatus, 30000);