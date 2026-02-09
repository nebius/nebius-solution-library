import type { DrugTarget } from '../../data/drugs';

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
            <div className="use-case-icon">{drug.icon}</div>
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
              {selectedDrug.icon} {selectedDrug.name} Details
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
