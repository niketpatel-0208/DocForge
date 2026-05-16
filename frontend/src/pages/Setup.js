import React, { useState } from 'react';
import { validateAuth, setStoredRepoUrl } from '../api';

export default function Setup({ onSuccess, isModal = false }) {
  // Never autofill – user must type fresh credentials each time
  const [repoUrl, setRepoUrl] = useState('');
  const [gitlab, setGitlab] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

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
        if (repoUrl.trim()) setStoredRepoUrl(repoUrl.trim());
        const msg = r.project_name
          ? `Connected as ${r.user} · Repo: ${r.project_name}`
          : `Connected as ${r.user} (@${r.username})`;
        setSuccess(msg);
        setTimeout(() => onSuccess(r, repoUrl.trim(), gitlab.trim()), 600);
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
        <div className="setup-hero">
          <div className="setup-logo-mark">⚙</div>
          <h1 className="setup-title">DocForge</h1>
          <p className="setup-sub">
            Generate publish-ready API documentation from your GitLab source code — instantly.
          </p>
        </div>
      )}
      <div className={isModal ? '' : 'card setup-card'}>
        <form onSubmit={submit}>
          <div className="form-group">
            <label className="label">GitLab Repository URL</label>
            <input
              className="input"
              type="url"
              placeholder="https://scm.intermesh.net/group/project"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
            />
            <p className="field-hint">
              Full URL of the repository · Leave blank to connect without a specific repo
            </p>
          </div>

          <div className="form-group">
            <label className="label">
              GitLab Personal Access Token <span className="required-star">*</span>
            </label>
            <input
              className="input"
              type="password"
              placeholder="glpat-xxxxxxxxxxxxxxxxxxxx"
              value={gitlab}
              onChange={(e) => setGitlab(e.target.value)}
              required
            />
            <p className="field-hint">
              Needs <code>read_api</code>, <code>read_repository</code> scopes
            </p>
          </div>

          {error && <div className="error-banner">{error}</div>}
          {success && <div className="success-banner">{success}</div>}

          <button
            className="btn btn-primary btn-glow"
            type="submit"
            disabled={loading}
            style={{ marginTop: 8, width: '100%', justifyContent: 'center' }}
          >
            {loading ? (
              <><span className="spinner" /> Connecting…</>
            ) : isModal ? (
              'Update & Verify'
            ) : (
              'Connect & Generate Docs →'
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
