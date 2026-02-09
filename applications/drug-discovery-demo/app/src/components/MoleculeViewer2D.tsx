import { useEffect, useRef, useState } from 'react';
import * as SmilesDrawer from 'smiles-drawer';

interface MoleculeViewer2DProps {
  smiles: string;
  width?: number;
  height?: number;
  theme?: 'light' | 'dark';
  showError?: boolean;
}

// Singleton drawer instance for performance
let drawerInstance: SmilesDrawer.SmiDrawer | null = null;

function getDrawer(): SmilesDrawer.SmiDrawer {
  if (!drawerInstance) {
    drawerInstance = new SmilesDrawer.SmiDrawer({
      width: 300,
      height: 200,
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

export function MoleculeViewer2D({
  smiles,
  width = 200,
  height = 150,
  theme = 'light',
  showError = true,
}: MoleculeViewer2DProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!canvasRef.current || !smiles) return;

    const canvas = canvasRef.current;
    const drawer = getDrawer();

    // Clear previous drawing
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    setError(null);

    try {
      // Parse and draw the molecule
      SmilesDrawer.parse(smiles, (tree: unknown) => {
        drawer.draw(tree, canvas, theme, false);
      }, (err: Error) => {
        console.warn('SMILES parse error:', err);
        setError('Invalid structure');
      });
    } catch (err) {
      console.warn('SMILES draw error:', err);
      setError('Draw error');
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
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        className="molecule-canvas"
      />
      {error && showError && (
        <div className="molecule-viewer-error">
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
