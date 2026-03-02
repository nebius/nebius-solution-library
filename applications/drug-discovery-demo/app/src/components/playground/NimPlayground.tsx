/**
 * NimPlayground Component
 *
 * Main container for the NIM Playground mode.
 * Allows direct interaction with any NIM endpoint using custom data.
 */

import { useState, useCallback, useMemo, useRef } from 'react';
import Markdown from 'react-markdown';
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
  const [parallelProgress, setParallelProgress] = useState<{ done: number; total: number } | null>(null);
  const [streamingText, setStreamingText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const streamAbortRef = useRef<AbortController | null>(null);

  const { endpoints, gatewayUrl } = useGateway();

  const nimConfig = useMemo(
    () => (selectedNimId ? getPlaygroundConfig(selectedNimId) : null),
    [selectedNimId]
  );

  const [isExampleResult, setIsExampleResult] = useState(false);

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
    setShowAdvanced(false);

    // Show example result if available
    if (config.exampleResult) {
      setResult(config.exampleResult);
      setIsExampleResult(true);
      setElapsedMs(0);
    } else {
      setResult(null);
      setIsExampleResult(false);
    }
  }, []);

  // Update a single form value
  const updateField = useCallback((fieldId: string, value: unknown) => {
    setFormValues((prev) => ({ ...prev, [fieldId]: value }));
  }, []);

  // Submit the request (supports parallel requests for NIMs with supportsParallel)
  const handleSubmit = useCallback(async () => {
    if (!nimConfig || !selectedNimId) return;

    const endpointConfig = ENDPOINT_CONFIG[selectedNimId];
    if (!endpointConfig) return;

    setIsRunning(true);
    setResult(null);
    setIsExampleResult(false);
    setParallelProgress(null);
    const startTime = Date.now();

    try {
      const requestBody = nimConfig.buildRequest(formValues);
      const path = nimConfig.endpointPath || endpointConfig.path;
      const port = nimConfig.port || endpointConfig.port;
      const url = buildNimUrl(gatewayUrl, port, path);
      const parallelCount = nimConfig.supportsParallel
        ? Math.max(1, Math.min(10, Number(formValues.parallelRequests ?? 1)))
        : 1;

      if (parallelCount > 1 && nimConfig.mergeResults) {
        // Parallel execution
        setParallelProgress({ done: 0, total: parallelCount });
        let completed = 0;

        const promises = Array.from({ length: parallelCount }, () =>
          fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
          })
            .then(async (response) => {
              if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
              }
              const data = await response.json();
              const parsed = nimConfig.parseResponse(data);
              completed++;
              setParallelProgress({ done: completed, total: parallelCount });
              return parsed;
            })
        );

        const settled = await Promise.allSettled(promises);
        const elapsed = Date.now() - startTime;
        setElapsedMs(elapsed);

        const successResults = settled
          .filter((r): r is PromiseFulfilledResult<PlaygroundResult> => r.status === 'fulfilled')
          .map((r) => r.value);
        const failCount = settled.filter((r) => r.status === 'rejected').length;

        if (successResults.length === 0) {
          const firstError = settled.find((r) => r.status === 'rejected') as PromiseRejectedResult | undefined;
          setResult({
            type: nimConfig.resultType,
            raw: { error: 'All parallel requests failed' },
            items: [],
            error: firstError?.reason?.message || 'All parallel requests failed',
          });
        } else {
          const merged = nimConfig.mergeResults(successResults);
          if (failCount > 0) {
            merged.error = `${failCount} of ${parallelCount} requests failed`;
          }
          setResult(merged);
        }
      } else if (nimConfig.supportsStreaming) {
        // Streaming request (LLM)
        streamAbortRef.current = new AbortController();
        setStreamingText('');
        setIsStreaming(true);
        setIsThinking(true);

        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestBody),
          signal: streamAbortRef.current.signal,
        });

        if (!response.ok) {
          const errorText = await response.text();
          let errorMessage: string;
          try {
            const errorJson = JSON.parse(errorText);
            errorMessage = errorJson.detail || errorJson.message || errorJson.error || errorText;
          } catch {
            errorMessage = errorText;
          }
          setElapsedMs(Date.now() - startTime);
          setResult({
            type: nimConfig.resultType,
            raw: { status: response.status, error: errorMessage },
            items: [],
            error: `HTTP ${response.status}: ${errorMessage}`,
          });
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';
        let content = '';
        let reasoning = '';
        let thinking = true;
        let usage: Record<string, number> | undefined;

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed || trimmed === 'data: [DONE]') continue;

              if (trimmed.startsWith('data: ')) {
                try {
                  const json = JSON.parse(trimmed.slice(6));
                  const delta = json.choices?.[0]?.delta;
                  if (delta?.reasoning_content) {
                    reasoning += delta.reasoning_content;
                  }
                  if (delta?.content) {
                    if (thinking) {
                      thinking = false;
                      setIsThinking(false);
                    }
                    content += delta.content;
                    setStreamingText(content);
                  }
                  if (json.usage) {
                    usage = json.usage;
                  }
                } catch {
                  // Skip malformed JSON
                }
              }
            }
          }
        } finally {
          reader.releaseLock();
        }

        const elapsed = Date.now() - startTime;
        setElapsedMs(elapsed);
        setIsStreaming(false);
        setIsThinking(false);

        // Build final result with all data
        const items: { label: string; value: string; format: 'text' }[] = [
          { label: 'Response', value: content, format: 'text' },
        ];
        if (reasoning) {
          items.push({ label: 'Reasoning', value: reasoning, format: 'text' });
        }
        if (usage) {
          items.push({
            label: 'Usage',
            value: `Prompt: ${usage.prompt_tokens} tokens | Completion: ${usage.completion_tokens} tokens | Total: ${usage.total_tokens} tokens`,
            format: 'text',
          });
        }
        setResult({ type: 'text', raw: { content, reasoning, usage }, items });
      } else {
        // Single non-streaming request
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
        if (nimConfig.resultType === 'docking' && formValues.protein) {
          parsed.proteinStructure = String(formValues.protein);
        }
        setResult(parsed);
      }
    } catch (error) {
      if (streamAbortRef.current?.signal.aborted) return;
      setElapsedMs(Date.now() - startTime);
      setResult({
        type: nimConfig.resultType,
        raw: { error: String(error) },
        items: [],
        error: error instanceof Error ? error.message : 'Request failed',
      });
    } finally {
      setIsRunning(false);
      setIsStreaming(false);
      setIsThinking(false);
      setParallelProgress(null);
      streamAbortRef.current = null;
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
                    {parallelProgress
                      ? `Running ${nimConfig.name}... (${parallelProgress.done}/${parallelProgress.total})`
                      : `Running ${nimConfig.name}...`
                    }
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

            {/* API Code Snippets */}
            <RequestPreview nimConfig={nimConfig} formValues={formValues} gatewayUrl={gatewayUrl} />

            {/* Streaming Display */}
            {isStreaming && (
              <div className="playground-result-card">
                <div className="playground-result-header">
                  <div className="playground-result-header-left">
                    <span className="playground-streaming-dot" />
                    <h3>{isThinking ? 'Thinking...' : 'Generating...'}</h3>
                  </div>
                </div>
                <div className="playground-card-body">
                  {isThinking ? (
                    <div className="playground-thinking">
                      <span className="spinner spinner-sm" />
                      <span>Reasoning...</span>
                    </div>
                  ) : (
                    <div className="playground-result-text playground-streaming-text">
                      <Markdown components={{ table: ({ children }) => <div className="playground-table-wrap"><table>{children}</table></div> }}>
                        {streamingText}
                      </Markdown>
                      <span className="playground-cursor" />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Results */}
            {!isStreaming && result && (
              <>
                {isExampleResult && (
                  <div className="playground-example-banner">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M8 5v3M8 10v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    <span>
                      <strong>Example result</strong> using default inputs — click <strong>Run</strong> to generate with your own data
                    </span>
                  </div>
                )}
                <NimResult result={result} elapsedMs={elapsedMs} />
              </>
            )}
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
              <span>Nemotron-3-Nano, MSA Search, Evo2</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Request Preview + Code Snippets
// ============================================================================

type SnippetTab = 'json' | 'curl' | 'python';

function RequestPreview({ nimConfig, formValues, gatewayUrl }: { nimConfig: NimPlaygroundDef; formValues: Record<string, unknown>; gatewayUrl: string }) {
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<SnippetTab>('curl');
  const [copied, setCopied] = useState(false);

  let requestBody: unknown;
  try {
    requestBody = nimConfig.buildRequest(formValues);
  } catch {
    requestBody = { error: 'Failed to build request' };
  }

  const endpointConfig = ENDPOINT_CONFIG[nimConfig.id];
  const port = nimConfig.port || endpointConfig?.port || 8000;
  const path = nimConfig.endpointPath || endpointConfig?.path || '(unknown)';

  // Build the direct URL (no proxy — for external use)
  const host = gatewayUrl.trim().replace(/^https?:\/\//, '').replace(/\/$/, '') || '<GATEWAY_HOST>';
  const directUrl = `http://${host}:${port}${path}`;
  const jsonStr = JSON.stringify(requestBody, null, 2);

  const buildCurl = () => {
    const escapedJson = JSON.stringify(requestBody);
    return `curl -X POST '${directUrl}' \\\n  -H 'Content-Type: application/json' \\\n  -d '${escapedJson}'`;
  };

  const buildPython = () => {
    return `import requests

url = "${directUrl}"

payload = ${jsonStr}

response = requests.post(url, json=payload)
response.raise_for_status()
data = response.json()
print(data)`;
  };

  const snippets: Record<SnippetTab, string> = {
    json: jsonStr,
    curl: buildCurl(),
    python: buildPython(),
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(snippets[activeTab]);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
      const textarea = document.createElement('textarea');
      textarea.value = snippets[activeTab];
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

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
        <span>API Code Snippets</span>
        <code className="playground-endpoint-badge">POST :{port}{path}</code>
      </button>
      {expanded && (
        <div className="playground-card-body">
          <div className="playground-snippet-tabs">
            <button
              className={`playground-snippet-tab ${activeTab === 'curl' ? 'active' : ''}`}
              onClick={() => setActiveTab('curl')}
            >curl</button>
            <button
              className={`playground-snippet-tab ${activeTab === 'python' ? 'active' : ''}`}
              onClick={() => setActiveTab('python')}
            >Python</button>
            <button
              className={`playground-snippet-tab ${activeTab === 'json' ? 'active' : ''}`}
              onClick={() => setActiveTab('json')}
            >JSON Body</button>
            <button
              className="playground-snippet-copy"
              onClick={handleCopy}
            >
              {copied ? (
                <>
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M3 7l3 3 5-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Copied!
                </>
              ) : (
                <>
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <rect x="4" y="4" width="8" height="8" rx="1" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M10 4V3a1 1 0 00-1-1H3a1 1 0 00-1 1v6a1 1 0 001 1h1" stroke="currentColor" strokeWidth="1.5" />
                  </svg>
                  Copy
                </>
              )}
            </button>
          </div>
          <pre className="playground-code-block">{snippets[activeTab]}</pre>
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
