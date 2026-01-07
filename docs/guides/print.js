(function() {
  function attachPrintHandlers() {
    const buttons = document.querySelectorAll('[data-print-pdf]');
    buttons.forEach((button) => {
      button.addEventListener('click', () => {
        window.print();
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attachPrintHandlers);
  } else {
    attachPrintHandlers();
  }
})();
