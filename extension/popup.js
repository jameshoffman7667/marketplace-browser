const $ = (s) => document.querySelector(s);
const SUPPORTED = (u) =>
  /^https:\/\/www\.facebook\.com\/marketplace/.test(u || '') || /^https:\/\/([^/]+\.)?kijiji\.ca\//.test(u || '');

function say(text, cls) {
  const m = $('#msg');
  m.textContent = text || '';
  m.className = cls || '';
}

async function render() {
  const { serverUrl, token, state = {} } = await chrome.storage.local.get(['serverUrl', 'token', 'state']);
  const configured = !!(serverUrl && token);
  $('#conn').textContent = configured ? 'Server: ' + serverUrl : 'Not set up yet. Open Options to add your server URL and ingest token.';
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  $('#capture').disabled = !configured || !SUPPORTED(tab && tab.url) || !!state.running;
  $('#run').disabled = !configured || !!state.running;
  $('#run').textContent = state.running ? 'Running: ' + (state.progress || '...') : 'Run all searches now';

  const last = $('#last');
  last.textContent = '';
  const lr = state.lastRun;
  if (lr) {
    const head = document.createElement('div');
    head.className = 'mute';
    head.textContent = 'Last run ' + new Date(lr.at).toLocaleString();
    last.appendChild(head);
    if (lr.error) {
      const e = document.createElement('div');
      e.className = 'bad';
      e.textContent = lr.error;
      last.appendChild(e);
    }
    for (const r of lr.results || []) {
      const d = document.createElement('div');
      d.className = 'res';
      const name = document.createElement('strong');
      name.textContent = r.search;
      d.appendChild(name);
      const s = document.createElement('div');
      s.className = r.error ? 'bad' : 'mute';
      s.textContent = r.error ? r.error : `${r.found} found, ${r.new || 0} new`;
      d.appendChild(s);
      last.appendChild(d);
    }
  }
}

$('#capture').onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  say('Reading the page...', 'mute');
  const r = await chrome.runtime.sendMessage({ type: 'capture-tab', tabId: tab.id, url: tab.url });
  if (r && r.error) say(r.error, 'bad');
  else say(`Sent ${r.found} listing(s) to ${r.source}; ${r.new_matches} new match(es).`, 'ok');
};
$('#run').onclick = async () => {
  say('', '');
  const r = await chrome.runtime.sendMessage({ type: 'run-now' });
  if (r && r.skipped) say('A run is already in progress.', 'mute');
  else if (r && r.error) say(r.error, 'bad');
};
$('#opts').onclick = (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); };
$('#open').onclick = async (e) => {
  e.preventDefault();
  const { serverUrl } = await chrome.storage.local.get('serverUrl');
  if (serverUrl) chrome.tabs.create({ url: serverUrl });
  else chrome.runtime.openOptionsPage();
};
chrome.storage.onChanged.addListener(render);
render();
