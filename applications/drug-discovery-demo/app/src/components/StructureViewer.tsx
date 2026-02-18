import { useEffect, useRef, useState } from 'react';

interface LigandPose {
  sdf: string; // SDF format ligand structure
  label?: string;
  color?: string; // Ligand color (default: green)
}

interface StructureViewerProps {
  structure: string;
  format: 'pdb' | 'cif' | 'mmcif';
  style?: 'cartoon' | 'stick' | 'sphere' | 'line';
  colorScheme?: 'spectrum' | 'chain' | 'secondary' | 'confidence';
  backgroundColor?: string;
  height?: number;
  showControls?: boolean;
  ligands?: LigandPose[]; // Optional ligand poses to display
  showLigands?: boolean; // Whether to show ligands (default: true if ligands provided)
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let $3Dmol: any = null;
let loadingPromise: Promise<void> | null = null;

async function load3Dmol() {
  if ($3Dmol) return;
  if (loadingPromise) return loadingPromise;

  loadingPromise = (async () => {
    const module = await import('3dmol/build/3Dmol.js');
    $3Dmol = module.default || module;
    // 3Dmol attaches to window
    if (!$3Dmol && typeof window !== 'undefined') {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      $3Dmol = (window as any).$3Dmol;
    }
  })();

  return loadingPromise;
}

export function StructureViewer({
  structure,
  format,
  style = 'cartoon',
  colorScheme = 'spectrum',
  backgroundColor = '#0a0a0f',
  height = 400,
  showControls = true,
  ligands = [],
  showLigands = true,
}: StructureViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const viewerRef = useRef<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [currentStyle, setCurrentStyle] = useState(style);
  const [currentColorScheme, setCurrentColorScheme] = useState(colorScheme);
  const [isSpinning, setIsSpinning] = useState(false);
  const [ligandsVisible, setLigandsVisible] = useState(showLigands);
  const [selectedLigandIndex, setSelectedLigandIndex] = useState(0);

  // Color schemes that work with 'color' property (simple spectrum-based)
  const simpleColorSchemes = ['spectrum'];

  // Get color specification for a scheme
  const getColorSpec = (scheme: string): string | object => {
    switch (scheme) {
      case 'spectrum':
        return 'spectrum';
      case 'chain':
        return 'chainHetatm';
      case 'secondary':
        return 'ssPyMOL'; // Note: correct capitalization for 3Dmol.js
      case 'confidence':
        // Color by B-factor (pLDDT is stored here)
        return { prop: 'b', gradient: 'roygb', min: 0, max: 100 };
      default:
        return 'spectrum';
    }
  };

  // Apply style to viewer - handles all combinations robustly
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const applyStyle = (viewer: any, styleType: string, colorSchemeType: string) => {
    try {
      viewer.setStyle({}, {}); // Clear styles

      const colorSpec = getColorSpec(colorSchemeType);
      const isSimpleScheme = simpleColorSchemes.includes(colorSchemeType);

      // Build style object based on style type
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let styleObj: any = {};

      switch (styleType) {
        case 'cartoon':
          // 'spectrum' uses color property, everything else uses colorscheme
          if (isSimpleScheme && typeof colorSpec === 'string') {
            styleObj = { cartoon: { color: colorSpec } };
          } else {
            // For chain, secondary, and gradient-based coloring, use colorscheme
            styleObj = { cartoon: { colorscheme: colorSpec } };
          }
          break;
        case 'stick':
          if (isSimpleScheme && typeof colorSpec === 'string') {
            styleObj = { stick: { color: colorSpec, radius: 0.15 } };
          } else {
            styleObj = { stick: { colorscheme: colorSpec, radius: 0.15 } };
          }
          break;
        case 'sphere':
          if (isSimpleScheme && typeof colorSpec === 'string') {
            styleObj = { sphere: { color: colorSpec, scale: 0.25 } };
          } else {
            styleObj = { sphere: { colorscheme: colorSpec, scale: 0.25 } };
          }
          break;
        case 'line':
          if (isSimpleScheme && typeof colorSpec === 'string') {
            styleObj = { line: { color: colorSpec } };
          } else {
            styleObj = { line: { colorscheme: colorSpec } };
          }
          break;
        default:
          styleObj = { cartoon: { color: 'spectrum' } };
      }

      viewer.setStyle({}, styleObj);
    } catch (err) {
      console.error('Failed to apply style:', err);
      // Fallback to simple stick representation
      try {
        viewer.setStyle({}, { stick: { color: 'spectrum' } });
      } catch {
        // Last resort - ignore
      }
    }
  };

  // Load 3Dmol and initialize viewer
  useEffect(() => {
    if (!containerRef.current || !structure) return;

    let mounted = true;

    const initViewer = async () => {
      setIsLoading(true);
      await load3Dmol();

      if (!mounted || !containerRef.current || !$3Dmol) {
        setIsLoading(false);
        return;
      }

      // Clear previous viewer
      if (viewerRef.current) {
        try {
          viewerRef.current.clear();
        } catch {
          // Ignore cleanup errors
        }
      }

      // Create new viewer
      try {
        const viewer = $3Dmol.createViewer(containerRef.current, {
          backgroundColor,
          antialias: true,
        });
        viewerRef.current = viewer;

        // Determine format for 3Dmol
        const mol3dFormat = format === 'mmcif' || format === 'cif' ? 'cif' : 'pdb';

        // Add model
        viewer.addModel(structure, mol3dFormat);

        // Compute secondary structure for cartoon representation
        // Some versions of 3Dmol.js may not have this method
        const model = viewer.getModel();
        if (model && typeof model.computeSecondaryStructure === 'function') {
          try {
            model.computeSecondaryStructure();
          } catch {
            // Ignore - secondary structure will use defaults
          }
        }

        // Apply initial style to protein
        applyStyle(viewer, currentStyle, currentColorScheme);

        // Add ligands if provided
        if (ligands.length > 0 && ligandsVisible) {
          const ligandColors = ['#00ff00', '#ff6600', '#00ccff', '#ff00ff', '#ffff00'];
          ligands.forEach((ligand, index) => {
            try {
              viewer.addModel(ligand.sdf, 'sdf');
              const ligandModel = viewer.getModel(index + 1); // Protein is model 0
              if (ligandModel) {
                const color = ligand.color || ligandColors[index % ligandColors.length];
                ligandModel.setStyle({}, {
                  stick: { radius: 0.2, color: color },
                  sphere: { radius: 0.4, color: color },
                });
              }
            } catch (ligandErr) {
              console.warn(`Failed to add ligand ${index}:`, ligandErr);
            }
          });
        }

        // Zoom to fit and render — fall back to stick if cartoon crashes
        viewer.zoomTo();
        try {
          viewer.render();
        } catch (renderErr) {
          console.warn('Initial render failed (likely cartoon), falling back to stick:', renderErr);
          try {
            viewer.setStyle({}, { stick: { color: 'spectrum', radius: 0.15 } });
            viewer.render();
            setCurrentStyle('stick');
          } catch {
            // Last resort - ignore
          }
        }
      } catch (err) {
        console.error('Failed to create 3Dmol viewer:', err);
      }

      setIsLoading(false);
    };

    initViewer();

    // Cleanup
    return () => {
      mounted = false;
      if (viewerRef.current) {
        try {
          viewerRef.current.clear();
        } catch {
          // Ignore cleanup errors
        }
        viewerRef.current = null;
      }
    };
  }, [structure, format, backgroundColor, ligands, ligandsVisible]);

  // Update style when changed
  useEffect(() => {
    if (!viewerRef.current || isLoading) return;
    try {
      applyStyle(viewerRef.current, currentStyle, currentColorScheme);
      viewerRef.current.render();
    } catch (err) {
      console.warn('Style render failed, falling back to stick:', err);
      try {
        viewerRef.current.setStyle({}, { stick: { color: 'spectrum', radius: 0.15 } });
        viewerRef.current.render();
        setCurrentStyle('stick');
      } catch {
        // Last resort - ignore
      }
    }
  }, [currentStyle, currentColorScheme, isLoading]);

  // Handle spinning
  useEffect(() => {
    if (!viewerRef.current || isLoading) return;
    if (isSpinning) {
      viewerRef.current.spin('y', 1);
    } else {
      viewerRef.current.spin(false);
    }
  }, [isSpinning, isLoading]);

  const handleZoomIn = () => {
    if (viewerRef.current) {
      viewerRef.current.zoom(1.2);
      viewerRef.current.render();
    }
  };

  const handleZoomOut = () => {
    if (viewerRef.current) {
      viewerRef.current.zoom(0.8);
      viewerRef.current.render();
    }
  };

  const handleReset = () => {
    if (viewerRef.current) {
      viewerRef.current.zoomTo();
      viewerRef.current.render();
    }
  };

  const handleToggleSpin = () => {
    setIsSpinning(!isSpinning);
  };

  return (
    <div className="structure-viewer-container">
      {isLoading && (
        <div
          className="structure-viewer-loading"
          style={{
            height: `${height}px`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: backgroundColor,
          }}
        >
          <span className="spinner" />
        </div>
      )}
      <div
        ref={containerRef}
        className="structure-viewer"
        style={{ height: `${height}px`, display: isLoading ? 'none' : 'block' }}
      />

      {showControls && !isLoading && (
        <div className="structure-viewer-controls">
          <div className="viewer-control-group">
            <label className="viewer-control-label">Style</label>
            <select
              className="viewer-control-select"
              value={currentStyle}
              onChange={(e) => setCurrentStyle(e.target.value as typeof currentStyle)}
            >
              <option value="cartoon">Cartoon</option>
              <option value="stick">Stick</option>
              <option value="sphere">Sphere</option>
              <option value="line">Line</option>
            </select>
          </div>

          <div className="viewer-control-group">
            <label className="viewer-control-label">Color</label>
            <select
              className="viewer-control-select"
              value={currentColorScheme}
              onChange={(e) => setCurrentColorScheme(e.target.value as typeof currentColorScheme)}
            >
              <option value="spectrum">Rainbow (N→C)</option>
              <option value="confidence">Confidence (pLDDT)</option>
              <option value="chain">By Chain</option>
              <option value="secondary">Secondary Structure</option>
            </select>
          </div>

          <div className="viewer-control-group viewer-control-buttons">
            <button className="viewer-btn" onClick={handleZoomIn} title="Zoom In">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.5" />
                <path d="M11 11l3 3M5 7h4M7 5v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
            <button className="viewer-btn" onClick={handleZoomOut} title="Zoom Out">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.5" />
                <path d="M11 11l3 3M5 7h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
            <button className="viewer-btn" onClick={handleReset} title="Reset View">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 8a6 6 0 1 1 1.5 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                <path d="M2 12V8h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <button
              className={`viewer-btn ${isSpinning ? 'active' : ''}`}
              onClick={handleToggleSpin}
              title={isSpinning ? 'Stop Spin' : 'Start Spin'}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M8 2v2M8 12v2M2 8h2M12 8h2M3.5 3.5l1.5 1.5M11 11l1.5 1.5M3.5 12.5l1.5-1.5M11 5l1.5-1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
            {ligands.length > 0 && (
              <button
                className={`viewer-btn ${ligandsVisible ? 'active' : ''}`}
                onClick={() => setLigandsVisible(!ligandsVisible)}
                title={ligandsVisible ? 'Hide Ligands' : 'Show Ligands'}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.5" />
                  <circle cx="4" cy="4" r="2" stroke="currentColor" strokeWidth="1.5" />
                  <circle cx="12" cy="12" r="2" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M6 6l-1-1M10 10l1 1" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              </button>
            )}
          </div>

          {/* Ligand selector for multiple ligands */}
          {ligands.length > 1 && ligandsVisible && (
            <div className="viewer-control-group">
              <label className="viewer-control-label">Ligand</label>
              <select
                className="viewer-control-select"
                value={selectedLigandIndex}
                onChange={(e) => setSelectedLigandIndex(parseInt(e.target.value))}
              >
                {ligands.map((ligand, i) => (
                  <option key={i} value={i}>
                    {ligand.label || `Pose ${i + 1}`}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}

      {!isLoading && (
        <div className="structure-viewer-hint">
          Drag to rotate • Scroll to zoom • Right-drag to pan
        </div>
      )}
    </div>
  );
}
