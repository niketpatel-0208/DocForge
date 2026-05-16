import React, { useState, useEffect } from 'react';
import { listRepos } from '../api';

export default function RepoList({ onSelect }) {
  const [repos, setRepos] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async (s = '') => {
    setLoading(true); setError('');
    try {
      const data = await listRepos(s);
      setRepos(data);
    } catch (e) {
      setError('Failed to load repos. Check your GitLab token.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    load(search);
  };

  return (
    <div>
      <div className="repos-header">
        <h2 className="repos-title">Select a Repository</h2>
        <form onSubmit={handleSearch} style={{display:'flex', gap:8}}>
          <input
            className="input"
            style={{width:260}}
            placeholder="Search repos…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <button className="btn btn-secondary" type="submit">Search</button>
        </form>
      </div>

      {error && <div className="error-banner" style={{marginBottom:16}}>{error}</div>}

      {loading ? (
        <div style={{textAlign:'center', padding:60, color:'var(--text2)'}}>
          <span className="spinner" style={{width:24,height:24,borderWidth:3}} /> Loading repositories…
        </div>
      ) : repos.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📁</div>
          <div className="empty-title">No repositories found</div>
          <p>Try a different search term or check your access token scopes.</p>
        </div>
      ) : (
        <div className="repo-grid">
          {repos.map(r => (
            <div key={r.id} className="card repo-card" onClick={() => onSelect(r)}>
              <div className="repo-name">{r.name}</div>
              <div className="repo-path">{r.path}</div>
              <div className="repo-meta">
                {r.last_activity_at && (
                  <span>Last activity: {new Date(r.last_activity_at).toLocaleDateString()}</span>
                )}
                {r.description && <span style={{color:'var(--text2)'}}>— {r.description}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
