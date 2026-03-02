import type { DrugTarget } from '../../data/drugs';

function DrugIcon({ name, size = 24 }: { name: string; size?: number }) {
  const s = size;
  const props = { width: s, height: s, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

  switch (name) {
    case 'pill':
      return <svg {...props}><rect x="3" y="10" width="18" height="4" rx="2" transform="rotate(-45 12 12)" /><line x1="12" y1="12" x2="12" y2="12" transform="rotate(-45 12 12)" /><path d="M8.5 8.5l7 7" /></svg>;
    case 'target':
      return <svg {...props}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" fill="currentColor" /></svg>;
    case 'bacteria':
      return <svg {...props}><ellipse cx="12" cy="12" rx="6" ry="8" /><path d="M6 8c-2-1-3-3-3-3M18 8c2-1 3-3 3-3M6 16c-2 1-3 3-3 3M18 16c2 1 3 3 3 3M9 4c-1-2-1-3-1-3M15 4c1-2 1-3 1-3" /></svg>;
    case 'dna':
      return <svg {...props}><path d="M6 3c0 4 12 4 12 8s-12 4-12 8" /><path d="M18 3c0 4-12 4-12 8s12 4 12 8" /><line x1="7" y1="7" x2="17" y2="7" /><line x1="7" y1="17" x2="17" y2="17" /><line x1="6" y1="12" x2="18" y2="12" /></svg>;
    case 'virus':
      return <svg {...props}><circle cx="12" cy="12" r="6" /><path d="M12 2v4M12 18v4M2 12h4M18 12h4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" /></svg>;
    case 'link':
      return <svg {...props}><path d="M10 14a4 4 0 01-1-6.5l2-2a4 4 0 015.6 5.6l-1 1" /><path d="M14 10a4 4 0 011 6.5l-2 2a4 4 0 01-5.6-5.6l1-1" /></svg>;
    case 'cube':
      return <svg {...props}><path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" /></svg>;
    case 'flask':
      return <svg {...props}><path d="M9 3h6M10 3v7l-5 8a1.5 1.5 0 001.3 2.2h11.4A1.5 1.5 0 0019 18l-5-8V3" /><path d="M7.5 16h9" /></svg>;
    case 'protein':
      return <svg {...props}><path d="M4 8c2-3 4 0 6-2s3-4 6-1" /><path d="M4 14c2 3 4 0 6 2s3 4 6 1" /><circle cx="7" cy="11" r="1.5" fill="currentColor" /><circle cx="14" cy="11" r="1.5" fill="currentColor" /></svg>;
    case 'brain':
      return <svg {...props}><path d="M12 3c-1.5 0-3 .8-3.8 2A4 4 0 004 9c0 1 .4 2 1 2.7A4 4 0 004 14a4 4 0 003.2 3.9C8 19.5 9.8 21 12 21" /><path d="M12 3c1.5 0 3 .8 3.8 2A4 4 0 0120 9c0 1-.4 2-1 2.7A4 4 0 0120 14a4 4 0 01-3.2 3.9C16 19.5 14.2 21 12 21" /><path d="M12 3v18" /></svg>;
    case 'microscope':
      return <svg {...props}><path d="M6 21h12" /><path d="M12 21v-4" /><path d="M9 17h6" /><circle cx="12" cy="8" r="5" /><path d="M12 3v2" /><path d="M15 11l3 3" /></svg>;
    default:
      return <svg {...props}><circle cx="12" cy="12" r="9" /><path d="M12 8v4M12 16h.01" /></svg>;
  }
}

interface UseCaseStepProps {
  drugs: DrugTarget[];
  selectedDrugId: string | null;
  customPrompt: string;
  onSelectDrug: (id: string) => void;
  onCustomPromptChange: (prompt: string) => void;
  onContinue: () => void;
}

export function UseCaseStep({
  drugs,
  selectedDrugId,
  customPrompt,
  onSelectDrug,
  onCustomPromptChange,
  onContinue,
}: UseCaseStepProps) {
  const selectedDrug = drugs.find((d) => d.id === selectedDrugId);
  const isCustom = selectedDrug?.isCustom;

  // Can continue if a drug is selected, and for custom, a prompt is entered
  const canContinue = selectedDrugId && (!isCustom || customPrompt.trim().length > 0);

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Select Drug Target</h1>
          <p className="content-subtitle">
            Choose a known drug to "rediscover" through our AI-powered workflow,
            or enter your own custom drug discovery prompt.
          </p>
        </div>
      </div>

      <div className="use-case-grid">
        {drugs.map((drug) => (
          <div
            key={drug.id}
            className={`use-case-card ${selectedDrugId === drug.id ? 'selected' : ''} ${drug.isCustom ? 'custom' : ''}`}
            onClick={() => onSelectDrug(drug.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                onSelectDrug(drug.id);
              }
            }}
          >
            <div className="use-case-icon"><DrugIcon name={drug.icon} /></div>
            <h3 className="use-case-title">{drug.name}</h3>
            <span className="use-case-category">{drug.category}</span>
            <p className="use-case-description">{drug.description}</p>
          </div>
        ))}
      </div>

      {/* Custom Prompt Input */}
      {isCustom && (
        <div className="card custom-prompt-card">
          <div className="card-header">
            <h3 className="card-title">Custom Discovery Prompt</h3>
            <span className="card-badge">Your Research Goal</span>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="custom-prompt">
              Describe your drug discovery objective
            </label>
            <textarea
              id="custom-prompt"
              className="form-textarea"
              rows={6}
              placeholder={`Example: Design a selective inhibitor of the dopamine D2 receptor for treating schizophrenia. The compound should have high binding affinity, good brain penetration, and minimal off-target effects on other dopamine receptor subtypes.

Include:
- Target protein and desired mechanism
- Therapeutic goal
- Any specific requirements or constraints`}
              value={customPrompt}
              onChange={(e) => onCustomPromptChange(e.target.value)}
            />
            <span className="form-hint">
              The AI will identify the target protein and UniProt ID from your description
            </span>
          </div>
        </div>
      )}

      {/* Pre-defined Drug Details */}
      {selectedDrug && !isCustom && (
        <div className="card selected-drug-details">
          <div className="card-header">
            <h3 className="card-title">
              <DrugIcon name={selectedDrug.icon} size={20} /> {selectedDrug.name} Details
            </h3>
            <span className="card-badge">{selectedDrug.category}</span>
          </div>

          <div className="drug-details-grid">
            <div className="drug-detail">
              <h4>Mechanism of Action</h4>
              <p>{selectedDrug.mechanism}</p>
            </div>

            <div className="drug-detail">
              <h4>Target Protein</h4>
              <p>
                <strong>{selectedDrug.targetProtein.name}</strong>
                <br />
                <span className="monospace">
                  UniProt: {selectedDrug.targetProtein.uniprotId}
                </span>
              </p>
            </div>

            <div className="drug-detail">
              <h4>Reference SMILES</h4>
              <code className="smiles-code">{selectedDrug.referenceSMILES}</code>
            </div>
          </div>

          {/* Scientific Caveats Warning */}
          {selectedDrug.caveats && selectedDrug.caveats.length > 0 && (
            <div className="drug-caveats">
              <div className="caveats-header">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M8 2l6 10H2L8 2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                  <path d="M8 6v3M8 11v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                <span>Scientific Limitations (Demo Context)</span>
              </div>
              <ul className="caveats-list">
                {selectedDrug.caveats.map((caveat, index) => (
                  <li key={index}>{caveat}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="step-actions">
        <button
          className="btn btn-secondary btn-lg"
          disabled={!canContinue}
          onClick={onContinue}
        >
          Continue to AI Planning
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path
              d="M7.5 15l5-5-5-5"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
    </div>
  );
}
