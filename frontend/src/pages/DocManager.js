import React, { useState, useEffect } from 'react';
import {
  scanRepo,
  getRoutes,
  generateApiDoc,
  generateApiDocTargeted,
} from '../api';

const MethodBadge = ({ method }) => (
  <span className={`method-badge method-${(method || 'GET').toUpperCase()}`}>
    {(method || 'GET').toUpperCase()}
  </span>
);

/**
 * DocManager
 *
 * Props:
 *   resolvedRepo   – { id?, name?, web_url } — may be null
 *   sessionCreds   – { repoUrl, token } — carried from Setup, never empty if user filled them
 *   onOpenDoc      – navigate to DocDetail
 *   getCachedRoutes / onCacheRoutes
 */
export default function DocManager({
  resolvedRepo,
  sessionCreds = { repoUrl: '', token: '' },
  onOpenDoc,
  getCachedRoutes,
  onCacheRoutes,
}) {
  // ── Mode ──────────────────────────────────────────────────────────────────
  const [mode, setMode] = useState('targeted'); // 'targeted' | 'fullscan'

  // ── Targeted mode: only the search hint fields; repo+PAT come from session ─
  // Allow user to override if sessionCreds is empty
  const needsCredentials = !sessionCreds.repoUrl || !sessionCreds.token;
  const [repoUrlOverride, setRepoUrlOverride] = useState('');
  const [tokenOverride, setTokenOverride] = useState('');

  const effectiveRepoUrl = needsCredentials ? repoUrlOverride : sessionCreds.repoUrl;
  const effectiveToken = needsCredentials ? tokenOverride : sessionCreds.token;

  const [controllerFile, setControllerFile] = useState('');
  const [endpointName, setEndpointName] = useState('');
  const [targetLoading, setTargetLoading] = useState(false);
  const [targetResult, setTargetResult] = useState(null);

  // ── Full-scan mode ────────────────────────────────────────────────────────
  const [scan, setScan] = useState(null);
  const [routes, setRoutes] = useState(
    resolvedRepo?.id ? getCachedRoutes(resolvedRepo.id) : null
  );
  const [scanLoading, setScanLoading] = useState(false);
  const [generating, setGenerating] = useState({});
  const [generatedDocs, setGeneratedDocs] = useState({});
  const [wholeFileMode, setWholeFileMode] = useState(false);

  const [error, setError] = useState('');

  // Auto-trigger full scan when switching to that mode
  useEffect(() => {
    if (mode === 'fullscan' && resolvedRepo?.id && !routes) {
      runFullScan(false);
    }
  }, [mode, resolvedRepo?.id]); // eslint-disable-line

  // ── Validation ────────────────────────────────────────────────────────────
  const targetedValid =
    effectiveRepoUrl.trim() &&
    effectiveToken.trim() &&
    (controllerFile.trim() || endpointName.trim());

  // ── Targeted generate ─────────────────────────────────────────────────────
  const handleTargetedGenerate = async () => {
    setError('');
    setTargetResult(null);
    setTargetLoading(true);
    try {
      const result = await generateApiDocTargeted(
        effectiveRepoUrl.trim(),
        effectiveToken.trim(),
        controllerFile.trim(),
        endpointName.trim()
      );
      setTargetResult(result);
      if (result.results?.length === 1) {
        const doc = result.results[0];
        onOpenDoc({ ...doc, endpoint: doc.endpoint, repo: resolvedRepo, type: 'api' });
      }
    } catch (e) {
      setError('Generation failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setTargetLoading(false);
    }
  };

  // ── Full-scan ─────────────────────────────────────────────────────────────
  const runFullScan = async (forceRescan = false) => {
    if (!resolvedRepo?.id) {
      setError('No project linked. Provide a repo URL during setup, then use Full Scan.');
      return;
    }
    setScanLoading(true);
    setError('');
    setRoutes(null);
    try {
      const s = await scanRepo(resolvedRepo.id, forceRescan);
      setScan(s);
      const r = await getRoutes(resolvedRepo.id, false, forceRescan);
      setRoutes(r);
      onCacheRoutes(resolvedRepo.id, r);
    } catch (e) {
      setError('Scan failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setScanLoading(false);
    }
  };

  const runWholeFileMode = async () => {
    if (!resolvedRepo?.id) return;
    setScanLoading(true);
    setError('');
    try {
      const r = await getRoutes(resolvedRepo.id, true);
      setRoutes(r);
      onCacheRoutes(resolvedRepo.id, r);
      setWholeFileMode(true);
    } catch (e) {
      setError('Whole-file mode failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setScanLoading(false);
    }
  };

  const generateFromScan = async (endpoint, idx) => {
    setGenerating((g) => ({ ...g, [idx]: true }));
    try {
      const doc = await generateApiDoc(endpoint, resolvedRepo.id);
      setGeneratedDocs((d) => ({ ...d, [idx]: doc }));
    } catch (e) {
      setError('Generate failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setGenerating((g) => ({ ...g, [idx]: false }));
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div>
      {error && (
        <div className="error-banner" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* Mode selector */}
      <div className="mode-selector">
        <button
          className={`mode-btn ${mode === 'targeted' ? 'active' : ''}`}
          onClick={() => setMode('targeted')}
        >
          🎯 Path / Endpoint Specific
        </button>
        <button
          className={`mode-btn ${mode === 'fullscan' ? 'active' : ''}`}
          onClick={() => setMode('fullscan')}
        >
          🔍 Full Repo Scan
        </button>
      </div>

      {/* ══ TARGETED MODE ═════════════════════════════════════════════════════ */}
      {mode === 'targeted' && (
        <div className="targeted-panel">
          <div className="card">
            {/* Connected repo badge */}
            {!needsCredentials && (
              <div className="session-badge">
                <span className="session-dot" />
                <span>
                  Connected to{' '}
                  <code>{effectiveRepoUrl.replace(/^https?:\/\/[^/]+\//, '')}</code>
                </span>
              </div>
            )}

            {/* Only show creds fields if session didn't carry them */}
            {needsCredentials && (
              <>
                <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>
                  Repository Access
                </h3>
                <div className="form-group">
                  <label className="label">
                    Repository URL <span className="required-star">*</span>
                  </label>
                  <input
                    className="input"
                    type="url"
                    placeholder="https://scm.intermesh.net/group/project"
                    value={repoUrlOverride}
                    onChange={(e) => setRepoUrlOverride(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label className="label">
                    GitLab PAT <span className="required-star">*</span>
                  </label>
                  <input
                    className="input"
                    type="password"
                    placeholder="glpat-xxxxxxxxxxxxxxxxxxxx"
                    value={tokenOverride}
                    onChange={(e) => setTokenOverride(e.target.value)}
                  />
                </div>
                <div className="form-divider" />
              </>
            )}

            <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
              Find by Controller File or Endpoint
            </h3>
            <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 16 }}>
              Provide the relative path to the controller file <em>or</em> the endpoint
              name/path — DocForge will search the repo and generate accurate docs using
              route + model files.
            </p>

            {/* Controller file */}
            <div className="form-group">
              <label className="label">
                Controller / Handler File Path{' '}
                <span style={{ color: 'var(--text2)', fontWeight: 400 }}>
                  (optional if Endpoint Name given)
                </span>
              </label>
              <input
                className="input"
                type="text"
                placeholder="e.g. controllers/smsController.go  or  internal/handler/mail.php"
                value={controllerFile}
                onChange={(e) => setControllerFile(e.target.value)}
              />
              <p className="field-hint">
                Relative path from repo root. Partial names work (e.g. <code>smsController</code>).
              </p>
            </div>

            {/* Endpoint name */}
            <div className="form-group">
              <label className="label">
                Endpoint Name / Path{' '}
                <span style={{ color: 'var(--text2)', fontWeight: 400 }}>
                  (optional if Controller File given)
                </span>
              </label>
              <input
                className="input"
                type="text"
                placeholder="e.g. /sms  or  sendSms  or  /esn/process"
                value={endpointName}
                onChange={(e) => setEndpointName(e.target.value)}
              />
              <p className="field-hint">
                Used to find the file in the repo and filter which endpoint to document.
              </p>
            </div>

            {!targetedValid && (
              <div className="info-hint">
                ℹ️ {needsCredentials
                  ? 'Fill in Repo URL, GitLab PAT, and at least one of Controller File or Endpoint Name.'
                  : 'Fill in at least one of Controller File or Endpoint Name.'}
              </div>
            )}

            <button
              className="btn btn-primary btn-glow"
              onClick={handleTargetedGenerate}
              disabled={targetLoading || !targetedValid}
              style={{ width: '100%', justifyContent: 'center', marginTop: 4 }}
            >
              {targetLoading ? (
                <><span className="spinner" /> Searching & Generating…</>
              ) : (
                '⚡ Generate Doc'
              )}
            </button>
          </div>

          {/* Results */}
          {targetResult && (
            <div style={{ marginTop: 16 }}>
              {targetResult.search_log?.length > 0 && (
                <div className="search-trace">
                  <div className="search-trace-title">🔍 Search trace</div>
                  {targetResult.search_log.map((line, i) => (
                    <div key={i}>{line}</div>
                  ))}
                  {targetResult.resolved_file && (
                    <div style={{ marginTop: 6, color: 'var(--green)' }}>
                      ✓ File used: <strong>{targetResult.resolved_file}</strong>
                    </div>
                  )}
                </div>
              )}

              <div style={{ fontSize: 14, color: 'var(--text2)', marginBottom: 12 }}>
                Found <strong>{targetResult.endpoints_found}</strong> endpoint(s) in{' '}
                <code>{targetResult.resolved_file || targetResult.file_path}</code>
              </div>

              <div className="endpoint-list">
                {targetResult.results?.map((doc, idx) => (
                  <div key={idx} className="endpoint-item">
                    <MethodBadge method={doc.endpoint?.method} />
                    <span className="endpoint-path">
                      {doc.endpoint?.path || endpointName || '/endpoint'}
                    </span>
                    <span className="endpoint-handler">{doc.endpoint?.handler_name}</span>
                    <span
                      style={{
                        fontSize: 15,
                        fontWeight: 700,
                        color:
                          doc.score?.score_percent >= 70
                            ? 'var(--green)'
                            : doc.score?.score_percent >= 40
                            ? 'var(--amber)'
                            : 'var(--red)',
                      }}
                    >
                      {doc.score?.score_percent ?? '?'}%
                    </span>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() =>
                        onOpenDoc({ ...doc, endpoint: doc.endpoint, repo: resolvedRepo, type: 'api' })
                      }
                    >
                      View Doc
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ══ FULL SCAN MODE ════════════════════════════════════════════════════ */}
      {mode === 'fullscan' && (
        <div>
          {!resolvedRepo?.id ? (
            <div className="empty-state">
              <div className="empty-icon">🔗</div>
              <div className="empty-title">No project linked</div>
              <p style={{ marginBottom: 16 }}>
                Full repo scan requires a project ID. Provide a repo URL on the Setup
                screen so DocForge can resolve the project.
              </p>
              <button className="btn btn-primary" onClick={() => setMode('targeted')}>
                Switch to Targeted Mode
              </button>
            </div>
          ) : scanLoading ? (
            <div style={{ textAlign: 'center', padding: 60, color: 'var(--text2)' }}>
              <span className="spinner" style={{ width: 24, height: 24, borderWidth: 3 }} />
              <p style={{ marginTop: 12 }}>
                Scanning <strong>{resolvedRepo.name || 'repo'}</strong> for API routes…
              </p>
              {scan && (
                <p style={{ marginTop: 4, fontSize: 12 }}>
                  Found {(scan.go_files || 0) + (scan.php_files || 0)} source files
                </p>
              )}
            </div>
          ) : routes?.no_routes_detected ? (
            <div className="empty-state">
              <div className="empty-icon">🔍</div>
              <div className="empty-title">No API routes detected</div>
              <p style={{ marginBottom: 16 }}>
                Standard router patterns (Gin, Echo, Chi, Laravel) were not found.
              </p>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
                <button className="btn btn-secondary" onClick={runWholeFileMode}>
                  Try Whole-File Mode
                </button>
                <button className="btn btn-primary" onClick={() => setMode('targeted')}>
                  Switch to Targeted Mode
                </button>
              </div>
            </div>
          ) : routes?.endpoints?.length > 0 ? (
            <div>
              {wholeFileMode && (
                <div className="warning-bar">Using whole-file context mode – parser fallback active</div>
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <span style={{ fontSize: 14, color: 'var(--text2)' }}>
                  <strong style={{ color: 'var(--text1)' }}>{routes.endpoints.length}</strong>{' '}
                  unique endpoint{routes.endpoints.length !== 1 ? 's' : ''} ·{' '}
                  {routes.language} / {routes.framework}
                </span>
                <button className="btn btn-secondary btn-sm" onClick={() => runFullScan(true)}>
                  ↺ Rescan
                </button>
              </div>
              <div className="endpoint-list">
                {routes.endpoints.map((ep, idx) => (
                  <div key={idx} className="endpoint-item">
                    <MethodBadge method={ep.method} />
                    <span className="endpoint-path">{ep.path}</span>
                    <span className="endpoint-handler">{ep.handler_name}</span>
                    {generatedDocs[idx] ? (
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span
                          style={{
                            fontSize: 16,
                            fontWeight: 700,
                            color:
                              generatedDocs[idx].score?.score_percent >= 70
                                ? 'var(--green)'
                                : generatedDocs[idx].score?.score_percent >= 40
                                ? 'var(--amber)'
                                : 'var(--red)',
                          }}
                        >
                          {generatedDocs[idx].score?.score_percent ?? '?'}%
                        </span>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() =>
                            onOpenDoc({ ...generatedDocs[idx], endpoint: ep, repo: resolvedRepo, type: 'api' })
                          }
                        >
                          View
                        </button>
                      </div>
                    ) : (
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={() => generateFromScan(ep, idx)}
                        disabled={generating[idx]}
                      >
                        {generating[idx] ? <><span className="spinner" /> Generating…</> : 'Generate'}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <button className="btn btn-primary" onClick={() => runFullScan(false)}>
                🔍 Scan Repository
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}