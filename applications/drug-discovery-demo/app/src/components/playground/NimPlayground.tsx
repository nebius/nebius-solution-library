/**
 * NimPlayground Component
 *
 * Main container for the NIM Playground mode.
 * Allows direct interaction with any NIM endpoint using custom data.
 */

import { useState, useCallback, useMemo } from 'react';
import { PlaygroundSidebar } from './PlaygroundSidebar';
import { NimResult } from './NimResult';
import { getPlaygroundConfig, type PlaygroundField, type PlaygroundResult, type NimPlaygroundDef } from '../../data/nimPlayground';
import { buildNimUrl, ENDPOINT_CONFIG } from '../../services/nimApi';
import { useGateway } from '../../contexts/GatewayContext';
import { NIM_ENDPOINTS } from '../../data/endpoints';

export function NimPlayground() {
  const [selectedNimId, setSelectedNimId] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, unknown>>({});
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<PlaygroundResult | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const { endpoints, gatewayUrl } = useGateway();

  const nimConfig = useMemo(
    () => (selectedNimId ? getPlaygroundConfig(selectedNimId) : null),
    [selectedNimId]
  );

  // Initialize form values when NIM changes
  const handleSelectNim = useCallback((nimId: string) => {
    const config = getPlaygroundConfig(nimId);
    if (!config) return;

    const defaults: Record<string, unknown> = {};
    for (const field of config.fields) {
      if (field.default !== undefined) {
        defaults[field.id] = field.default;
      }
    }

    setSelectedNimId(nimId);
    setFormValues(defaults);
    setResult(null);
    setShowAdvanced(false);
  }, []);

  // Update a single form value
  const updateField = useCallback((fieldId: string, value: unknown) => {
    setFormValues((prev) => ({ ...prev, [fieldId]: value }));
  }, []);

  // Submit the request
  const handleSubmit = useCallback(async () => {
    if (!nimConfig || !selectedNimId) return;

    const endpointConfig = ENDPOINT_CONFIG[selectedNimId];
    if (!endpointConfig) return;

    setIsRunning(true);
    setResult(null);
    const startTime = Date.now();

    try {
      const requestBody = nimConfig.buildRequest(formValues);
      const url = buildNimUrl(gatewayUrl, endpointConfig.port, endpointConfig.path);

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      const elapsed = Date.now() - startTime;
      setElapsedMs(elapsed);

      if (!response.ok) {
        const errorText = await response.text();
        let errorMessage: string;
        try {
          const errorJson = JSON.parse(errorText);
          errorMessage = errorJson.detail || errorJson.message || errorJson.error || errorText;
        } catch {
          errorMessage = errorText;
        }
        setResult({
          type: nimConfig.resultType,
          raw: { status: response.status, error: errorMessage },
          items: [],
          error: `HTTP ${response.status}: ${errorMessage}`,
        });
        return;
      }

      const data = await response.json();
      const parsed = nimConfig.parseResponse(data);
      setResult(parsed);
    } catch (error) {
      setElapsedMs(Date.now() - startTime);
      setResult({
        type: nimConfig.resultType,
        raw: { error: String(error) },
        items: [],
        error: error instanceof Error ? error.message : 'Request failed',
      });
    } finally {
      setIsRunning(false);
    }
  }, [nimConfig, selectedNimId, formValues, gatewayUrl]);

  // Check if required fields are filled
  const canSubmit = useMemo(() => {
    if (!nimConfig || isRunning || !gatewayUrl.trim()) return false;
    for (const field of nimConfig.fields) {
      if (field.required) {
        const val = formValues[field.id];
        if (!val || (typeof val === 'string' && !val.trim())) return false;
      }
    }
    return true;
  }, [nimConfig, isRunning, formValues, gatewayUrl]);

  // Group fields
  const fieldGroups = useMemo(() => {
    if (!nimConfig) return { input: [], parameters: [], advanced: [] };
    return {
      input: nimConfig.fields.filter((f) => f.group === 'input'),
      parameters: nimConfig.fields.filter((f) => f.group === 'parameters'),
      advanced: nimConfig.fields.filter((f) => f.group === 'advanced'),
    };
  }, [nimConfig]);

  const selectedEndpoint = selectedNimId
    ? endpoints.find((e) => e.id === selectedNimId)
    : undefined;
  const endpointStatus = selectedEndpoint?.status;
  const endpointDef = selectedNimId
    ? NIM_ENDPOINTS.find((e) => e.id === selectedNimId)
    : undefined;

  return (
    <>
      <PlaygroundSidebar
        selectedNimId={selectedNimId}
        onSelectNim={handleSelectNim}
      />

      <div className="content">
        {!nimConfig ? (
          <PlaygroundWelcome />
        ) : (
          <div className="step-content">
            {/* Header */}
            <div className="playground-nim-header">
              <div className="playground-nim-header-info">
                <h1>{nimConfig.name}</h1>
                <p>{nimConfig.description}</p>
                <div className="playground-nim-badges">
                  <span className="playground-badge category">{nimConfig.category}</span>
                  {endpointDef && (
                    <span className="playground-badge port">:{endpointDef.port}</span>
                  )}
                  {endpointDef && (
                    <span className="playground-badge gpu">
                      {endpointDef.gpu}{endpointDef.gpuCount && endpointDef.gpuCount > 1 ? ` x${endpointDef.gpuCount}` : ''}
                    </span>
                  )}
                  {endpointStatus && (
                    <span className={`playground-badge ${endpointStatus === 'ready' ? 'status-online' : 'status-offline'}`}>
                      {endpointStatus === 'ready' ? 'Online' : 'Offline'}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Input Section */}
            <div className="playground-card">
              <div className="playground-card-header">
                <h3 className="playground-card-title">Data Input</h3>
              </div>
              <div className="playground-card-body">
                <div className="playground-form">
                  {fieldGroups.input.map((field) => (
                    <FieldRenderer
                      key={field.id}
                      field={field}
                      value={formValues[field.id]}
                      onChange={(val) => updateField(field.id, val)}
                    />
                  ))}
                </div>
              </div>
            </div>

            {/* Parameters Section */}
            {fieldGroups.parameters.length > 0 && (
              <div className="playground-card">
                <div className="playground-card-header">
                  <h3 className="playground-card-title">Parameters</h3>
                </div>
                <div className="playground-card-body">
                  <div className="playground-form playground-form-grid">
                    {fieldGroups.parameters.map((field) => (
                      <FieldRenderer
                        key={field.id}
                        field={field}
                        value={formValues[field.id]}
                        onChange={(val) => updateField(field.id, val)}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Advanced Section */}
            {fieldGroups.advanced.length > 0 && (
              <div className="playground-card">
                <button
                  className="playground-advanced-toggle"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                >
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 12 12"
                    fill="none"
                    className={`playground-chevron ${showAdvanced ? 'expanded' : ''}`}
                  >
                    <path d="M4 3l4 3-4 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>Advanced Options ({fieldGroups.advanced.length})</span>
                </button>
                {showAdvanced && (
                  <div className="playground-card-body">
                    <div className="playground-form playground-form-grid">
                      {fieldGroups.advanced.map((field) => (
                        <FieldRenderer
                          key={field.id}
                          field={field}
                          value={formValues[field.id]}
                          onChange={(val) => updateField(field.id, val)}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Run Button */}
            <div className="playground-run-section">
              <button
                className="playground-run-btn"
                onClick={handleSubmit}
                disabled={!canSubmit}
              >
                {isRunning ? (
                  <>
                    <span className="spinner spinner-sm" />
                    Running {nimConfig.name}...
                  </>
                ) : (
                  <>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M4 2l10 6-10 6V2z" fill="currentColor" />
                    </svg>
                    Run {nimConfig.name}
                  </>
                )}
              </button>
              {!gatewayUrl.trim() && (
                <span className="playground-run-hint">Set a gateway URL in the sidebar to run queries</span>
              )}
            </div>

            {/* Request Preview */}
            <RequestPreview nimConfig={nimConfig} formValues={formValues} />

            {/* Results */}
            {result && <NimResult result={result} elapsedMs={elapsedMs} />}
          </div>
        )}
      </div>
    </>
  );
}

// ============================================================================
// Welcome Screen
// ============================================================================

function PlaygroundWelcome() {
  return (
    <div className="step-content">
      <div className="playground-welcome">
        <div className="playground-welcome-hero">
          <div className="playground-welcome-icon">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <path d="M26 4L6 28h18l-2 16 20-24H24l2-16z" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 className="playground-welcome-title">NIM Playground</h1>
          <p className="playground-welcome-subtitle">
            Interact directly with any NIM endpoint using your own data.
            Select a NIM from the sidebar to get started.
          </p>
        </div>
        <div className="playground-welcome-features">
          <div className="playground-welcome-feature">
            <div className="playground-welcome-feature-icon structure">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M10 2L3 6v8l7 4 7-4V6l-7-4z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
              </svg>
            </div>
            <div>
              <strong>Structure Prediction</strong>
              <span>OpenFold3, Boltz2, OpenFold2</span>
            </div>
          </div>
          <div className="playground-welcome-feature">
            <div className="playground-welcome-feature-icon molecule">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <circle cx="7" cy="8" r="3" stroke="currentColor" strokeWidth="1.5" />
                <circle cx="13" cy="8" r="3" stroke="currentColor" strokeWidth="1.5" />
                <circle cx="10" cy="15" r="3" stroke="currentColor" strokeWidth="1.5" />
              </svg>
            </div>
            <div>
              <strong>Molecule Generation</strong>
              <span>GenMol, MolMIM</span>
            </div>
          </div>
          <div className="playground-welcome-feature">
            <div className="playground-welcome-feature-icon docking">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <rect x="3" y="3" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.5" />
                <rect x="11" y="11" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.5" />
                <path d="M9 9l2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </div>
            <div>
              <strong>Docking & Design</strong>
              <span>DiffDock, ProteinMPNN, RFDiffusion</span>
            </div>
          </div>
          <div className="playground-welcome-feature">
            <div className="playground-welcome-feature-icon utility">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M3 5h14M3 10h10M3 15h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </div>
            <div>
              <strong>LLM & Utilities</strong>
              <span>Qwen3-80B, MSA Search, Evo2</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Request Preview
// ============================================================================

function RequestPreview({ nimConfig, formValues }: { nimConfig: NimPlaygroundDef; formValues: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false);

  let requestBody: unknown;
  try {
    requestBody = nimConfig.buildRequest(formValues);
  } catch {
    requestBody = { error: 'Failed to build request' };
  }

  const endpointConfig = ENDPOINT_CONFIG[nimConfig.id];
  const path = endpointConfig?.path || '(unknown)';

  return (
    <div className="playground-request-preview">
      <button className="playground-advanced-toggle" onClick={() => setExpanded(!expanded)}>
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          className={`playground-chevron ${expanded ? 'expanded' : ''}`}
        >
          <path d="M4 3l4 3-4 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span>Request Preview</span>
        <code className="playground-endpoint-badge">POST {path}</code>
      </button>
      {expanded && (
        <div className="playground-card-body">
          <pre className="playground-code-block">{JSON.stringify(requestBody, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Field Renderer
// ============================================================================

interface FieldRendererProps {
  field: PlaygroundField;
  value: unknown;
  onChange: (value: unknown) => void;
}

function FieldRenderer({ field, value, onChange }: FieldRendererProps) {
  const id = `pg-${field.id}`;

  return (
    <div className={`playground-field ${field.type === 'textarea' ? 'playground-field-full' : ''}`}>
      <label className="form-label" htmlFor={id}>
        {field.label}
        {field.required && <span className="playground-required">*</span>}
      </label>

      {field.type === 'text' && (
        <input
          id={id}
          type="text"
          className="form-input"
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
        />
      )}

      {field.type === 'textarea' && (
        <textarea
          id={id}
          className="form-textarea"
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          rows={field.rows || 4}
        />
      )}

      {field.type === 'number' && (
        <input
          id={id}
          type="number"
          className="form-input"
          value={value !== undefined ? Number(value) : ''}
          onChange={(e) => onChange(e.target.value === '' ? undefined : Number(e.target.value))}
          min={field.min}
          max={field.max}
          step={field.step}
        />
      )}

      {field.type === 'select' && (
        <select
          id={id}
          className="form-input"
          value={(value as string) ?? (field.default as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
        >
          {field.options?.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      )}

      {field.type === 'checkbox' && (
        <label className="playground-checkbox-label">
          <input
            type="checkbox"
            checked={!!value}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span>{field.description}</span>
        </label>
      )}

      {field.type === 'multiselect' && (
        <div className="playground-multiselect">
          {field.options?.map((opt) => {
            const selected = Array.isArray(value) ? (value as string[]).includes(opt.value) : false;
            return (
              <button
                key={opt.value}
                className={`playground-multiselect-btn ${selected ? 'active' : ''}`}
                onClick={() => {
                  const current = Array.isArray(value) ? (value as string[]) : [];
                  if (selected) {
                    onChange(current.filter((v) => v !== opt.value));
                  } else {
                    onChange([...current, opt.value]);
                  }
                }}
                type="button"
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      )}

      {field.description && field.type !== 'checkbox' && (
        <span className="playground-field-hint">{field.description}</span>
      )}
    </div>
  );
}
