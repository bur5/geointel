# GEOINTEL frontend v0.1

A local intelligence workstation for navigating country coverage, risk monitoring, forecasts, briefings, and a scripted analyst conversation.

## Run locally

Requirements are Node.js 22.12+ on the Node 22 line or Node.js 24+, and npm.

```sh
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5173/>. Select a country on the map or in the country panel. The zoom controls increase or decrease zoom and reset the viewport. Drag the map or focus it and use the arrow keys to pan. Navigation links support browser history and direct linking, such as `/#briefings`.

For a local preview of the production build, run `npm run build` followed by `npm run preview` and open <http://127.0.0.1:4173/>. The preview server can use the same local forecast proxy.

## Data modes

- **Demo mode** is the default. It loads no backend data. The fixed March 2025 fixture covers eight countries and includes six monthly readings per country, scripted event records, and a subset of illustrative one-month projections. Its 0–100 score is an illustrative index without a probability interpretation. Breakpoints are 45 for Elevated and 70 for High. Country and time filters apply to the fixture. Forecast bounds are illustrative and confidence is unavailable. Scripted chat history is kept in memory for the current page session.
- **API mode** can be selected in the header or opened directly at `/?mode=api#forecasts`. Start the backend using the repository root README and expose FastAPI on loopback port 8000. The frontend's local proxy forwards its forecast request to the verified `GET /forecasts` route. The client validates the response and preserves the forecast ID, analysis run ID, horizon, version, timestamp, probability bounds, confidence, and evidence text. Missing bounds are shown as unavailable. Empty results, failed requests, and invalid responses have explicit states.
- Country coverage, map risk, monitoring, briefings, and chat need compatible read-only APIs. Current API forecasts are a collection without geographic identifiers in the forecast response, so the prototype does not link those records to countries. Forecast records expose evidence text and run IDs. Canonical source-level citations require an additional provenance contract. Scenario simulation is outside this prototype.

Boundaries use [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/) data packaged by [World Atlas](https://github.com/topojson/world-atlas), rendered with D3 Geo and TopoJSON. Boundaries provide geographic context and are not evidence of country-level data coverage.

## Checks

```sh
npm run lint
npm run build
npx playwright install chromium
npm test
```

To use an existing Chromium binary, set `GEOINTEL_CHROMIUM` to its absolute path. Browser tests intercept requests to exercise API success, empty results and failure paths independently of backend services. The production build consists of static assets. API mode in any other local serving environment requires a same-origin mapping from `/geointel-api/forecasts` to FastAPI's `/forecasts`.

## Screenshots

- [Desktop overview](screenshots/overview.png)
- [Mobile overview](screenshots/overview-mobile.png)
