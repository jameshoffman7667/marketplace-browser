const $ = (s) => document.querySelector(s);
const msg = (t, cls) => { $('#msg').textContent = t; $('#msg').className = cls || 'mute'; };

async function load() {
  const c = await chrome.storage.local.get(['serverUrl', 'token', 'auto', 'intervalMin', 'maxPerRun', 'foreground']);
  $('#url').value = c.serverUrl || '';
  $('#tok').value = c.token || '';
  $('#auto').checked = !!c.auto;
  $('#int').value = c.intervalMin || 30;
  $('#max').value = c.maxPerRun || 10;
  $('#fg').checked = !!c.foreground;
}

async function save() {
  const serverUrl = $('#url').value.trim().replace(/\/+$/, '');
  if (serverUrl && !/^https?:\/\//.test(serverUrl)) { msg('The server URL must start with http:// or https://', 'bad'); return false; }
  await chrome.storage.local.set({
    serverUrl,
    token: $('#tok').value.trim(),
    auto: $('#auto').checked,
    intervalMin: Math.max(15, Number($('#int').value) || 30),
    maxPerRun: Math.min(30, Math.max(1, Number($('#max').value) || 10)),
    foreground: $('#fg').checked,
  });
  msg('Saved.', 'ok');
  return true;
}

$('#save').onclick = save;
$('#test').onclick = async () => {
  if (!(await save())) return;
  msg('Testing...');
  const r = await chrome.runtime.sendMessage({ type: 'test' });
  if (r && r.error) msg(r.error, 'bad');
  else msg(`Connected to Classifieds Tracker v${r.health.version}. ${r.tasks} search page(s) queued for this extension.`, 'ok');
};
load();
