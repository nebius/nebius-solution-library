import { useState, useCallback, useEffect, useMemo } from 'react';
import Markdown from 'react-markdown';
import { streamChat } from '../../services/nimApi';
import type { DrugTarget } from '../../data/drugs';
import type { StructurePredictionResult } from '../../services/structurePrediction';
import type { GeneratedMolecule } from '../../services/moleculeGeneration';
import type { DockingResult } from '../../services/docking';
import { formatSimilarity, getSimilarityLevel, analyzeRediscovery } from '../../services/similarity';
import { lookupMultipleMolecules, formatMoleculeName, type MoleculeInfo } from '../../services/moleculeLookup';

interface SummaryStepProps {
  selectedDrug: DrugTarget | null;
  proteinInfo: {
    accession: string;
    name: string;
    organism: string;
    sequence: string;
    length: number;
  } | null;
  structureResult: StructurePredictionResult | null;
  generatedMolecules: GeneratedMolecule[];
  dockingResults: DockingResult[];
  gatewayUrl: string;
  onBack: () => void;
  onRestart: () => void;
}

const SUMMARY_SYSTEM_PROMPT = `You are an expert computational drug discovery scientist presenting results to a conference audience. Summarize the drug rediscovery workflow results in a clear, engaging way.

Structure your summary:
1. **Objective** - What we set out to discover
2. **Key Findings** - Highlight the most promising results
3. **Success Assessment** - Did we rediscover the target drug?
4. **Scientific Insights** - What this tells us about the approach
5. **Next Steps** - Recommendations for further research

Be concise but impactful. Use scientific language appropriate for a biotech conference.`;

export function SummaryStep({
  selectedDrug,
  proteinInfo,
  structureResult,
  generatedMolecules,
  dockingResults,
  gatewayUrl,
  onBack,
  onRestart,
}: SummaryStepProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [summary, setSummary] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [moleculeNames, setMoleculeNames] = useState<Map<string, MoleculeInfo>>(new Map());
  const [isLookingUp, setIsLookingUp] = useState(false);

  // Compute rediscovery analysis
  const rediscoveryResult = useMemo(() => {
    if (!selectedDrug?.referenceSMILES || dockingResults.length === 0) return null;
    const dockedSmiles = dockingResults.filter(r => r.poses.length > 0).map(r => r.ligandSmiles);
    if (dockedSmiles.length === 0) return null;
    return analyzeRediscovery(selectedDrug.referenceSMILES, selectedDrug.name, dockedSmiles);
  }, [selectedDrug, dockingResults]);

  // Best docking results (top 5)
  const topDockingResults = useMemo(() => {
    return dockingResults
      .filter(r => r.poses.length > 0)
      .sort((a, b) => b.bestConfidence - a.bestConfidence)
      .slice(0, 5);
  }, [dockingResults]);

  const bestDocking = topDockingResults[0] || null;

  // Look up molecule names from PubChem
  useEffect(() => {
    if (topDockingResults.length === 0) return;

    const smilesToLookup = topDockingResults.map(r => r.ligandSmiles);

    setIsLookingUp(true);
    lookupMultipleMolecules(smilesToLookup, 3)
      .then(results => {
        setMoleculeNames(results);
      })
      .catch(console.error)
      .finally(() => setIsLookingUp(false));
  }, [topDockingResults]);

  // Build prompt with workflow data
  const buildPrompt = useCallback(() => {
    const parts = [];

    parts.push(`# Drug Rediscovery Workflow Summary Request`);
    parts.push(`## Target: ${selectedDrug?.name || 'Unknown'}`);
    parts.push(`Category: ${selectedDrug?.category || 'Unknown'}`);
    parts.push(`Reference SMILES: ${selectedDrug?.referenceSMILES || 'N/A'}`);

    if (proteinInfo) {
      parts.push(`\n## Target Protein`);
      parts.push(`- Name: ${proteinInfo.name}`);
      parts.push(`- UniProt: ${proteinInfo.accession}`);
      parts.push(`- Length: ${proteinInfo.length} residues`);
    }

    if (structureResult) {
      parts.push(`\n## Structure Prediction`);
      parts.push(`- Model: ${structureResult.modelUsed}`);
      parts.push(`- Confidence: ${(structureResult.confidenceScore * 100).toFixed(1)}%`);
      parts.push(`- pLDDT: ${structureResult.plddt.toFixed(1)}`);
    }

    parts.push(`\n## Molecule Generation`);
    parts.push(`- Candidates generated: ${generatedMolecules.length}`);
    if (generatedMolecules.length > 0) {
      const avgScore = generatedMolecules.reduce((sum, m) => sum + m.score, 0) / generatedMolecules.length;
      parts.push(`- Average QED score: ${avgScore.toFixed(3)}`);
      parts.push(`- Top candidate SMILES: ${generatedMolecules[0]?.smiles || 'N/A'}`);
    }

    parts.push(`\n## Docking Results`);
    parts.push(`- Molecules docked: ${dockingResults.length}`);
    parts.push(`- Successful docks: ${dockingResults.filter(r => r.poses.length > 0).length}`);
    if (bestDocking) {
      const bestMolName = moleculeNames.get(bestDocking.ligandSmiles)?.name;
      const isRefDrug = bestDocking.ligandSmiles.toLowerCase() === selectedDrug?.referenceSMILES?.toLowerCase();
      parts.push(`- Best docking confidence: ${(bestDocking.bestConfidence * 100).toFixed(1)}%`);
      parts.push(`- Best docking molecule: ${isRefDrug ? selectedDrug?.name : (bestMolName || 'Novel compound')}`);
    }
    // Include reference drug's docking score if different from best
    if (selectedDrug?.referenceSMILES) {
      const refDocking = dockingResults.find(
        r => r.ligandSmiles.toLowerCase() === selectedDrug.referenceSMILES.toLowerCase()
      );
      if (refDocking && refDocking.poses.length > 0) {
        const isAlsoBest = bestDocking?.ligandSmiles.toLowerCase() === selectedDrug.referenceSMILES.toLowerCase();
        if (!isAlsoBest) {
          parts.push(`- ${selectedDrug.name} (reference) docking confidence: ${(refDocking.bestConfidence * 100).toFixed(1)}%`);
        }
      } else if (refDocking) {
        parts.push(`- ${selectedDrug.name} (reference) docking: Failed or no poses`);
      }
    }

    if (rediscoveryResult) {
      const isHighSimilarity = (rediscoveryResult.bestMatch?.similarity || 0) >= 0.7;
      parts.push(`\n## Rediscovery Analysis`);
      parts.push(`- Best similarity to ${selectedDrug?.name}: ${formatSimilarity(rediscoveryResult.bestMatch?.similarity || 0)}`);
      parts.push(`- Status: ${rediscoveryResult.exactMatch ? 'EXACT MATCH - Drug rediscovered!' : isHighSimilarity ? 'HIGH SIMILARITY - Drug rediscovered!' : 'Similar compounds found'}`);
      parts.push(`- Exact match: ${rediscoveryResult.exactMatch ? 'Yes' : 'No'}`);
    }

    parts.push(`\n---`);
    parts.push(`Please provide a comprehensive summary of these results suitable for a biotech conference presentation.`);

    return parts.join('\n');
  }, [selectedDrug, proteinInfo, structureResult, generatedMolecules, dockingResults, bestDocking, rediscoveryResult, moleculeNames]);

  // Generate summary on mount
  const handleGenerateSummary = useCallback(async () => {
    if (!gatewayUrl) return;

    setIsGenerating(true);
    setSummary('');
    setError(null);

    try {
      const messages = [
        { role: 'system' as const, content: SUMMARY_SYSTEM_PROMPT },
        { role: 'user' as const, content: buildPrompt() },
      ];

      let fullSummary = '';
      for await (const chunk of streamChat(gatewayUrl, messages, { maxTokens: 1500 })) {
        fullSummary += chunk;
        setSummary(fullSummary);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate summary';
      setError(message);
    } finally {
      setIsGenerating(false);
    }
  }, [gatewayUrl, buildPrompt]);

  // Auto-generate on mount
  useEffect(() => {
    if (gatewayUrl && !summary && !isGenerating) {
      handleGenerateSummary();
    }
  }, [gatewayUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!selectedDrug) {
    return (
      <div className="step-content">
        <div className="content-header">
          <div>
            <h1 className="content-title">Results Summary</h1>
            <p className="content-subtitle">No workflow data available.</p>
          </div>
        </div>
        <div className="step-actions">
          <button className="btn btn-ghost" onClick={onBack}>Back</button>
        </div>
      </div>
    );
  }

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Results Summary</h1>
          <p className="content-subtitle">
            Complete drug rediscovery workflow results for {selectedDrug.name}
          </p>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="summary-stats">
        <div className="summary-stat-card">
          <div className="summary-stat-icon protein">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
              <path d="M12 6v6l4 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>
          <div className="summary-stat-content">
            <span className="summary-stat-value">{proteinInfo?.length || 0}</span>
            <span className="summary-stat-label">Residues</span>
          </div>
        </div>

        <div className="summary-stat-card">
          <div className="summary-stat-icon structure">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
              <path d="M2 17l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
              <path d="M2 12l10 5 10-5" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="summary-stat-content">
            <span className="summary-stat-value">
              {structureResult ? `${(structureResult.confidenceScore * 100).toFixed(0)}%` : '-'}
            </span>
            <span className="summary-stat-label">Structure Confidence</span>
          </div>
        </div>

        <div className="summary-stat-card">
          <div className="summary-stat-icon molecules">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
              <circle cx="6" cy="6" r="2" stroke="currentColor" strokeWidth="2" />
              <circle cx="18" cy="6" r="2" stroke="currentColor" strokeWidth="2" />
              <circle cx="18" cy="18" r="2" stroke="currentColor" strokeWidth="2" />
              <path d="M9 9l-2-2M15 9l2-2M15 15l2 2" stroke="currentColor" strokeWidth="2" />
            </svg>
          </div>
          <div className="summary-stat-content">
            <span className="summary-stat-value">{generatedMolecules.length}</span>
            <span className="summary-stat-label">Molecules Generated</span>
          </div>
        </div>

        <div className="summary-stat-card">
          <div className="summary-stat-icon docking">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>
          <div className="summary-stat-content">
            <span className="summary-stat-value">
              {bestDocking ? `${(bestDocking.bestConfidence * 100).toFixed(0)}%` : '-'}
            </span>
            <span className="summary-stat-label">Best Docking Score</span>
          </div>
        </div>

        <div className={`summary-stat-card ${rediscoveryResult?.exactMatch || (rediscoveryResult?.bestMatch?.similarity || 0) >= 0.7 ? 'success' : 'partial'}`}>
          <div className="summary-stat-icon rediscovery">
            {rediscoveryResult?.exactMatch || (rediscoveryResult?.bestMatch?.similarity || 0) >= 0.7 ? (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                <path d="M22 4L12 14.01l-3-3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            ) : (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
                <path d="M12 8v4M12 16h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            )}
          </div>
          <div className="summary-stat-content">
            <span className={`summary-stat-value ${getSimilarityLevel(rediscoveryResult?.bestMatch?.similarity || 0)}`}>
              {formatSimilarity(rediscoveryResult?.bestMatch?.similarity || 0)}
            </span>
            <span className="summary-stat-label">
              {rediscoveryResult?.exactMatch ? 'Exact Match!' : (rediscoveryResult?.bestMatch?.similarity || 0) >= 0.7 ? 'Rediscovered!' : 'Best Similarity'}
            </span>
          </div>
        </div>
      </div>

      {/* Top Discovered Molecules */}
      {topDockingResults.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Top Discovered Molecules</h3>
            {isLookingUp && (
              <span className="card-badge">
                <span className="spinner spinner-sm" /> Looking up names...
              </span>
            )}
          </div>
          <div className="discovered-molecules-list">
            {topDockingResults.map((result, index) => {
              const info = moleculeNames.get(result.ligandSmiles);
              const isReference = result.ligandSmiles.toLowerCase() === selectedDrug?.referenceSMILES?.toLowerCase();
              const similarity = rediscoveryResult?.similarities.find(
                s => s.smiles === result.ligandSmiles
              );

              return (
                <div
                  key={result.ligandSmiles}
                  className={`discovered-molecule-item ${isReference ? 'reference' : ''} ${info?.isKnownDrug ? 'known-drug' : ''}`}
                >
                  <div className="discovered-molecule-rank">#{index + 1}</div>
                  <div className="discovered-molecule-info">
                    <div className="discovered-molecule-name">
                      {isReference ? (
                        <span className="reference-badge">
                          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                            <path d="M6 1l5 3v4l-5 3-5-3V4l5-3z" stroke="currentColor" strokeWidth="1.5" />
                          </svg>
                          {selectedDrug?.name}
                        </span>
                      ) : info?.name ? (
                        <span className={info.isKnownDrug ? 'known-drug-name' : ''}>
                          {info.name}
                          {info.isKnownDrug && (
                            <span className="known-drug-badge">Known Drug</span>
                          )}
                        </span>
                      ) : (
                        <code className="smiles-preview">
                          {result.ligandSmiles.length > 40
                            ? result.ligandSmiles.substring(0, 40) + '...'
                            : result.ligandSmiles}
                        </code>
                      )}
                    </div>
                    {info?.iupacName && !info.isKnownDrug && (
                      <div className="discovered-molecule-iupac">
                        {info.iupacName.length > 60
                          ? info.iupacName.substring(0, 60) + '...'
                          : info.iupacName}
                      </div>
                    )}
                  </div>
                  <div className="discovered-molecule-scores">
                    <div className="score-item">
                      <span className="score-label">Docking</span>
                      <span className="score-value">{(result.bestConfidence * 100).toFixed(0)}%</span>
                    </div>
                    {similarity && (
                      <div className="score-item">
                        <span className="score-label">Similarity</span>
                        <span className={`score-value ${getSimilarityLevel(similarity.similarity)}`}>
                          {formatSimilarity(similarity.similarity)}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* AI Summary */}
      <div className="card summary-card">
        <div className="card-header">
          <h3 className="card-title">AI-Generated Summary</h3>
          <div className="card-actions">
            {!isGenerating && (
              <button className="btn btn-ghost btn-sm" onClick={handleGenerateSummary}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M1 7a6 6 0 1 1 12 0A6 6 0 0 1 1 7z" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M7 4v3l2 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                Regenerate
              </button>
            )}
          </div>
        </div>

        {isGenerating && !summary && (
          <div className="summary-generating">
            <span className="spinner spinner-md" />
            <span>Generating summary with Qwen3...</span>
          </div>
        )}

        {summary && (
          <div className="summary-content">
            <Markdown>{summary}</Markdown>
            {isGenerating && <span className="summary-cursor" />}
          </div>
        )}

        {error && (
          <div className="summary-error">
            <p>{error}</p>
            <button className="btn btn-outline btn-sm" onClick={handleGenerateSummary}>
              Try Again
            </button>
          </div>
        )}
      </div>

      {/* Workflow Complete Banner */}
      <div className="workflow-complete-banner">
        <div className="workflow-complete-icon">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <circle cx="24" cy="24" r="22" stroke="currentColor" strokeWidth="3" />
            <path d="M14 24l7 7 13-13" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div className="workflow-complete-content">
          <h2>Drug Discovery Workflow Complete</h2>
          <p>
            Successfully completed the {selectedDrug.name} rediscovery pipeline using
            NVIDIA NIMs on Nebius AI Cloud.
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className="step-actions">
        <button className="btn btn-ghost" onClick={onBack}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12.5 15l-5-5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back
        </button>
        <button className="btn btn-primary btn-lg" onClick={onRestart}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M3 10a7 7 0 1 1 14 0A7 7 0 0 1 3 10z" stroke="currentColor" strokeWidth="2" />
            <path d="M10 6v4l2.5 1.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          Start New Discovery
        </button>
      </div>
    </div>
  );
}
