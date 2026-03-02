/**
 * NimResult Component
 *
 * Renders the result of a NIM API call.
 * Handles different result types: structure, molecules, sequences, alignment, text, json.
 */

import { useState, useCallback, useMemo } from 'react';
import Markdown from 'react-markdown';
import type { PlaygroundResult, PlaygroundResultItem } from '../../data/nimPlayground';
import { StructureViewer } from '../StructureViewer';
import { MoleculeViewer2D } from '../MoleculeViewer2D';

const LIGAND_COLORS = ['#00FF88', '#FF6644', '#44AAFF', '#FFAA00', '#CC44FF'];

interface NimResultProps {
  result: PlaygroundResult;
  elapsedMs: number;
}

export function NimResult({ result, elapsedMs }: NimResultProps) {
  const [showRaw, setShowRaw] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Set<number>>(new Set([0]));

  const toggleItem = useCallback((index: number) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }, []);

  const handleDownload = useCallback((item: PlaygroundResultItem) => {
    const blob = new Blob([item.value], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = item.downloadFilename || 'result.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  const handleCopy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
  }, []);

  if (result.error) {
    return (
      <div className="playground-result-card">
        <div className="playground-result-header">
          <div className="playground-result-header-left">
            <h3>Error</h3>
          </div>
        </div>
        <div className="playground-card-body">
          <div className="playground-error">{result.error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="playground-result-card">
      <div className="playground-result-header">
        <div className="playground-result-header-left">
          <span className="playground-result-success-dot" />
          <h3>Results</h3>
        </div>
        <div className="playground-result-header-actions">
          <span className="playground-time-badge">
            {(elapsedMs / 1000).toFixed(2)}s
          </span>
          <button
            className={`playground-toggle-btn ${showRaw ? 'active' : ''}`}
            onClick={() => setShowRaw(!showRaw)}
          >
            {showRaw ? 'Formatted' : 'Raw JSON'}
          </button>
        </div>
      </div>

      {showRaw ? (
        <div className="playground-result-raw">
          <pre className="playground-code-block">{JSON.stringify(result.raw, null, 2)}</pre>
          <button
            className="playground-copy-btn"
            onClick={() => handleCopy(JSON.stringify(result.raw, null, 2))}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="4" y="4" width="8" height="8" rx="1" stroke="currentColor" strokeWidth="1.5" />
              <path d="M10 4V3a1 1 0 00-1-1H3a1 1 0 00-1 1v6a1 1 0 001 1h1" stroke="currentColor" strokeWidth="1.5" />
            </svg>
            Copy
          </button>
        </div>
      ) : (
        <div className="playground-result-items">
          {/* Docking: combined 3D view showing protein + all ligand poses */}
          {result.type === 'docking' && result.proteinStructure && result.items.some(i => i.format === 'docking') && (
            <div className="playground-result-item">
              <div className="playground-result-item-content">
                <StructureViewer
                  structure={result.proteinStructure}
                  format="pdb"
                  style="stick"
                  height={500}
                  colorScheme="spectrum"
                  showControls={true}
                  ligands={result.items
                    .filter(i => i.format === 'docking')
                    .map((item, idx) => ({
                      sdf: item.value,
                      label: item.label,
                      color: LIGAND_COLORS[idx % LIGAND_COLORS.length],
                    }))}
                />
              </div>
            </div>
          )}
          {result.items.map((item, index) => (
            <div key={index} className="playground-result-item">
              <div
                className="playground-result-item-header"
                role="button"
                tabIndex={0}
                onClick={() => toggleItem(index)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleItem(index); } }}
              >
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 12 12"
                  fill="none"
                  className={`playground-chevron ${expandedItems.has(index) ? 'expanded' : ''}`}
                >
                  <path d="M4 3l4 3-4 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="playground-result-item-label">{item.label}</span>
                <div className="playground-result-item-actions">
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCopy(item.value);
                    }}
                    title="Copy to clipboard"
                  >
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                      <rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1" stroke="currentColor" strokeWidth="1.25" />
                      <path d="M8.5 3.5V2.5a1 1 0 00-1-1H3a1 1 0 00-1 1v4.5a1 1 0 001 1h1" stroke="currentColor" strokeWidth="1.25" />
                    </svg>
                  </button>
                  {item.downloadFilename && (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDownload(item);
                      }}
                      title={`Download as ${item.downloadFilename}`}
                    >
                      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                        <path d="M6 1v7M3 5.5l3 3 3-3M2 10h8" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                  )}
                </div>
              </div>
              {expandedItems.has(index) && (
                <div className="playground-result-item-content">
                  <ResultContent item={item} proteinStructure={result.proteinStructure} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ResultContent({ item, proteinStructure }: { item: PlaygroundResultItem; proteinStructure?: string }) {
  switch (item.format) {
    case 'text':
      return (
        <div className="playground-result-text">
          <Markdown components={{ table: ({ children }) => <div className="playground-table-wrap"><table>{children}</table></div> }}>
            {item.value}
          </Markdown>
        </div>
      );

    case 'code':
    case 'json':
      return (
        <pre className="playground-code-block">
          {item.value.length > 10000 ? item.value.slice(0, 10000) + '\n\n... (truncated)' : item.value}
        </pre>
      );

    case 'structure': {
      // Detect format from content
      const isCif = item.value.trimStart().startsWith('data_') || item.value.includes('_atom_site.');
      const structFormat = isCif ? 'cif' : 'pdb';
      return (
        <StructureViewer
          structure={item.value}
          format={structFormat as 'pdb' | 'cif'}
          height={450}
          colorScheme="confidence"
          showControls={true}
        />
      );
    }

    case 'docking': {
      // Individual docking pose — show protein + single ligand if protein available
      if (proteinStructure) {
        return (
          <StructureViewer
            structure={proteinStructure}
            format="pdb"
            style="stick"
            height={400}
            colorScheme="spectrum"
            showControls={true}
            ligands={[{ sdf: item.value, label: item.label }]}
          />
        );
      }
      // Fallback: show raw SDF
      return (
        <pre className="playground-code-block">
          {item.value.length > 5000 ? item.value.slice(0, 5000) + '\n\n... (truncated)' : item.value}
        </pre>
      );
    }

    case 'smiles':
      return <MoleculeResultGrid value={item.value} />;

    case 'sequence':
      return (
        <pre className="playground-code-block playground-sequence-block">
          {item.value}
        </pre>
      );

    default:
      return <pre className="playground-code-block">{item.value}</pre>;
  }
}

// ============================================================================
// Molecule Result Grid — renders SMILES lines as 2D structure cards
// ============================================================================

interface ParsedMolecule {
  index: number;
  smiles: string;
  score?: number;
  extra?: string;
}

function parseMoleculeLines(text: string): ParsedMolecule[] {
  return text
    .split('\n')
    .filter((line) => line.trim())
    .map((line) => {
      // Expected format: "1. CC(C)C (score: 0.674) [sim: 0.350]"
      const numMatch = line.match(/^(\d+)\.\s*/);
      const rest = numMatch ? line.slice(numMatch[0].length) : line;

      // Extract score from (score: X.XXX)
      const scoreMatch = rest.match(/\(score:\s*([\d.]+)\)/);
      const score = scoreMatch ? parseFloat(scoreMatch[1]) : undefined;

      // Extract similarity from [sim: X.XXX]
      const simMatch = rest.match(/\[sim:\s*([\d.]+)\]/);
      const extra = simMatch ? `sim: ${simMatch[1]}` : undefined;

      // SMILES is everything before the first parenthesis/bracket annotation
      const smiles = rest.replace(/\s*\(score:.*?\)/, '').replace(/\s*\[sim:.*?\]/, '').trim();

      return {
        index: numMatch ? parseInt(numMatch[1]) : 0,
        smiles,
        score,
        extra,
      };
    })
    .filter((m) => m.smiles.length > 0);
}

function MoleculeResultGrid({ value }: { value: string }) {
  const molecules = useMemo(() => parseMoleculeLines(value), [value]);

  if (molecules.length === 0) {
    return <pre className="playground-code-block">{value}</pre>;
  }

  return (
    <div className="playground-molecule-grid">
      {molecules.map((mol) => (
        <div key={`${mol.index}-${mol.smiles}`} className="playground-molecule-card">
          <div className="playground-molecule-viewer">
            <MoleculeViewer2D
              smiles={mol.smiles}
              width={200}
              height={150}
              theme="dark"
            />
          </div>
          <div className="playground-molecule-info">
            <code className="playground-molecule-smiles" title={mol.smiles}>
              {mol.smiles.length > 30 ? mol.smiles.slice(0, 28) + '...' : mol.smiles}
            </code>
            <div className="playground-molecule-scores">
              {mol.score !== undefined && (
                <span className="playground-molecule-score">
                  QED: {mol.score.toFixed(3)}
                </span>
              )}
              {mol.extra && (
                <span className="playground-molecule-extra">{mol.extra}</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
