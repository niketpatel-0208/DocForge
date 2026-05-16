import React, { useState, useEffect } from 'react';
import { validateAuth, setStoredRepoUrl, getStoredRepoUrl } from '../api';

export default function Setup({ onSuccess, isModal = false }) {
  const [repoUrl, setRepoUrl] = useState('');
  const [gitlab, setGitlab] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Pre-fill from localStorage if available
  useEffect(() => {
    const storedToken = localStorage.getItem('docforge_gitlab_token') || '';
    const storedUrl = getStoredRepoUrl();
    if (storedToken) setGitlab(storedToken);
    if (storedUrl) setRepoUrl(storedUrl);
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (!gitlab.trim()) {
      setError('GitLab Personal Access Token is required.');
      return;
    }

    setLoading(true);
    try {
      const r = await validateAuth(gitlab.trim(), repoUrl.trim());
      if (r.ok) {
        // Persist repo URL for later use
        if (repoUrl.trim()) {
          setStoredRepoUrl(repoUrl.trim());
        }
        const msg = r.project_name
          ? `Connected as ${r.user} · Repo: ${r.project_name}`
          : `Connected as ${r.user} (@${r.username})`;
        setSuccess(msg);
        setTimeout(() => onSuccess(r), 600);
      }
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Connection failed. Check your token and URL, then try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={isModal ? '' : 'setup-wrap'}>
      {!isModal && (
        <>
          <h1 className="setup-title">⚙ DocForge</h1>
          <p className="setup-sub">
            Generate publish-ready API docs and SOPs from your GitLab source code.
          </p>
        </>
      )}
      <div className={isModal ? '' : 'card'}>
        <form onSubmit={submit}>
          {/* Repo URL */}
          <div className="form-group">
            <label className="label">GitLab Repository URL</label>
            <input
              className="input"
              type="url"
              placeholder="https://scm.intermesh.net/group/project"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
            />
            <p style={{ fontSize: 12, color: 'var(--text2)', marginTop: 6 }}>
              Full URL of the GitLab repository · Leave blank to connect without a specific repo
            </p>
          </div>

          {/* GitLab PAT */}
          <div className="form-group">
            <label className="label">
              GitLab Personal Access Token <span style={{ color: 'var(--red)' }}>*</span>
            </label>
            <input
              className="input"
              type="password"
              placeholder="glpat-xxxxxxxxxxxxxxxxxxxx"
              value={gitlab}
              onChange={(e) => setGitlab(e.target.value)}
              required
            />
            <p style={{ fontSize: 12, color: 'var(--text2)', marginTop: 6 }}>
              Needs: <code>read_api</code>, <code>read_repository</code> scopes on scm.intermesh.net
            </p>
          </div>

          {/* Info banner – LiteLLM key is server-managed */}
          <div
            style={{
              background: 'var(--surface2, #1e293b)',
              border: '1px solid var(--border, #334155)',
              borderRadius: 8,
              padding: '10px 14px',
              fontSize: 12,
              color: 'var(--text2)',
              marginBottom: 16,
              display: 'flex',
              gap: 8,
              alignItems: 'flex-start',
            }}
          >
            <span style={{ fontSize: 16 }}>🔑</span>
            <span>
              <strong>LLM access is pre-configured on the server</strong> — no API key input
              needed. Model: <code>anthropic/claude-sonnet-4-6</code>
            </span>
          </div>

          {error && <div className="error-banner">{error}</div>}
          {success && <div className="success-banner">{success}</div>}

          <button
            className="btn btn-primary"
            type="submit"
            disabled={loading}
            style={{ marginTop: 8, width: '100%', justifyContent: 'center' }}
          >
            {loading ? (
              <>
                <span className="spinner" /> Connecting…
              </>
            ) : isModal ? (
              'Update & Verify'
            ) : (
              'Connect & Continue'
            )}
          </button>
        </form>
      </div>
    </div>
  );
}