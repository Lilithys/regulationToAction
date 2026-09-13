# Temporary demo deployment

The user authorized deployment with disposable storage on 2026-09-13.

## Netlify deployment

The user selected a public Netlify frontend with disposable Render storage.
The current frontend URL is https://regulation2action.netlify.app.
The Netlify project dashboard is https://app.netlify.com/projects/regulation2action.

Deployment completed on 2026-09-13. The complete six-file frontend was published
through Netlify Drop, replacing an incomplete HTML-only upload. All six live
assets return HTTP 200 and match the validated local source byte-for-byte.
Published deploy: `6aa666a55a330d9194e4bc56`.

Render now permits `https://regulation2action.netlify.app` through
`CORS_ALLOW_ORIGIN`. Health and case-list requests returned HTTP 200, and POST
preflight returned HTTP 204 with the correct origin and allowed methods.

### Publishing updates

The current Netlify project uses manual Netlify Drop uploads. GitHub integration
is not connected because its authorization flow returned server errors. Code is
preserved in the personal fork on `deploy/temporary-demo`; a Git push alone does
not update this Netlify site.

Run `python3 frontend_v2/build_static.py` from the repository root, then upload
**the entire `frontend_v2/dist` folder** to the existing Netlify project's
Production deploys area. Alternatively, upload a ZIP containing all six assets
at its root. Uploading `index.html` alone omits the stylesheet and application.

Only these files belong in the published output: `index.html`, `styles.css`,
`icons.js`, `display_text.js`, `api.js` and `app.js`. Do not upload documentation,
tests, backend files, databases or the Sites hosting manifest.

For future Git-connected builds, the root `netlify.toml` defines:

- Repository: `Lilithys/regulationToAction`.
- Production branch: `deploy/temporary-demo` (select in the Netlify dashboard).
- Base directory: `frontend_v2`.
- Build command: `python3 build_static.py`.
- Publish directory: `dist`, relative to the base directory.

The previous Sites project is retained privately as a historical deployment.
It is no longer the demo entry point; the API's CORS origin now targets Netlify.

## Source and deployment branch

- Original repository: https://github.com/Ruigithu/regulationToAction (read-only).
- Personal fork: https://github.com/Lilithys/regulationToAction.
- Deployment branch: `deploy/temporary-demo`.
- Render backend: https://regulation-to-action-demo-api.onrender.com.
- Render dashboard: https://dashboard.render.com/web/srv-daj5m2u7bikc73aqoal0.
- Frontend: https://regulation2action.netlify.app.
- Local remote `origin` still points to the original repository; `personal`
  points to the fork. Render uses the personal branch; Netlify currently uses manual uploads.

## Runtime

- Frontend: public static assets hosted through Netlify. Publish only `index.html`,
  `styles.css`, `icons.js`, `display_text.js`, `api.js` and `app.js`.
- Backend: one Render Free Python web service, configured in `render.yaml`.
- Start command: `python agent/serve_demo.py`, from `reguagent-main`.
- Runtime database: `/tmp/regulation-to-action-demo/cases.sqlite3`.
- Uploaded evidence: `/tmp/regulation-to-action-demo/evidence_artifacts`.
- Health endpoint: `/api/health`.
- No persistent disk, production records or model credentials are required.
  The deployed API accepts replay mode only.

`serve_demo.py` atomically creates two replay cases when the database is empty:
one full investigation awaiting a business answer, and one reviewed-request
summary awaiting action acceptance. Existing cases are preserved while the
temporary database exists. A storage reset recreates the starting cases.

Render Free services sleep after 15 minutes without inbound traffic and may
restart. Runtime database changes and uploads are lost on restart, redeploy or
sleep. The next wake-up takes about a minute. See
[Render Free limitations](https://render.com/docs/free).

## Release procedure

1. Validate and push this branch to the personal fork.
2. Create the Render service from that branch, explicitly selecting Free and no
   disk. Use the root/build/start/health settings in `render.yaml`.
3. Set the frontend's API URL to the actual Render HTTPS URL, publish its static
   assets, and set `CORS_ALLOW_ORIGIN` to the frontend origin if appropriate.
4. Verify the health endpoint, seeded cases, queue operations and static assets.
   The user authorized a public frontend. Backend data is disposable synthetic
   demo data; its API is not an authenticated multi-user production service.

Redeployment can reset the hosted demo. Local historical case databases are not
uploaded or rewritten by the bootstrap.

## English display

Legacy replay prose is translated only in frontend GET projections; raw audit
history, identifiers and POST bodies remain unchanged. New replay output is
English. Unknown user-supplied text remains verbatim. Live prompts request English,
but live model calls are disabled in this disposable deployment.

## Validation

- The Netlify production site serves all six assets with HTTP 200 and exact
  local-source matches. Browser checks confirmed the English case registry,
  case overview, queue and action-acceptance form, plans/actions, and audit log.
  No human decisions were submitted during validation.
- Render health, two-case registry and POST preflight checks pass with the
  Netlify origin after the CORS configuration deployment.
- Six frontend checks, five disposable-demo checks and 21 existing interface
  tests passed locally.
- The deployed backend passed health, two-case registry, 14 view projection,
  English-content, CORS/preflight and replay-only enforcement checks.
- Sites version 1 published the validated six frontend assets successfully.

Run from the repository root:

```bash
node --test frontend_v2/tests/display_text.test.js
python3 frontend_v2/build_static.py
python3 -m unittest discover -s reguagent-main/agent -p 'test_serve_demo.py'
python3 -m unittest discover -s reguagent-main/agent -p 'test_m5_interface.py'
```

The earlier language audit checked all eight local historical cases across seven
projections plus the case list (15,699 text values). No Chinese remained after
display conversion, and the original database checksum and audit chains were
unchanged.
