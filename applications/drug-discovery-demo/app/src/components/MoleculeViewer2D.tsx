import { useEffect, useRef, useState } from 'react';
import * as SmilesDrawer from 'smiles-drawer';

interface MoleculeViewer2DProps {
  smiles: string;
  width?: number;
  height?: number;
  theme?: 'light' | 'dark';
  showError?: boolean;
}

// Singleton SmiDrawer instance for performance
let drawerInstance: SmilesDrawer.SmiDrawer | null = null;

function getDrawer(): SmilesDrawer.SmiDrawer {
  if (!drawerInstance) {
    drawerInstance = new SmilesDrawer.SmiDrawer({
      bondThickness: 1.5,
      bondLength: 25,
      shortBondLength: 0.8,
      bondSpacing: 4,
      atomVisualization: 'default',
      isomeric: true,
      debug: false,
      terminalCarbons: false,
      explicitHydrogens: false,
      overlapSensitivity: 0.42,
      overlapResolutionIterations: 1,
      compactDrawing: true,
      fontSizeLarge: 11,
      fontSizeSmall: 6,
      padding: 20,
      themes: {
        light: {
          C: '#222',
          O: '#e74c3c',
          N: '#3498db',
          F: '#27ae60',
          Cl: '#27ae60',
          Br: '#e67e22',
          I: '#9b59b6',
          P: '#e67e22',
          S: '#f1c40f',
          B: '#e67e22',
          Si: '#e67e22',
          H: '#222',
          BACKGROUND: '#fff',
        },
        dark: {
          C: '#fff',
          O: '#e74c3c',
          N: '#3498db',
          F: '#27ae60',
          Cl: '#27ae60',
          Br: '#e67e22',
          I: '#9b59b6',
          P: '#e67e22',
          S: '#f1c40f',
          B: '#e67e22',
          Si: '#e67e22',
          H: '#fff',
          BACKGROUND: '#1a1a2e',
        },
      },
    });
  }
  return drawerInstance;
}

/**
 * Quick structural validation before passing to the PEG parser.
 * Rejects obviously-broken SMILES (unbalanced parens/brackets, unclosed rings).
 */
function isPlausibleSmiles(smi: string): boolean {
  if (!smi || smi.length < 2) return false;

  // Balanced parentheses and brackets
  let parenDepth = 0;
  let bracketDepth = 0;
  for (const ch of smi) {
    if (ch === '(') parenDepth++;
    else if (ch === ')') parenDepth--;
    else if (ch === '[') bracketDepth++;
    else if (ch === ']') bracketDepth--;
    if (parenDepth < 0 || bracketDepth < 0) return false;
  }
  if (parenDepth !== 0 || bracketDepth !== 0) return false;

  // Ring-closure digits must come in pairs
  // Count single digits outside brackets, and %nn pairs
  let inBracket = false;
  const ringCounts = new Map<string, number>();
  for (let i = 0; i < smi.length; i++) {
    const ch = smi[i];
    if (ch === '[') { inBracket = true; continue; }
    if (ch === ']') { inBracket = false; continue; }
    if (inBracket) continue;
    if (ch === '%' && i + 2 < smi.length) {
      const pair = smi[i + 1] + smi[i + 2];
      if (/^\d{2}$/.test(pair)) {
        ringCounts.set(pair, (ringCounts.get(pair) || 0) + 1);
        i += 2;
        continue;
      }
    }
    if (/\d/.test(ch)) {
      ringCounts.set(ch, (ringCounts.get(ch) || 0) + 1);
    }
  }
  for (const count of ringCounts.values()) {
    if (count % 2 !== 0) return false;
  }

  // Must contain at least one organic atom
  if (!/[BCNOPSFIHcnops]/.test(smi)) return false;

  return true;
}

export function MoleculeViewer2D({
  smiles,
  width = 200,
  height = 150,
  theme = 'dark',
  showError = true,
}: MoleculeViewer2DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current || !smiles) return;

    const container = containerRef.current;

    // Clear previous drawing
    container.innerHTML = '';
    setError(null);

    // Fast-reject invalid SMILES before touching the DOM
    if (!isPlausibleSmiles(smiles)) {
      setError('Invalid SMILES');
      return;
    }

    // Create a fresh SVG element outside React's control
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    svg.setAttributeNS(null, 'width', String(width));
    svg.setAttributeNS(null, 'height', String(height));
    container.appendChild(svg);

    const drawer = getDrawer();
    try {
      drawer.draw(
        smiles,
        svg,
        theme,
        () => { /* success */ },
        () => {
          // Parse/draw error — remove the broken SVG
          container.innerHTML = '';
          setError('Invalid SMILES');
        },
      );
    } catch {
      container.innerHTML = '';
      setError('Invalid SMILES');
    }
  }, [smiles, width, height, theme]);

  if (!smiles) {
    return (
      <div className="molecule-viewer-2d molecule-viewer-empty" style={{ width, height }}>
        <span>No molecule</span>
      </div>
    );
  }

  return (
    <div className="molecule-viewer-2d" style={{ width, height }}>
      <div
        ref={containerRef}
        className="molecule-canvas"
        style={{ width, height }}
      />
      {error && showError && (
        <div className="molecule-viewer-error">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="12" cy="12" r="6" />
            <line x1="8" y1="8" x2="16" y2="16" />
          </svg>
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

// Grid component for displaying multiple molecules
interface MoleculeGridProps {
  molecules: Array<{
    smiles: string;
    label?: string;
    score?: number;
    selected?: boolean;
    onClick?: () => void;
  }>;
  moleculeSize?: { width: number; height: number };
  columns?: number;
}

export function MoleculeGrid({
  molecules,
  moleculeSize = { width: 180, height: 140 },
  columns = 4,
}: MoleculeGridProps) {
  return (
    <div
      className="molecule-grid"
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gap: 'var(--spacing-md)',
      }}
    >
      {molecules.map((mol, index) => (
        <div
          key={`${mol.smiles}-${index}`}
          className={`molecule-grid-item ${mol.selected ? 'selected' : ''}`}
          onClick={mol.onClick}
          style={{ cursor: mol.onClick ? 'pointer' : 'default' }}
        >
          <MoleculeViewer2D
            smiles={mol.smiles}
            width={moleculeSize.width}
            height={moleculeSize.height}
          />
          {(mol.label || mol.score !== undefined) && (
            <div className="molecule-grid-item-info">
              {mol.label && <span className="molecule-label">{mol.label}</span>}
              {mol.score !== undefined && (
                <span className="molecule-score">{mol.score.toFixed(2)}</span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
