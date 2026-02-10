// Workflow types determine which steps are shown
export type WorkflowType =
  | 'small-molecule'      // Traditional drug discovery: sequence → structure → molecules → docking
  | 'protein-binder'      // Design protein that binds target: target structure → RFDiffusion → ProteinMPNN
  | 'de-novo-protein'     // Create new protein from scratch: RFDiffusion → ProteinMPNN → validate
  | 'enzyme-engineering'; // Analyze/modify enzyme: sequence → structure → analysis

export type WorkflowStepId =
  // Common steps
  | 'use-case'
  | 'summary'
  // Small molecule workflow
  | 'sequence'
  | 'structure'
  | 'molecules'
  | 'docking'
  | 'rediscovery'
  // Protein design workflow
  | 'target-structure'    // Get target protein structure (for binder design)
  | 'protein-design'      // RFDiffusion - design protein backbone
  | 'sequence-design'     // ProteinMPNN - design amino acid sequence
  | 'validation';         // Validate designed protein with structure prediction

export type StepStatus = 'pending' | 'active' | 'completed' | 'error';

export interface WorkflowStep {
  id: WorkflowStepId;
  title: string;
  subtitle: string;
  status: StepStatus;
}

export interface AppSettings {
  loadBalancerUrl: string;
  selectedDrugId: string | null;
}

export interface HealthCheckResult {
  endpointId: string;
  status: 'ready' | 'not-ready' | 'error';
  latency?: number;
  error?: string;
}

// Workflow data that flows between steps
export interface WorkflowData {
  // Step 1: Use case selection
  selectedDrugId: string | null;
  customPrompt: string | null; // For custom drug discovery

  // UniProt ID (auto-populated from selected drug)
  identifiedUniprotId: string | null;

  // Step 2: Sequence retrieval
  proteinSequence: string | null; // FASTA sequence from UniProt
  sequenceLength: number | null;

  // Step 4: Structure prediction output
  proteinStructure: string | null; // PDB format
  structureModel: string | null; // Which model was used

  // Step 5: Molecule generation output
  generatedMolecules: GeneratedMolecule[];

  // Step 6: Docking output
  dockingResults: DockingResult[];

  // Step 7: Rediscovery results
  rediscoveryResults: RediscoveryResult[];

  // Step 8: Summary
  summary: string | null;
}

export interface GeneratedMolecule {
  id: string;
  smiles: string;
  score?: number;
}

export interface DockingResult {
  moleculeId: string;
  smiles: string;
  bindingScore: number;
  pose?: string; // PDB format of docked pose
}

export interface RediscoveryResult {
  moleculeId: string;
  smiles: string;
  similarityScore: number; // Tanimoto similarity to reference drug
  similarityLevel: 'exact' | 'high' | 'medium' | 'low'; // Based on Tanimoto score
  rank: number;
}
