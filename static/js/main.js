// ===== Custom Toast =====
function showToast(message, type = 'info', duration = 4000) {
    const colors = {
        success: '#10b981',
        danger: '#ef4444',
        warning: '#f59e0b',
        info: '#06b6d4'
    };
    const icons = {
        success: 'check-circle',
        danger: 'times-circle',
        warning: 'exclamation-triangle',
        info: 'info-circle'
    };
    
    const toast = document.createElement('div');
    toast.className = 'custom-toast';
    toast.style.borderLeftColor = colors[type] || colors.info;
    toast.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="fas fa-${icons[type]} me-2" style="color:${colors[type]};font-size:1.2rem;"></i>
            <span>${message}</span>
        </div>
    `;
    
    document.getElementById('toastContainer').appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(50px)';
        setTimeout(() => toast.remove(), 400);
    }, duration);
}

// ===== Scan Single Device =====
function scanDevice(deviceId) {
    if (!confirm('🚀 Start scanning this device?')) return;
    
    showToast('Initiating device scan...', 'info');
    
    fetch(`/api/scan/device/${deviceId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        showToast('✅ Scan started successfully!', 'success');
        setTimeout(() => location.reload(), 5000);
    })
    .catch(err => showToast('❌ Error: ' + err, 'danger'));
}

// ===== Scan All Devices =====
function scanAllDevices() {
    if (!confirm('🌐 Scan ALL devices? This may take a few minutes.')) return;
    
    showToast('🔄 Starting full network scan...', 'info');
    
    fetch('/api/scan/all', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        showToast('✅ Full scan initiated!', 'success');
        setTimeout(() => location.reload(), 15000);
    })
    .catch(err => showToast('❌ Error: ' + err, 'danger'));
}

// ===== Delete Device =====
function deleteDevice(deviceId) {
    if (!confirm('⚠️ Delete this device and ALL its data?')) return;
    
    fetch(`/api/device/${deviceId}/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            showToast('✅ Device deleted', 'success');
            setTimeout(() => location.href = '/', 1000);
        } else {
            showToast('❌ ' + data.message, 'danger');
        }
    })
    .catch(err => showToast('❌ Error: ' + err, 'danger'));
}