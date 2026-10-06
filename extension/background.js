// Service worker: talks to the Classifieds Tracker server and drives the scraping tabs.
// Everything happens in the user's own browser session, at human pace: one page at a time,
// randomised gaps, a capped number of pages per run, and a 15 minute floor between automatic runs.
import { extractPage } from './extractor.js';

const SOURCES = { facebook: 'Facebook Marketplace', kijiji: 'Kijiji' };
const DEFAULTS = { serverUrl: '', token: '', auto: false, intervalMin: 30, maxPerRun: 10, foreground: false };
const MIN_INTERVAL = 15;
let running = false;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const getCfg = async () => ({ ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) });

async function setState(patch) {
  const { state = {} } = await chrome.storage.local.get('state');
  await chrome.storage.local.set({ state: { ...state, ...patch } });
}
async function addLog(msg) {
  const { logs = [] } = await chrome.storage.local.get('logs');
  logs.unshift({ t: Date.now(), msg });
  await chrome.storage.local.set({ logs: logs.slice(0, 40) });
}

async function api(path, opts = {}) {
  const cfg = await getCfg();
  if (!cfg.serverUrl || !cfg.token) throw new Error('Set the server URL and ingest token in the extension options first.');
  let r;
  try {
    r = await fetch(cfg.serverUrl.replace(/\/+$/, '') + path, {
      ...opts,
      headers: { 'Content-Type': 'application/json', 'X-Ingest-Token': cfg.token, ...(opts.headers || {}) },
    });
  } catch (e) {
    throw new Error('Cannot reach the server at ' + cfg.serverUrl + ' (' + e.message + ')');
  }
  const data = await r.json().catch(() => ({}));
  if (r.status === 401) throw new Error('The server rejected the ingest token.');
  if (!r.ok) throw new Error(data.error || 'Server error ' + r.status);
  return data;
}

function sourceForUrl(url) {
  try {
    const u = new URL(url);
    if (u.hostname.endsWith('facebook.com') && u.pathname.startsWith('/marketplace')) return SOURCES.facebook;
    if (u.hostname.endsWith('kijiji.ca')) return SOURCES.kijiji;
  } catch (e) { /* not a URL */ }
  return null;
}

function waitComplete(tabId, timeout = 45000) {
  return new Promise((resolve, reject) => {
    let done = false;
    const finish = (err) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      err ? reject(err) : resolve();
    };
    const listener = (id, info) => { if (id === tabId && info.status === 'complete') finish(); };
    const timer = setTimeout(() => finish(new Error('The page took too long to load.')), timeout);
    chrome.tabs.onUpdated.addListener(listener);
    chrome.tabs.get(tabId).then((t) => { if (t.status === 'complete') finish(); }).catch(() => {});
  });
}

async function extractFromTab(tabId, scrolls) {
  const [res] = await chrome.scripting.executeScript({
    target: { tabId },
    func: extractPage,
    args: [{ scrolls, waitMs: 1500 }],
  });
  if (!res || !res.result) throw new Error('Nothing came back from the page.');
  return res.result;
}

async function scrapeUrl(url, cfg, scrolls = 3) {
  const tab = await chrome.tabs.create({ url, active: !!cfg.foreground });
  try {
    await waitComplete(tab.id);
    await sleep(2500); // let the page hydrate before reading it
    return await extractFromTab(tab.id, scrolls);
  } finally {
    chrome.tabs.remove(tab.id).catch(() => {});
  }
}

function checkPage(page) {
  if (page.items.length) return;
  throw new Error(page.warnings[0] || 'No listings recognised on the page.');
}

async function ingest(source, searchId, items) {
  const body = { source, listings: items };
  if (searchId) body.search_id = searchId;
  return api('/api/ingest', { method: 'POST', body: JSON.stringify(body) });
}

async function runAll() {
  if (running) return { skipped: true };
  running = true;
  const results = [];
  let error = null;
  try {
    const cfg = await getCfg();
    await setState({ running: true, progress: 'Fetching searches from the server...' });
    const { tasks } = await api('/api/extension/tasks');
    const list = tasks.slice(0, Math.max(1, Number(cfg.maxPerRun) || 10));
    if (!list.length) {
      error = 'The server has no browser-extension searches yet. Add a source of type "Browser extension / API" with a URL template, and a saved search.';
    }
    for (let i = 0; i < list.length; i++) {
      const t = list[i];
      await setState({ progress: `${i + 1}/${list.length}: ${t.search}` });
      const r = { search: t.search, source: t.source };
      try {
        const page = await scrapeUrl(t.url, cfg, 3);
        r.found = page.items.length;
        checkPage(page);
        const resp = await ingest(t.source, t.search_id, page.items);
        r.new = resp.new_matches;
      } catch (e) {
        r.error = e.message;
      }
      results.push(r);
      if (i < list.length - 1) await sleep(8000 + Math.random() * 12000);
    }
  } catch (e) {
    error = e.message;
  } finally {
    running = false;
    const total = results.reduce((n, r) => n + (r.new || 0), 0);
    await setState({ running: false, progress: '', lastRun: { at: Date.now(), results, error } });
    await chrome.action.setBadgeBackgroundColor({ color: '#1f6f5c' });
    await chrome.action.setBadgeText({ text: total ? String(total) : '' });
    await addLog(error ? 'Run failed: ' + error : `Run finished: ${results.length} page(s), ${total} new match(es)`);
  }
  return { results, error };
}

async function captureTab(tabId, url) {
  const source = sourceForUrl(url);
  if (!source) throw new Error('Open a Facebook Marketplace or Kijiji results page first.');
  const page = await extractFromTab(tabId, 2);
  checkPage(page);
  const resp = await ingest(source, null, page.items);
  await addLog(`Captured ${page.items.length} listing(s) from ${source}`);
  return { source, found: page.items.length, stored: resp.stored, new_matches: resp.new_matches };
}

async function schedule() {
  const cfg = await getCfg();
  await chrome.alarms.clear('run');
  if (cfg.auto && cfg.serverUrl && cfg.token) {
    chrome.alarms.create('run', { delayInMinutes: 1, periodInMinutes: Math.max(MIN_INTERVAL, Number(cfg.intervalMin) || 30) });
  }
}

chrome.alarms.onAlarm.addListener((a) => { if (a.name === 'run') runAll(); });
chrome.runtime.onInstalled.addListener(schedule);
chrome.runtime.onStartup.addListener(schedule);
chrome.storage.onChanged.addListener((ch, area) => {
  if (area === 'local' && (ch.auto || ch.intervalMin || ch.serverUrl || ch.token)) schedule();
});
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    if (msg.type === 'run-now') return runAll();
    if (msg.type === 'capture-tab') return captureTab(msg.tabId, msg.url);
    if (msg.type === 'test') {
      const tasks = (await api('/api/extension/tasks')).tasks.length; // checks the token too
      const health = await api('/api/health');
      return { health, tasks };
    }
    return { error: 'Unknown message' };
  })().then(sendResponse, (e) => sendResponse({ error: e.message }));
  return true;
});

setState({ running: false, progress: '' }); // a service worker restart means no run is in progress
