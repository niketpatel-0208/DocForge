import React, { useState, useMemo } from 'react';
import { scoreDoc, exportYamlUrl, exportSopUrl } from '../api';

const SWAGGER_EDITOR_URL = 'https://editor.swagger.io';

export default function DocDetail({ doc, repo, onBack }) {
  const [tab, setTab] = useState('yaml');
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
    // Always download raw YAML file directly
    const blob = new Blob([yaml], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const endpointPath = (doc.endpoint?.path && doc.endpoint.path !== '/unknown'
      ? doc.endpoint.path
      : _extractPathFromYaml(yaml)
    ).replace(/\//g, '_').replace(/^_/, '');
    a.download = `${repoName}-${endpointPath || 'openapi'}.yaml`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const openInSwaggerEditor = () => {
    navigator.clipboard.writeText(yaml).then(() => {
      window.open(SWAGGER_EDITOR_URL, '_blank');
    });
  };

  const scoreColor = (s) =>
    s >= 70 ? 'score-green' : s >= 40 ? 'score-amber' : 'score-red';

  const apiTabs = ['yaml', 'score'];
  const sopTabs = ['yaml'];
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

  // Extract the first path key from the YAML for display when endpoint path is /unknown
  function _extractPathFromYaml(yamlText) {
    try {
      // eslint-disable-next-line
      const jsYaml = require('js-yaml');
      const parsed = jsYaml.load(yamlText);
      const paths = Object.keys(parsed?.paths || {});
      return paths[0] || '/unknown';
    } catch {
      return '/unknown';
    }
  }

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
              ? `${doc.endpoint?.method || ''} ${doc.endpoint?.path && doc.endpoint.path !== '/unknown' ? doc.endpoint.path : (doc.yaml ? _extractPathFromYaml(doc.yaml) : doc.endpoint?.path || '')}`
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
            {t === 'yaml' ? 'YAML' : t === 'score' ? 'Score' : t}
          </div>
        ))}
      </div>

      {/* YAML Tab */}
      {tab === 'yaml' && isSop && (
        <div>
          <div className="sop-preview">{doc.sop}</div>
        </div>
      )}

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

    </div>
  );
}