# GEOINTEL frontend

The workstation reads coverage, country indicators, operational and UCDP observations, external model forecasts, and GEOINTEL assessments.

## Run locally

Use Node.js 22.12+ on the Node 22 line or Node.js 24+, and npm. From the repository root, install GEOINTEL and start the read-only ASGI application with an appropriate database:

```sh
python -m pip install -e '.[dev]'
uvicorn geointel.api.app:dashboard_app --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:5173/>. Vite forwards the same-origin `/api/v1/dashboard` prefix to the local read-only application. Set `GEOINTEL_DASHBOARD_ORIGIN` if it runs on another loopback port. Static builds need a same-origin gateway for that prefix. See the [isolation and review notes](../docs/DASHBOARD_RECONSTRUCTION.md) before selecting a database.

## Data modes

- **API mode** is the default. Global Overview shows coverage and a neutral country map. Country Intelligence scopes coverage and all five record series by ISO alpha-3. Risk Monitoring shows global operational and UCDP observations. Forecasts shows provider output and GEOINTEL assessments in separate panels. Global lists include records with non-country or unresolved geography. The API supplies dates and freshness, and provider target periods can expire independently of issuance freshness. Values and units come from stored records.
- **Demo mode** is available from the header or at `/?mode=demo`. It uses the inherited, labelled synthetic March 2025 frontend fixtures. It makes no API requests. The illustrative demo index and projections are confined to demo mode. The demo screenshots show this mode.

The dashboard API provides record availability and recency. Provider health, aggregate risk scores, provider uncertainty intervals, assessment target dates, and production briefings and chat have no dashboard contract. See the [API reference](../docs/DASHBOARD_API.md).

Country boundaries use [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/) data packaged by [World Atlas](https://github.com/topojson/world-atlas).

## Checks

```sh
npm run lint
npm run build
npx playwright install chromium
npm test
```

Set `GEOINTEL_CHROMIUM` to use an existing Chromium executable. The actual ASGI and PostgreSQL browser test requires the isolated fixture database and flags described in the [review instructions](../docs/DASHBOARD_RECONSTRUCTION.md).
