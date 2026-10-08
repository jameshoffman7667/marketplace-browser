# Third-party Facebook Marketplace scrapers: options (researched 2026-10-07)

Status: research from 2026-10-07. The Apify option was integrated in v0.3 (tested against a fake Apify API only); the others are not integrated. Nothing was tested live. Prices and features come from vendor pages and one vendor-authored comparison, and change often; re-check before buying.

## Why consider it

The v0.1/v0.2 extension reads Facebook Marketplace from your own signed-in browser. That needs the browser open, risks your Facebook account if run too often, and depends on page markup. A hosted scraper would run on a schedule from the server with no browser. The trade-off is cost, a third party handling your searches, and no control over reliability.

## Options

| Option | What it is | Fit for this app |
| --- | --- | --- |
| Bright Data, Web Scraper API for Facebook Marketplace | Managed scraper; you send a search/URL and get structured listings back (API or dataset). Documented at docs.brightdata.com. Pay per record/request | Most robust and best documented; most expensive and enterprise-oriented. Meta v. Bright Data (Jan 2024) went Bright Data's way for public, logged-out data, but that is not legal advice for your use |
| Apify actors (`apify/facebook-marketplace-scraper`, `raidr-api/facebook-marketplace-scraper`) | Pay-per-result or per-run actors on Apify; run via REST API, scheduling built in | Easiest to try (free credit tier, simple API). Quality varies by actor author; listed prices conflicted between pages, so confirm on the actor page |
| Secondhand MCP (`jlsookiki/secondhand-mcp`, secondhandmcp.com) | MCP server for searching Facebook Marketplace and other secondhand sites from an AI client | Assumed to be what you meant by "secondhand". Built for conversational use, not scheduled polling; a poor fit for a server that polls saved searches |
| ScrapeCreators, Swoopa and similar | Marketplace-focused APIs or alert services | ScrapeCreators is an API (fits). Swoopa is a finished alert product, so it replaces this app rather than feeding it |

## How it plugs in (built for Apify in v0.3)

The app already has an ingest path. A new optional source type `provider` would, on each poll, call the vendor with the saved search keywords plus the global location and radius, map the returned records to the ingest format (id, url, title, price, image, location, lat/lon if given), and reuse baselining, dedupe and alerts unchanged. API key stored like the SMTP password. Off by default, with a per-day request cap so a bad interval cannot run up a bill.

## Cost model

Cost is roughly: searches x polls per day x 30 x records or requests per poll x vendor unit price. Per-record pricing punishes frequent polling of broad searches (the same listings are paid for every time); per-request pricing is steadier. For example, 10 searches polled every 30 minutes is 480 polls a day, about 14,400 a month. Multiply by the unit price on the vendor's page. Polling hourly and keeping searches narrow cuts this in half or better.

## Recommendation

Keep the extension as the default (free). If you want no browser dependency, prototype with an Apify actor first (cheapest to test, a few dollars of credit), and move to Bright Data only if reliability matters more than cost. Skip Secondhand MCP for this purpose. Before building v0.3, run one real search through the chosen vendor and check that results include stable listing IDs and location.

## Caveats

- The comparison article used was written by a vendor (ScrapeCreators) and is not neutral.
- Apify pricing for the two actors differed between sources.
- Terms of service: Facebook's terms prohibit automated collection; using a third party shifts who does it, not whether it is against the terms. Personal use only.
- Nothing was run against any of these services.

## Sources

- https://scrapecreators.com/blog/facebook-marketplace-api-tools
- https://brightdata.com/products/web-scraper/facebook/marketplace
- https://docs.brightdata.com/products/scrapers/facebook/introduction
- https://apify.com/apify/facebook-marketplace-scraper
- https://apify.com/raidr-api/facebook-marketplace-scraper
- https://github.com/jlsookiki/secondhand-mcp
- https://secondhandmcp.com/marketplaces/facebook-marketplace
- https://getswoopa.com
- https://scrapecreators.com
- https://www.zyte.com/blog/california-court-meta-ruling/
