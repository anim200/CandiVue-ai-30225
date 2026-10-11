// Where the browser reaches the LiveKit video server: the same address as
// the app (nginx forwards /rtc to LiveKit), as ws:// or wss://.
export function liveKitUrl() {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}`;
}
