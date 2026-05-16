import React, { useState, useEffect } from 'react';
import {
  scanRepo,
  getRoutes,
  generateApiDoc,
  generateApiDocTargeted,
  generateSop,
  getStoredRepoUrl,
} from '../api';

const MethodBadge = ({ method }) => (
  <span className={`method-badge method-${(method || 'GET').toUpperCase()}`}>
    {(method || 'GET').toUpperCase()}
  </span>
);

/**
 * DocManager – the main doc generation screen.
 *
 * Props:
 *   resolvedRepo  – { id?, name?, web_url, path? } from Setup (may be null)
 *   onOpenDoc     – navigate to DocDetail
 *   getCachedRoutes / onCacheRoutes – route cache helpers
 */
export default function DocManager({ resolvedRepo, onOpenDoc, getCachedRoutes, onCacheRoutes }) {
  // ── Top-level mode ─────────────────────────────────────────────────────────
  // 'targeted' = new primary flow (URL + PAT + hints)
  // 'fullscan' = legacy full-repo scan flow (requires known project_id)
  const [mode, setMode] = useState('targeted');

  // ── Targeted mode state ────────────────────────────────────────────────────
  const [repoUrl, setRepoUrl] = useState(resolvedRepo?.web_url || getStoredRepoUrl() || '');
  const [gitlabToken, setGitlabToken] = useState(
    localStorage.getItem('docforge_gitlab_token') || ''
  );
  const [controllerFile, setControllerFile] = useState('');
  const [endpointName, setEndpointName] = useState('');
  const [targetLoading, setTargetLoading] = useState(false);
  const [targetResult, setTargetResult] = useState(null);

  // ── Full-scan mode state ───────────────────────────────────────────────────
  const [scan, setScan] = useState(null);
  const [routes, setRoutes] = useState(
    resolvedRepo?.id ? getCachedRoutes(resolvedRepo.id) : null
  );
  const [scanLoading, setScanLoading] = useState(false);
  const [generating, setGenerating] = useState({});
  const [generatedDocs, setGeneratedDocs] = useState({});
  const [wholeFileMode, setWholeFileMode] = useState(false);

  // ── SOP tab ────────────────────────────────────────────────────────────────
  const [tab, setTab] = useState('api'); // 'api' | 'sop'
  const [sopLoading, setSopLoading] = useState(false);
  const [sopDoc, setSopDoc] = useState(null);

  const [error, setError] = useState('');

  // Keep repoUrl in sync with resolvedRepo prop changes
  useEffect(() => {
    if (resolvedRepo?.web_url && !repoUrl) {
      setRepoUrl(resolvedRepo.web_url);
    }
  }, [resolvedRepo]); // eslint-disable-line

  // Auto-load scan if we already have a project_id
  useEffect(() => {
    if (mode === 'fullscan' && resolvedRepo?.id && !routes) {
      runFullScan(false);
    }
  }, [mode, resolvedRepo?.id]); // eslint-disable-line

  // ── Validation ─────────────────────────────────────────────────────────────
  const targetedValid =
    repoUrl.trim() &&
    gitlabToken.trim() &&
    (controllerFile.trim() || endpointName.trim());

  // ── Targeted generate ──────────────────────────────────────────────────────
  const handleTargetedGenerate = async () => {
    setError('');
    setTargetResult(null);
    setTargetLoading(true);
    try {
      const result = await generateApiDocTargeted(
        repoUrl.trim(),
        gitlabToken.trim(),
        controllerFile.trim(),
        endpointName.trim()
      );
      setTargetResult(result);
      // Auto-open if exactly one result
      if (result.results?.length === 1) {
        const doc = result.results[0];
        onOpenDoc({ ...doc, endpoint: doc.endpoint, repo: resolvedRepo, type: 'api' });
      }
    } catch (e) {
      const detail = e.response?.data?.detail;
      setError('Generation failed: ' + (detail || e.message));
    } finally {
      setTargetLoading(false);
    }
  };

  // ── Full-scan mode ─────────────────────────────────────────────────────────
  const runFullScan = async (forceRescan = false) => {
    if (!resolvedRepo?.id) {
      setError('No project ID available for full scan. Provide a repo URL in Setup or use Targeted mode.');
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

  // ── SOP ────────────────────────────────────────────────────────────────────
  const generateSopDoc = async () => {
    if (!resolvedRepo?.id) {
      setError('SOP generation requires a project ID. Please provide a repo URL in Setup.');
      return;
    }
    setSopLoading(true);
    setError('');
    try {
      const doc = await generateSop(resolvedRepo.id);
      setSopDoc(doc);
      if (!doc.no_infra_detected) {
        onOpenDoc({ ...doc, repo: resolvedRepo, type: 'sop' });
      }
    } catch (e) {
      setError('SOP generation failed: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSopLoading(false);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div>
      {/* ── Tab bar ── */}
      <div className="dm-tabs">
        <div
          className={`dm-tab ${tab === 'api' ? 'active' : ''}`}
          onClick={() => setTab('api')}
        >
          API Docs
        </div>
        <div
          className={`dm-tab ${tab === 'sop' ? 'active' : ''}`}
          onClick={() => setTab('sop')}
        >
          SOP
        </div>
      </div>

      {error && (
        <div className="error-banner" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* ══ API DOCS TAB ══════════════════════════════════════════════════════ */}
      {tab === 'api' && (
        <div>
          {/* Mode selector */}
          <div className="mode-selector">
            <button
              className={`mode-btn ${mode === 'targeted' ? 'active' : ''}`}
              onClick={() => setMode('targeted')}
            >
              🎯 Targeted (URL + Hints)
            </button>
            <button
              className={`mode-btn ${mode === 'fullscan' ? 'active' : ''}`}
              onClick={() => setMode('fullscan')}
            >
              🔍 Full Repo Scan
            </button>
          </div>

          {/* ── TARGETED MODE ─────────────────────────────────────────────── */}
          {mode === 'targeted' && (
            <div className="targeted-panel">
              <div className="card">
                <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>
                  🎯 Targeted Doc Generation
                </h3>
                <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 16 }}>
                  Provide the repo URL, your PAT, and at least one of: the relative path to the
                  controller file <em>or</em> the endpoint name/path. DocForge will search the
                  repo and generate docs without scanning the entire codebase.
                </p>

                {/* Repo URL */}
                <div className="form-group">
                  <label className="label">
                    Repository URL <span style={{ color: 'var(--red)' }}>*</span>
                  </label>
                  <input
                    className="input"
                    type="url"
                    placeholder="https://scm.intermesh.net/group/project"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                  />
                </div>

                {/* GitLab PAT */}
                <div className="form-group">
                  <label className="label">
                    GitLab PAT <span style={{ color: 'var(--red)' }}>*</span>
                  </label>
                  <input
                    className="input"
                    type="password"
                    placeholder="glpat-xxxxxxxxxxxxxxxxxxxx"
                    value={gitlabToken}
                    onChange={(e) => setGitlabToken(e.target.value)}
                  />
                </div>

                {/* Controller file path (optional if endpoint given) */}
                <div className="form-group">
                  <label className="label">
                    Controller / Handler File Path{' '}
                    <span style={{ color: 'var(--text2)', fontWeight: 400 }}>(optional)</span>
                  </label>
                  <input
                    className="input"
                    type="text"
                    placeholder="e.g. controllers/smsController.go  or  internal/handler/mail.php"
                    value={controllerFile}
                    onChange={(e) => setControllerFile(e.target.value)}
                  />
                  <p style={{ fontSize: 12, color: 'var(--text2)', marginTop: 5 }}>
                    Relative path from repo root. Partial names work too (e.g.{' '}
                    <code>smsController</code>). At least one of this or Endpoint Name is required.
                  </p>
                </div>

                {/* Endpoint name (optional if controller given) */}
                <div className="form-group">
                  <label className="label">
                    Endpoint Name / Path{' '}
                    <span style={{ color: 'var(--text2)', fontWeight: 400 }}>(optional)</span>
                  </label>
                  <input
                    className="input"
                    type="text"
                    placeholder="e.g. /sms  or  sendSms  or  SmsController"
                    value={endpointName}
                    onChange={(e) => setEndpointName(e.target.value)}
                  />
                  <p style={{ fontSize: 12, color: 'var(--text2)', marginTop: 5 }}>
                    Used both to find files in the repo and to filter which endpoint to document.
                    At least one of this or Controller File is required.
                  </p>
                </div>

                {/* Validation hint */}
                {!targetedValid && (
                  <div
                    style={{
                      background: 'var(--surface2, #1e293b)',
                      border: '1px solid var(--border, #334155)',
                      borderRadius: 6,
                      padding: '8px 12px',
                      fontSize: 12,
                      color: 'var(--text2)',
                      marginBottom: 14,
                    }}
                  >
                    ℹ️ Fill in Repo URL, GitLab PAT, and at least one of Controller File or
                    Endpoint Name.
                  </div>
                )}

                <button
                  className="btn btn-primary"
                  onClick={handleTargetedGenerate}
                  disabled={targetLoading || !targetedValid}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  {targetLoading ? (
                    <>
                      <span className="spinner" /> Searching & Generating…
                    </>
                  ) : (
                    '⚡ Generate Doc'
                  )}
                </button>
              </div>

              {/* Results */}
              {targetResult && (
                <div style={{ marginTop: 16 }}>
                  {/* Search trace */}
                  {targetResult.search_log?.length > 0 && (
                    <div
                      style={{
                        background: 'var(--surface2, #0f172a)',
                        border: '1px solid var(--border, #1e293b)',
                        borderRadius: 6,
                        padding: '10px 14px',
                        fontSize: 12,
                        color: 'var(--text2)',
                        marginBottom: 12,
                        fontFamily: 'monospace',
                      }}
                    >
                      <div style={{ fontWeight: 600, marginBottom: 4, color: 'var(--text1)' }}>
                        🔍 Search trace
                      </div>
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
                            onOpenDoc({
                              ...doc,
                              endpoint: doc.endpoint,
                              repo: resolvedRepo,
                              type: 'api',
                            })
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

          {/* ── FULL SCAN MODE ─────────────────────────────────────────────── */}
          {mode === 'fullscan' && (
            <div>
              {!resolvedRepo?.id ? (
                <div className="empty-state">
                  <div className="empty-icon">🔗</div>
                  <div className="empty-title">No project linked</div>
                  <p style={{ marginBottom: 16 }}>
                    Full repo scan requires a project ID. Provide a repo URL during Setup
                    (click ⚙ in the top bar) so DocForge can resolve the project, then
                    come back here.
                  </p>
                  <button
                    className="btn btn-primary"
                    onClick={() => setMode('targeted')}
                  >
                    Switch to Targeted Mode
                  </button>
                </div>
              ) : scanLoading ? (
                <div style={{ textAlign: 'center', padding: 60, color: 'var(--text2)' }}>
                  <span className="spinner" style={{ width: 24, height: 24, borderWidth: 3 }} />
                  <p style={{ marginTop: 12 }}>
                    Scanning {resolvedRepo.name || 'repo'} for API routes…
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
                    Standard router patterns (Gin, Echo, Chi, Laravel) were not found in the
                    scanned files.
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
                    <div className="warning-bar">
                      Using whole-file context mode – parser fallback active
                    </div>
                  )}
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: 14,
                    }}
                  >
                    <span style={{ fontSize: 14, color: 'var(--text2)' }}>
                      {routes.endpoints.length} endpoint
                      {routes.endpoints.length !== 1 ? 's' : ''} · {routes.language} /{' '}
                      {routes.framework}
                    </span>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => runFullScan(true)}
                    >
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
                                onOpenDoc({
                                  ...generatedDocs[idx],
                                  endpoint: ep,
                                  repo: resolvedRepo,
                                  type: 'api',
                                })
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
                            {generating[idx] ? (
                              <>
                                <span className="spinner" /> Generating…
                              </>
                            ) : (
                              'Generate'
                            )}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                // No routes loaded yet
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <button
                    className="btn btn-primary"
                    onClick={() => runFullScan(false)}
                  >
                    🔍 Scan Repository
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ══ SOP TAB ═══════════════════════════════════════════════════════════ */}
      {tab === 'sop' && (
        <div>
          {!resolvedRepo?.id ? (
            <div className="empty-state">
              <div className="empty-icon">📋</div>
              <div className="empty-title">No project linked</div>
              <p>
                SOP generation requires a project ID. Provide a repo URL during Setup so
                DocForge can resolve the project.
              </p>
            </div>
          ) : scan && scan.infra_files === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📋</div>
              <div className="empty-title">No infrastructure files found</div>
              <p>No Dockerfile, K8s manifests, or shell scripts were detected in this repo.</p>
            </div>
          ) : (
            <div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 16,
                }}
              >
                <div style={{ fontSize: 14, color: 'var(--text2)' }}>
                  {scan ? (
                    <span>
                      {scan.infra_files} infrastructure file
                      {scan.infra_files !== 1 ? 's' : ''} found
                    </span>
                  ) : (
                    <span>Run a full scan first to detect infra files, or try generating anyway.</span>
                  )}
                </div>
                <button
                  className="btn btn-primary"
                  onClick={generateSopDoc}
                  disabled={sopLoading}
                >
                  {sopLoading ? (
                    <>
                      <span className="spinner" /> Generating SOP…
                    </>
                  ) : (
                    'Generate SOP Draft'
                  )}
                </button>
              </div>
              {sopDoc?.no_infra_detected && (
                <div className="empty-state">
                  <div className="empty-icon">📋</div>
                  <div className="empty-title">No infrastructure files found</div>
                  <p>{sopDoc.message}</p>
                </div>
              )}
              {sopDoc && !sopDoc.no_infra_detected && (
                <div className="card" style={{ marginTop: 14 }}>
                  <p style={{ fontSize: 14, color: 'var(--green)' }}>
                    SOP generated – opening in DocDetail…
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}