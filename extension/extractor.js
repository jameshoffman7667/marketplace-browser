// Page extraction, injected into a marketplace results page with chrome.scripting.executeScript.
// IMPORTANT: extractPage is serialised and run inside the page, so it must stay fully self-contained
// (no references to anything outside the function body).
//
// Facebook and Kijiji change their markup often and use obfuscated class names, so the adapters
// anchor on stable things (item URLs, data-testid attributes) and read visible text lines.

export async function extractPage(opts) {
  const o = Object.assign({ scrolls: 3, waitMs: 1500, maxItems: 150 }, opts || {});
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const host = location.hostname;
  const out = { url: location.href, host, adapter: '', items: [], warnings: [], loginRequired: false };

  const PRICE = /(CA|US|C|A)?\$\s?(\d[\d,]*(?:\.\d{1,2})?)/;
  const FREE = /^free$/i;
  const parsePrice = (line) => {
    if (FREE.test(line)) return { price: 0, currency: '' };
    const m = line.match(PRICE);
    if (!m) return null;
    const cur = m[1] === 'CA' || m[1] === 'C' ? 'CAD' : m[1] === 'US' ? 'USD' : '';
    return { price: Number(m[2].replace(/,/g, '')), currency: cur };
  };
  // One "line" per element that directly holds text. More reliable than innerText on card markup,
  // where price, title and location are often inline spans with no line breaks between them.
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'svg']);
  const linesOf = (root) => {
    const lines = [];
    const walk = (el) => {
      if (SKIP.has(el.tagName)) return;
      let own = '';
      for (const n of el.childNodes) if (n.nodeType === 3) own += n.nodeValue;
      own = own.replace(/\s+/g, ' ').trim();
      if (own) lines.push(own);
      for (const c of el.children) walk(c);
    };
    walk(root);
    return lines;
  };
  const looksLikeLocation = (s) => /,\s*[A-Z]{2}\b/.test(s) || /^[A-Z][\w .'-]+,\s*[A-Z][\w .'-]+$/.test(s);
  const firstImg = (el) => {
    const img = el.querySelector('img[src^="http"]');
    return img ? img.currentSrc || img.src : '';
  };

  // Turn the visible text lines of a card into title / price / location.
  const fromLines = (lines, loose) => {
    let price = null, currency = '';
    const rest = [];
    for (const ln of lines) {
      const p = parsePrice(ln);
      if (p && price === null && ln.length <= 24) { price = p.price; currency = p.currency; continue; }
      if (p && ln.length <= 24) continue; // old / crossed-out price
      rest.push(ln);
    }
    // loose: accept a bare city name as the second line (Kijiji); Facebook's second line may be mileage etc.
    const location = rest.find(looksLikeLocation) || (loose && rest.length > 1 ? rest[1] : '');
    const title = rest.find((s) => s !== location) || '';
    return { title, price, currency, location };
  };

  const found = new Map();
  const add = (it) => {
    if (!it.id || found.has(it.id) || !it.title) return;
    found.set(it.id, it);
  };

  const facebook = () => {
    out.adapter = 'facebook';
    for (const a of document.querySelectorAll('a[href*="/marketplace/item/"]')) {
      const m = (a.getAttribute('href') || '').match(/\/marketplace\/item\/(\d+)/);
      if (!m) continue;
      const t = fromLines(linesOf(a));
      add({ id: m[1], url: 'https://www.facebook.com/marketplace/item/' + m[1] + '/', image: firstImg(a), ...t });
    }
  };

  const kijiji = () => {
    out.adapter = 'kijiji';
    const cards = document.querySelectorAll('[data-testid="listing-card"], [data-listing-id], li[data-testid^="listing"]');
    const handle = (card) => {
      const a = card.matches('a[href]') ? card : card.querySelector('a[href*="/v-"]');
      if (!a) return;
      const href = new URL(a.getAttribute('href'), location.href);
      const m = href.pathname.match(/\/(\d{6,})\/?$/);
      const id = (card.getAttribute && card.getAttribute('data-listing-id')) || (m && m[1]);
      if (!id) return;
      const q = (sel) => { const e = card.querySelector(sel); return e ? e.innerText.trim() : ''; };
      let title = q('[data-testid="listing-title"]');
      let priceLine = q('[data-testid="listing-price"]');
      let place = q('[data-testid="listing-location"]');
      let price = null, currency = '';
      if (priceLine) { const p = parsePrice(priceLine); if (p) { price = p.price; currency = p.currency; } }
      if (!title || (price === null && !priceLine)) {
        const t = fromLines(linesOf(card), true);
        title = title || t.title;
        if (price === null) { price = t.price; currency = t.currency; }
        place = place || t.location;
      }
      add({ id, url: href.origin + href.pathname, image: firstImg(card), title, price, currency, location: place });
    };
    if (cards.length) cards.forEach(handle);
    else for (const a of document.querySelectorAll('a[href*="/v-"]')) handle(a);
  };

  const collect = () => {
    if (host.endsWith('facebook.com')) facebook();
    else if (host.endsWith('kijiji.ca')) kijiji();
    else { out.adapter = 'none'; }
  };

  collect();
  for (let i = 0; i < o.scrolls && found.size < o.maxItems; i++) {
    window.scrollTo(0, document.documentElement.scrollHeight);
    await sleep(o.waitMs);
    collect();
  }
  window.scrollTo(0, 0);

  out.items = [...found.values()].slice(0, o.maxItems);
  if (out.adapter === 'none') out.warnings.push('This site is not supported by the extension yet.');
  if (!out.items.length) {
    const loggedOut =
      location.pathname.startsWith('/login') ||
      !!document.querySelector('input[name="pass"], form[action*="login"], [data-testid="royal_login_form"]');
    if (loggedOut) { out.loginRequired = true; out.warnings.push('Not signed in on this site.'); }
    else out.warnings.push('No listings recognised on this page (the site layout may have changed).');
  }
  return out;
}
