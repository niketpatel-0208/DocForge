import React, { useState, useMemo } from 'react';
import { scoreDoc, exportYamlUrl, exportSopUrl } from '../api';

const SWAGGER_EDITOR_URL = 'https://editor.swagger.io';

export default function DocDetail({ doc, repo, onBack }) {
  const [tab, setTab] = useState('preview');
  const [yaml, setYaml] = useState(doc?.yaml || '');
  const [score, setScore] = useState(doc?.score || null);
  const [rescoring, setRescoring] = useState(false);
  const [copied, setCopied] = useState(false);

  // repo may be null in the URL-based flow – derive display values safely
  const repoName = repo?.name || doc?.endpoint?.service_name || doc?.project_name || 'repo';
  const repoId = repo?.id ?? doc?.project_id;

  const isApi = doc.type === 'api';
  const isSop = doc.type === 'sop';

  const rescore = async () => {
    setRescoring(true);
    try {
      const r = await scoreDoc(yaml, false);
      setScore(r);
    } catch (e) {}
    setRescoring(false);
  };

  const copyYaml = () => {
    navigator.clipboard.writeText(yaml);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const copySop = () => {
    navigator.clipboard.writeText(doc.sop || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const downloadYaml = () => {
    if (doc.doc_id !== undefined && repoId !== undefined) {
      window.location.href = exportYamlUrl(repoId, doc.doc_id);
    } else {
      const blob = new Blob([yaml], { type: 'text/yaml' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${repoName}-openapi.yaml`;
      a.click();
    }
  };

  const openInSwaggerEditor = () => {
    navigator.clipboard.writeText(yaml).then(() => {
      window.open(SWAGGER_EDITOR_URL, '_blank');
    });
  };

  const scoreColor = (s) =>
    s >= 70 ? 'score-green' : s >= 40 ? 'score-amber' : 'score-red';

  const apiTabs = ['preview', 'yaml', 'score', 'swagger'];
  const sopTabs = ['preview'];
  const tabs = isApi ? apiTabs : sopTabs;

  const parsedYaml = useMemo(() => {
    try {
      // eslint-disable-next-line
      const jsYaml = require('js-yaml');
      return jsYaml.load(yaml);
    } catch {
      return null;
    }
  }, [yaml]);

  const scoreSummary = score?.summary || {
    yes: score?.checks?.filter((c) => c.status === 'YES').length || 0,
    no: score?.checks?.filter((c) => c.status === 'NO').length || 0,
    partial: score?.checks?.filter((c) => c.status === 'PARTIAL').length || 0,
    na: score?.checks?.filter((c) => c.status === 'NA').length || 0,
  };

  return (
    <div>
      <div className="dd-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn btn-secondary btn-sm" onClick={onBack}>
            ← Back
          </button>
          <h2 style={{ fontSize: 18, fontWeight: 600 }}>
            {isApi
              ? `${doc.endpoint?.method} ${doc.endpoint?.path}`
              : `${doc.service_name || repoName} – SOP`}
          </h2>
          {isApi && score && (
            <span
              className={`tag ${
                score.score_percent >= 70
                  ? 'tag-green'
                  : score.score_percent >= 40
                  ? 'tag-amber'
                  : 'tag-red'
              }`}
            >
              {score.score_percent}% compliance
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {isApi && (
            <>
              <button className="btn btn-secondary btn-sm" onClick={copyYaml}>
                {copied ? '✓ Copied' : '📋 Copy YAML'}
              </button>
              <button className="btn btn-secondary btn-sm" onClick={downloadYaml}>
                ↓ Download
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={openInSwaggerEditor}
                title="YAML will be copied to clipboard – paste into the editor"
              >
                🔗 Open in Swagger Editor
              </button>
            </>
          )}
          {isSop && (
            <button className="btn btn-secondary btn-sm" onClick={copySop}>
              {copied ? '✓ Copied' : '📋 Copy SOP'}
            </button>
          )}
        </div>
      </div>

      {doc.parse_warning && (
        <div className="parse-warning">
          ⚠ Parse warning – YAML may have formatting issues. Review before publishing.
        </div>
      )}

      <div className="dd-tabs">
        {tabs.map((t) => (
          <div
            key={t}
            className={`dd-tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t === 'swagger'
              ? '🔍 Swagger Preview'
              : t.charAt(0).toUpperCase() + t.slice(1)}
          </div>
        ))}
      </div>

      {/* Preview Tab */}
      {tab === 'preview' && isApi && (
        <div className="card">
          <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--text2)' }}>
            OpenAPI 3.0 ·{' '}
            <span style={{ color: 'var(--accent-h)' }}>{repoName}</span>
            {doc.confidence !== undefined && (
              <span style={{ marginLeft: 12 }}>
                Confidence: {Math.round(doc.confidence * 100)}%
              </span>
            )}
          </div>
          <pre className="yaml-preview">{yaml}</pre>
          {doc.missing?.length > 0 && (
            <div className="todo-bar">
              <strong>TODOs in generated doc:</strong> {doc.missing.join(', ')}
            </div>
          )}
        </div>
      )}

      {tab === 'preview' && isSop && (
        <div>
          <div className="sop-preview">{doc.sop}</div>
          {doc.needs_human_input?.filter(Boolean).length > 0 && (
            <div className="needs-input-list" style={{ marginTop: 16 }}>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  marginBottom: 8,
                  color: 'var(--text2)',
                }}
              >
                Needs Human Input ({doc.needs_human_input.filter(Boolean).length})
              </div>
              {doc.needs_human_input.filter(Boolean).map((item, i) => (
                <div key={i} className="needs-input-item">
                  {item}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* YAML Editor Tab */}
      {tab === 'yaml' && isApi && (
        <div>
          <div className="action-bar">
            <button
              className="btn btn-primary btn-sm"
              onClick={rescore}
              disabled={rescoring}
            >
              {rescoring ? (
                <>
                  <span className="spinner" /> Re-scoring…
                </>
              ) : (
                '↻ Re-score (22 criteria)'
              )}
            </button>
            {score && (
              <span
                className={`score-number ${scoreColor(score.score_percent)}`}
                style={{ fontSize: 16 }}
              >
                {score.score_percent}%
              </span>
            )}
          </div>
          <textarea
            className="yaml-editor"
            value={yaml}
            onChange={(e) => setYaml(e.target.value)}
            spellCheck={false}
          />
        </div>
      )}

      {/* Score Tab */}
      {tab === 'score' && isApi && (
        <div>
          {score ? (
            <>
              <div className="score-ring-wrap">
                <div className={`score-number ${scoreColor(score.score_percent)}`}>
                  {score.score_percent}%
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                    Compliance Score (22-criteria rubric)
                  </div>
                  <div className="score-summary-badges">
                    <span className="score-badge badge-yes">
                      ✓ YES: {scoreSummary.yes}
                    </span>
                    <span className="score-badge badge-no">
                      ✗ NO: {scoreSummary.no}
                    </span>
                    <span className="score-badge badge-partial">
                      ⚠ PARTIAL: {scoreSummary.partial}
                    </span>
                    <span className="score-badge badge-na">
                      • NA: {scoreSummary.na}
                    </span>
                  </div>
                </div>
              </div>
              <div className="check-list">
                {score.checks?.map((c) => (
                  <div key={c.id} className="check-item">
                    <span className="check-id">Q{c.id}</span>
                    <span className={`check-status status-${c.status}`}>
                      {c.status}
                    </span>
                    <span>{c.finding}</span>
                  </div>
                ))}
              </div>
              {score.quick_fixes?.length > 0 && (
                <div className="quick-fixes">
                  <div
                    style={{
                      fontSize: 14,
                      fontWeight: 600,
                      marginBottom: 10,
                      marginTop: 24,
                      color: 'var(--text2)',
                    }}
                  >
                    Improvement Suggestions ({score.quick_fixes.length})
                  </div>
                  {score.quick_fixes.map((f, i) => (
                    <div key={i} className="quick-fix-item">
                      <div className="fix-issue">{f.issue}</div>
                      <div className="fix-action">→ {f.fix}</div>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">📊</div>
              <div className="empty-title">No score yet</div>
              <button className="btn btn-primary" onClick={rescore}>
                Run 22-Criteria Score
              </button>
            </div>
          )}
        </div>
      )}

      {/* Swagger Preview Tab */}
      {tab === 'swagger' && isApi && (
        <div>
          <div className="swagger-panel">
            <div className="swagger-header">
              <h3 style={{ fontSize: 16, fontWeight: 600 }}>Swagger UI Preview</h3>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={openInSwaggerEditor}
                >
                  🔗 Open in Swagger Editor
                </button>
              </div>
            </div>
            <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 16 }}>
              Your YAML will be copied to clipboard. Paste it into the Swagger
              Editor for an interactive API preview.
            </p>

            {parsedYaml ? (
              <div className="swagger-structured">
                <div className="swagger-section">
                  <h4>{parsedYaml.info?.title || 'Untitled API'}</h4>
                  <span className="tag tag-blue">
                    v{parsedYaml.info?.version || '1.0.0'}
                  </span>
                  {parsedYaml.info?.description && (
                    <p className="swagger-desc">
                      {parsedYaml.info.description.slice(0, 300)}…
                    </p>
                  )}
                </div>

                {parsedYaml.servers?.length > 0 && (
                  <div className="swagger-section">
                    <h5>Servers</h5>
                    {parsedYaml.servers.map((s, i) => (
                      <div key={i} className="swagger-server">
                        <code>{s.url}</code>
                        <span className="text-muted">
                          {' '}
                          – {s.description || 'Server'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {parsedYaml.paths &&
                  Object.entries(parsedYaml.paths).map(([path, methods]) => (
                    <div key={path} className="swagger-section">
                      {Object.entries(methods).map(([method, op]) => {
                        if (
                          !['get', 'post', 'put', 'patch', 'delete'].includes(
                            method
                          )
                        )
                          return null;
                        return (
                          <div key={method} className="swagger-endpoint">
                            <div className="swagger-endpoint-header">
                              <span
                                className={`method-badge method-${method.toUpperCase()}`}
                              >
                                {method.toUpperCase()}
                              </span>
                              <code className="swagger-path">{path}</code>
                              {op?.summary && (
                                <span className="swagger-summary">
                                  {op.summary}
                                </span>
                              )}
                            </div>

                            {op?.requestBody?.content && (
                              <div className="swagger-params">
                                <h6>Request Body</h6>
                                {Object.entries(op.requestBody.content).map(
                                  ([ct, ctVal]) => {
                                    const props =
                                      ctVal?.schema?.properties || {};
                                    const required =
                                      ctVal?.schema?.required || [];
                                    return (
                                      <div key={ct}>
                                        <span
                                          className="tag tag-grey"
                                          style={{ marginBottom: 8 }}
                                        >
                                          {ct}
                                        </span>
                                        <table className="swagger-table">
                                          <thead>
                                            <tr>
                                              <th>Name</th>
                                              <th>Type</th>
                                              <th>Required</th>
                                              <th>Description</th>
                                            </tr>
                                          </thead>
                                          <tbody>
                                            {Object.entries(props)
                                              .slice(0, 20)
                                              .map(([name, prop]) => (
                                                <tr key={name}>
                                                  <td>
                                                    <code>{name}</code>
                                                  </td>
                                                  <td>
                                                    {prop?.type || '—'}
                                                  </td>
                                                  <td>
                                                    {required.includes(name)
                                                      ? '✓'
                                                      : '—'}
                                                  </td>
                                                  <td className="text-muted">
                                                    {(
                                                      prop?.description || ''
                                                    ).slice(0, 80)}
                                                  </td>
                                                </tr>
                                              ))}
                                          </tbody>
                                        </table>
                                      </div>
                                    );
                                  }
                                )}
                              </div>
                            )}

                            {op?.responses && (
                              <div className="swagger-responses">
                                <h6>Responses</h6>
                                {Object.entries(op.responses).map(
                                  ([code, resp]) => (
                                    <div
                                      key={code}
                                      className="swagger-response-item"
                                    >
                                      <span
                                        className={`tag ${
                                          code.startsWith('2')
                                            ? 'tag-green'
                                            : code.startsWith('4')
                                            ? 'tag-amber'
                                            : 'tag-red'
                                        }`}
                                      >
                                        {code}
                                      </span>
                                      <span className="text-muted">
                                        {typeof resp === 'object'
                                          ? (resp?.description || '').slice(
                                              0,
                                              100
                                            )
                                          : ''}
                                      </span>
                                    </div>
                                  )
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ))}
              </div>
            ) : (
              <div className="empty-state" style={{ padding: 30 }}>
                <div className="empty-icon">⚠️</div>
                <div className="empty-title">Cannot parse YAML</div>
                <p>Fix YAML syntax errors to see the structured preview.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}