export type WorkflowStepId =
  | 'use-case'
  | 'ai-planning'
  | 'sequence'
  | 'structure'
  | 'molecules'
  | 'docking'
  | 'rediscovery'
  | 'summary';

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

  // Step 2: AI Planning output
  researchPlan: string | null;
  identifiedUniprotId: string | null; // UniProt ID extracted from Qwen's response
  identifiedProteinName: string | null;

  // Step 3: Sequence retrieval
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
