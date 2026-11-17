/* Minimal i18n for a house-style tool. Rename KEY, fill STRINGS.
 *
 *   I18N.t('list.empty')                      -> text in the current language
 *   I18N.t('notes.count', { n: 3 })           -> plural entry ['{n} note', '{n} notes']
 *   <button data-i18n="tools.help" data-i18n-title="tools.help.tip">  -> I18N.apply()
 *
 * Language: ?lang=xx wins, then the stored choice, then DEFAULT. Missing keys fall back
 * to DEFAULT, then to the key itself (visible, so it gets noticed). A flag chip
 * (#langBtn) shows the current language and toggles. Content written by people or agents
 * is never translated: only the interface. */
(function (root) {
  var KEY = 'tool.lang';
  var DEFAULT = 'en';
  var LANGS = ['en', 'es'];
  var FLAGS = { es: '🇪🇸', en: '🇬🇧' };
  var STRINGS = {
    es: { 'lang.title': 'Idioma: español. Cambiar a English', 'notes.count': ['{n} nota', '{n} notas'] },
    en: { 'lang.title': 'Language: English. Switch to español', 'notes.count': ['{n} note', '{n} notes'] },
  };

  function pick() {
    try {
      var q = new URLSearchParams(location.search).get('lang');
      if (LANGS.indexOf(q) >= 0) return q;
      var s = localStorage.getItem(KEY);
      if (LANGS.indexOf(s) >= 0) return s;
    } catch (e) { /* blocked */ }
    return DEFAULT;
  }
  var lang = pick();

  function t(key, vars) {
    var v = (STRINGS[lang] || {})[key];
    if (v === undefined) v = (STRINGS[DEFAULT] || {})[key];
    if (v === undefined) return key;
    vars = vars || {};
    if (Array.isArray(v)) v = vars.n === 1 ? v[0] : v[1];
    return String(v).replace(/\{(\w+)\}/g, function (_, k) {
      return vars[k + 'Text'] !== undefined ? vars[k + 'Text'] : (vars[k] !== undefined ? vars[k] : '{' + k + '}');
    });
  }

  function apply(doc) {
    doc = doc || document;
    doc.documentElement.lang = lang;
    var map = { 'data-i18n': null, 'data-i18n-title': 'title', 'data-i18n-aria-label': 'aria-label',
                'data-i18n-placeholder': 'placeholder', 'data-i18n-content': 'content' };
    Object.keys(map).forEach(function (attr) {
      doc.querySelectorAll('[' + attr + ']').forEach(function (el) {
        var text = t(el.getAttribute(attr));
        if (map[attr]) el.setAttribute(map[attr], text); else el.textContent = text;
      });
    });
    var chip = doc.getElementById('langBtn');
    if (chip) { chip.textContent = FLAGS[lang]; chip.title = t('lang.title'); chip.setAttribute('aria-label', t('lang.title')); }
  }

  function setLang(next) {
    if (LANGS.indexOf(next) < 0) return;
    lang = next;
    try { localStorage.setItem(KEY, next); } catch (e) { /* blocked */ }
    try {
      var u = new URL(location.href);
      if (u.searchParams.has('lang')) { u.searchParams.set('lang', next); history.replaceState(history.state, '', u); }
    } catch (e) { /* old browser */ }
    apply();
    document.dispatchEvent(new CustomEvent('langchange', { detail: { lang: next } }));
  }

  var api = {
    t: t, apply: apply, setLang: setLang, LANGS: LANGS,
    lang: function () { return lang; },
    toggle: function () { setLang(LANGS[(LANGS.indexOf(lang) + 1) % LANGS.length]); },
    locale: function () { return lang === 'es' ? 'es-ES' : 'en-GB'; },
    STRINGS: STRINGS,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.I18N = api;
})(typeof window !== 'undefined' ? window : this);
