self.addEventListener('install', (e) => {
    console.log('[Service Worker] Установлен');
});

self.addEventListener('fetch', (e) => {
    // Этот пустой обработчик обязателен, чтобы браузер разрешил кнопку "Установить приложение"
});
