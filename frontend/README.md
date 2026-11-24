# GEOINTEL website

Static site (Vite + TypeScript, D3 map) showing the daily global risk snapshot in Russian and
English: probability map by event type and horizon, country details with 90% ranges, changes
since the previous data update and since the visitor's last visit (kept in the browser),
method and sources.

The site reads `data/risk.json` (schema `geointel-risk-snapshot-v1`, see
`docs/RISK_ENGINE.md`). In production the Risk snapshot workflow copies the latest snapshot
into the build and deploys to GitHub Pages.

## Run locally

```sh
cd frontend
npm ci
cp /path/to/risk.json public/data/risk.json   # e.g. from the risk-data branch
npm run dev
```

## Checks

```sh
npm run build
npx playwright install chromium
npm test   # serves the dev server with a fixture snapshot
```

Boundaries: Natural Earth via World Atlas.
