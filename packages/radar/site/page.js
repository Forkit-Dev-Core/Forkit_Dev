const button = document.getElementById('copy');
const command = document.getElementById('install-command');
const status = document.getElementById('copy-status');
button.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(command.textContent);
    status.textContent = 'Copied. Run this in the supplied source checkout.';
  } catch {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(command);
    selection.removeAllRanges();
    selection.addRange(range);
    status.textContent = 'Command selected. Use your browser’s Copy action.';
  }
});
