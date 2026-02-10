/**
 * ScreeningStep Component
 *
 * Seventh step: Deploy model and screen compounds or sequences.
 * Molecular: SMILES input; Protein: sequence input.
 */

import { useState, useCallback } from 'react';
import { useFineTuning } from '../../../contexts/FineTuningContext';
import { getNebiusClient } from '../../../services/nebiusServerless';
import type { ScreeningResult } from '../../../types/finetuning';

interface ScreeningStepProps {
  gatewayUrl: string;
}

// Sample SMILES for molecular demo
const SAMPLE_SMILES = [
  'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
  'COc1ccc2c(c1)c(CC(=O)O)c(C)n2C(=O)c3ccc(Cl)cc3',
  'Cc1ccc(cc1)C2=CC(=O)c3c(O2)ccc(c3)O',
  'O=C(O)Cc1ccccc1Nc2c(Cl)cccc2Cl',
  'COc1ccc(cc1OC)C2CC(=O)c3c(O)cc(O)cc3O2',
  'CC(=O)Oc1ccccc1C(=O)O',
  'CN1C=NC2=C1C(=O)N(C(=O)N2C)C',
  'CC(C)NCC(O)c1ccc(O)c(O)c1',
  'CC12CCC3C(C1CCC2O)CCC4=CC(=O)CCC34C',
  'CN1CCC(=C2c3ccccc3Sc4ccc(Cl)cc24)CC1',
];

// Sample protein sequences for protein demo
const SAMPLE_SEQUENCES = [
  'MEKFLILNKQKQLAWDLNPHADYLARIQKLF',
  'GKKVFLIANAQKALIDLNVSTQDDLARIQALFE',
  'MKTVRQERLKSIVRILERSKEPVSGAQLA',
  'MKWVTFISLLFLFSSAYSRGVFRRDAHKSEVAHRFKD',
  'MGSSHHHHHHSSGLVPRGSHMRGPNPTAAQLK',
];

export function ScreeningStep({ gatewayUrl }: ScreeningStepProps) {
  const {
    trainingResult,
    selectedModel,
    endpoint,
    setEndpoint,
    screeningResults,
    setScreeningResults,
    resetAll,
    goToPrevStep,
  } = useFineTuning();

  const isProtein = selectedModel?.modality === 'protein';

  const [isDeploying, setIsDeploying] = useState(false);
  const [isScreening, setIsScreening] = useState(false);
  const [inputText, setInputText] = useState(
    isProtein ? SAMPLE_SEQUENCES.join('\n') : SAMPLE_SMILES.join('\n')
  );
  const [screeningTime, setScreeningTime] = useState<number | null>(null);

  // Deploy model
  const handleDeploy = useCallback(async () => {
    if (!trainingResult) return;

    setIsDeploying(true);

    try {
      const client = getNebiusClient({ apiBaseUrl: gatewayUrl });
      const endpointInfo = await client.deployModel(
        trainingResult.modelId,
        `${isProtein ? 'protein' : 'qsar'}-predictor-${Date.now().toString(36)}`
      );
      setEndpoint(endpointInfo);
    } catch (error) {
      console.error('Deployment failed:', error);
    } finally {
      setIsDeploying(false);
    }
  }, [trainingResult, gatewayUrl, setEndpoint, isProtein]);

  // Run screening
  const handleScreen = useCallback(async () => {
    if (!endpoint) return;

    const inputList = inputText
      .split('\n')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    if (inputList.length === 0) return;

    setIsScreening(true);
    setScreeningResults(null);
    const startTime = Date.now();

    try {
      const client = getNebiusClient({ apiBaseUrl: gatewayUrl });
      const predictions = await client.predict(
        endpoint.endpointId,
        inputList,
        endpoint.authToken
      );

      const sortedResults: ScreeningResult[] = predictions
        .sort((a, b) => a.predictedActivity - b.predictedActivity)
        .map((p, i) => ({ ...p, rank: i + 1 }));

      setScreeningResults(sortedResults);
      setScreeningTime(Date.now() - startTime);
    } catch (error) {
      console.error('Screening failed:', error);
    } finally {
      setIsScreening(false);
    }
  }, [endpoint, inputText, gatewayUrl, setScreeningResults]);

  // Download results as CSV
  const handleDownload = useCallback(() => {
    if (!screeningResults) return;

    const header = isProtein
      ? 'rank,sequence,predicted_score,confidence'
      : 'rank,smiles,predicted_activity_nM,confidence';

    const csv = [
      header,
      ...screeningResults.map(
        (r) => `${r.rank},${r.smiles},${r.predictedActivity.toFixed(2)},${r.confidence}`
      ),
    ].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `screening_results_${isProtein ? 'protein' : 'molecular'}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [screeningResults, isProtein]);

  if (!trainingResult) {
    return (
      <div className="step-content">
        <div className="content-header">
          <h1 className="content-title">Deploy & Screen</h1>
          <p className="content-subtitle">Please complete training first.</p>
        </div>
        <div className="step-actions">
          <button className="btn btn-ghost" onClick={goToPrevStep}>
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
          <h1 className="content-title">Deploy & Screen</h1>
          <p className="content-subtitle">
            Deploy your model to Nebius Jobs and screen {isProtein ? 'protein sequences' : 'compound libraries'}.
          </p>
        </div>
      </div>

      {/* Deployment Section */}
      <div className="card">
        <div className="card-header">
          <div className="deployment-header">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path
                d="M10 2L2 6l8 4 8-4-8-4zM2 14l8 4 8-4M2 10l8 4 8-4"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <h3 className="card-title">Nebius Jobs Endpoint</h3>
          </div>
          {endpoint && (
            <span className={`endpoint-status ${endpoint.state}`}>
              <span className="status-dot" />
              {endpoint.state.charAt(0).toUpperCase() + endpoint.state.slice(1)}
            </span>
          )}
        </div>

        {!endpoint ? (
          <div className="deployment-prompt">
            <p>Deploy your trained model as a serverless endpoint for real-time predictions.</p>
            <div className="deployment-features">
              <div className="deployment-feature">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M4 8l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>Auto-scaling (0-10 replicas)</span>
              </div>
              <div className="deployment-feature">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M4 8l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>No idle costs</span>
              </div>
              <div className="deployment-feature">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M4 8l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>~3s cold start</span>
              </div>
            </div>
            <button
              className="btn btn-primary"
              onClick={handleDeploy}
              disabled={isDeploying}
            >
              {isDeploying ? (
                <>
                  <span className="spinner spinner-sm" />
                  Deploying...
                </>
              ) : (
                <>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                  Deploy to Nebius Jobs
                </>
              )}
            </button>
          </div>
        ) : (
          <div className="endpoint-info">
            <div className="endpoint-details">
              <div className="endpoint-detail">
                <span className="endpoint-label">Endpoint URL</span>
                <code className="endpoint-value">{endpoint.url}</code>
              </div>
              <div className="endpoint-detail">
                <span className="endpoint-label">Model</span>
                <span className="endpoint-value">{selectedModel?.name || endpoint.modelId}</span>
              </div>
              <div className="endpoint-detail">
                <span className="endpoint-label">Platform</span>
                <span className="endpoint-value">{endpoint.platform}</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Screening Section */}
      {endpoint && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">
              {isProtein ? 'Sequence Screening' : 'Virtual Screening'}
            </h3>
          </div>

          <div className="screening-input">
            <label className="form-label">
              {isProtein
                ? 'Enter protein sequences (one per line):'
                : 'Enter SMILES (one per line) or paste a compound library:'}
            </label>
            <textarea
              className="form-textarea"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              rows={8}
              placeholder={
                isProtein
                  ? 'MEKFLILNKQKQLAWDLNPHADYLARIQKLF\nGKKVFLIANAQKALIDLNVSTQDDLARIQALFE\n...'
                  : 'CC(C)Cc1ccc(cc1)C(C)C(=O)O\nCOc1ccc2c(c1)c(CC(=O)O)c(C)n2C(=O)c3ccc(Cl)cc3\n...'
              }
            />
            <div className="screening-input-footer">
              <span className="compound-count">
                {inputText.split('\n').filter((s) => s.trim()).length} {isProtein ? 'sequences' : 'compounds'}
              </span>
              <button
                className="btn btn-primary"
                onClick={handleScreen}
                disabled={isScreening || !inputText.trim()}
              >
                {isScreening ? (
                  <>
                    <span className="spinner spinner-sm" />
                    Screening...
                  </>
                ) : (
                  <>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M4 4l8 4-8 4V4z" fill="currentColor" />
                    </svg>
                    Screen {isProtein ? 'Sequences' : 'Library'}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Results Section */}
      {screeningResults && screeningResults.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Screening Results</h3>
            <div className="card-header-actions">
              <span className="card-badge">
                {screeningResults.length} {isProtein ? 'sequences' : 'compounds'}
              </span>
              {screeningTime && (
                <span className="card-badge">
                  {(screeningTime / 1000).toFixed(2)}s ({Math.round(screeningResults.length / (screeningTime / 1000))} /s)
                </span>
              )}
            </div>
          </div>

          <div className="screening-results">
            <div className="results-table-header">
              <span className="results-col rank">Rank</span>
              <span className="results-col smiles">{isProtein ? 'Sequence' : 'SMILES'}</span>
              <span className="results-col activity">{isProtein ? 'Predicted Score' : 'Predicted IC50'}</span>
              <span className="results-col confidence">Confidence</span>
            </div>
            <div className="results-table-body">
              {screeningResults.slice(0, 20).map((result) => (
                <div key={result.rank} className="results-table-row">
                  <span className="results-col rank">#{result.rank}</span>
                  <span className="results-col smiles">
                    <code>
                      {result.smiles.length > 40
                        ? `${result.smiles.slice(0, 40)}...`
                        : result.smiles}
                    </code>
                  </span>
                  <span className="results-col activity">
                    {result.predictedActivity.toFixed(isProtein ? 3 : 1)} {result.predictedUnit}
                  </span>
                  <span className={`results-col confidence ${result.confidence}`}>
                    {result.confidence.charAt(0).toUpperCase() + result.confidence.slice(1)}
                  </span>
                </div>
              ))}
            </div>
            {screeningResults.length > 20 && (
              <div className="results-more">
                Showing top 20 of {screeningResults.length} results
              </div>
            )}
          </div>

          <div className="results-actions">
            <button className="btn btn-ghost" onClick={handleDownload}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1v8M3 6l4 4 4-4M2 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Download All Results (CSV)
            </button>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="step-actions">
        <button className="btn btn-ghost" onClick={goToPrevStep}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12.5 15l-5-5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back
        </button>
        <button className="btn btn-outline" onClick={resetAll}>
          Start New Training
        </button>
      </div>
    </div>
  );
}
