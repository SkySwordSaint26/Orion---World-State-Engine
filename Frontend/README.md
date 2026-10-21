# React + TypeScript + Vite

## Local API connection

Start the backend on `127.0.0.1:8000` and run `npm run dev` here. API requests use
`/api/v1` on the frontend's own origin; Vite forwards them to the backend, including
when Vite selects port 5174 because 5173 is occupied. Sign-in requests time out after
15 seconds with a retryable error instead of hiding the form indefinitely.
If `VITE_API_BASE_URL` is set, Vite uses it as the proxy target during development.

For a deployment with a separate API origin, set `VITE_API_BASE_URL` at build time
and allow that frontend origin in the backend's CORS configuration.

## Browser regression tests

Run `npm install`, then `npx playwright install chromium` and `npm run test:e2e`.
The suite starts Vite and supplies isolated API fixtures; it never writes to a real world database.
It covers ledger event counts, entity-card relationships, graph connections, chapter text selections,
and page navigation. Set `PLAYWRIGHT_CHANNEL=msedge` to use an installed Microsoft Edge browser.

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
