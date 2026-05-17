// Nav toggle for mobile
function toggleNav() {
  document.querySelector('.nav-links').classList.toggle('open');
}

// Logout
async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.href = '/';
}
