// Light or dark before the app starts, so a dark page never flashes white
// (the app itself switches it with Mantine; key "candivue-theme").
try {
  var scheme = window.localStorage.getItem('candivue-theme') === 'dark' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-mantine-color-scheme', scheme);
} catch (error) {
  // storage blocked: the app starts in light
}
