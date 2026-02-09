import { useState, useCallback } from 'react';
import Markdown from 'react-markdown';
import { streamChat } from '../../services/nimApi';
import { isDemoMode } from '../../services/demoService';
import type { DrugTarget } from '../../data/drugs';

interface AIPlanningStepProps {
  selectedDrug: DrugTarget | null;
  customPrompt: string;
  gatewayUrl: string;
  savedPlan: string;
  savedUniprotId: string;
  onPlanChange: (plan: string, uniprotId: string) => void;
  onContinue: (plan: string, uniprotId: string) => void;
  onBack: () => void;
}

const SYSTEM_PROMPT = `You are an expert computational drug discovery and protein design scientist. Your task is to create a detailed research plan based on the given requirements.

## Available AI Models

### Structure Prediction
- **OpenFold3**: Next-gen structure prediction, good balance of speed and accuracy. Recommended for most proteins.
- **Boltz2**: Fast structure prediction, great for rapid prototyping.
- **OpenFold2**: High accuracy with MSA + templates, best for well-characterized proteins.

### Small Molecule Generation
- **GenMol**: De novo molecule generation, creates novel drug-like compounds from scratch.
- **MolMIM**: SMILES-guided generation, explores chemical space around a seed molecule. Good for lead optimization.

### Molecular Docking
- **DiffDock**: Predicts how small molecules bind to proteins, returns poses and confidence scores.

### Protein Design
- **RFDiffusion**: De novo protein structure generation. Can design novel folds, binders, scaffolds.
- **ProteinMPNN**: Designs amino acid sequences that fold into a given structure.

### Utilities
- **MSA Search**: Finds homologous sequences for improved structure prediction.
- **Evo2-40B**: DNA/RNA foundation model for genomic analysis.

## Your Task
Analyze the research objective and design an appropriate workflow using the available models.

IMPORTANT: You MUST identify the primary target and provide its UniProt accession ID (if it's a known protein).

## Response Structure

1. **Objective Summary** - Brief restatement of the goal

2. **Task Classification** - What type of task is this?
   - Small molecule drug discovery
   - De novo protein design
   - Protein binder design
   - Lead optimization
   - Other (specify)

3. **Target Information**
   - Name: [Target name]
   - UniProt ID: [ACCESSION_ID] (e.g., P35354) - REQUIRED for known proteins
   - Type: [Protein / Pathway / Other]
   - Key features: [Binding sites, domains, etc.]

4. **Recommended Workflow** - Choose the appropriate models for each step:
   | Step | Model | Purpose |
   |------|-------|---------|
   | 1    | [Model name] | [What this step achieves] |
   | 2    | [Model name] | [What this step achieves] |
   | ...  | ... | ... |

5. **Key Considerations**
   - Potential challenges
   - Alternative approaches if primary fails
   - Scientific caveats

6. **Success Criteria** - How we'll evaluate results

Keep the plan concise but comprehensive. Adapt the workflow to the specific problem - don't use all models if not needed.`;

/**
 * Extract UniProt ID from the generated plan
 * Prioritizes the "Target Protein" section to avoid picking up comparison mentions
 */
function extractUniprotId(text: string): string {
  // First, try to find the Target Protein section and extract from there
  const targetProteinSection = text.match(/Target\s*Protein[^]*?(?=##|$)/i);
  const sectionToSearch = targetProteinSection ? targetProteinSection[0] : text;

  // Look for explicit "UniProt ID:" pattern first (most reliable)
  const explicitIdMatch = sectionToSearch.match(/UniProt\s+ID[:\s]+([A-Z][A-Z0-9]{5,9})/i);
  if (explicitIdMatch && explicitIdMatch[1]) {
    return explicitIdMatch[1].toUpperCase();
  }

  // Look for "UniProt:" but NOT followed by parenthetical notes like "(UniProt: ...)"
  // This avoids picking up comparison mentions like "over COX-1 (UniProt: P23219)"
  const uniprotMatch = sectionToSearch.match(/(?<!\()UniProt[:\s]+([A-Z][A-Z0-9]{5,9})(?!\))/i);
  if (uniprotMatch && uniprotMatch[1]) {
    return uniprotMatch[1].toUpperCase();
  }

  // Fallback patterns for other formats
  const fallbackPatterns = [
    /UniProt[:\s]+([A-Z][A-Z0-9]{5,9})/i,
    /\[([A-Z][A-Z0-9]{5,9})\]/,  // [P35354]
    /accession[:\s]+([A-Z][A-Z0-9]{5,9})/i,
  ];

  for (const pattern of fallbackPatterns) {
    const match = sectionToSearch.match(pattern);
    if (match && match[1]) {
      return match[1].toUpperCase();
    }
  }

  // If nothing found in section, try the full text
  if (targetProteinSection) {
    for (const pattern of fallbackPatterns) {
      const match = text.match(pattern);
      if (match && match[1]) {
        return match[1].toUpperCase();
      }
    }
  }

  return '';
}

export function AIPlanningStep({
  selectedDrug,
  customPrompt,
  gatewayUrl,
  savedPlan,
  savedUniprotId,
  onPlanChange,
  onContinue,
  onBack,
}: AIPlanningStepProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  // Initialize from saved values
  const [generatedPlan, setGeneratedPlan] = useState(savedPlan || '');
  const [extractedUniprotId, setExtractedUniprotId] = useState(savedUniprotId || '');
  const [error, setError] = useState<string | null>(null);

  // Determine the prompt to use
  const isCustom = selectedDrug?.isCustom;
  const userPrompt = isCustom ? customPrompt : selectedDrug?.llmPrompt || '';

  const handleGeneratePlan = useCallback(async () => {
    const demoMode = isDemoMode();
    if (!userPrompt || (!gatewayUrl && !demoMode)) return;

    setIsGenerating(true);
    setGeneratedPlan('');
    setExtractedUniprotId('');
    setError(null);

    try {
      const messages = [
        { role: 'system' as const, content: SYSTEM_PROMPT },
        { role: 'user' as const, content: userPrompt },
      ];

      let fullPlan = '';
      for await (const chunk of streamChat(gatewayUrl, messages, {
        maxTokens: 1500,
      })) {
        fullPlan += chunk;
        setGeneratedPlan(fullPlan);
      }

      // Extract UniProt ID from the completed plan
      let uniprotId = extractUniprotId(fullPlan);
      setExtractedUniprotId(uniprotId);

      // If we have a pre-defined drug with a known UniProt ID, use that as fallback
      if (!uniprotId && selectedDrug && !isCustom && selectedDrug.targetProtein.uniprotId) {
        uniprotId = selectedDrug.targetProtein.uniprotId;
        setExtractedUniprotId(uniprotId);
      }

      // Save plan to parent state so it persists when navigating
      onPlanChange(fullPlan, uniprotId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate plan';
      setError(message);
    } finally {
      setIsGenerating(false);
    }
  }, [userPrompt, gatewayUrl, selectedDrug, isCustom, onPlanChange]);

  const handleContinue = useCallback(() => {
    // Use extracted ID, or fall back to drug's known ID
    const uniprotId = extractedUniprotId || selectedDrug?.targetProtein.uniprotId || '';
    onContinue(generatedPlan, uniprotId);
  }, [generatedPlan, extractedUniprotId, selectedDrug, onContinue]);

  if (!selectedDrug) {
    return (
      <div className="step-content">
        <div className="content-header">
          <div>
            <h1 className="content-title">AI Planning</h1>
            <p className="content-subtitle">Please select a drug target first.</p>
          </div>
        </div>
        <div className="step-actions">
          <button className="btn btn-ghost" onClick={onBack}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M12.5 15l-5-5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">AI Planning</h1>
          <p className="content-subtitle">
            {isCustom
              ? 'Generate a research plan for your custom drug discovery goal using Qwen3-80B.'
              : `Generate a research plan for ${selectedDrug.name} discovery using Qwen3-80B.`}
          </p>
        </div>
      </div>

      {/* Prompt Preview Card */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Research Objective</h3>
          <span className="card-badge">{selectedDrug.category}</span>
        </div>
        <div className="prompt-preview">
          <p className="prompt-text">{userPrompt || 'No prompt provided'}</p>
        </div>
        {!isCustom && selectedDrug.targetProtein.uniprotId && (
          <div className="prompt-meta">
            <span className="prompt-meta-item">
              <strong>Known Target:</strong> {selectedDrug.targetProtein.name}
            </span>
            <span className="prompt-meta-item">
              <strong>UniProt:</strong> {selectedDrug.targetProtein.uniprotId}
            </span>
          </div>
        )}
      </div>

      {/* Generate Button / Generated Plan */}
      {!generatedPlan && !isGenerating && (
        <div className="card generate-card">
          <div className="generate-content">
            <div className="generate-icon">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <rect width="48" height="48" rx="12" fill="var(--color-lime)" />
                <path d="M24 14v20M14 24h20" stroke="var(--color-deep-blue)" strokeWidth="3" strokeLinecap="round" />
              </svg>
            </div>
            <h3 className="generate-title">Ready to Generate Plan</h3>
            <p className="generate-description">
              Qwen3-80B will analyze the research objective, identify the target protein,
              and create a comprehensive computational drug discovery plan.
            </p>
            <div className="generate-buttons">
              <button
                className="btn btn-secondary btn-lg"
                onClick={handleGeneratePlan}
                disabled={(!gatewayUrl && !isDemoMode()) || !userPrompt}
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M10 2v16M2 10h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                Generate Research Plan
              </button>
              <button
                className="btn btn-outline"
                onClick={() => {
                  // Use the drug's known UniProt ID when skipping
                  const uniprotId = selectedDrug?.targetProtein.uniprotId || '';
                  onContinue('', uniprotId);
                }}
              >
                Skip this step
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M6 12l4-4-4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
            {!gatewayUrl && !isDemoMode() && (
              <p className="generate-hint">Enter the NIM Gateway URL in the sidebar to continue.</p>
            )}
            {!userPrompt && isCustom && (
              <p className="generate-hint">Enter a custom prompt to continue.</p>
            )}
          </div>
        </div>
      )}

      {/* Generating State */}
      {isGenerating && (
        <div className="card plan-card">
          <div className="card-header">
            <h3 className="card-title">Research Plan</h3>
            <span className="card-badge generating">
              <span className="spinner spinner-sm"></span>
              Generating...
            </span>
          </div>
          <div className="plan-content">
            <div className="plan-text">
              <Markdown>{generatedPlan || 'Thinking...'}</Markdown>
            </div>
            <span className="typing-cursor" />
          </div>
        </div>
      )}

      {/* Generated Plan */}
      {generatedPlan && !isGenerating && (
        <div className="card plan-card">
          <div className="card-header">
            <h3 className="card-title">Research Plan</h3>
            <span className="card-badge success">Complete</span>
          </div>
          <div className="plan-content">
            <div className="plan-text">
              <Markdown>{generatedPlan}</Markdown>
            </div>
          </div>

          {/* Extracted UniProt ID */}
          <div className="extracted-info">
            <span className="extracted-label">Identified Target:</span>
            {extractedUniprotId ? (
              <span className="extracted-value success">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <circle cx="7" cy="7" r="5" fill="var(--color-success)" />
                  <path d="M4.5 7l1.5 1.5 3-3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                UniProt: {extractedUniprotId}
              </span>
            ) : selectedDrug.targetProtein.uniprotId ? (
              <span className="extracted-value fallback">
                Using known ID: {selectedDrug.targetProtein.uniprotId}
              </span>
            ) : (
              <span className="extracted-value warning">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <circle cx="7" cy="7" r="5" stroke="var(--color-warning)" strokeWidth="1.5" />
                  <path d="M7 4v3M7 9v.5" stroke="var(--color-warning)" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                No UniProt ID found - you can enter it manually in the next step
              </span>
            )}
          </div>

          <div className="plan-actions">
            <button className="btn btn-ghost btn-sm" onClick={handleGeneratePlan}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 8a6 6 0 1 1 12 0A6 6 0 0 1 2 8z" stroke="currentColor" strokeWidth="1.5" />
                <path d="M8 4v4l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              Regenerate
            </button>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="card error-card">
          <div className="card-header">
            <h3 className="card-title">Error</h3>
            <span className="card-badge error">Failed</span>
          </div>
          <p className="error-message">{error}</p>
          <button className="btn btn-outline btn-sm" onClick={handleGeneratePlan}>
            Try Again
          </button>
        </div>
      )}

      {/* Actions */}
      <div className="step-actions">
        <button className="btn btn-ghost" onClick={onBack}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12.5 15l-5-5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back
        </button>
        <button
          className="btn btn-secondary btn-lg"
          onClick={handleContinue}
          disabled={!generatedPlan || isGenerating}
        >
          Continue to Sequence
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
