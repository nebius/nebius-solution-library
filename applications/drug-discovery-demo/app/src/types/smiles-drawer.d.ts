declare module 'smiles-drawer' {
  interface SmiDrawerOptions {
    width?: number;
    height?: number;
    bondThickness?: number;
    bondLength?: number;
    shortBondLength?: number;
    bondSpacing?: number;
    atomVisualization?: 'default' | 'balls' | 'none';
    isomeric?: boolean;
    debug?: boolean;
    terminalCarbons?: boolean;
    explicitHydrogens?: boolean;
    overlapSensitivity?: number;
    overlapResolutionIterations?: number;
    compactDrawing?: boolean;
    fontSizeLarge?: number;
    fontSizeSmall?: number;
    padding?: number;
    themes?: {
      [key: string]: {
        [element: string]: string;
      };
    };
  }

  class SmiDrawer {
    constructor(options?: SmiDrawerOptions);
    draw(
      tree: unknown,
      canvas: HTMLCanvasElement,
      theme?: string,
      infoOnly?: boolean
    ): void;
  }

  function parse(
    smiles: string,
    successCallback: (tree: unknown) => void,
    errorCallback: (error: Error) => void
  ): void;

  export { SmiDrawer, parse };
  export default { SmiDrawer, parse };
}
