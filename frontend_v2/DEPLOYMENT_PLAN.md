# Temporary demo deployment

The user authorized deployment with disposable storage on 2026-09-13.

Deployment completed on 2026-09-13: Render reports the backend live and Sites
reports frontend version 1 published successfully with owner-only access.
The frontend requires signing in with the owner's ChatGPT account.

## Source and deployment branch

- Original repository: https://github.com/Ruigithu/regulationToAction (read-only).
- Personal fork: https://github.com/Lilithys/regulationToAction.
- Deployment branch: `deploy/temporary-demo`.
- Render backend: https://regulation-to-action-demo-api.onrender.com.
- Render dashboard: https://dashboard.render.com/web/srv-daj5m2u7bikc73aqoal0.
- Frontend: https://northstar-regulation-demo.yishanmai330.chatgpt.site.
- Local remote `origin` still points to the original repository; `personal`
  points to the fork. Deployments use the personal branch.

## Runtime

- Frontend: static assets hosted through Sites. Publish only `index.html`,
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
   Keep the frontend private by default. Backend data is disposable synthetic
   demo data; its API is not an authenticated multi-user production service.

Redeployment can reset the hosted demo. Local historical case databases are not
uploaded or rewritten by the bootstrap.

## English display

Legacy replay prose is translated only in frontend GET projections; raw audit
history, identifiers and POST bodies remain unchanged. New replay output is
English. Unknown user-supplied text remains verbatim. Live prompts request English,
but live model calls are disabled in this disposable deployment.

## Validation

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
