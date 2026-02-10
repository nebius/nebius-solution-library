/**
 * EvaluationStep Component
 *
 * Sixth step: Evaluate the trained model performance.
 * Shows regression metrics (R², MAE, scatter plot) or
 * classification metrics (Accuracy, F1, AUC-ROC, confusion matrix).
 */

import { useMemo, useEffect } from 'react';
import { useFineTuning } from '../../../contexts/FineTuningContext';
import type { EvaluationResult, ClassificationMetrics } from '../../../types/finetuning';

export function EvaluationStep() {
  const {
    trainingResult,
    evaluationResult,
    setEvaluationResult,
    selectedModel,
    goToNextStep,
    goToPrevStep,
  } = useFineTuning();

  const isClassification = selectedModel?.taskType === 'classification';

  // Generate evaluation data if not already present
  useEffect(() => {
    if (!trainingResult || evaluationResult) return;

    if (isClassification) {
      // Generate classification evaluation
      const numPoints = 100;
      const predictions = Array.from({ length: numPoints }, (_, i) => {
        const actual = Math.random() > 0.5 ? 1 : 0;
        const noise = (Math.random() - 0.5) * 0.3;
        const predicted = Math.min(1, Math.max(0, actual + noise));
        return {
          actual,
          predicted,
          smiles: `SEQ${i}`,
          residual: predicted - actual,
        };
      });

      const acc = trainingResult.finalMetrics.testAccuracy ?? 0.87;
      const f1 = trainingResult.finalMetrics.testF1 ?? 0.85;
      const aucRoc = trainingResult.finalMetrics.testAucRoc ?? 0.92;

      // Simulate confusion matrix from accuracy
      const total = numPoints;
      const tp = Math.round(total * acc * 0.5);
      const tn = Math.round(total * acc * 0.5);
      const fp = Math.round(total * (1 - acc) * 0.5);
      const fn = total - tp - tn - fp;

      const classificationMetrics: ClassificationMetrics = {
        accuracy: acc,
        f1,
        aucRoc,
        confusionMatrix: [[tp, fp], [fn, tn]],
        classLabels: ['Positive', 'Negative'],
      };

      const residuals = predictions.map((p) => p.residual);
      const mean = residuals.reduce((a, b) => a + b, 0) / residuals.length;
      const variance = residuals.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / residuals.length;

      const result: EvaluationResult = {
        testMetrics: {
          r2: 0,
          mae: 0,
          rmse: 0,
          pearsonR: 0,
          spearmanR: 0,
        },
        classificationMetrics,
        predictions,
        residualStats: {
          mean,
          std: Math.sqrt(variance),
          min: Math.min(...residuals),
          max: Math.max(...residuals),
        },
      };

      setEvaluationResult(result);
    } else {
      // Generate regression evaluation (existing logic)
      const numPoints = 100;
      const predictions = Array.from({ length: numPoints }, (_, i) => {
        const actual = Math.random() * 4 - 1;
        const noise = (Math.random() - 0.5) * 0.8;
        const predicted = actual + noise;
        return {
          actual,
          predicted,
          smiles: `C${i}CC(=O)O`,
          residual: predicted - actual,
        };
      });

      predictions.sort((a, b) => a.actual - b.actual);

      const residuals = predictions.map((p) => p.residual);
      const mean = residuals.reduce((a, b) => a + b, 0) / residuals.length;
      const variance = residuals.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / residuals.length;

      const result: EvaluationResult = {
        testMetrics: {
          r2: trainingResult.finalMetrics.testR2,
          mae: trainingResult.finalMetrics.testMae,
          rmse: trainingResult.finalMetrics.testRmse,
          pearsonR: Math.sqrt(trainingResult.finalMetrics.testR2),
          spearmanR: Math.sqrt(trainingResult.finalMetrics.testR2) - 0.02,
        },
        predictions,
        residualStats: {
          mean,
          std: Math.sqrt(variance),
          min: Math.min(...residuals),
          max: Math.max(...residuals),
        },
        comparisonBaseline: {
          r2: 0.534,
          mae: 0.623,
          name: 'Random Forest Baseline',
        },
      };

      setEvaluationResult(result);
    }
  }, [trainingResult, evaluationResult, setEvaluationResult, isClassification]);

  // Quality assessment
  const qualityAssessment = useMemo(() => {
    if (!evaluationResult) return null;

    if (isClassification && evaluationResult.classificationMetrics) {
      const { accuracy, f1 } = evaluationResult.classificationMetrics;
      if (accuracy >= 0.85 && f1 >= 0.8) {
        return { level: 'excellent', message: 'Excellent classification performance! Ready for screening.', color: 'var(--color-success)' };
      } else if (accuracy >= 0.7 && f1 >= 0.65) {
        return { level: 'good', message: 'Good performance. Consider more data or hyperparameter tuning.', color: 'var(--color-warning)' };
      }
      return { level: 'needs-improvement', message: 'Model needs improvement. Try more data or different hyperparameters.', color: 'var(--color-error)' };
    }

    const { r2, mae } = evaluationResult.testMetrics;
    if (r2 >= 0.8 && mae <= 0.4) {
      return { level: 'excellent', message: 'Excellent model performance! Ready for virtual screening.', color: 'var(--color-success)' };
    } else if (r2 >= 0.6 && mae <= 0.6) {
      return { level: 'good', message: 'Good performance. Consider more data or hyperparameter tuning for improvement.', color: 'var(--color-warning)' };
    }
    return { level: 'needs-improvement', message: 'Model needs improvement. Try more training data or different hyperparameters.', color: 'var(--color-error)' };
  }, [evaluationResult, isClassification]);

  // Improvement over baseline (regression only)
  const improvement = useMemo(() => {
    if (!evaluationResult?.comparisonBaseline || isClassification) return null;
    const baselineR2 = evaluationResult.comparisonBaseline.r2;
    const modelR2 = evaluationResult.testMetrics.r2;
    return ((modelR2 - baselineR2) / baselineR2) * 100;
  }, [evaluationResult, isClassification]);

  if (!trainingResult) {
    return (
      <div className="step-content">
        <div className="content-header">
          <h1 className="content-title">Model Evaluation</h1>
          <p className="content-subtitle">Please complete training first.</p>
        </div>
        <div className="step-actions">
          <button className="btn btn-ghost" onClick={goToPrevStep}>
            Back to Training
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Model Evaluation</h1>
          <p className="content-subtitle">
            Review {selectedModel?.name || 'your model'}'s performance on the held-out test set.
          </p>
        </div>
      </div>

      {/* Quality Assessment Banner */}
      {qualityAssessment && (
        <div
          className="quality-banner"
          style={{ borderLeftColor: qualityAssessment.color }}
        >
          <div className="quality-banner-icon">
            {qualityAssessment.level === 'excellent' ? (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            ) : qualityAssessment.level === 'good' ? (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            ) : (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </div>
          <div className="quality-banner-content">
            <span className="quality-banner-title">
              {qualityAssessment.level.charAt(0).toUpperCase() + qualityAssessment.level.slice(1).replace('-', ' ')} Performance
            </span>
            <span className="quality-banner-message">{qualityAssessment.message}</span>
          </div>
        </div>
      )}

      {/* Classification Metrics */}
      {isClassification && evaluationResult?.classificationMetrics && (
        <>
          <div className="metrics-cards">
            <div className="metric-card primary">
              <div className="metric-card-value">{evaluationResult.classificationMetrics.accuracy.toFixed(3)}</div>
              <div className="metric-card-label">Accuracy</div>
              <div className="metric-card-bar">
                <div
                  className="metric-card-bar-fill"
                  style={{ width: `${evaluationResult.classificationMetrics.accuracy * 100}%` }}
                />
              </div>
            </div>

            <div className="metric-card">
              <div className="metric-card-value">{evaluationResult.classificationMetrics.f1.toFixed(3)}</div>
              <div className="metric-card-label">F1 Score</div>
            </div>

            <div className="metric-card">
              <div className="metric-card-value">{evaluationResult.classificationMetrics.aucRoc.toFixed(3)}</div>
              <div className="metric-card-label">AUC-ROC</div>
            </div>
          </div>

          {/* Confusion Matrix */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Confusion Matrix</h3>
              <span className="card-badge">Test Set</span>
            </div>
            <div className="confusion-matrix">
              <div className="confusion-matrix-grid">
                <div className="confusion-matrix-corner" />
                <div className="confusion-matrix-header">Pred Positive</div>
                <div className="confusion-matrix-header">Pred Negative</div>
                <div className="confusion-matrix-label">Actual Positive</div>
                <div className="confusion-matrix-cell tp">
                  {evaluationResult.classificationMetrics.confusionMatrix[0][0]}
                  <span>TP</span>
                </div>
                <div className="confusion-matrix-cell fp">
                  {evaluationResult.classificationMetrics.confusionMatrix[0][1]}
                  <span>FP</span>
                </div>
                <div className="confusion-matrix-label">Actual Negative</div>
                <div className="confusion-matrix-cell fn">
                  {evaluationResult.classificationMetrics.confusionMatrix[1][0]}
                  <span>FN</span>
                </div>
                <div className="confusion-matrix-cell tn">
                  {evaluationResult.classificationMetrics.confusionMatrix[1][1]}
                  <span>TN</span>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Regression Metrics */}
      {!isClassification && evaluationResult && (
        <>
          <div className="metrics-cards">
            <div className="metric-card primary">
              <div className="metric-card-value">{evaluationResult.testMetrics.r2.toFixed(3)}</div>
              <div className="metric-card-label">R² Score</div>
              <div className="metric-card-bar">
                <div
                  className="metric-card-bar-fill"
                  style={{ width: `${evaluationResult.testMetrics.r2 * 100}%` }}
                />
              </div>
            </div>

            <div className="metric-card">
              <div className="metric-card-value">{evaluationResult.testMetrics.mae.toFixed(3)}</div>
              <div className="metric-card-label">MAE (log₁₀)</div>
            </div>

            <div className="metric-card">
              <div className="metric-card-value">{evaluationResult.testMetrics.rmse.toFixed(3)}</div>
              <div className="metric-card-label">RMSE (log₁₀)</div>
            </div>

            <div className="metric-card">
              <div className="metric-card-value">{evaluationResult.testMetrics.pearsonR.toFixed(3)}</div>
              <div className="metric-card-label">Pearson r</div>
            </div>
          </div>

          {/* Predicted vs Actual Plot */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Predicted vs Actual</h3>
              <span className="card-badge">Test Set ({evaluationResult.predictions.length} compounds)</span>
            </div>
            <div className="scatter-plot">
              <div className="scatter-plot-area">
                <div className="scatter-diagonal" />
                {evaluationResult.predictions.map((p, i) => {
                  const minVal = -1;
                  const maxVal = 3;
                  const range = maxVal - minVal;
                  const x = ((p.actual - minVal) / range) * 100;
                  const y = 100 - ((p.predicted - minVal) / range) * 100;
                  return (
                    <div
                      key={i}
                      className="scatter-point"
                      style={{
                        left: `${Math.max(0, Math.min(100, x))}%`,
                        top: `${Math.max(0, Math.min(100, y))}%`,
                      }}
                      title={`Actual: ${p.actual.toFixed(2)}, Predicted: ${p.predicted.toFixed(2)}`}
                    />
                  );
                })}
              </div>
              <div className="scatter-axis-x">
                <span>-1</span>
                <span>Actual log₁₀(Activity)</span>
                <span>3</span>
              </div>
              <div className="scatter-axis-y">
                <span>3</span>
                <span>Predicted</span>
                <span>-1</span>
              </div>
            </div>
            <div className="scatter-legend">
              <span>R² = {evaluationResult.testMetrics.r2.toFixed(3)}</span>
            </div>
          </div>

          {/* Baseline Comparison */}
          {evaluationResult.comparisonBaseline && improvement !== null && (
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">Comparison with Baseline</h3>
              </div>
              <div className="comparison-table">
                <div className="comparison-header">
                  <span></span>
                  <span>Your Model</span>
                  <span>{evaluationResult.comparisonBaseline.name}</span>
                  <span>Improvement</span>
                </div>
                <div className="comparison-row">
                  <span className="comparison-label">R² Score</span>
                  <span className="comparison-value highlight">
                    {evaluationResult.testMetrics.r2.toFixed(3)}
                  </span>
                  <span className="comparison-value">
                    {evaluationResult.comparisonBaseline.r2.toFixed(3)}
                  </span>
                  <span className={`comparison-improvement ${improvement > 0 ? 'positive' : 'negative'}`}>
                    {improvement > 0 ? '+' : ''}{improvement.toFixed(1)}%
                  </span>
                </div>
                <div className="comparison-row">
                  <span className="comparison-label">MAE</span>
                  <span className="comparison-value highlight">
                    {evaluationResult.testMetrics.mae.toFixed(3)}
                  </span>
                  <span className="comparison-value">
                    {evaluationResult.comparisonBaseline.mae.toFixed(3)}
                  </span>
                  <span className="comparison-improvement positive">
                    {((evaluationResult.comparisonBaseline.mae - evaluationResult.testMetrics.mae) / evaluationResult.comparisonBaseline.mae * 100).toFixed(1)}% better
                  </span>
                </div>
              </div>
              {improvement > 0 && (
                <div className="comparison-summary">
                  Your fine-tuned model outperforms the baseline by{' '}
                  <strong>{improvement.toFixed(0)}%</strong>!
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Actions */}
      <div className="step-actions">
        <button className="btn btn-ghost" onClick={goToPrevStep}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12.5 15l-5-5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back
        </button>
        <button className="btn btn-primary btn-lg" onClick={goToNextStep}>
          Deploy & Screen
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
