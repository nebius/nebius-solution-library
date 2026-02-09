import { createPortal } from 'react-dom';
import type { NimEndpoint } from '../data/endpoints';

interface ServiceOverviewModalProps {
  endpoints: NimEndpoint[];
  gatewayUrl: string;
  onClose: () => void;
}

const CATEGORY_LABELS: Record<NimEndpoint['category'], string> = {
  llm: 'Language Model',
  structure: 'Structure Prediction',
  molecule: 'Molecule Generation',
  docking: 'Molecular Docking',
  design: 'Protein Design',
  utility: 'Utilities',
};

const CATEGORY_ORDER: NimEndpoint['category'][] = [
  'llm',
  'structure',
  'molecule',
  'docking',
  'design',
  'utility',
];

export function ServiceOverviewModal({
  endpoints,
  gatewayUrl,
  onClose,
}: ServiceOverviewModalProps) {
  const readyCount = endpoints.filter((e) => e.status === 'ready').length;
  const totalCount = endpoints.length;

  // Group endpoints by category
  const groupedEndpoints = CATEGORY_ORDER.map((category) => ({
    category,
    label: CATEGORY_LABELS[category],
    endpoints: endpoints.filter((e) => e.category === category),
  })).filter((group) => group.endpoints.length > 0);

  return createPortal(
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">NIM Services</h2>
            <p className="modal-subtitle">
              {gatewayUrl ? `Connected to ${gatewayUrl}` : 'No gateway configured'}
            </p>
          </div>
          <button className="modal-close" onClick={onClose}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path
                d="M18 6L6 18M6 6l12 12"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>

        <div className="modal-summary">
          <div className={`summary-badge ${readyCount === totalCount ? 'all-ready' : 'partial'}`}>
            <span className="summary-count">{readyCount}/{totalCount}</span>
            <span className="summary-label">Services Ready</span>
          </div>
        </div>

        <div className="modal-body">
          {groupedEndpoints.map((group) => (
            <div key={group.category} className="service-group">
              <h3 className="service-group-title">{group.label}</h3>
              <div className="service-list">
                {group.endpoints.map((endpoint) => (
                  <div
                    key={endpoint.id}
                    className={`service-item ${endpoint.status}`}
                  >
                    <div className="service-status-indicator">
                      {endpoint.status === 'ready' && (
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                          <circle cx="8" cy="8" r="6" fill="var(--color-success)" />
                          <path d="M5 8l2 2 4-4" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                      {endpoint.status === 'not-ready' && (
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                          <circle cx="8" cy="8" r="6" fill="var(--color-error)" />
                          <path d="M6 6l4 4M10 6l-4 4" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
                        </svg>
                      )}
                      {endpoint.status === 'checking' && (
                        <div className="spinner spinner-sm" />
                      )}
                      {endpoint.status === 'unknown' && (
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                          <circle cx="8" cy="8" r="6" fill="var(--color-gray-300)" />
                          <path d="M8 5v3M8 10v1" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
                        </svg>
                      )}
                    </div>
                    <div className="service-info">
                      <div className="service-name">
                        {endpoint.name}
                        {endpoint.required && <span className="required-tag">Required</span>}
                        <span className={`gpu-tag gpu-${endpoint.gpu.toLowerCase().replace(' ', '-')}`}>
                          {endpoint.gpuCount && endpoint.gpuCount > 1 ? `${endpoint.gpuCount}× ` : ''}{endpoint.gpu}
                        </span>
                      </div>
                      <div className="service-description">{endpoint.description}</div>
                      <div className="service-endpoint">
                        Port {endpoint.port} &middot; {endpoint.path}
                      </div>
                    </div>
                    <div className="service-status-label">
                      {endpoint.status === 'ready' && 'Ready'}
                      {endpoint.status === 'not-ready' && 'Offline'}
                      {endpoint.status === 'checking' && 'Checking...'}
                      {endpoint.status === 'unknown' && 'Unknown'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>,
    document.body
  );
}
