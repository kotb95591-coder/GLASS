document.addEventListener('DOMContentLoaded', function() {
    console.log('GSLASE мессенджер загружен');

    // Базовая функциональность для настроек
    const themeSelect = document.querySelector('select');
    if (themeSelect) {
        themeSelect.addEventListener('change', function() {
            console.log('Тема изменена на:', this.value);
        });
    }
});
