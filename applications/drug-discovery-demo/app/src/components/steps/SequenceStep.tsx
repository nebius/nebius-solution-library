import { useState, useCallback } from 'react';
import { fetchSequence, formatSequence, isValidAccession } from '../../services/uniprot';
import { proteinToDna, calculateGcContent, generateSequenceVariations } from '../../services/evo2';

interface ProteinInfo {
  accession: string;
  name: string;
  organism: string;
  sequence: string;
  length: number;
}

interface SequenceStepProps {
  uniprotId: string;
  onUniprotIdChange: (id: string) => void;
  proteinInfo: ProteinInfo | null;
  onProteinInfoChange: (info: ProteinInfo | null) => void;
  gatewayUrl: string;
  onBack: () => void;
  onContinue: () => void;
}

export function SequenceStep({
  uniprotId,
  onUniprotIdChange,
  proteinInfo,
  onProteinInfoChange,
  gatewayUrl,
  onBack,
  onContinue,
}: SequenceStepProps) {
  const [isFetching, setIsFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Evo2 state
  const [showDnaAnalysis, setShowDnaAnalysis] = useState(false);
  const [dnaSequence, setDnaSequence] = useState<string | null>(null);
  const [gcContent, setGcContent] = useState<number | null>(null);
  const [isGeneratingVariations, setIsGeneratingVariations] = useState(false);
  const [dnaVariations, setDnaVariations] = useState<string[]>([]);
  const [evo2Error, setEvo2Error] = useState<string | null>(null);

  const handleFetchSequence = useCallback(async () => {
    if (!uniprotId.trim()) {
      setError('Please enter a UniProt ID');
      return;
    }

    if (!isValidAccession(uniprotId)) {
      setError('Invalid UniProt ID format. Expected 6-10 alphanumeric characters (e.g., P35354)');
      return;
    }

    setIsFetching(true);
    setError(null);
    // Reset DNA analysis when fetching new sequence
    setDnaSequence(null);
    setGcContent(null);
    setDnaVariations([]);
    setShowDnaAnalysis(false);

    try {
      const entry = await fetchSequence(uniprotId);
      onProteinInfoChange({
        accession: entry.accession,
        name: entry.proteinName,
        organism: entry.organism,
        sequence: entry.sequence,
        length: entry.length,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch sequence';
      setError(message);
      onProteinInfoChange(null);
    } finally {
      setIsFetching(false);
    }
  }, [uniprotId, onProteinInfoChange]);

  // DNA Analysis with Evo2
  const handleShowDnaAnalysis = useCallback(() => {
    if (!proteinInfo) return;
    const dna = proteinToDna(proteinInfo.sequence);
    setDnaSequence(dna);
    setGcContent(calculateGcContent(dna));
    setShowDnaAnalysis(true);
  }, [proteinInfo]);

  const handleGenerateVariations = useCallback(async () => {
    if (!dnaSequence || !gatewayUrl) return;

    setIsGeneratingVariations(true);
    setEvo2Error(null);

    try {
      // Only use a portion of the DNA for Evo2 (first 512 bases) due to model limits
      const truncatedDna = dnaSequence.substring(0, 512);
      const result = await generateSequenceVariations(gatewayUrl, truncatedDna, {
        numVariations: 3,
        temperature: 0.7,
      });
      setDnaVariations(result.sequences);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate variations';
      setEvo2Error(message);
    } finally {
      setIsGeneratingVariations(false);
    }
  }, [dnaSequence, gatewayUrl]);

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Protein Sequence</h1>
          <p className="content-subtitle">
            Fetch the target protein sequence from UniProt, the authoritative protein database.
          </p>
        </div>
      </div>

      {/* UniProt ID Input */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">UniProt Accession</h3>
          <a
            href="https://www.uniprot.org/"
            target="_blank"
            rel="noopener noreferrer"
            className="card-badge"
            style={{ textDecoration: 'none' }}
          >
            UniProt.org
          </a>
        </div>

        <div className="uniprot-input-row">
          <div className="form-group" style={{ flex: 1 }}>
            <label className="form-label" htmlFor="uniprot-id">
              UniProt ID
            </label>
            <input
              id="uniprot-id"
              type="text"
              className="form-input"
              placeholder="e.g., P35354"
              value={uniprotId}
              onChange={(e) => onUniprotIdChange(e.target.value.toUpperCase())}
            />
            <span className="form-hint">
              Enter the UniProt accession ID identified by the AI in the previous step
            </span>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleFetchSequence}
            disabled={isFetching || !uniprotId.trim()}
            style={{ alignSelf: 'flex-end', marginBottom: '24px' }}
          >
            {isFetching ? (
              <>
                <span className="spinner spinner-sm" />
                Fetching...
              </>
            ) : (
              <>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path
                    d="M14 8a6 6 0 1 1-12 0 6 6 0 0 1 12 0z"
                    stroke="currentColor"
                    strokeWidth="1.5"
                  />
                  <path
                    d="M8 5v6M5 8h6"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                </svg>
                Fetch Sequence
              </>
            )}
          </button>
        </div>

        {error && (
          <div className="error-banner">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 5v4M8 11v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            {error}
          </div>
        )}
      </div>

      {/* Protein Info Display */}
      {proteinInfo && (
        <div className="card sequence-card">
          <div className="card-header">
            <h3 className="card-title">{proteinInfo.name || proteinInfo.accession}</h3>
            <span className="card-badge success">{proteinInfo.length} residues</span>
          </div>

          <div className="protein-meta">
            <div className="protein-meta-item">
              <span className="protein-meta-label">Accession</span>
              <span className="protein-meta-value">{proteinInfo.accession}</span>
            </div>
            <div className="protein-meta-item">
              <span className="protein-meta-label">Organism</span>
              <span className="protein-meta-value">{proteinInfo.organism || 'Unknown'}</span>
            </div>
          </div>

          <div className="sequence-display">
            <div className="sequence-header">
              <span className="sequence-label">Amino Acid Sequence</span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => navigator.clipboard.writeText(proteinInfo.sequence)}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <rect x="4" y="4" width="8" height="8" rx="1" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M2 10V3a1 1 0 0 1 1-1h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                Copy
              </button>
            </div>
            <pre className="sequence-text">{formatSequence(proteinInfo.sequence)}</pre>
          </div>
        </div>
      )}

      {/* Evo2 DNA Analysis (Optional) */}
      {proteinInfo && (
        <div className="card">
          <div className="card-header">
            <div className="msa-header-content">
              <h3 className="card-title">DNA Analysis</h3>
              <span className="optional-badge">Optional</span>
              <span className="gpu-tag gpu-h200">Evo2-40B</span>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={showDnaAnalysis}
                onChange={(e) => e.target.checked ? handleShowDnaAnalysis() : setShowDnaAnalysis(false)}
              />
              <span className="toggle-slider" />
            </label>
          </div>

          {!showDnaAnalysis && (
            <p className="msa-description">
              View the back-translated DNA sequence and use Evo2-40B to generate codon-optimized variations.
            </p>
          )}

          {showDnaAnalysis && dnaSequence && (
            <div className="dna-analysis-content">
              <div className="dna-stats">
                <div className="msa-stat">
                  <span className="msa-stat-value">{dnaSequence.length}</span>
                  <span className="msa-stat-label">Nucleotides</span>
                </div>
                <div className="msa-stat">
                  <span className="msa-stat-value">{((gcContent || 0) * 100).toFixed(1)}%</span>
                  <span className="msa-stat-label">GC Content</span>
                </div>
                <div className="msa-stat">
                  <span className="msa-stat-value">{Math.floor(dnaSequence.length / 3)}</span>
                  <span className="msa-stat-label">Codons</span>
                </div>
              </div>

              <div className="sequence-display">
                <div className="sequence-header">
                  <span className="sequence-label">DNA Sequence (Back-translated)</span>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => navigator.clipboard.writeText(dnaSequence)}
                  >
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <rect x="4" y="4" width="8" height="8" rx="1" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M2 10V3a1 1 0 0 1 1-1h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    Copy
                  </button>
                </div>
                <pre className="sequence-text dna-sequence">
                  {dnaSequence.match(/.{1,60}/g)?.slice(0, 5).map((chunk, i) => (
                    <div key={i} className="sequence-line">
                      <span className="sequence-position">{i * 60 + 1}</span>
                      <span className="sequence-chunk">{chunk}</span>
                    </div>
                  ))}
                  {dnaSequence.length > 300 && (
                    <div className="sequence-truncated">
                      ... {dnaSequence.length - 300} more nucleotides
                    </div>
                  )}
                </pre>
              </div>

              {/* Evo2 Variation Generation */}
              <div className="evo2-section">
                <div className="evo2-header">
                  <h4>Generate Variations with Evo2</h4>
                  <p className="evo2-description">
                    Use the Evo2-40B foundation model to explore sequence variations.
                  </p>
                </div>

                {!dnaVariations.length && !isGeneratingVariations && (
                  <button
                    className="btn btn-primary"
                    onClick={handleGenerateVariations}
                    disabled={!gatewayUrl || isGeneratingVariations}
                  >
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M8 2v2M8 12v2M2 8h2M12 8h2M3.5 3.5l1.5 1.5M11 11l1.5 1.5M3.5 12.5l1.5-1.5M11 5l1.5-1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    Generate Variations
                  </button>
                )}

                {isGeneratingVariations && (
                  <div className="msa-searching">
                    <span className="spinner" />
                    <span>Generating variations with Evo2-40B...</span>
                  </div>
                )}

                {evo2Error && (
                  <div className="msa-error">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M8 5v4M8 11v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    <span>{evo2Error}</span>
                  </div>
                )}

                {dnaVariations.length > 0 && (
                  <div className="evo2-variations">
                    <h5>Generated Variations</h5>
                    {dnaVariations.map((variation, i) => (
                      <div key={i} className="variation-item">
                        <span className="variation-label">Variation {i + 1}</span>
                        <code className="variation-preview">
                          {variation.substring(0, 60)}...
                        </code>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => navigator.clipboard.writeText(variation)}
                        >
                          Copy
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="step-actions">
        <button className="btn btn-ghost" onClick={onBack}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path
              d="M12.5 15l-5-5 5-5"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Back
        </button>
        <button
          className="btn btn-secondary btn-lg"
          onClick={onContinue}
          disabled={!proteinInfo}
        >
          Continue to Structure Prediction
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
