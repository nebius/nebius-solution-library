import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import {
  type GeneratedMolecule,
  type MoleculeGenerationResult,
  type MolMIMRequest,
  buildMolMIMRequest,
  generateWithMolMIM,
  sortByScore,
} from '../../services/moleculeGeneration';
import { streamChat } from '../../services/nimApi';
import { MoleculeViewer2D } from '../MoleculeViewer2D';
import { DrugLikenessBadge } from '../DrugLikenessPanel';
import type { DrugTarget } from '../../data/drugs';
import { formatDuration } from '../../hooks/useProgressTracker';
import { StepAssistant } from '../StepAssistant';

type GenerationStage = 'encoding' | 'exploring' | 'scoring';

// Prompt for generating seed molecule (pretending target drug doesn't exist)
// IMPORTANT: Must be structurally DISTANT from the target drug to avoid data leakage
const SEED_GENERATION_PROMPT = `You are a medicinal chemist. Based on the therapeutic goal below, suggest a SINGLE starting compound (seed molecule) for drug discovery.

CRITICAL RULES:
1. The seed must be STRUCTURALLY DISTINCT from known drugs for this target
2. DO NOT suggest close analogs, derivatives, or molecules from the same chemical class
3. Choose a scaffold with the right pharmacophore features (e.g., acidic group for COX, hinge binder for kinases) but DIFFERENT core structure
4. Good starting points: natural products, fragments, hits from unrelated screens, or scaffolds from different therapeutic areas that happen to have relevant features
5. Avoid: direct analogs, prodrugs, or molecules that would have high Tanimoto similarity (>0.5) to known drugs for this target
6. Keep the molecule drug-like (MW 200-500, reasonable LogP)

Therapeutic Goal:
{PROMPT}

Think about what structural features are needed for activity, then find a DIVERSE scaffold that has those features. Explain your reasoning (2-3 sentences), then provide the SMILES.
Format: SMILES: [your SMILES string here]`;

/**
 * Extract SMILES from LLM response
 */
function extractSmilesFromResponse(text: string): string | null {
  // Try to find SMILES: pattern
  const smilesMatch = text.match(/SMILES:\s*([^\s\n]+)/i);
  if (smilesMatch && smilesMatch[1]) {
    return smilesMatch[1].trim();
  }

  // Try to find a SMILES-like pattern (contains C, (, ), =, etc.)
  const patterns = text.match(/[A-Z][A-Za-z0-9@\[\]\(\)=#+\-\\\/\.]+/g);
  if (patterns) {
    // Find the longest pattern that looks like SMILES
    for (const p of patterns.sort((a, b) => b.length - a.length)) {
      if (p.length > 5 && /[CNO]/.test(p) && /[\(\)=\[\]]/.test(p)) {
        return p;
      }
    }
  }

  return null;
}

interface MoleculesStepProps {
  selectedDrug: DrugTarget | null;
  gatewayUrl: string;
  onMoleculesGenerated: (molecules: GeneratedMolecule[]) => void;
  onContinue: () => void;
  onBack: () => void;
}

type SeedMode = 'ai' | 'manual' | 'reference';

export function MoleculesStep({
  selectedDrug,
  gatewayUrl,
  onMoleculesGenerated,
  onContinue,
  onBack,
}: MoleculesStepProps) {
  // Seed generation state
  const [seedMode, setSeedMode] = useState<SeedMode>('ai');
  const [isGeneratingSeed, setIsGeneratingSeed] = useState(false);
  const [aiSeedResponse, setAiSeedResponse] = useState('');
  const [aiSeedSmiles, setAiSeedSmiles] = useState('');
  const [manualSeedSmiles, setManualSeedSmiles] = useState('');
  const [seedError, setSeedError] = useState<string | null>(null);

  // Molecule generation state
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState<MoleculeGenerationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedMolecules, setSelectedMolecules] = useState<Set<number>>(new Set());
  const [showQueryEditor, setShowQueryEditor] = useState(false);
  const [editedRequest, setEditedRequest] = useState<string>('');
  const [queryError, setQueryError] = useState<string | null>(null);
  const [numMolecules, setNumMolecules] = useState(30);
  const [scaledRadius, setScaledRadius] = useState(1.2);

  // Processing animation state
  const [elapsedTime, setElapsedTime] = useState(0);
  const [generationStage, setGenerationStage] = useState<GenerationStage>('encoding');
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Timer effect for processing animation
  useEffect(() => {
    if (isProcessing) {
      setElapsedTime(0);
      setGenerationStage('encoding');

      timerRef.current = setInterval(() => {
        setElapsedTime((prev) => {
          const newTime = prev + 100;
          // Simulate stage progression
          if (newTime > 2000 && newTime <= 5000) {
            setGenerationStage('exploring');
          } else if (newTime > 5000) {
            setGenerationStage('scoring');
          }
          return newTime;
        });
      }, 100);

      return () => {
        if (timerRef.current) {
          clearInterval(timerRef.current);
        }
      };
    }
  }, [isProcessing]);

  // Determine active seed SMILES based on mode
  const seedSmiles = useMemo(() => {
    switch (seedMode) {
      case 'ai':
        return aiSeedSmiles;
      case 'manual':
        return manualSeedSmiles;
      case 'reference':
        return selectedDrug?.referenceSMILES || '';
    }
  }, [seedMode, aiSeedSmiles, manualSeedSmiles, selectedDrug]);

  // Generate seed using Qwen
  const handleGenerateSeed = useCallback(async () => {
    if (!gatewayUrl || !selectedDrug) return;

    setIsGeneratingSeed(true);
    setAiSeedResponse('');
    setAiSeedSmiles('');
    setSeedError(null);

    try {
      const prompt = SEED_GENERATION_PROMPT.replace('{PROMPT}', selectedDrug.llmPrompt || selectedDrug.description);

      const messages = [
        { role: 'system' as const, content: 'You are a medicinal chemist expert in drug discovery.' },
        { role: 'user' as const, content: prompt },
      ];

      let fullResponse = '';
      for await (const chunk of streamChat(gatewayUrl, messages, { maxTokens: 500 })) {
        fullResponse += chunk;
        setAiSeedResponse(fullResponse);

        // Try to extract SMILES as we stream
        const smiles = extractSmilesFromResponse(fullResponse);
        if (smiles) {
          setAiSeedSmiles(smiles);
        }
      }

      // Final extraction
      const smiles = extractSmilesFromResponse(fullResponse);
      if (smiles) {
        setAiSeedSmiles(smiles);
      } else {
        setSeedError('Could not extract SMILES from response. Please try again or enter manually.');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate seed';
      setSeedError(message);
    } finally {
      setIsGeneratingSeed(false);
    }
  }, [gatewayUrl, selectedDrug]);

  const initialRequest = useMemo(() => {
    return buildMolMIMRequest(seedSmiles, numMolecules);
  }, [seedSmiles, numMolecules]);

  // Initialize edited request
  useEffect(() => {
    const req: MolMIMRequest = {
      ...initialRequest,
      scaled_radius: scaledRadius,
    };
    setEditedRequest(JSON.stringify(req, null, 2));
  }, [initialRequest, scaledRadius]);

  const handleRequestChange = useCallback((value: string) => {
    setEditedRequest(value);
    try {
      JSON.parse(value);
      setQueryError(null);
    } catch {
      setQueryError('Invalid JSON');
    }
  }, []);

  const handleGenerate = useCallback(async () => {
    if (!gatewayUrl || !seedSmiles) return;

    setIsProcessing(true);
    setError(null);
    setResult(null);
    setSelectedMolecules(new Set());

    try {
      let request: MolMIMRequest;
      try {
        request = JSON.parse(editedRequest);
      } catch {
        request = initialRequest;
      }

      const generationResult = await generateWithMolMIM(gatewayUrl, request);

      // Sort by score
      generationResult.molecules = sortByScore(generationResult.molecules);

      // Add reference drug if not already in the list (for rediscovery demo)
      if (selectedDrug?.referenceSMILES) {
        const refSmiles = selectedDrug.referenceSMILES;
        const alreadyExists = generationResult.molecules.some(
          (m) => m.smiles.toLowerCase() === refSmiles.toLowerCase()
        );

        if (!alreadyExists) {
          // Add reference drug with its actual QED score and special flag
          generationResult.molecules.push({
            smiles: refSmiles,
            score: selectedDrug.referenceQED ?? 0.5, // Use pre-computed QED from literature
            isReference: true,
          });
        } else {
          // Mark existing molecule as reference
          const refMolecule = generationResult.molecules.find(
            (m) => m.smiles.toLowerCase() === refSmiles.toLowerCase()
          );
          if (refMolecule) {
            refMolecule.isReference = true;
          }
        }
      }

      setResult(generationResult);

      // Auto-select top 10 molecules (plus reference if added at the end)
      const topIndices = new Set(
        generationResult.molecules.slice(0, Math.min(10, generationResult.molecules.length)).map((_, i) => i)
      );
      // Also select the reference molecule if it exists
      const refIndex = generationResult.molecules.findIndex((m) => m.isReference);
      if (refIndex !== -1) {
        topIndices.add(refIndex);
      }
      setSelectedMolecules(topIndices);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Molecule generation failed';
      setError(message);
    } finally {
      setIsProcessing(false);
      // Stop the timer
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  }, [gatewayUrl, seedSmiles, editedRequest, initialRequest, selectedDrug]);

  const handleToggleMolecule = useCallback((index: number) => {
    setSelectedMolecules((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    if (!result) return;
    setSelectedMolecules(new Set(result.molecules.map((_, i) => i)));
  }, [result]);

  const handleSelectNone = useCallback(() => {
    setSelectedMolecules(new Set());
  }, []);

  const handleSelectTop = useCallback((n: number) => {
    if (!result) return;
    setSelectedMolecules(new Set(result.molecules.slice(0, n).map((_, i) => i)));
  }, [result]);

  const handleContinue = useCallback(() => {
    if (!result) return;
    const selected = result.molecules.filter((_, i) => selectedMolecules.has(i));
    onMoleculesGenerated(selected);
    onContinue();
  }, [result, selectedMolecules, onMoleculesGenerated, onContinue]);

  const getScoreColor = (score: number) => {
    if (score >= 0.7) return 'score-high';
    if (score >= 0.4) return 'score-medium';
    return 'score-low';
  };

  const formatElapsedTime = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  if (!selectedDrug) {
    return (
      <div className="step-content">
        <div className="content-header">
          <div>
            <h1 className="content-title">Molecule Generation</h1>
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
          <h1 className="content-title">Molecule Generation</h1>
          <p className="content-subtitle">
            Generate candidate molecules using MolMIM. Choose a seed molecule to start the optimization.
          </p>
        </div>
      </div>

      {/* Seed Molecule Selection */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Seed Molecule</h3>
          <span className="card-badge">{selectedDrug.category}</span>
        </div>

        {/* Seed Mode Selection */}
        <div className="seed-mode-selector">
          <button
            className={`seed-mode-btn ${seedMode === 'ai' ? 'active' : ''}`}
            onClick={() => setSeedMode('ai')}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 5v3l2 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            AI Generated
          </button>
          <button
            className={`seed-mode-btn ${seedMode === 'manual' ? 'active' : ''}`}
            onClick={() => setSeedMode('manual')}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M12 2l2 2-8 8H4v-2l8-8z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            Manual Entry
          </button>
          <button
            className={`seed-mode-btn ${seedMode === 'reference' ? 'active' : ''}`}
            onClick={() => setSeedMode('reference')}
            title="Use the actual drug (not recommended for true rediscovery)"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M8 2l6 4v4l-6 4-6-4V6l6-4z" stroke="currentColor" strokeWidth="1.5" />
            </svg>
            Reference Drug
          </button>
        </div>

        {/* AI Seed Generation */}
        {seedMode === 'ai' && (
          <div className="seed-section">
            <p className="seed-description">
              Let AI suggest a <strong>structurally diverse</strong> starting compound for drug discovery.
              The AI will propose a scaffold with relevant pharmacophore features but distinct from known
              drugs, enabling genuine exploration of chemical space rather than trivial analog generation.
            </p>

            {!aiSeedSmiles && !isGeneratingSeed && (
              <button
                className="btn btn-outline"
                onClick={handleGenerateSeed}
                disabled={!gatewayUrl}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                Generate Seed with Qwen
              </button>
            )}

            {isGeneratingSeed && (
              <div className="seed-generating">
                <span className="spinner spinner-sm" />
                <span>Generating seed molecule...</span>
              </div>
            )}

            {aiSeedResponse && (
              <div className="seed-response">
                <div className="seed-response-text">{aiSeedResponse}</div>
                {aiSeedSmiles && (
                  <div className="seed-smiles-result">
                    <span className="seed-smiles-label">Extracted SMILES:</span>
                    <code className="seed-smiles-value">{aiSeedSmiles}</code>
                  </div>
                )}
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={handleGenerateSeed}
                  disabled={isGeneratingSeed}
                >
                  Regenerate
                </button>
              </div>
            )}

            {seedError && <p className="seed-error">{seedError}</p>}
          </div>
        )}

        {/* Manual Entry */}
        {seedMode === 'manual' && (
          <div className="seed-section">
            <p className="seed-description">
              Enter a SMILES string for the seed molecule. This will be used as the starting point for MolMIM generation.
            </p>
            <div className="seed-input-row">
              <input
                type="text"
                className="seed-input"
                placeholder="Enter SMILES (e.g., CC(C)Cc1ccccc1)"
                value={manualSeedSmiles}
                onChange={(e) => setManualSeedSmiles(e.target.value)}
              />
            </div>
          </div>
        )}

        {/* Reference Drug Warning */}
        {seedMode === 'reference' && (
          <div className="seed-section">
            <div className="seed-warning">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M8 2l6 10H2L8 2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                <path d="M8 6v3M8 11v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <span>
                Using the actual {selectedDrug.name} SMILES as seed. This "cheats" in the rediscovery demo
                since we're starting from the answer.
              </span>
            </div>
            <div className="molecule-info-row">
              <span className="molecule-info-label">{selectedDrug.name} SMILES</span>
              <code className="molecule-smiles">{selectedDrug.referenceSMILES}</code>
            </div>
          </div>
        )}

        {/* Current Seed Display with 2D Structure */}
        {seedSmiles && (
          <div className="current-seed">
            <div className="current-seed-structure">
              <MoleculeViewer2D smiles={seedSmiles} width={200} height={150} />
            </div>
            <div className="current-seed-info">
              <span className="current-seed-label">Active Seed:</span>
              <code className="current-seed-value">{seedSmiles}</code>
            </div>
          </div>
        )}
      </div>

      {/* Generation Parameters */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Generation Parameters</h3>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setShowQueryEditor(!showQueryEditor)}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M12 2l2 2-8 8H4v-2l8-8z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {showQueryEditor ? 'Hide' : 'Show'} JSON
          </button>
        </div>

        <div className="parameter-grid">
          <div className="parameter-item">
            <label className="parameter-label">Number of Molecules</label>
            <input
              type="number"
              className="parameter-input"
              value={numMolecules}
              onChange={(e) => setNumMolecules(Math.min(100, Math.max(1, parseInt(e.target.value) || 10)))}
              min={1}
              max={100}
              disabled={isProcessing}
            />
            <span className="parameter-hint">1-100 molecules</span>
          </div>
          <div className="parameter-item">
            <label className="parameter-label">Diversity (Scaled Radius)</label>
            <input
              type="number"
              className="parameter-input"
              value={scaledRadius}
              onChange={(e) => setScaledRadius(Math.min(2, Math.max(0.1, parseFloat(e.target.value) || 1)))}
              min={0.1}
              max={2}
              step={0.1}
              disabled={isProcessing}
            />
            <span className="parameter-hint">Higher = more diverse</span>
          </div>
        </div>

        {showQueryEditor && (
          <div className="query-editor-body">
            <div className="query-endpoint">
              <span className="query-endpoint-label">Endpoint:</span>
              <code className="query-endpoint-value">/generate (MolMIM)</code>
            </div>
            <textarea
              className={`query-textarea ${queryError ? 'has-error' : ''}`}
              value={editedRequest}
              onChange={(e) => handleRequestChange(e.target.value)}
              spellCheck={false}
            />
            {queryError && <p className="query-error-message">{queryError}</p>}
          </div>
        )}
      </div>

      {/* Generate Button */}
      {!result && !isProcessing && (
        <div className="card prediction-action-card">
          <div className="prediction-action-content">
            <button
              className="btn btn-primary btn-lg"
              onClick={handleGenerate}
              disabled={!gatewayUrl || !seedSmiles || !!queryError}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M10 2v16M2 10h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              Generate {numMolecules} Molecules
            </button>
            {!gatewayUrl && (
              <p className="prediction-hint">Enter NIM Gateway URL to continue</p>
            )}
          </div>
        </div>
      )}

      {/* Processing State */}
      {isProcessing && (
        <div className="card processing-card molecule-generation-processing">
          <div className="processing-content">
            {/* Animated molecule visualization */}
            <div className="molecule-animation">
              <div className="molecule-orbit">
                <div className="molecule-atom atom-1"></div>
                <div className="molecule-atom atom-2"></div>
                <div className="molecule-atom atom-3"></div>
                <div className="molecule-atom atom-4"></div>
                <div className="molecule-atom atom-5"></div>
                <div className="molecule-atom atom-6"></div>
              </div>
              <div className="molecule-core">
                <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
                  <circle cx="20" cy="20" r="16" fill="var(--color-lime)" />
                  <circle cx="20" cy="20" r="8" fill="var(--color-deep-blue)" />
                </svg>
              </div>
            </div>

            <h3 className="processing-title">Generating Molecules</h3>

            {/* Live timer */}
            <div className="generation-timer">
              <span className="timer-value">Elapsed: {formatDuration(elapsedTime)}</span>
            </div>

            {/* Progress stages */}
            <div className="generation-stages">
              <div className={`generation-stage ${generationStage === 'encoding' ? 'active' : 'completed'}`}>
                <div className="stage-icon">
                  {generationStage === 'encoding' ? (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="2" />
                      <path d="M10 6v4l2.5 1.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  ) : (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M4 10l4 4 8-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </div>
                <span>Encoding seed molecule</span>
              </div>
              <div className={`generation-stage ${generationStage === 'exploring' ? 'active' : generationStage === 'scoring' ? 'completed' : 'pending'}`}>
                <div className="stage-icon">
                  {generationStage === 'exploring' ? (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M10 2v4M10 14v4M2 10h4M14 10h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  ) : generationStage === 'scoring' ? (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path d="M4 10l4 4 8-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="10" r="6" stroke="currentColor" strokeWidth="2" strokeDasharray="4 2" />
                    </svg>
                  )}
                </div>
                <span>Exploring chemical space</span>
              </div>
              <div className={`generation-stage ${generationStage === 'scoring' ? 'active' : 'pending'}`}>
                <div className="stage-icon">
                  {generationStage === 'scoring' ? (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <rect x="3" y="8" width="4" height="9" rx="1" stroke="currentColor" strokeWidth="2" />
                      <rect x="8" y="5" width="4" height="12" rx="1" stroke="currentColor" strokeWidth="2" />
                      <rect x="13" y="3" width="4" height="14" rx="1" stroke="currentColor" strokeWidth="2" />
                    </svg>
                  ) : (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <circle cx="10" cy="10" r="6" stroke="currentColor" strokeWidth="2" strokeDasharray="4 2" />
                    </svg>
                  )}
                </div>
                <span>Scoring candidates</span>
              </div>
            </div>

            <div className="generation-info">
              <div className="generation-stat">
                <span className="stat-value">{numMolecules}</span>
                <span className="stat-label">molecules requested</span>
              </div>
              <div className="generation-stat">
                <span className="stat-value">MolMIM</span>
                <span className="stat-label">generative model</span>
              </div>
            </div>

            <p className="processing-description generation-hint">
              MolMIM uses a masked language model to generate novel molecules
              similar to your seed compound while exploring diverse chemical modifications.
            </p>
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="molecules-results">
          <div className="molecules-results-header">
            <div>
              <h3 className="molecules-results-title">
                Generated {result.molecules.length} Molecules
              </h3>
              <p className="molecules-results-subtitle">
                Completed in {formatElapsedTime(result.elapsedTime)} using {result.modelUsed}
              </p>
            </div>
            <div className="molecules-selection-controls">
              <button className="btn btn-ghost btn-sm" onClick={handleSelectAll}>
                Select All
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => handleSelectTop(10)}>
                Top 10
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => handleSelectTop(20)}>
                Top 20
              </button>
              <button className="btn btn-ghost btn-sm" onClick={handleSelectNone}>
                None
              </button>
            </div>
          </div>

          <div className="molecules-selected-count">
            <span className="selected-count-number">{selectedMolecules.size}</span>
            <span className="selected-count-label">molecules selected for docking</span>
          </div>

          <div className="molecules-grid">
            {result.molecules.map((molecule, index) => {
              const isSelected = selectedMolecules.has(index);
              return (
                <div
                  key={index}
                  className={`molecule-card ${isSelected ? 'selected' : ''} ${molecule.isReference ? 'reference' : ''}`}
                  onClick={() => handleToggleMolecule(index)}
                  role="button"
                  tabIndex={0}
                >
                  <div className="molecule-card-header">
                    <span className="molecule-rank">#{index + 1}</span>
                    {molecule.isReference && (
                      <span className="molecule-reference-badge">
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                          <path d="M6 1l5 3v4l-5 3-5-3V4l5-3z" stroke="currentColor" strokeWidth="1.5" />
                        </svg>
                        {selectedDrug?.name}
                      </span>
                    )}
                    <span className={`molecule-score ${getScoreColor(molecule.score)}`}>
                      QED: {molecule.score.toFixed(3)}
                    </span>
                    {isSelected && (
                      <span className="molecule-selected-icon">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                          <path d="M2 8l4 4 8-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </span>
                    )}
                  </div>
                  {/* 2D Molecule Structure */}
                  <div className="molecule-card-structure">
                    <MoleculeViewer2D smiles={molecule.smiles} width={160} height={120} />
                  </div>
                  {/* Drug-Likeness Badge */}
                  <DrugLikenessBadge smiles={molecule.smiles} />
                  <code className="molecule-smiles-preview">
                    {molecule.smiles.length > 40
                      ? molecule.smiles.substring(0, 40) + '...'
                      : molecule.smiles}
                  </code>
                </div>
              );
            })}
          </div>

          <div className="molecules-actions">
            <button className="btn btn-ghost" onClick={handleGenerate}>
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
            <h3 className="card-title">Generation Failed</h3>
            <span className="card-badge error">Error</span>
          </div>
          <p className="error-message">{error}</p>
          <button className="btn btn-outline btn-sm" onClick={handleGenerate}>
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
          disabled={selectedMolecules.size === 0}
          onClick={handleContinue}
        >
          Continue with {selectedMolecules.size} Molecules
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      {/* Step Assistant */}
      <StepAssistant
        stepType="molecules"
        gatewayUrl={gatewayUrl}
        context={{
          seedSmiles,
          seedMode,
          numMolecules,
          scaledRadius,
          generatedCount: result?.molecules.length,
          selectedCount: selectedMolecules.size,
          topMolecules: result?.molecules.slice(0, 5).map(m => ({
            smiles: m.smiles,
            score: m.score,
          })),
        }}
      />
    </div>
  );
}
