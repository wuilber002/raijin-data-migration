(() => {
  const STORAGE_KEY = 'raijin-ui-language';
  const localeFor = value => value === 'en' ? 'en-US' : 'pt-BR';
  let language = localStorage.getItem(STORAGE_KEY) === 'en' ? 'en' : 'pt';
  window.raijinI18nReady = window.i18next.use(window.i18nextHttpBackend).init({
    lng: localeFor(language), fallbackLng: 'pt-BR',
    // The catalog is regional (en-US/pt-BR).  Do not also request the
    // non-existent parent catalog (en), which adds failed requests during
    // every page initialization.
    load: 'currentOnly',
    backend: {loadPath: '/static/locales/{{lng}}.json'},
    interpolation: {escapeValue: false}, returnNull: false,
    keySeparator: false, nsSeparator: false
  }).then(result => { if (language === 'en') applyLanguage(); return result; });
  let translating = false;
  const textSources = new WeakMap();
  const attributeSources = new WeakMap();
  const pendingElements = new Set();
  let localizationScheduled = false;

  const translate = value => {
    if (!value || !value.trim() || language !== 'en') return value;
    const prefix = value.match(/^\s*/)?.[0] || '';
    const suffix = value.match(/\s*$/)?.[0] || '';
    const core = value.slice(prefix.length, value.length - suffix.length);
    const catalog = window.i18next?.getResourceBundle(localeFor(language), 'translation') || {};
    const translated = Object.hasOwn(catalog, core)
      ? window.i18next.t(core, {defaultValue: core}) : core;
    return `${prefix}${translated}${suffix}`;
  };
  const localizeElement = (element) => {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT, {
      acceptNode: node => ['SCRIPT', 'STYLE'].includes(node.parentElement?.tagName) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
    });
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => { if (!textSources.has(node)) textSources.set(node, node.nodeValue); node.nodeValue = translate(textSources.get(node)); });
    element.querySelectorAll?.('[placeholder],[title],[aria-label],[data-help]').forEach(node => {
      ['placeholder', 'title', 'aria-label', 'data-help'].forEach(attribute => {
        if (!node.hasAttribute(attribute)) return;
        if (!attributeSources.has(node)) attributeSources.set(node, {});
        const sources = attributeSources.get(node);
        if (!(attribute in sources)) sources[attribute] = node.getAttribute(attribute);
        node.setAttribute(attribute, translate(sources[attribute]));
      });
    });
  };
  const syncLanguagePicker = () => {
    const trigger = document.querySelector('#language-trigger');
    if (!trigger) return;
    const english = language === 'en';
    trigger.innerHTML = `<span class="country-flag ${english ? 'us' : 'br'}" aria-hidden="true"></span>`;
    trigger.title = english ? 'English (US)' : 'Português (Brasil)';
    trigger.setAttribute('aria-label', english ? 'Interface language: English (US)' : 'Idioma da interface: Português (Brasil)');
    document.querySelectorAll('#language-menu-options [data-language]').forEach(option => option.setAttribute('aria-checked', String(option.dataset.language === language)));
  };
  const applyLanguage = () => {
    translating = true;
    document.documentElement.lang = language === 'en' ? 'en-US' : 'pt-BR';
    // Each modal is already a direct child of body. Translating it again via
    // the former second selector multiplied the work during a page refresh.
    document.querySelectorAll('body > :not(script)').forEach(localizeElement);
    syncLanguagePicker();
    translating = false;
  };
  const scheduleLocalization = elements => {
    if (language !== 'en') return;
    elements.forEach(element => {
      if (element?.nodeType === Node.ELEMENT_NODE) pendingElements.add(element);
    });
    if (localizationScheduled || !pendingElements.size) return;
    localizationScheduled = true;
    requestAnimationFrame(() => {
      localizationScheduled = false;
      // Keep a rendering frame available even when a table inserts many rows.
      // Nested entries are covered by their ancestor and never translated twice.
      const pending = [...pendingElements], batch = [];
      for (const element of pending) {
        if (batch.length >= 12) break;
        if (!batch.some(ancestor => ancestor.contains(element))) batch.push(element);
      }
      // Descendants are covered by their selected ancestor in this frame.
      pending.filter(element => batch.some(ancestor => ancestor.contains(element)))
        .forEach(element => pendingElements.delete(element));
      translating = true;
      batch.forEach(localizeElement);
      translating = false;
      if (pendingElements.size) scheduleLocalization([]);
    });
  };
  window.raijinLocale = () => localeFor(language);
  window.t = (key, values) => window.i18next?.t(key, values) || key;
  window.uiText = text => language === 'en' ? translate(text) : text;
  window.setLanguage = async value => { language = value === 'en' ? 'en' : 'pt'; localStorage.setItem(STORAGE_KEY, language); await window.raijinI18nReady; await window.i18next.changeLanguage(localeFor(language)); applyLanguage(); document.querySelector('#language-menu-options')?.classList.add('hidden'); document.querySelector('#language-trigger')?.setAttribute('aria-expanded', 'false'); document.dispatchEvent(new CustomEvent('raijin:language-changed')); };
  window.toggleLanguageMenu = event => { event?.stopPropagation(); const menu = document.querySelector('#language-menu-options'), trigger = document.querySelector('#language-trigger'); if (!menu || !trigger) return; const open = menu.classList.toggle('hidden'); trigger.setAttribute('aria-expanded', String(!open)); };
  window.addEventListener('DOMContentLoaded', () => {
    applyLanguage();
    document.addEventListener('click', event => { if (!event.target.closest('.language-menu')) { document.querySelector('#language-menu-options')?.classList.add('hidden'); document.querySelector('#language-trigger')?.setAttribute('aria-expanded', 'false'); } });
    new MutationObserver(records => { if (!translating) {
      const roots = [];
      records.forEach(record => record.addedNodes.forEach(node => {
        if (node.nodeType === Node.ELEMENT_NODE) roots.push(node);
        if (node.nodeType === Node.TEXT_NODE && node.parentElement) roots.push(node.parentElement);
      }));
      scheduleLocalization(roots);
    }}).observe(document.body, {childList: true, subtree: true});
  });
})();
