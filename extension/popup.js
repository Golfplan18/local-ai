const dot = document.getElementById('status-dot');
const text = document.getElementById('status-text');
const btn = document.getElementById('reconnect');

function updateUI(connected) {
  dot.className = connected ? 'dot connected' : 'dot disconnected';
  text.textContent = connected ? 'Connected to Ora' : 'Disconnected';
}

chrome.runtime.sendMessage({ type: 'getStatus' }, (response) => {
  updateUI(response?.connected || false);
});

btn.addEventListener('click', () => {
  text.textContent = 'Reconnecting...';
  dot.className = 'dot disconnected';
  chrome.runtime.sendMessage({ type: 'reconnect' }, () => {
    setTimeout(() => {
      chrome.runtime.sendMessage({ type: 'getStatus' }, (response) => {
        updateUI(response?.connected || false);
      });
    }, 3000);
  });
});
