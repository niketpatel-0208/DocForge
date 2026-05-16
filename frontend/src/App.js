import React, { useState, useCallback, useRef } from 'react';
import Setup from './pages/Setup';
import DocManager from './pages/DocManager';
import DocDetail from './pages/DocDetail';
import { hasStoredAuth, clearAuth, getStoredRepoUrl } from './api';
import './App.css';

export default function App() {
  // If we already have a stored token, go straight to docmanager (targeted mode)
  const [screen, setScreen] = useState(hasStoredAuth() ? 'docmanager' : 'setup');

  // Repo resolved from Setup (may be null if user skipped URL)
  const [resolvedRepo, setResolvedRepo] = useState(() => {
    const url = getStoredRepoUrl();
    return url ? { web_url: url, name: '' } : null;
  });

  const [selectedDoc, setSelectedDoc] = useState(null);
  const [showSettings, setShowSettings] = useState(false);

  // Cache routes per project to avoid rescanning
  const routesCacheRef = useRef({});
  const getCachedRoutes = useCallback((projectId) => routesCacheRef.current[projectId] || null, []);
  const setCachedRoutes = useCallback((projectId, data) => { routesCacheRef.current[projectId] = data; }, []);

  const handleSetupSuccess = (authResult) => {
    // authResult may include project_id, project_name, project_path if repo URL was provided
    if (authResult?.project_id) {
      setResolvedRepo({
        id: authResult.project_id,
        name: authResult.project_name || '',
        path: authResult.project_path || '',
        web_url: getStoredRepoUrl(),
      });
    }
    setScreen('docmanager');
  };

  const handleLogout = () => {
    clearAuth();
    setResolvedRepo(null);
    setSelectedDoc(null);
    routesCacheRef.current = {};
    setScreen('setup');
  };

  const nav = {
    toDocManager: () => { setSelectedDoc(null); setScreen('docmanager'); },
    toDocDetail: (doc) => { setSelectedDoc(doc); setScreen('docdetail'); },
    toSetup: () => setScreen('setup'),
  };

  return (
    <div className="app">
      <header className="topbar">
        <span
          className="logo"
          onClick={screen !== 'setup' ? nav.toDocManager : undefined}
          style={{ cursor: screen !== 'setup' ? 'pointer' : 'default' }}
        >
          ⚙ DocForge
        </span>

        {screen !== 'setup' && (
          <>
            <nav className="breadcrumb">
              <span className="crumb" onClick={nav.toDocManager}>
                {resolvedRepo?.name || 'Doc Generator'}
              </span>
              {selectedDoc && (
                <>
                  <span className="sep">›</span>
                  <span className="crumb-active">Doc</span>
                </>
              )}
            </nav>
            <div className="topbar-actions">
              <button
                className="btn btn-secondary btn-sm topbar-btn"
                onClick={() => setShowSettings(!showSettings)}
                title="Settings – Change repo / token"
              >
                ⚙
              </button>
              <button
                className="btn btn-secondary btn-sm topbar-btn"
                onClick={handleLogout}
                title="Logout"
              >
                ↪ Logout
              </button>
            </div>
          </>
        )}
      </header>

      {/* Settings modal */}
      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Settings</h3>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setShowSettings(false)}
              >
                ✕
              </button>
            </div>
            <Setup
              onSuccess={(r) => {
                if (r?.project_id) {
                  setResolvedRepo({
                    id: r.project_id,
                    name: r.project_name || '',
                    path: r.project_path || '',
                    web_url: getStoredRepoUrl(),
                  });
                }
                setShowSettings(false);
              }}
              isModal={true}
            />
          </div>
        </div>
      )}

      <main className="main-content">
        {screen === 'setup' && <Setup onSuccess={handleSetupSuccess} />}

        {screen === 'docmanager' && (
          <DocManager
            resolvedRepo={resolvedRepo}
            onOpenDoc={nav.toDocDetail}
            getCachedRoutes={getCachedRoutes}
            onCacheRoutes={setCachedRoutes}
          />
        )}

        {screen === 'docdetail' && (
          <DocDetail
            doc={selectedDoc}
            repo={resolvedRepo}
            onBack={nav.toDocManager}
          />
        )}
      </main>
    </div>
  );
}