// Type declarations for 3Dmol.js
declare module '3dmol/build/3Dmol.js' {
  export interface ViewerSpec {
    backgroundColor?: string;
    id?: string;
    antialias?: boolean;
    cartoonQuality?: number;
  }

  export interface AtomStyleSpec {
    cartoon?: CartoonStyleSpec;
    stick?: StickStyleSpec;
    sphere?: SphereStyleSpec;
    line?: LineStyleSpec;
  }

  export interface CartoonStyleSpec {
    color?: string | ((atom: AtomSpec) => string);
    colorscheme?: string | ColorScheme;
    style?: 'trace' | 'oval' | 'rectangle' | 'parabola' | 'edged';
    arrows?: boolean;
    tubes?: boolean;
    thickness?: number;
    opacity?: number;
  }

  export interface StickStyleSpec {
    radius?: number;
    color?: string;
    colorscheme?: string | ColorScheme;
    opacity?: number;
  }

  export interface SphereStyleSpec {
    radius?: number;
    scale?: number;
    color?: string;
    colorscheme?: string | ColorScheme;
    opacity?: number;
  }

  export interface LineStyleSpec {
    color?: string;
    colorscheme?: string | ColorScheme;
    lineWidth?: number;
  }

  export interface ColorScheme {
    prop?: string;
    map?: Record<string, string>;
    gradient?: string;
    min?: number;
    max?: number;
  }

  export interface AtomSpec {
    x: number;
    y: number;
    z: number;
    elem: string;
    atom: string;
    serial: number;
    resi: number;
    resn: string;
    chain: string;
    b: number;
    ss: string;
    color?: number;
  }

  export interface Model {
    setStyle(sel: AtomSelectionSpec, style: AtomStyleSpec): void;
    addStyle(sel: AtomSelectionSpec, style: AtomStyleSpec): void;
    computeSecondaryStructure(): void;
  }

  export interface AtomSelectionSpec {
    chain?: string | string[];
    resi?: number | number[] | string;
    resn?: string | string[];
    elem?: string | string[];
    atom?: string | string[];
    ss?: string;
    b?: number | [number, number];
  }

  export interface GLViewer {
    addModel(data: string, format: string): Model;
    getModel(id?: number): Model | null;
    setStyle(sel: AtomSelectionSpec, style: AtomStyleSpec): void;
    setBackgroundColor(color: string | number): void;
    zoomTo(sel?: AtomSelectionSpec): void;
    render(): void;
    clear(): void;
    zoom(factor: number): void;
    rotate(angle: number, axis: string): void;
    spin(axis: string | boolean): void;
    removeAllModels(): void;
    resize(): void;
  }

  export function createViewer(
    element: HTMLElement,
    config?: ViewerSpec
  ): GLViewer;
}
