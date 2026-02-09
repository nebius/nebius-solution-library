// Agent Tools Definition
// Defines the tools available to the AI agent for dynamic drug discovery workflows

export interface ToolParameter {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'object';
  description: string;
  required: boolean;
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: ToolParameter[];
}

// Available Models Overview (for LLM context)
export const AVAILABLE_MODELS = `
## Available AI Models

### Structure Prediction
- **OpenFold3** (port 8000): Next-gen structure prediction, good balance of speed and accuracy. Recommended for most cases.
- **Boltz2** (port 8001): Fast structure prediction, great for rapid prototyping.
- **OpenFold2** (port 8004): High accuracy with MSA + templates, best for well-characterized proteins.

### Small Molecule Generation
- **GenMol** (port 8005): De novo molecule generation, creates novel drug-like compounds.
- **MolMIM** (port 8006): SMILES-guided generation, explores chemical space around a seed molecule.

### Molecular Docking
- **DiffDock** (port 8007): Predicts how small molecules bind to proteins, returns poses and confidence scores.

### Protein Design
- **RFDiffusion** (port 8010): De novo protein structure generation. Can design:
  - Novel protein folds from scratch
  - Binders to target proteins
  - Scaffolds with specific geometries
  - Inpainting/redesign of protein regions
- **ProteinMPNN** (port 8009): Designs amino acid sequences that fold into a given structure. Use after RFDiffusion.

### Utilities
- **MSA Search** (port 8003): Finds homologous sequences for improved structure prediction.
- **Evo2-40B** (port 8002): DNA/RNA foundation model for genomic analysis.

## Workflow Patterns

### Small Molecule Drug Discovery
search_uniprot → predict_structure → generate_molecules → dock_molecules → analyze

### De Novo Protein Design
design_protein (RFDiffusion) → design_sequence (ProteinMPNN) → predict_structure (validation)

### Protein Binder Design
predict_structure (target) → design_binder (RFDiffusion) → design_sequence (ProteinMPNN) → validate

### Lead Optimization
generate_molecules (around seed) → dock_molecules → calculate_similarity → compare
`;

// Tools available to the agent
export const AGENT_TOOLS: ToolDefinition[] = [
  {
    name: 'search_uniprot',
    description: 'Search UniProt database for a protein by name or accession ID. Returns protein sequence, name, and metadata.',
    parameters: [
      {
        name: 'query',
        type: 'string',
        description: 'Protein name or UniProt accession ID (e.g., "P35354" or "COX-2")',
        required: true,
      },
    ],
  },
  {
    name: 'predict_structure',
    description: 'Predict the 3D structure of a protein from its amino acid sequence. Uses state-of-the-art AI models (OpenFold3, Boltz2, or OpenFold2).',
    parameters: [
      {
        name: 'sequence',
        type: 'string',
        description: 'Amino acid sequence of the protein',
        required: true,
      },
      {
        name: 'model',
        type: 'string',
        description: 'Structure prediction model to use: "openfold3" (recommended), "boltz2" (fast), or "openfold2" (with MSA)',
        required: false,
      },
      {
        name: 'num_copies',
        type: 'number',
        description: 'Number of copies of the protein chain for homo-oligomers (default: 1 for monomer, use 2 for homodimer). Only applies to openfold3.',
        required: false,
      },
    ],
  },
  {
    name: 'generate_molecules',
    description: 'Generate novel drug-like molecules using MolMIM generative model. Uses a seed molecule to explore chemical space.',
    parameters: [
      {
        name: 'seed_smiles',
        type: 'string',
        description: 'SMILES string of the seed molecule to start generation from',
        required: true,
      },
      {
        name: 'num_molecules',
        type: 'number',
        description: 'Number of molecules to generate (default: 30, max: 100)',
        required: false,
      },
      {
        name: 'diversity',
        type: 'number',
        description: 'Diversity scaling factor (default: 1.2, higher = more diverse)',
        required: false,
      },
    ],
  },
  {
    name: 'dock_molecules',
    description: 'Perform molecular docking to predict how molecules bind to a protein structure using DiffDock.',
    parameters: [
      {
        name: 'protein_structure',
        type: 'string',
        description: 'Protein structure in CIF or PDB format',
        required: true,
      },
      {
        name: 'ligand_smiles',
        type: 'string',
        description: 'SMILES string(s) of molecules to dock (comma-separated for multiple)',
        required: true,
      },
    ],
  },
  {
    name: 'calculate_similarity',
    description: 'Calculate Tanimoto similarity between molecules using molecular fingerprints.',
    parameters: [
      {
        name: 'smiles_list',
        type: 'string',
        description: 'Comma-separated list of SMILES strings to compare',
        required: true,
      },
      {
        name: 'reference_smiles',
        type: 'string',
        description: 'Reference SMILES to compare against',
        required: true,
      },
    ],
  },
  {
    name: 'design_protein',
    description: 'Design a novel protein structure using RFDiffusion. Can generate new folds, binders, or scaffolds.',
    parameters: [
      {
        name: 'mode',
        type: 'string',
        description: 'Design mode: "unconditional" (new fold), "binder" (design binder to target), "scaffold" (specific topology)',
        required: true,
      },
      {
        name: 'length',
        type: 'number',
        description: 'Desired protein length in residues (50-500)',
        required: true,
      },
      {
        name: 'target_structure',
        type: 'string',
        description: 'For binder mode: target protein structure in PDB format',
        required: false,
      },
      {
        name: 'hotspot_residues',
        type: 'string',
        description: 'For binder mode: comma-separated residue numbers to target on the binding interface',
        required: false,
      },
    ],
  },
  {
    name: 'design_sequence',
    description: 'Design an amino acid sequence for a given protein structure using ProteinMPNN. Use after design_protein.',
    parameters: [
      {
        name: 'structure',
        type: 'string',
        description: 'Protein backbone structure in PDB format (from RFDiffusion or other source)',
        required: true,
      },
      {
        name: 'num_sequences',
        type: 'number',
        description: 'Number of sequence designs to generate (default: 4)',
        required: false,
      },
      {
        name: 'temperature',
        type: 'number',
        description: 'Sampling temperature (default: 0.1, higher = more diverse)',
        required: false,
      },
      {
        name: 'fixed_positions',
        type: 'string',
        description: 'Comma-separated residue positions to keep fixed (optional)',
        required: false,
      },
    ],
  },
  {
    name: 'ask_user',
    description: 'Ask the user a question to clarify requirements or get their input on a decision.',
    parameters: [
      {
        name: 'question',
        type: 'string',
        description: 'The question to ask the user',
        required: true,
      },
      {
        name: 'options',
        type: 'string',
        description: 'Optional comma-separated list of options for the user to choose from',
        required: false,
      },
    ],
  },
  {
    name: 'show_results',
    description: 'Display results to the user in a formatted way (structure viewer, molecule grid, etc.)',
    parameters: [
      {
        name: 'result_type',
        type: 'string',
        description: 'Type of result to display: "structure", "molecules", "docking", "similarity"',
        required: true,
      },
      {
        name: 'data',
        type: 'object',
        description: 'The data to display (format depends on result_type)',
        required: true,
      },
    ],
  },
  {
    name: 'complete',
    description: 'Mark the task as complete and provide a final summary to the user.',
    parameters: [
      {
        name: 'summary',
        type: 'string',
        description: 'Summary of what was accomplished',
        required: true,
      },
    ],
  },
  {
    name: 'execute_raw_request',
    description: 'Execute a raw JSON request directly against a NIM API endpoint. IMPORTANT: Use this tool when the user provides a specific JSON payload and asks to "run this query", "execute this request", or "test this API call". Pass their exact JSON as the body parameter without modification.',
    parameters: [
      {
        name: 'endpoint',
        type: 'string',
        description: 'Target endpoint: "openfold3", "boltz2", "openfold2", "molmim", "diffdock", "rfdiffusion", "proteinmpnn", or a full URL',
        required: true,
      },
      {
        name: 'body',
        type: 'object',
        description: 'The raw JSON body to send to the API - use the exact JSON provided by the user',
        required: true,
      },
    ],
  },
];

// Format tools for LLM prompt
export function formatToolsForPrompt(): string {
  return AGENT_TOOLS.map((tool) => {
    const params = tool.parameters
      .map((p) => `  - ${p.name} (${p.type}${p.required ? ', required' : ''}): ${p.description}`)
      .join('\n');
    return `**${tool.name}**\n${tool.description}\nParameters:\n${params}`;
  }).join('\n\n');
}

// Parse tool call from LLM response
export interface ParsedToolCall {
  tool: string;
  arguments: Record<string, unknown>;
}

export function parseToolCall(response: string): ParsedToolCall | null {
  // Look for tool call patterns
  // Pattern 1: <tool_call>{"tool": "name", "arguments": {...}}</tool_call>
  const toolCallMatch = response.match(/<tool_call>([\s\S]*?)<\/tool_call>/);
  if (toolCallMatch) {
    try {
      const parsed = JSON.parse(toolCallMatch[1]);
      return {
        tool: parsed.tool || parsed.name,
        arguments: parsed.arguments || parsed.params || {},
      };
    } catch {
      // Try to extract just JSON from the match
    }
  }

  // Pattern 2: ```json with tool/arguments
  const jsonMatch = response.match(/```json\s*([\s\S]*?)\s*```/);
  if (jsonMatch) {
    try {
      const parsed = JSON.parse(jsonMatch[1]);
      if (parsed.tool || parsed.name) {
        return {
          tool: parsed.tool || parsed.name,
          arguments: parsed.arguments || parsed.params || {},
        };
      }
    } catch {
      // Continue to next pattern
    }
  }

  // Pattern 3: TOOL: name\nARGUMENTS: {...}
  const toolNameMatch = response.match(/TOOL:\s*(\w+)/i);
  const argsMatch = response.match(/ARGUMENTS:\s*(\{[\s\S]*?\})/i);
  if (toolNameMatch) {
    let args = {};
    if (argsMatch) {
      try {
        args = JSON.parse(argsMatch[1]);
      } catch {
        // Empty args
      }
    }
    return {
      tool: toolNameMatch[1],
      arguments: args,
    };
  }

  return null;
}
