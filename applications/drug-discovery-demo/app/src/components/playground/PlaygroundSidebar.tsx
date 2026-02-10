/**
 * PlaygroundSidebar Component
 *
 * Sidebar for the NIM Playground mode.
 * Shows shared sections (mode selector, gateway, infra) via SidebarCommon,
 * plus NIM list grouped by category with health status indicators.
 */

import { useGateway } from '../../contexts/GatewayContext';
import { SidebarCommon } from '../SidebarCommon';
import { getPlaygroundConfigsByCategory, type NimPlaygroundDef } from '../../data/nimPlayground';
import { ENDPOINT_CONFIG } from '../../services/nimApi';

interface PlaygroundSidebarProps {
  selectedNimId: string | null;
  onSelectNim: (nimId: string) => void;
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  LLM: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M2 4h12M2 8h8M2 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  'Structure Prediction': (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M8 2L3 5v6l5 3 5-3V5L8 2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx="8" cy="8" r="1.5" fill="currentColor" />
    </svg>
  ),
  'Molecule Generation': (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="5" cy="6" r="2" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="11" cy="6" r="2" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="8" cy="12" r="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M6.5 7.5L7 10.5M9.5 7.5L9 10.5" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  ),
  'Molecular Docking': (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <path d="M7 7l2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
  Utilities: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  ),
  'Protein Design': (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M4 12L8 2l4 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5.5 8h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
};

export function PlaygroundSidebar({
  selectedNimId,
  onSelectNim,
}: PlaygroundSidebarProps) {
  const { endpoints } = useGateway();
  const categorized = getPlaygroundConfigsByCategory();

  const getEndpointStatus = (nimId: string) => {
    const ep = endpoints.find((e) => e.id === nimId);
    return ep?.status || 'unknown';
  };

  return (
    <aside className="sidebar">
      <SidebarCommon />

      {/* Branding */}
      <div className="sidebar-section">
        <div className="serverless-brand">
          <div className="serverless-brand-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="serverless-brand-text">
            <span className="serverless-brand-title">NIM Playground</span>
            <span className="serverless-brand-subtitle">Direct API Access</span>
          </div>
        </div>
      </div>

      {/* NIM List */}
      <div className="sidebar-section sidebar-section-scroll">
        <h3 className="sidebar-section-title">Select NIM</h3>
        <div className="playground-nim-list">
          {Object.entries(categorized).map(([category, nims]) => (
            <div key={category} className="playground-nim-group">
              <div className="playground-nim-category">
                {CATEGORY_ICONS[category] || null}
                <span>{category}</span>
              </div>
              {nims.map((nim: NimPlaygroundDef) => {
                const status = getEndpointStatus(nim.id);
                const port = ENDPOINT_CONFIG[nim.id]?.port;
                return (
                  <button
                    key={nim.id}
                    className={`playground-nim-item ${selectedNimId === nim.id ? 'selected' : ''}`}
                    onClick={() => onSelectNim(nim.id)}
                  >
                    <span className={`status-dot ${status === 'ready' ? 'connected' : status === 'checking' ? 'checking' : 'disconnected'}`} />
                    <span className="playground-nim-name">{nim.name}</span>
                    {port && <span className="playground-nim-port">:{port}</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
