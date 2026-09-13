// Thin client for the real reguagent HTTP API (agent/api_server.py).
// Every function here maps 1:1 to a route defined in api_server.py's ROUTES table.
// No mock data anywhere in this file -- if the server is down or CORS-blocks the
// request, these calls reject and the UI shows an error, it does not fall back
// to fake data.

const IS_LOCAL = ['localhost', '127.0.0.1', ''].includes(location.hostname);

const Api = {
  // Local dev talks to the stdlib server on 8765. Deployed, this must point at
  // the Render backend's URL -- replace the placeholder below after creating
  // the Render web service (or call Api.configure(url, caseId) before use).
  base: IS_LOCAL ? 'http://127.0.0.1:8765' : 'https://REPLACE-WITH-YOUR-RENDER-BACKEND.onrender.com',
  caseId: null,
  mode: 'live',

  configure(base, caseId) {
    this.base = base.replace(/\/$/, '');
    this.caseId = caseId;
  },

  start(mode, goal) {
    this.mode = mode;
    return this._post('/api/cases/start', {
      mode,
      goal: goal || undefined,
      run: true,
      budget: Api.defaultBudget(mode),
    });
  },

  run() {
    return this._post(`/api/cases/${encodeURIComponent(this.caseId)}/run`, {
      budget: Api.defaultBudget(),
    });
  },

  defaultBudget(mode = this.mode) {
    if (mode === 'replay') {
      return {
        max_model_calls: 36,
        max_tool_calls: 70,
        max_delegations: 5,
        max_seconds: 180,
        max_request_tokens: 16000,
        max_output_tokens: 2400,
        min_request_interval: 0,
        tokens_per_minute: 0,
      };
    }
    return {
      max_model_calls: 4,
      max_tool_calls: 16,
      max_delegations: 3,
      max_seconds: 120,
      max_request_tokens: 9000,
      max_output_tokens: 1600,
      min_request_interval: 15,
      tokens_per_minute: 8000,
    };
  },

  async _get(path) {
    let res;
    try {
      res = await fetch(`${this.base}${path}`);
    } catch (err) {
      // A network-level failure here is very often CORS, not a bad URL --
      // api_server.py (as shipped) sends no Access-Control-Allow-Origin header,
      // so a fetch from a different origin/port is blocked by the browser
      // before it even reaches this code. See README.md.
      throw new Error(
        `Network error calling ${path}. If the API base is reachable in a new ` +
        `browser tab but fails here, this is almost certainly CORS -- ` +
        `api_server.py needs an Access-Control-Allow-Origin header added.`
      );
    }
    return Api._parse(res);
  },

  async _post(path, body) {
    let res;
    try {
      res = await fetch(`${this.base}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
      });
    } catch (err) {
      throw new Error(`Network error calling ${path}. See CORS note in README.md.`);
    }
    return Api._parse(res);
  },

  async _parse(res) {
    let data;
    try {
      data = await res.json();
    } catch (err) {
      throw new Error(`Server returned a non-JSON response (status ${res.status}).`);
    }
    if (!res.ok) {
      // api_server.py's error shape: { error: "...", message: "..." }
      throw new Error(data.message || data.error || `Request failed (${res.status})`);
    }
    return data;
  },

  // GET /api/cases/:case_id
  overview() {
    return this._get(`/api/cases/${encodeURIComponent(this.caseId)}`);
  },

  cases() {
    return this._get('/api/cases');
  },

  decisionView() {
    return this._get(`/api/cases/${encodeURIComponent(this.caseId)}/decision-view`);
  },

  // GET /api/cases/:case_id/investigation
  investigation() {
    return this._get(`/api/cases/${encodeURIComponent(this.caseId)}/investigation`);
  },

  // GET /api/cases/:case_id/plans
  plans() {
    return this._get(`/api/cases/${encodeURIComponent(this.caseId)}/plans`);
  },

  // GET /api/cases/:case_id/evidence
  evidence() {
    return this._get(`/api/cases/${encodeURIComponent(this.caseId)}/evidence`);
  },

  // GET /api/cases/:case_id/audit
  audit() {
    return this._get(`/api/cases/${encodeURIComponent(this.caseId)}/audit`);
  },

  // GET /api/cases/:case_id/queue
  queue() {
    return this._get(`/api/cases/${encodeURIComponent(this.caseId)}/queue`);
  },

  // POST /api/cases/:case_id/queue/:item_id/resolve
  // item_id is the full "section:key" string from a queue item's `id` field --
  // it must be URL-encoded because it can itself contain '/' and ':'.
  resolve(itemId, body) {
    return this._post(
      `/api/cases/${encodeURIComponent(this.caseId)}/queue/${encodeURIComponent(itemId)}/resolve`,
      body
    );
  },

  // POST /api/cases/:case_id/evidence
  // Server expects: action_key, evidence_slot, evidence_type, submitted_by_role_id,
  // filename, content_base64. The file itself is base64-encoded JSON, not multipart.
  async submitEvidence({ actionKey, evidenceSlot, evidenceType, submittedByRoleId, file }) {
    const contentBase64 = await Api._fileToBase64(file);
    return this._post(`/api/cases/${encodeURIComponent(this.caseId)}/evidence`, {
      action_key: actionKey,
      evidence_slot: evidenceSlot,
      evidence_type: evidenceType,
      submitted_by_role_id: submittedByRoleId,
      filename: file.name,
      content_base64: contentBase64,
    });
  },

  _fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        // reader.result is "data:<mime>;base64,<data>" -- strip the prefix.
        const base64 = reader.result.split(',')[1];
        resolve(base64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  },
};

// Exposed on window explicitly -- top-level `const` does not become a window
// property on its own (unlike `var` or function declarations), and this object
// is useful to reach from devtools or test harnesses.
window.Api = Api;
