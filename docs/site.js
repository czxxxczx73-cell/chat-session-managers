(() => {
  const button = document.querySelector('#language-toggle');
  const translated = document.querySelectorAll('[data-en][data-zh]');
  const localizedImages = document.querySelectorAll('[data-en-src][data-zh-src]');
  if (!button || !translated.length) return;

  let stored = null;
  try {
    stored = window.localStorage.getItem('csm-language');
  } catch (_) {
    stored = null;
  }
  const preferred = stored || (navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en');

  const setLanguage = (language) => {
    const next = language === 'zh' ? 'zh' : 'en';
    document.documentElement.lang = next === 'zh' ? 'zh-CN' : 'en';
    translated.forEach((node) => {
      node.textContent = node.dataset[next];
    });
    localizedImages.forEach((image) => {
      image.src = image.dataset[`${next}Src`];
      image.alt = image.dataset[`${next}Alt`];
    });
    button.textContent = next === 'zh' ? 'English' : '中文';
    button.setAttribute('aria-label', next === 'zh' ? 'Switch to English' : '切换为中文');
    try {
      window.localStorage.setItem('csm-language', next);
    } catch (_) {
      // Language switching remains functional when storage is unavailable.
    }
  };

  setLanguage(preferred);
  button.addEventListener('click', () => {
    setLanguage(document.documentElement.lang.startsWith('zh') ? 'en' : 'zh');
  });
})();
