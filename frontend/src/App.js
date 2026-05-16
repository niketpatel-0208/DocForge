import React, { useState, useCallback, useRef } from 'react';
import Setup from './pages/Setup';
import DocManager from './pages/DocManager';
import DocDetail from './pages/DocDetail';
import { hasStoredAuth, clearAuth } from './api';
import './App.css';

export default function App() {
  const [screen, setScreen] = useState(hasStoredAuth() ? 'docmanager' : 'setup');
  const [resolvedRepo, setResolvedRepo] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState(null);
  // Credentials carried from Setup so DocManager doesn't ask again
  const [sessionCreds, setSessionCreds] = useState({ repoUrl: '', token: '' });

  const routesCacheRef = useRef({});
  const getCachedRoutes = useCallback((projectId) => routesCacheRef.current[projectId] || null, []);
  const setCachedRoutes = useCallback((projectId, data) => { routesCacheRef.current[projectId] = data; }, []);

  const handleSetupSuccess = (authResult, repoUrl, token) => {
    setSessionCreds({ repoUrl: repoUrl || '', token: token || '' });
    if (authResult?.project_id) {
      setResolvedRepo({
        id: authResult.project_id,
        name: authResult.project_name || '',
        path: authResult.project_path || '',
        web_url: repoUrl || '',
      });
    }
    setScreen('docmanager');
  };

  const nav = {
    toDocManager: () => { setSelectedDoc(null); setScreen('docmanager'); },
    toDocDetail: (doc) => { setSelectedDoc(doc); setScreen('docdetail'); },
    toSetup: () => { clearAuth(); setResolvedRepo(null); setSelectedDoc(null); routesCacheRef.current = {}; setScreen('setup'); },
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
              {selectedDoc && (
                <>
                  <span className="crumb" onClick={nav.toDocManager}>Generator</span>
                  <span className="sep">›</span>
                  <span className="crumb-active">Doc</span>
                </>
              )}
            </nav>
            <div className="topbar-actions">
              <button
                className="btn btn-ghost btn-sm topbar-btn"
                onClick={nav.toSetup}
                title="Back to Setup"
              >
                ← New Session
              </button>
            </div>
          </>
        )}
      </header>

      <main className="main-content">
        {screen === 'setup' && <Setup onSuccess={handleSetupSuccess} />}

        {screen === 'docmanager' && (
          <DocManager
            resolvedRepo={resolvedRepo}
            sessionCreds={sessionCreds}
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
