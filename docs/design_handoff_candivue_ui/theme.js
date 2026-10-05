/* CandiVue AI light/dark theme switch.
   Screens are authored in light colours; in dark mode this remaps inline colours
   (and generated hover rules) through the token maps below. Choice is stored in
   localStorage and shared across tabs. Subtrees with [data-cv-theme-skip] are untouched. */
(function () {
  if (window.__cvTheme) return;
  var KEY = 'candivue-theme';
  var BG = {
    '#ffffff': '#1A2226', '#f5f7f8': '#12181B', '#fafbfb': '#161D21', '#f8f9fa': '#161D21', '#f7fbfb': '#142124',
    '#f1f4f5': '#222B30', '#edf0f2': '#263035', '#eef1f3': '#263035', '#e9ecee': '#2B353A', '#e3e7ea': '#2B353A', '#dee3e6': '#2B353A',
    '#edf5f6': '#1C3A3E', '#d5e9eb': '#24474C', '#a9d2d6': '#2E6A70',
    '#e7f3ec': '#1E3A2B', '#fbf0d9': '#3D3115', '#fbe9e7': '#41201C', '#e7eef9': '#1B2A42',
    '#fffaef': '#2E2716', '#fff8e6': '#3A2F12', '#fffbfa': '#2A1D1B', '#fff7f6': '#2A1D1B', '#f0f0fa': '#25264A'
  };
  var TX = {
    '#1a2227': '#E6ECEE', '#48535b': '#B5C0C5', '#66717a': '#A3AFB4', '#3e484f': '#C2CCD0', '#8a949a': '#7D8A91',
    '#1c5d65': '#7FD0D8', '#103a40': '#BDEDF1', '#164a51': '#A9E3E8', '#23717a': '#5DB3BC',
    '#245f3e': '#8FD3A9', '#2d7a4e': '#5CB582', '#1e4a31': '#B5E3C6', '#2b5a3f': '#A8DABA',
    '#7a5000': '#F0C66E', '#5a3d00': '#F0D9A6', '#c08a1e': '#E0B04F',
    '#932e24': '#F2A096', '#5a2620': '#F5C2BB', '#b03a2e': '#E07A6E',
    '#234e8b': '#9DBDF0', '#1f3b66': '#BFD3F5', '#2b5fa8': '#7FA6E6', '#6b4a9e': '#C3A8EC'
  };
  var BD = {
    '#dee3e6': '#2B353A', '#e9ecee': '#263035', '#f0f2f4': '#222B30', '#c9d0d4': '#3A464C', '#e3e7ea': '#2B353A',
    '#d5e9eb': '#24474C', '#cfe5e8': '#24474C', '#a9d2d6': '#2E5A5F', '#a3adb3': '#5A666C',
    '#f0d9a6': '#5A4A22', '#e3b7b1': '#6B3A33', '#f0c7c1': '#6B3A33', '#e8cc8f': '#5A4A22', '#a9c0e4': '#3A5683', '#ffffff': '#1A2226'
  };
  function toRgb(h) { h = h.replace('#', ''); if (h.length === 3) h = h.split('').map(function (c) { return c + c; }).join('');
    return 'rgb(' + parseInt(h.slice(0, 2), 16) + ', ' + parseInt(h.slice(2, 4), 16) + ', ' + parseInt(h.slice(4, 6), 16) + ')'; }
  function build(m) { var o = {}; for (var k in m) o[toRgb(k)] = toRgb(m[k]); return o; }
  var M = { bg: build(BG), tx: build(TX), bd: build(BD) };
  var PROPS = [['color', 'tx'], ['fill', 'tx'], ['background-color', 'bg'], ['border-top-color', 'bd'], ['border-right-color', 'bd'], ['border-bottom-color', 'bd'], ['border-left-color', 'bd'], ['outline-color', 'bd']];
  var RGB = /rgb\(\d+, \d+, \d+\)/g;
  var orig = new WeakMap(), ruleOrig = new WeakMap();
  var dark = false, applying = false;

  function mapStyle(st, store, owner) {
    for (var i = 0; i < PROPS.length; i++) {
      var p = PROPS[i][0], map = M[PROPS[i][1]], v = st.getPropertyValue(p);
      if (!v) continue;
      var rec = store.get(owner) || {};
      if (dark) {
        if (rec[p] && rec[p].d === v) continue;
        var nv = v.replace(RGB, function (m) { return map[m] || m; });
        if (nv !== v) { rec[p] = { o: v, d: nv }; store.set(owner, rec); st.setProperty(p, nv, st.getPropertyPriority(p)); }
      } else if (rec[p]) {
        if (rec[p].d === v) st.setProperty(p, rec[p].o, st.getPropertyPriority(p));
        delete rec[p];
      }
    }
  }
  function skip(el) { return el.closest && el.closest('[data-cv-theme-skip]'); }
  function processEl(el) { if (el.nodeType === 1 && el.hasAttribute('style') && !skip(el)) mapStyle(el.style, orig, el); }
  function processTree(root) {
    if (!root || root.nodeType !== 1) return;
    processEl(root);
    var list = root.querySelectorAll('[style]');
    for (var i = 0; i < list.length; i++) processEl(list[i]);
  }
  function processRules() {
    var sheets = document.styleSheets;
    for (var i = 0; i < sheets.length; i++) {
      var s = sheets[i], rules;
      if (s.ownerNode && s.ownerNode.id === 'cv-theme-css') continue;
      try { rules = s.cssRules; } catch (e) { continue; }
      if (!rules) continue;
      for (var j = 0; j < rules.length; j++) { var r = rules[j]; if (r.style && /hover|focus|active|cc-|dc-|sc-/.test(r.selectorText || '')) mapStyle(r.style, ruleOrig, r); }
    }
  }
  var CSS = 'html[data-cv-theme=dark],html[data-cv-theme=dark] body{background:#0E1416!important;color:#E6ECEE;color-scheme:dark}' +
    'html[data-cv-theme=dark] .dv-card{background:#1A2226;border-color:#2B353A;box-shadow:0 1px 3px rgba(0,0,0,.4)}' +
    'html[data-cv-theme=dark] .dv-turn{border-color:rgba(255,255,255,.08)}' +
    'html[data-cv-theme=dark] .dv-tname{color:#E6ECEE}html[data-cv-theme=dark] .dv-olabel,html[data-cv-theme=dark] .dv-next{color:rgba(255,255,255,.6)}' +
    'html[data-cv-theme=dark] .dv-oid{background:rgba(255,255,255,.1);color:#E6ECEE}html[data-cv-theme=dark] .dv-tid{background:#E6ECEE;color:#0E1416}' +
    'html[data-cv-theme=dark] a{color:#7FD0D8}html[data-cv-theme=dark] a:hover{color:#A9E3E8}' +
    'html[data-cv-theme=dark] input,html[data-cv-theme=dark] textarea{background-color:#12181B;color:#E6ECEE}' +
    'html[data-cv-theme=dark] input::placeholder,html[data-cv-theme=dark] textarea::placeholder{color:#7D8A91}' +
    'html,body,.dv-card,[style]{transition-property:background-color,color,border-color;transition-duration:.25s}' +
    '@keyframes cvmenu{from{opacity:0;transform:translateY(-4px) scale(.98)}to{opacity:1;transform:none}}';
  function injectCss() { if (document.getElementById('cv-theme-css')) return; var st = document.createElement('style'); st.id = 'cv-theme-css'; st.textContent = CSS; (document.head || document.documentElement).appendChild(st); }

  function apply(isDark) {
    dark = isDark; applying = true;
    document.documentElement.setAttribute('data-cv-theme', dark ? 'dark' : 'light');
    processTree(document.body); processRules(); syncControls();
    applying = false;
  }
  function set(mode) { try { localStorage.setItem(KEY, mode); } catch (e) {} apply(mode === 'dark'); }

  function syncControls() {
    var segs = document.querySelectorAll('[data-cv-theme-set]');
    for (var i = 0; i < segs.length; i++) {
      var on = (segs[i].getAttribute('data-cv-theme-set') === 'dark') === dark;
      segs[i].style.background = on ? (dark ? '#3A464C' : '#fff') : 'transparent';
      segs[i].style.boxShadow = on ? '0 1px 2px rgba(0,0,0,.15)' : 'none';
      segs[i].style.color = on ? (dark ? '#E6ECEE' : '#1A2227') : (dark ? '#A3AFB4' : '#48535B');
    }
    var tg = document.querySelectorAll('[data-cv-theme-toggle] i');
    for (var j = 0; j < tg.length; j++) tg[j].className = dark ? 'ti ti-sun' : 'ti ti-moon';
  }

  var menu = null;
  function closeMenu() { if (menu) { menu.remove(); menu = null; } }
  function openMenu(anchor) {
    closeMenu();
    var c = dark ? { bg: '#1A2226', bd: '#2B353A', tx: '#E6ECEE', dim: '#A3AFB4', seg: '#12181B', hov: '#222B30', red: '#F2A096', redbg: '#41201C' }
                 : { bg: '#fff', bd: '#DEE3E6', tx: '#1A2227', dim: '#66717A', seg: '#E9ECEE', hov: '#F1F4F5', red: '#932E24', redbg: '#FBE9E7' };
    menu = document.createElement('div');
    menu.setAttribute('data-cv-theme-skip', '');
    menu.setAttribute('data-component', 'UserMenu.Dropdown');
    menu.style.cssText = 'position:absolute;top:calc(100% + 6px);right:0;width:260px;z-index:1000;background:' + c.bg + ';border:1px solid ' + c.bd + ';border-radius:8px;box-shadow:0 10px 30px rgba(0,0,0,.18);padding:6px;display:flex;flex-direction:column;gap:2px;text-align:left;cursor:default;animation:cvmenu .18s ease-out;font-family:inherit';
    var name = (anchor.textContent || '').indexOf('Interviewer') >= 0 ? 'Interviewer A' : 'Signed in';
    var item = function (icon, label, extra) { return '<div data-cv-item style="height:36px;padding:0 10px;border-radius:4px;display:flex;align-items:center;gap:10px;font-size:14px;color:' + (extra || c.tx) + ';cursor:pointer"><i class="ti ' + icon + '" style="font-size:17px"></i>' + label + '</div>'; };
    menu.innerHTML =
      '<div style="padding:8px 10px 10px;border-bottom:1px solid ' + c.bd + ';margin-bottom:4px"><div style="font-size:14px;font-weight:600;color:' + c.tx + '">' + name + '</div><div style="font-size:12px;color:' + c.dim + '">interviewer.a@example.com</div></div>' +
      '<div style="padding:6px 10px;display:flex;justify-content:space-between;align-items:center;font-size:14px;color:' + c.tx + '"><span style="display:flex;align-items:center;gap:10px"><i class="ti ti-sun-moon" style="font-size:17px;color:' + c.dim + '"></i>Appearance</span>' +
      '<div style="display:flex;background:' + c.seg + ';border-radius:5px;padding:2px"><span data-cv-theme-set="light" style="height:24px;padding:0 9px;border-radius:4px;font-size:12px;font-weight:600;display:inline-flex;align-items:center;gap:4px;cursor:pointer;transition:background .15s"><i class="ti ti-sun" style="font-size:13px"></i>Light</span><span data-cv-theme-set="dark" style="height:24px;padding:0 9px;border-radius:4px;font-size:12px;font-weight:600;display:inline-flex;align-items:center;gap:4px;cursor:pointer;transition:background .15s"><i class="ti ti-moon" style="font-size:13px"></i>Dark</span></div></div>' +
      item('ti-help-circle', 'Help') +
      '<div style="height:1px;background:' + c.bd + ';margin:4px 0"></div>' +
      '<a href="Login.dc.html" data-cv-item style="height:36px;padding:0 10px;border-radius:4px;display:flex;align-items:center;gap:10px;font-size:14px;color:' + c.red + ';text-decoration:none"><i class="ti ti-logout" style="font-size:17px"></i>Sign out</a>';
    var its = menu.querySelectorAll('[data-cv-item]');
    for (var i = 0; i < its.length; i++) (function (el, red) {
      el.addEventListener('mouseenter', function () { el.style.background = red ? c.redbg : c.hov; });
      el.addEventListener('mouseleave', function () { el.style.background = 'transparent'; });
    })(its[i], its[i].tagName === 'A');
    if (getComputedStyle(anchor).position === 'static') anchor.style.position = 'relative';
    anchor.appendChild(menu);
    syncControls();
  }

  document.addEventListener('click', function (e) {
    var t = e.target;
    var setter = t.closest && t.closest('[data-cv-theme-set]');
    if (setter) { e.stopPropagation(); set(setter.getAttribute('data-cv-theme-set')); if (menu && menu.contains(setter)) { var a = menu.parentNode; openMenu(a); } return; }
    var tog = t.closest && t.closest('[data-cv-theme-toggle]');
    if (tog) { set(dark ? 'light' : 'dark'); return; }
    if (menu && menu.contains(t)) return;
    var um = t.closest && t.closest('[data-component="UserMenu"]');
    if (um) { if (menu && menu.parentNode === um) closeMenu(); else openMenu(um); return; }
    closeMenu();
  }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMenu(); });
  window.addEventListener('storage', function (e) { if (e.key === KEY) apply(e.newValue === 'dark'); });

  var ruleTimer = null;
  var mo = new MutationObserver(function (muts) {
    if (applying) return;
    if (!dark) { return; }
    applying = true;
    for (var i = 0; i < muts.length; i++) {
      var m = muts[i];
      if (m.type === 'attributes') processEl(m.target);
      else for (var j = 0; j < m.addedNodes.length; j++) processTree(m.addedNodes[j]);
    }
    applying = false;
    clearTimeout(ruleTimer); ruleTimer = setTimeout(function () { applying = true; processRules(); applying = false; }, 120);
  });

  function start() {
    injectCss();
    var saved = 'light'; try { saved = localStorage.getItem(KEY) || 'light'; } catch (e) {}
    apply(saved === 'dark');
    mo.observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ['style'] });
  }
  window.__cvTheme = { set: set, get: function () { return dark ? 'dark' : 'light'; } };
  injectCss();
  try { if (localStorage.getItem(KEY) === 'dark') document.documentElement.setAttribute('data-cv-theme', 'dark'); } catch (e) {}
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
})();
