/**
 * NIM Playground Configuration
 *
 * Defines form schemas, request builders, and result types for all NIM endpoints.
 * Each NIM has a complete configuration that drives the dynamic playground form.
 */

// ============================================================================
// Types
// ============================================================================

export type FieldType = 'text' | 'textarea' | 'number' | 'select' | 'checkbox' | 'multiselect';

export type FieldGroup = 'input' | 'parameters' | 'advanced';

export type ResultType = 'structure' | 'molecules' | 'sequences' | 'alignment' | 'text' | 'json' | 'docking';

export interface PlaygroundField {
  id: string;
  label: string;
  type: FieldType;
  group: FieldGroup;
  description?: string;
  required?: boolean;
  default?: string | number | boolean | string[];
  placeholder?: string;
  // Number fields
  min?: number;
  max?: number;
  step?: number;
  // Textarea fields
  rows?: number;
  // Select / multiselect fields
  options?: { value: string; label: string }[];
}

export interface PlaygroundResult {
  type: ResultType;
  raw: unknown;
  items: PlaygroundResultItem[];
  error?: string;
  /** Protein structure (PDB) for docking results — used to render protein+ligand 3D views */
  proteinStructure?: string;
}

export interface PlaygroundResultItem {
  label: string;
  value: string;
  format: 'text' | 'code' | 'structure' | 'smiles' | 'sequence' | 'json' | 'docking';
  downloadFilename?: string;
}

export interface NimPlaygroundDef {
  id: string;
  name: string;
  category: string;
  categoryIcon: string;
  description: string;
  fields: PlaygroundField[];
  resultType: ResultType;
  buildRequest: (values: Record<string, unknown>) => unknown;
  parseResponse: (data: unknown) => PlaygroundResult;
  /** Merge multiple parallel results into one (required when supportsParallel is true) */
  mergeResults?: (results: PlaygroundResult[]) => PlaygroundResult;
  /** Override endpoint path (if different from ENDPOINT_CONFIG) */
  endpointPath?: string;
  /** Override port (if different from ENDPOINT_CONFIG) */
  port?: number;
  /** Pre-computed example result shown before the user clicks Run */
  exampleResult?: PlaygroundResult;
  /** Allow sending multiple requests in parallel behind a load balancer */
  supportsParallel?: boolean;
}

import { OPENFOLD3_EXAMPLE, BOLTZ2_EXAMPLE, OPENFOLD2_EXAMPLE, MOLMIM_EXAMPLE, GENMOL_EXAMPLE, DIFFDOCK_EXAMPLE, MSA_SEARCH_EXAMPLE, EVO2_EXAMPLE, PROTEINMPNN_EXAMPLE, RFDIFFUSION_EXAMPLE, OPENFOLD3_STRUCTURE } from './exampleResponses';

// ============================================================================
// Helper Functions
// ============================================================================

function parseChainSequences(text: string): { id: string; sequence: string }[] {
  const lines = (text || '').split('\n').filter((s) => s.trim());
  return lines.map((line, i) => {
    if (line.includes(':')) {
      const [id, ...rest] = line.split(':');
      return { id: id.trim(), sequence: rest.join(':').trim() };
    }
    return { id: String.fromCharCode(65 + i), sequence: line.trim() };
  });
}

// ============================================================================
// NIM Configurations
// ============================================================================

// --------------------------------------------------------------------------
// 1. Qwen3 (LLM Chat)
// --------------------------------------------------------------------------

const QWEN3: NimPlaygroundDef = {
  id: 'qwen3',
  name: 'Qwen3-80B',
  category: 'LLM',
  categoryIcon: 'chat',
  description: 'Large language model for scientific reasoning, drug discovery planning, and analysis.',
  resultType: 'text',
  fields: [
    {
      id: 'systemPrompt',
      label: 'System Prompt',
      type: 'textarea',
      group: 'input',
      rows: 3,
      placeholder: 'You are a helpful assistant specializing in drug discovery...',
      description: 'Optional system prompt to set the assistant behavior',
    },
    {
      id: 'userMessage',
      label: 'User Message',
      type: 'textarea',
      group: 'input',
      required: true,
      rows: 6,
      placeholder: 'Explain the mechanism of action of ibuprofen...',
      description: 'Your message to the model',
    },
    {
      id: 'temperature',
      label: 'Temperature',
      type: 'number',
      group: 'parameters',
      default: 0.7,
      min: 0,
      max: 2,
      step: 0.1,
      description: 'Higher = more creative, lower = more deterministic',
    },
    {
      id: 'maxTokens',
      label: 'Max Tokens',
      type: 'number',
      group: 'parameters',
      default: 2048,
      min: 1,
      max: 8192,
      step: 256,
      description: 'Maximum number of tokens to generate',
    },
    {
      id: 'topP',
      label: 'Top P',
      type: 'number',
      group: 'advanced',
      default: 1.0,
      min: 0,
      max: 1,
      step: 0.05,
      description: 'Nucleus sampling threshold',
    },
    {
      id: 'model',
      label: 'Model Name',
      type: 'text',
      group: 'advanced',
      default: 'Qwen/Qwen3-Next-80B-A3B-Instruct',
      description: 'Model identifier',
    },
  ],
  buildRequest(values) {
    const messages: { role: string; content: string }[] = [];
    if (values.systemPrompt) {
      messages.push({ role: 'system', content: String(values.systemPrompt) });
    }
    messages.push({ role: 'user', content: String(values.userMessage) });
    return {
      model: values.model || 'Qwen/Qwen3-Next-80B-A3B-Instruct',
      messages,
      temperature: Number(values.temperature ?? 0.7),
      max_tokens: Number(values.maxTokens ?? 2048),
      top_p: Number(values.topP ?? 1.0),
      stream: false,
    };
  },
  parseResponse(data: unknown): PlaygroundResult {
    const d = data as Record<string, unknown>;
    const choices = d.choices as Array<{ message?: { content?: string } }>;
    const content = choices?.[0]?.message?.content || '';
    const usage = d.usage as Record<string, number> | undefined;
    const items: PlaygroundResultItem[] = [
      { label: 'Response', value: content, format: 'text' },
    ];
    if (usage) {
      items.push({
        label: 'Usage',
        value: `Prompt: ${usage.prompt_tokens} tokens | Completion: ${usage.completion_tokens} tokens | Total: ${usage.total_tokens} tokens`,
        format: 'text',
      });
    }
    return { type: 'text', raw: data, items };
  },
};

// --------------------------------------------------------------------------
// 2. OpenFold3 (Structure Prediction)
// --------------------------------------------------------------------------

const OPENFOLD3: NimPlaygroundDef = {
  id: 'openfold3',
  name: 'OpenFold3',
  category: 'Structure Prediction',
  categoryIcon: 'structure',
  description: 'Next-generation structure prediction supporting protein, DNA, RNA, and ligand complexes.',
  resultType: 'structure',
  exampleResult: OPENFOLD3_EXAMPLE,
  fields: [
    {
      id: 'sequences',
      label: 'Protein Sequences',
      type: 'textarea',
      group: 'input',
      required: true,
      rows: 6,
      default: 'A:LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF',
      placeholder: 'A:MKFLILNKQKQLAWDLNPHADYLARIQKLF\nB:GKKVFLIANAQKALIDLNVSTQDDLARIQALFE',
      description: 'One chain per line, format: ChainID:Sequence (or just the sequence)',
    },
    {
      id: 'ligandSmiles',
      label: 'Ligand SMILES',
      type: 'text',
      group: 'input',
      placeholder: 'CC(=O)Oc1ccccc1C(=O)O',
      description: 'Optional small-molecule ligand to co-fold',
    },
    {
      id: 'dnaSequences',
      label: 'DNA Sequences',
      type: 'textarea',
      group: 'advanced',
      rows: 3,
      placeholder: 'D:ATCGATCGATCG',
      description: 'Optional DNA chains (ChainID:Sequence)',
    },
    {
      id: 'rnaSequences',
      label: 'RNA Sequences',
      type: 'textarea',
      group: 'advanced',
      rows: 3,
      placeholder: 'R:AUCGAUCGAUCG',
      description: 'Optional RNA chains (ChainID:Sequence)',
    },
    {
      id: 'msa',
      label: 'MSA Alignment (A3M)',
      type: 'textarea',
      group: 'input',
      rows: 6,
      default: '>query\nLSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF',
      placeholder: '>query\nMKFLILNK...\n>hit1\nMKFLILNK...',
      description: 'MSA in A3M format. At minimum, provide the query sequence. A single-sequence MSA is auto-generated if left empty.',
    },
    {
      id: 'diffusionSamples',
      label: 'Diffusion Samples',
      type: 'number',
      group: 'parameters',
      default: 1,
      min: 1,
      max: 5,
      step: 1,
      description: 'Number of structure samples to generate',
    },
    {
      id: 'outputFormat',
      label: 'Output Format',
      type: 'select',
      group: 'parameters',
      default: 'pdb',
      options: [
        { value: 'pdb', label: 'PDB' },
        { value: 'cif', label: 'mmCIF' },
      ],
    },
  ],
  buildRequest(values) {
    const molecules: Record<string, unknown>[] = [];

    // Protein chains
    const chains = parseChainSequences(String(values.sequences || ''));
    for (const chain of chains) {
      // OpenFold3 requires MSA for every protein chain — use provided MSA
      // for the first chain, or auto-generate a single-sequence MSA
      const msaAlignment = molecules.length === 0 && values.msa
        ? String(values.msa)
        : `>query\n${chain.sequence}`;
      const mol: Record<string, unknown> = {
        type: 'protein',
        id: chain.id,
        sequence: chain.sequence,
        msa: {
          main: {
            a3m: {
              alignment: msaAlignment,
              format: 'a3m',
            },
          },
        },
      };
      molecules.push(mol);
    }

    // Ligand
    if (values.ligandSmiles && String(values.ligandSmiles).trim()) {
      molecules.push({
        type: 'ligand',
        id: String.fromCharCode(65 + molecules.length),
        smiles: String(values.ligandSmiles).trim(),
      });
    }

    // DNA chains
    if (values.dnaSequences) {
      const dnaChains = parseChainSequences(String(values.dnaSequences));
      for (const chain of dnaChains) {
        molecules.push({
          type: 'dna',
          id: chain.id,
          sequence: chain.sequence,
        });
      }
    }

    // RNA chains
    if (values.rnaSequences) {
      const rnaChains = parseChainSequences(String(values.rnaSequences));
      for (const chain of rnaChains) {
        molecules.push({
          type: 'rna',
          id: chain.id,
          sequence: chain.sequence,
        });
      }
    }

    return {
      inputs: [
        {
          input_id: 'playground_prediction',
          molecules,
          diffusion_samples: Number(values.diffusionSamples ?? 1),
          output_format: values.outputFormat || 'pdb',
        },
      ],
    };
  },
  parseResponse(data: unknown): PlaygroundResult {
    const d = data as Record<string, unknown>;
    const items: PlaygroundResultItem[] = [];

    // Normalize pLDDT to 0-100 scale (API may return 0-1 or 0-100)
    const normalizePlddt = (v: number): number => (v > 0 && v <= 1.0 ? v * 100 : v);

    // Try new format first: { playground_prediction: { structures: [{ structure, plddt, ptm }] } }
    const predictionKey = Object.keys(d).find((k) => k !== 'outputs' && d[k] && typeof d[k] === 'object' && 'structures' in (d[k] as Record<string, unknown>));
    if (predictionKey) {
      const prediction = d[predictionKey] as Record<string, unknown>;
      const structures = prediction.structures as Array<Record<string, unknown>> | undefined;
      if (structures?.[0]) {
        const struct = structures[0];
        const structureData = (struct.structure || '') as string;
        const metrics = (struct.metrics || (prediction.metrics as Record<string, unknown>) || {}) as Record<string, unknown>;
        const plddt = (metrics.avg_plddt ?? metrics.complex_plddt_score ?? struct.plddt) as number | undefined;
        const ptm = (metrics.ptm ?? metrics.ptm_score ?? struct.ptm) as number | undefined;
        const confidence = (metrics.confidence_score ?? metrics.ranking_score) as number | undefined;

        if (structureData) {
          const scores: string[] = [];
          if (plddt !== undefined) scores.push(`pLDDT: ${normalizePlddt(plddt).toFixed(1)}`);
          if (ptm !== undefined) scores.push(`pTM: ${ptm.toFixed(3)}`);
          if (confidence !== undefined) scores.push(`Confidence: ${(confidence * 100).toFixed(1)}%`);
          const ext = String(structureData).startsWith('data_') ? 'cif' : 'pdb';
          items.push({
            label: `Predicted Structure${scores.length ? ` (${scores.join(', ')})` : ''}`,
            value: structureData,
            format: 'structure',
            downloadFilename: `openfold3_prediction.${ext}`,
          });
        }
      }
    }

    // Fallback: old format { outputs: [{ structures_with_scores: [{ structure, complex_plddt_score, confidence_score, ptm_score }] }] }
    if (items.length === 0) {
      const nested = d.data as Record<string, unknown> | undefined;
      const outputs = (d.outputs || nested?.outputs) as Array<Record<string, unknown>> | undefined;
      if (outputs?.[0]) {
        const output = outputs[0];
        const structures = output.structures_with_scores as Array<Record<string, unknown>> | undefined;
        if (structures?.[0]) {
          const struct = structures[0];
          const structureData = (struct.structure || struct.pdb_string || struct.cif_string || '') as string;
          const plddt = struct.complex_plddt_score as number | undefined;
          const ptm = struct.ptm_score as number | undefined;
          const confidence = struct.confidence_score as number | undefined;
          const ext = String(structureData).startsWith('data_') ? 'cif' : 'pdb';
          const scores: string[] = [];
          if (plddt !== undefined) scores.push(`pLDDT: ${normalizePlddt(plddt).toFixed(1)}`);
          if (ptm !== undefined) scores.push(`pTM: ${ptm.toFixed(3)}`);
          if (confidence !== undefined) scores.push(`Confidence: ${(confidence * 100).toFixed(1)}%`);
          items.push({
            label: `Predicted Structure${scores.length ? ` (${scores.join(', ')})` : ''}`,
            value: structureData,
            format: 'structure',
            downloadFilename: `openfold3_prediction.${ext}`,
          });
        }
      }
    }

    if (items.length === 0) {
      items.push({ label: 'Raw Response', value: JSON.stringify(data, null, 2), format: 'json' });
    }

    return { type: 'structure', raw: data, items };
  },
};

// --------------------------------------------------------------------------
// 3. Boltz2 (Structure Prediction)
// --------------------------------------------------------------------------

const BOLTZ2: NimPlaygroundDef = {
  id: 'boltz2',
  name: 'Boltz2',
  category: 'Structure Prediction',
  categoryIcon: 'structure',
  description: 'Fast and accurate biomolecular structure prediction with affinity estimation.',
  resultType: 'structure',
  exampleResult: BOLTZ2_EXAMPLE,
  fields: [
    {
      id: 'sequences',
      label: 'Protein Sequences',
      type: 'textarea',
      group: 'input',
      required: true,
      rows: 6,
      default: 'A:LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF',
      placeholder: 'A:MKFLILNKQKQLAWDLNPHADYLARIQKLF\nB:GKKVFLIANAQKALIDLNVSTQDDLARIQALFE',
      description: 'One chain per line, format: ChainID:Sequence',
    },
    {
      id: 'ligandSmiles',
      label: 'Ligand SMILES',
      type: 'text',
      group: 'input',
      placeholder: 'CC(=O)Oc1ccccc1C(=O)O',
      description: 'Optional ligand to co-fold',
    },
    {
      id: 'recyclingSteps',
      label: 'Recycling Steps',
      type: 'number',
      group: 'parameters',
      default: 3,
      min: 1,
      max: 10,
      step: 1,
      description: 'Number of recycling iterations',
    },
    {
      id: 'samplingSteps',
      label: 'Sampling Steps',
      type: 'number',
      group: 'parameters',
      default: 200,
      min: 50,
      max: 500,
      step: 50,
      description: 'Number of diffusion sampling steps',
    },
    {
      id: 'diffusionSamples',
      label: 'Diffusion Samples',
      type: 'number',
      group: 'parameters',
      default: 1,
      min: 1,
      max: 5,
      step: 1,
      description: 'Number of structure samples to generate',
    },
    {
      id: 'stepScale',
      label: 'Step Scale',
      type: 'number',
      group: 'advanced',
      default: 1.638,
      min: 0.1,
      max: 5,
      step: 0.1,
      description: 'Diffusion step scale factor',
    },
    {
      id: 'predictAffinity',
      label: 'Predict Affinity',
      type: 'checkbox',
      group: 'advanced',
      default: false,
      description: 'Estimate binding affinity (slower)',
    },
  ],
  buildRequest(values) {
    const polymers: Record<string, unknown>[] = [];
    const chains = parseChainSequences(String(values.sequences || ''));
    for (const chain of chains) {
      polymers.push({
        molecule_type: 'protein',
        sequence: chain.sequence,
        cyclic: false,
      });
    }

    const ligands: Record<string, unknown>[] = [];
    if (values.ligandSmiles && String(values.ligandSmiles).trim()) {
      ligands.push({
        id: String.fromCharCode(65 + polymers.length),
        smiles: String(values.ligandSmiles).trim(),
      });
    }

    const request: Record<string, unknown> = {
      polymers,
      recycling_steps: Number(values.recyclingSteps ?? 3),
      sampling_steps: Number(values.samplingSteps ?? 200),
      diffusion_samples: Number(values.diffusionSamples ?? 1),
      step_scale: Number(values.stepScale ?? 1.638),
      output_format: 'mmcif',
    };

    if (ligands.length > 0) request.ligands = ligands;
    if (values.predictAffinity) request.predict_affinity = true;

    return request;
  },
  parseResponse(data: unknown): PlaygroundResult {
    const d = data as Record<string, unknown>;
    const items: PlaygroundResultItem[] = [];

    // Boltz2 response: { structures: [{structure: "mmCIF..."}], confidence_scores: [n], complex_plddt_scores: [n], ptm_scores: [n] }
    const structures = d.structures as Array<Record<string, unknown>> | undefined;
    const confidenceScores = d.confidence_scores as number[] | undefined;
    const plddtScores = d.complex_plddt_scores as number[] | undefined;
    const ptmScores = d.ptm_scores as number[] | undefined;

    if (structures?.[0]) {
      const structure = (structures[0].structure || '') as string;
      const confidence = confidenceScores?.[0];
      const plddt = plddtScores?.[0];
      const ptm = ptmScores?.[0];

      if (structure) {
        const scores: string[] = [];
        if (plddt !== undefined) scores.push(`pLDDT: ${(plddt * 100).toFixed(1)}`);
        if (confidence !== undefined) scores.push(`confidence: ${confidence.toFixed(3)}`);
        if (ptm !== undefined) scores.push(`pTM: ${ptm.toFixed(3)}`);
        items.push({
          label: `Predicted Structure${scores.length ? ` (${scores.join(', ')})` : ''}`,
          value: structure,
          format: 'structure',
          downloadFilename: 'boltz2_prediction.cif',
        });
      }
    }

    // Fallback: direct structure field
    if (items.length === 0) {
      const structure = (d.pdb_string || d.cif_string || d.structure || '') as string;
      if (structure) {
        items.push({
          label: 'Predicted Structure',
          value: structure,
          format: 'structure',
          downloadFilename: 'boltz2_prediction.cif',
        });
      }
    }

    // Check for affinity prediction
    const affinity = d.affinity as Record<string, unknown> | undefined;
    if (affinity) {
      items.push({
        label: 'Affinity Prediction',
        value: JSON.stringify(affinity, null, 2),
        format: 'json',
      });
    }

    if (items.length === 0) {
      items.push({ label: 'Raw Response', value: JSON.stringify(data, null, 2), format: 'json' });
    }

    return { type: 'structure', raw: data, items };
  },
};

// --------------------------------------------------------------------------
// 4. OpenFold2 (Structure from MSA)
// --------------------------------------------------------------------------

const OPENFOLD2: NimPlaygroundDef = {
  id: 'openfold2',
  name: 'OpenFold2',
  category: 'Structure Prediction',
  categoryIcon: 'structure',
  description: 'Structure prediction from multiple sequence alignment (MSA) and templates.',
  resultType: 'structure',
  exampleResult: OPENFOLD2_EXAMPLE,
  fields: [
    {
      id: 'sequence',
      label: 'Protein Sequence',
      type: 'textarea',
      group: 'input',
      required: true,
      rows: 4,
      default: 'LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF',
      placeholder: 'MKFLILNKQKQLAWDLNPHADYLARIQKLF',
      description: 'Single protein sequence (no chain ID needed)',
    },
    {
      id: 'alignment',
      label: 'MSA Alignment (A3M)',
      type: 'textarea',
      group: 'input',
      rows: 8,
      default: '>query\nLSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF',
      placeholder: '>query\nMKFLILNK...\n>hit1\nMKFLILNK...\n>hit2\nMKFLILNK...',
      description: 'Multiple sequence alignment in A3M format. If empty, a single-sequence MSA is auto-generated.',
    },
    {
      id: 'selectedModels',
      label: 'Selected Models',
      type: 'multiselect',
      group: 'parameters',
      default: ['1', '2', '3', '4', '5'],
      options: [
        { value: '1', label: 'Model 1' },
        { value: '2', label: 'Model 2' },
        { value: '3', label: 'Model 3' },
        { value: '4', label: 'Model 4' },
        { value: '5', label: 'Model 5' },
      ],
      description: 'AlphaFold2 model variants to use',
    },
  ],
  buildRequest(values) {
    const selectedModels = Array.isArray(values.selectedModels)
      ? (values.selectedModels as string[]).map(Number)
      : [1, 2, 3, 4, 5];

    const sequence = String(values.sequence || '').trim();
    const alignment = values.alignment && String(values.alignment).trim()
      ? String(values.alignment).trim()
      : `>query\n${sequence}`;

    return {
      sequence,
      alignments: {
        uniref90: {
          a3m: {
            alignment,
            format: 'a3m',
          },
        },
      },
      templates: [],
      selected_models: selectedModels,
      output_format: 'cif',
    };
  },
  parseResponse(data: unknown): PlaygroundResult {
    const d = data as Record<string, unknown>;
    const items: PlaygroundResultItem[] = [];

    // OpenFold2 response: { structures_in_ranked_order: [{ structure, format, confidence }] }
    const ranked = d.structures_in_ranked_order as Array<Record<string, unknown>> | undefined;
    if (ranked?.[0]) {
      const struct = ranked[0];
      const structure = (struct.structure || '') as string;
      const confidence = struct.confidence as number | undefined;

      if (structure) {
        const plddt = confidence !== undefined ? (confidence > 1 ? confidence : confidence * 100) : undefined;
        items.push({
          label: `Predicted Structure${plddt !== undefined ? ` (pLDDT: ${plddt.toFixed(1)})` : ''}`,
          value: structure,
          format: 'structure',
          downloadFilename: 'openfold2_prediction.cif',
        });
      }
    }

    // Fallback: direct structure field
    if (items.length === 0) {
      const structure = (d.pdb_string || d.structure || '') as string;
      if (structure) {
        items.push({
          label: 'Predicted Structure',
          value: structure,
          format: 'structure',
          downloadFilename: 'openfold2_prediction.cif',
        });
      }
    }

    if (items.length === 0) {
      items.push({ label: 'Raw Response', value: JSON.stringify(data, null, 2), format: 'json' });
    }

    return { type: 'structure', raw: data, items };
  },
};

// --------------------------------------------------------------------------
// 5. GenMol (Molecule Generation)
// --------------------------------------------------------------------------

const GENMOL: NimPlaygroundDef = {
  id: 'genmol',
  name: 'GenMol',
  category: 'Molecule Generation',
  categoryIcon: 'molecule',
  description: 'Generate novel drug-like molecules using SAFE notation. Use [*{min-max}] to specify generation regions.',
  resultType: 'molecules',
  endpointPath: '/generate',
  exampleResult: GENMOL_EXAMPLE,
  supportsParallel: true,
  fields: [
    {
      id: 'smiles',
      label: 'SAFE Input',
      type: 'text',
      group: 'input',
      required: true,
      default: '[*{20-30}]',
      placeholder: '[*{20-30}]',
      description: 'SAFE notation: [*{min-max}] for de novo, or scaffold.[*{min-max}] for scaffold-based (e.g. c1ccccc1.[*{10-20}])',
    },
    {
      id: 'numMolecules',
      label: 'Number of Molecules',
      type: 'number',
      group: 'parameters',
      default: 10,
      min: 1,
      max: 100,
      step: 1,
      description: 'How many candidate molecules to generate per request',
    },
    {
      id: 'parallelRequests',
      label: 'Parallel Requests',
      type: 'number',
      group: 'parameters',
      default: 1,
      min: 1,
      max: 10,
      step: 1,
      description: 'Number of parallel requests to the load-balanced NIM. Each request generates the above number of molecules — results are merged.',
    },
    {
      id: 'temperature',
      label: 'Temperature',
      type: 'number',
      group: 'parameters',
      default: 2.0,
      min: 0.1,
      max: 10.0,
      step: 0.1,
      description: 'Sampling temperature (higher = more diverse)',
    },
    {
      id: 'scoring',
      label: 'Scoring Function',
      type: 'select',
      group: 'parameters',
      default: 'QED',
      options: [
        { value: 'QED', label: 'QED (Drug-likeness)' },
        { value: 'plogP', label: 'plogP (Penalized LogP)' },
      ],
      description: 'Score generated molecules with this function',
    },
    {
      id: 'unique',
      label: 'Unique Only',
      type: 'checkbox',
      group: 'parameters',
      default: true,
      description: 'Only return unique molecules (deduplicate)',
    },
    {
      id: 'noise',
      label: 'Noise',
      type: 'number',
      group: 'advanced',
      default: 1.0,
      min: 0,
      max: 2,
      step: 0.1,
      description: 'Noise factor for top-K sampling',
    },
    {
      id: 'stepSize',
      label: 'Step Size',
      type: 'number',
      group: 'advanced',
      default: 1,
      min: 1,
      max: 10,
      step: 1,
      description: 'Diffusion step size',
    },
  ],
  buildRequest(values) {
    return {
      smiles: String(values.smiles || ''),
      num_molecules: Number(values.numMolecules ?? 10),
      temperature: Number(values.temperature ?? 2.0),
      noise: Number(values.noise ?? 1.0),
      step_size: Number(values.stepSize ?? 1),
      scoring: values.scoring || 'QED',
      unique: values.unique !== false,
    };
  },
  parseResponse(data: unknown): PlaygroundResult {
    const d = data as Record<string, unknown>;
    const items: PlaygroundResultItem[] = [];

    const molecules = (d.generated || d.molecules || d.generated_molecules || d.results) as
      | Array<Record<string, unknown>>
      | undefined;

    if (Array.isArray(molecules)) {
      const smilesLines = molecules
        .map((m, i) => {
          const smi = m.smiles || m.smi || m.molecule || '';
          const score = m.score ?? m.qed ?? '';
          return `${i + 1}. ${smi}${score ? ` (score: ${Number(score).toFixed(3)})` : ''}`;
        })
        .join('\n');
      items.push({
        label: `Generated Molecules (${molecules.length})`,
        value: smilesLines,
        format: 'smiles',
        downloadFilename: 'genmol_molecules.txt',
      });
    }

    if (items.length === 0) {
      items.push({ label: 'Raw Response', value: JSON.stringify(data, null, 2), format: 'json' });
    }

    return { type: 'molecules', raw: data, items };
  },
  mergeResults(results: PlaygroundResult[]): PlaygroundResult {
    // Collect all raw molecule arrays and deduplicate by SMILES
    const seen = new Set<string>();
    const allMolecules: { smi: string; score: number | null }[] = [];
    for (const result of results) {
      const raw = result.raw as Record<string, unknown>;
      const molecules = (raw.generated || raw.molecules || raw.generated_molecules || raw.results) as
        | Array<Record<string, unknown>>
        | undefined;
      if (Array.isArray(molecules)) {
        for (const m of molecules) {
          const smi = String(m.smiles || m.smi || m.molecule || '');
          if (!smi || seen.has(smi)) continue;
          seen.add(smi);
          const score = m.score ?? m.qed ?? null;
          allMolecules.push({ smi, score: score !== null ? Number(score) : null });
        }
      }
    }
    // Sort by score descending (best first)
    allMolecules.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));

    const smilesLines = allMolecules
      .map((m, i) => `${i + 1}. ${m.smi}${m.score !== null ? ` (score: ${m.score.toFixed(3)})` : ''}`)
      .join('\n');

    return {
      type: 'molecules',
      raw: { merged: true, requestCount: results.length, totalMolecules: allMolecules.length },
      items: [{
        label: `Generated Molecules (${allMolecules.length} unique from ${results.length} requests)`,
        value: smilesLines,
        format: 'smiles',
        downloadFilename: 'genmol_molecules.txt',
      }],
    };
  },
};

// --------------------------------------------------------------------------
// 6. MolMIM (Molecule Generation)
// --------------------------------------------------------------------------

const MOLMIM: NimPlaygroundDef = {
  id: 'molmim',
  name: 'MolMIM',
  category: 'Molecule Generation',
  categoryIcon: 'molecule',
  description: 'Generate molecules similar to a reference compound using controlled molecular interpolation.',
  resultType: 'molecules',
  exampleResult: MOLMIM_EXAMPLE,
  endpointPath: '/generate',
  fields: [
    {
      id: 'smi',
      label: 'Reference SMILES',
      type: 'text',
      group: 'input',
      required: true,
      default: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
      placeholder: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
      description: 'Reference molecule SMILES to generate analogs of (default: Ibuprofen)',
    },
    {
      id: 'numMolecules',
      label: 'Number of Molecules',
      type: 'number',
      group: 'parameters',
      default: 10,
      min: 1,
      max: 100,
      step: 1,
      description: 'How many analog molecules to generate',
    },
    {
      id: 'algorithm',
      label: 'Algorithm',
      type: 'select',
      group: 'parameters',
      default: 'none',
      options: [
        { value: 'none', label: 'Random Sampling' },
        { value: 'CMA-ES', label: 'CMA-ES Optimization' },
      ],
      description: 'Generation algorithm — Random Sampling is fast, CMA-ES optimizes for the chosen property',
    },
    {
      id: 'propertyName',
      label: 'Scoring Property',
      type: 'select',
      group: 'parameters',
      default: 'QED',
      options: [
        { value: 'QED', label: 'QED (Drug-likeness)' },
        { value: 'plogP', label: 'plogP (Penalized LogP)' },
      ],
      description: 'Property to score/optimize molecules by',
    },
    {
      id: 'minSimilarity',
      label: 'Minimum Similarity',
      type: 'number',
      group: 'parameters',
      default: 0.3,
      min: 0,
      max: 0.7,
      step: 0.05,
      description: 'Minimum Tanimoto similarity to reference molecule (max 0.7)',
    },
    {
      id: 'scaledRadius',
      label: 'Sampling Radius',
      type: 'number',
      group: 'advanced',
      default: 1.0,
      min: 0.1,
      max: 3.0,
      step: 0.1,
      description: 'Radius of the latent space sampling (higher = more diverse)',
    },
    {
      id: 'iterations',
      label: 'CMA-ES Iterations',
      type: 'number',
      group: 'advanced',
      default: 10,
      min: 1,
      max: 1000,
      step: 1,
      description: 'CMA-ES optimization iterations (only used with CMA-ES algorithm)',
    },
    {
      id: 'particles',
      label: 'Particles',
      type: 'number',
      group: 'advanced',
      default: 30,
      min: 2,
      max: 100,
      step: 1,
      description: 'Number of candidate particles in CMA-ES (must be >= num_molecules)',
    },
  ],
  buildRequest(values) {
    const algorithm = String(values.algorithm || 'none');
    const request: Record<string, unknown> = {
      smi: String(values.smi || ''),
      num_molecules: Number(values.numMolecules ?? 10),
      algorithm,
      property_name: values.propertyName || 'QED',
      min_similarity: Number(values.minSimilarity ?? 0.3),
      scaled_radius: Number(values.scaledRadius ?? 1.0),
    };
    if (algorithm === 'CMA-ES') {
      request.iterations = Number(values.iterations ?? 10);
      request.particles = Math.max(
        Number(values.particles ?? 30),
        Number(values.numMolecules ?? 10),
      );
    }
    return request;
  },
  parseResponse(data: unknown): PlaygroundResult {
    const d = data as Record<string, unknown>;
    const items: PlaygroundResultItem[] = [];

    const molecules = (d.generated || d.molecules || d.generated_molecules || d.results) as
      | Array<Record<string, unknown>>
      | undefined;

    if (Array.isArray(molecules)) {
      const smilesLines = molecules
        .map((m, i) => {
          const smi = m.smiles || m.smi || m.molecule || '';
          const score = m.score ?? m.qed ?? '';
          const similarity = m.similarity ?? m.tanimoto ?? '';
          return `${i + 1}. ${smi}${score ? ` (score: ${Number(score).toFixed(3)})` : ''}${similarity ? ` [sim: ${Number(similarity).toFixed(3)}]` : ''}`;
        })
        .join('\n');
      items.push({
        label: `Generated Analogs (${molecules.length})`,
        value: smilesLines,
        format: 'smiles',
        downloadFilename: 'molmim_molecules.txt',
      });
    }

    if (items.length === 0) {
      items.push({ label: 'Raw Response', value: JSON.stringify(data, null, 2), format: 'json' });
    }

    return { type: 'molecules', raw: data, items };
  },
};

// --------------------------------------------------------------------------
// 7. DiffDock (Molecular Docking)
// --------------------------------------------------------------------------

const DIFFDOCK: NimPlaygroundDef = {
  id: 'diffdock',
  name: 'DiffDock',
  category: 'Molecular Docking',
  categoryIcon: 'docking',
  description: 'Predict how a small molecule binds to a protein using diffusion-based docking.',
  resultType: 'docking',
  exampleResult: DIFFDOCK_EXAMPLE,
  fields: [
    {
      id: 'protein',
      label: 'Protein Structure (PDB)',
      type: 'textarea',
      group: 'input',
      required: true,
      rows: 10,
      default: OPENFOLD3_STRUCTURE,
      placeholder: 'ATOM      1  N   ALA A   1       1.000   2.000   3.000  1.00  0.00           N\n...',
      description: 'Protein structure in PDB format. Paste PDB content or use output from structure prediction NIMs.',
    },
    {
      id: 'ligand',
      label: 'Ligand',
      type: 'textarea',
      group: 'input',
      required: true,
      rows: 3,
      default: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
      placeholder: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
      description: 'Ligand as SMILES string or SDF content',
    },
    {
      id: 'ligandFileType',
      label: 'Ligand Format',
      type: 'select',
      group: 'parameters',
      default: 'smi',
      options: [
        { value: 'smi', label: 'SMILES' },
        { value: 'sdf', label: 'SDF' },
      ],
      description: 'Format of the ligand input',
    },
    {
      id: 'numPoses',
      label: 'Number of Poses',
      type: 'number',
      group: 'parameters',
      default: 10,
      min: 1,
      max: 40,
      step: 1,
      description: 'Number of docking poses to generate',
    },
    {
      id: 'timeDivisions',
      label: 'Time Divisions',
      type: 'number',
      group: 'advanced',
      default: 20,
      min: 1,
      max: 40,
      step: 1,
      description: 'Number of time divisions for diffusion',
    },
    {
      id: 'steps',
      label: 'Diffusion Steps',
      type: 'number',
      group: 'advanced',
      default: 18,
      min: 1,
      max: 40,
      step: 1,
      description: 'Number of diffusion steps per time division',
    },
  ],
  buildRequest(values) {
    // DiffDock API uses 'txt' for SMILES input, not 'smi'
    const fileType = values.ligandFileType === 'smi' || !values.ligandFileType ? 'txt' : String(values.ligandFileType);
    return {
      protein: String(values.protein || ''),
      ligand: String(values.ligand || ''),
      ligand_file_type: fileType,
      num_poses: Number(values.numPoses ?? 10),
      time_divisions: Number(values.timeDivisions ?? 20),
      steps: Number(values.steps ?? 18),
    };
  },
  parseResponse(data: unknown): PlaygroundResult {
    const d = data as Record<string, unknown>;
    const items: PlaygroundResultItem[] = [];

    // DiffDock response: { ligand_positions: string[], position_confidence: number[], status, details }
    const ligandPositions = d.ligand_positions as string[] | undefined;
    const positionConfidence = d.position_confidence as number[] | undefined;

    if (Array.isArray(ligandPositions)) {
      // Build poses with normalized confidence
      const poses: { sdf: string; confidence: number; rawScore: number }[] = [];
      for (let i = 0; i < ligandPositions.length; i++) {
        if (!ligandPositions[i]) continue;
        const rawScore = positionConfidence?.[i];
        if (rawScore === null || rawScore === undefined) continue;
        // DiffDock confidence is negative log-likelihood (more negative = worse)
        // exp(score) gives probability [0, 1] — no negation needed for negative scores
        const confidence = Math.min(1, Math.max(0, Math.exp(rawScore)));
        poses.push({ sdf: ligandPositions[i], confidence, rawScore });
      }
      // Sort by confidence descending
      poses.sort((a, b) => b.confidence - a.confidence);

      poses.forEach((pose, i) => {
        items.push({
          label: `Pose ${i + 1} — ${(pose.confidence * 100).toFixed(1)}% confidence`,
          value: pose.sdf,
          format: 'docking',
          downloadFilename: `diffdock_pose_${i + 1}.sdf`,
        });
      });
    }

    if (items.length === 0) {
      items.push({ label: 'Raw Response', value: JSON.stringify(data, null, 2), format: 'json' });
    }

    return { type: 'docking', raw: data, items };
  },
};

// --------------------------------------------------------------------------
// 8. MSA Search
// --------------------------------------------------------------------------

const MSA_SEARCH: NimPlaygroundDef = {
  id: 'msa-search',
  name: 'MSA Search',
  category: 'Utilities',
  categoryIcon: 'utility',
  description: 'Search for homologous sequences to build multiple sequence alignments for structure prediction.',
  resultType: 'alignment',
  exampleResult: MSA_SEARCH_EXAMPLE,
  fields: [
    {
      id: 'sequence',
      label: 'Protein Sequence',
      type: 'textarea',
      group: 'input',
      required: true,
      rows: 4,
      default: 'LSDEDFKAVFGMTRSAFANLPLWKQQNLKKEKGLF',
      placeholder: 'MKFLILNKQKQLAWDLNPHADYLARIQKLF',
      description: 'Protein sequence to search for homologs',
    },
    {
      id: 'databases',
      label: 'Databases',
      type: 'multiselect',
      group: 'parameters',
      default: ['Uniref30_2302', 'colabfold_envdb_202108'],
      options: [
        { value: 'Uniref30_2302', label: 'UniRef30' },
        { value: 'colabfold_envdb_202108', label: 'ColabFold EnvDB' },
        { value: 'pdb100_230517', label: 'PDB100' },
        { value: 'PDB70_220313', label: 'PDB70' },
      ],
      description: 'Sequence databases to search',
    },
    {
      id: 'eValue',
      label: 'E-value Threshold',
      type: 'number',
      group: 'parameters',
      default: 0.001,
      min: 0.000001,
      max: 10,
      step: 0.001,
      description: 'Maximum E-value for including hits',
    },
    {
      id: 'maxMsaSequences',
      label: 'Max MSA Sequences',
      type: 'number',
      group: 'parameters',
      default: 500,
      min: 1,
      max: 500,
      step: 50,
      description: 'Maximum number of sequences in the resulting MSA',
    },
  ],
  buildRequest(values) {
    return {
      sequence: String(values.sequence || '').trim(),
      databases: Array.isArray(values.databases) ? values.databases : ['Uniref30_2302', 'colabfold_envdb_202108'],
      e_value: Number(values.eValue ?? 0.001),
      max_msa_sequences: Number(values.maxMsaSequences ?? 500),
    };
  },
  parseResponse(data: unknown): PlaygroundResult {
    const d = data as Record<string, unknown>;
    const items: PlaygroundResultItem[] = [];

    // Response format: { alignments: { <db>: { a3m: { alignment: "..." } }, ... , colabfold: { ... } }, metrics: {...} }
    const alignments = d.alignments as Record<string, Record<string, unknown>> | undefined;
    if (alignments) {
      // Use the merged 'colabfold' key if available, otherwise concatenate individual databases
      const merged = alignments.colabfold as Record<string, unknown> | undefined;
      const a3mData = merged?.a3m as Record<string, unknown> | undefined;
      const alignment = (a3mData?.alignment || '') as string;

      if (alignment) {
        const seqCount = (alignment.match(/>/g) || []).length;
        items.push({
          label: `MSA Alignment (${seqCount} sequences)`,
          value: alignment,
          format: 'code',
          downloadFilename: 'msa_search_result.a3m',
        });
      }

      // If no merged key, try individual databases
      if (items.length === 0) {
        for (const [dbName, dbData] of Object.entries(alignments)) {
          if (dbName === 'colabfold') continue;
          const dbA3m = (dbData as Record<string, unknown>)?.a3m as Record<string, unknown> | undefined;
          const dbAlignment = (dbA3m?.alignment || '') as string;
          if (dbAlignment) {
            const seqCount = (dbAlignment.match(/>/g) || []).length;
            items.push({
              label: `${dbName} (${seqCount} sequences)`,
              value: dbAlignment,
              format: 'code',
              downloadFilename: `msa_${dbName}.a3m`,
            });
          }
        }
      }
    }

    // Fallback: flat alignment string
    if (items.length === 0) {
      const alignment = (d.alignment || d.a3m || d.msa || d.output || '') as string;
      if (alignment) {
        const seqCount = (alignment.match(/>/g) || []).length;
        items.push({
          label: `MSA Alignment (${seqCount} sequences)`,
          value: alignment,
          format: 'code',
          downloadFilename: 'msa_search_result.a3m',
        });
      }
    }

    if (items.length === 0) {
      items.push({ label: 'Raw Response', value: JSON.stringify(data, null, 2), format: 'json' });
    }

    return { type: 'alignment', raw: data, items };
  },
};

// --------------------------------------------------------------------------
// 9. Evo2 (DNA/RNA Foundation Model)
// --------------------------------------------------------------------------

const EVO2: NimPlaygroundDef = {
  id: 'evo2',
  name: 'Evo2-40B',
  category: 'Utilities',
  categoryIcon: 'utility',
  description: 'DNA/RNA foundation model for sequence generation and analysis.',
  resultType: 'sequences',
  exampleResult: EVO2_EXAMPLE,
  fields: [
    {
      id: 'sequence',
      label: 'Input Sequence',
      type: 'textarea',
      group: 'input',
      required: true,
      rows: 4,
      default: 'ATCGATCGATCGATCG',
      placeholder: 'ATCGATCGATCGATCG',
      description: 'DNA or RNA seed sequence to extend',
    },
    {
      id: 'numTokens',
      label: 'Tokens to Generate',
      type: 'number',
      group: 'parameters',
      default: 100,
      min: 1,
      max: 2048,
      step: 50,
      description: 'Number of nucleotide tokens to generate',
    },
    {
      id: 'temperature',
      label: 'Temperature',
      type: 'number',
      group: 'parameters',
      default: 1.0,
      min: 0.1,
      max: 2.0,
      step: 0.1,
      description: 'Sampling temperature',
    },
    {
      id: 'topK',
      label: 'Top K',
      type: 'number',
      group: 'advanced',
      default: 4,
      min: 1,
      max: 100,
      step: 1,
      description: 'Top-K sampling parameter',
    },
    {
      id: 'topP',
      label: 'Top P',
      type: 'number',
      group: 'advanced',
      default: 1.0,
      min: 0,
      max: 1,
      step: 0.05,
      description: 'Nucleus sampling threshold',
    },
  ],
  buildRequest(values) {
    return {
      sequence: String(values.sequence || '').trim(),
      num_tokens: Number(values.numTokens ?? 100),
      temperature: Number(values.temperature ?? 1.0),
      top_k: Number(values.topK ?? 4),
      top_p: Number(values.topP ?? 1.0),
    };
  },
  parseResponse(data: unknown): PlaygroundResult {
    const d = data as Record<string, unknown>;
    const items: PlaygroundResultItem[] = [];

    const sequence = (d.sequence || d.generated_sequence || d.output || '') as string;
    if (sequence) {
      items.push({
        label: `Generated Sequence (${sequence.length} nt)`,
        value: sequence,
        format: 'sequence',
        downloadFilename: 'evo2_generated.fasta',
      });
    }

    if (items.length === 0) {
      items.push({ label: 'Raw Response', value: JSON.stringify(data, null, 2), format: 'json' });
    }

    return { type: 'sequences', raw: data, items };
  },
};

// --------------------------------------------------------------------------
// 10. ProteinMPNN (Sequence Design)
// --------------------------------------------------------------------------

const PROTEINMPNN: NimPlaygroundDef = {
  id: 'proteinmpnn',
  name: 'ProteinMPNN',
  category: 'Protein Design',
  categoryIcon: 'design',
  description: 'Design amino acid sequences for a given protein backbone structure.',
  resultType: 'sequences',
  exampleResult: PROTEINMPNN_EXAMPLE,
  fields: [
    {
      id: 'inputPdb',
      label: 'Input PDB Structure',
      type: 'textarea',
      group: 'input',
      required: true,
      rows: 10,
      default: OPENFOLD3_STRUCTURE,
      placeholder: 'ATOM      1  N   ALA A   1       1.000   2.000   3.000  1.00  0.00           N\n...',
      description: 'Protein backbone structure in PDB format',
    },
    {
      id: 'chainsToDesign',
      label: 'Chains to Design',
      type: 'text',
      group: 'parameters',
      default: 'A',
      placeholder: 'A',
      description: 'Chain IDs to redesign (comma-separated for multiple)',
    },
    {
      id: 'samplingTemp',
      label: 'Sampling Temperature',
      type: 'number',
      group: 'parameters',
      default: 0.1,
      min: 0.01,
      max: 1.0,
      step: 0.05,
      description: 'Lower = more conservative, higher = more diverse sequences',
    },
    {
      id: 'numSeqPerTarget',
      label: 'Sequences per Target',
      type: 'number',
      group: 'parameters',
      default: 8,
      min: 1,
      max: 64,
      step: 1,
      description: 'Number of designed sequences to generate',
    },
    {
      id: 'omitAAs',
      label: 'Omit Amino Acids',
      type: 'text',
      group: 'advanced',
      default: 'X',
      placeholder: 'CX',
      description: 'Amino acid letters to exclude from design (e.g., "C,X" to omit Cys and unknown)',
    },
    {
      id: 'biasAAs',
      label: 'Amino Acid Bias (JSON)',
      type: 'textarea',
      group: 'advanced',
      rows: 3,
      placeholder: '{"A": 1.5, "G": 1.2}',
      description: 'JSON object of amino acid letter to bias multiplier',
    },
  ],
  buildRequest(values) {
    // API expects: input_pdb (string), input_pdb_chains (string[]), sampling_temp (number[]), omit_AAs (string[])
    const chains = String(values.chainsToDesign || 'A').split(',').map(s => s.trim()).filter(Boolean);
    const omit = String(values.omitAAs || 'X').split('').filter(c => c.trim());
    const request: Record<string, unknown> = {
      input_pdb: String(values.inputPdb || ''),
      input_pdb_chains: chains,
      sampling_temp: [Number(values.samplingTemp ?? 0.1)],
      num_seq_per_target: Number(values.numSeqPerTarget ?? 8),
      omit_AAs: omit,
    };
    if (values.biasAAs && String(values.biasAAs).trim()) {
      try {
        request.bias_AA_jsonl = String(values.biasAAs).trim();
      } catch {
        // Skip invalid JSON
      }
    }
    return request;
  },
  parseResponse(data: unknown): PlaygroundResult {
    const d = data as Record<string, unknown>;
    const items: PlaygroundResultItem[] = [];

    // Actual API response: { mfasta: "...", scores: number[], probs: number[][][] }
    const mfasta = d.mfasta as string | undefined;
    if (mfasta) {
      // Parse FASTA entries to extract designed sequences (skip the input sequence)
      const entries = mfasta.split(/(?=^>)/m).filter(s => s.trim());
      const designedEntries = entries.filter(e => !e.startsWith('>input'));
      const seqCount = designedEntries.length;

      items.push({
        label: `Designed Sequences (${seqCount})`,
        value: mfasta,
        format: 'sequence',
        downloadFilename: 'proteinmpnn_sequences.fasta',
      });
    }

    // Fallback: array of sequence objects
    if (items.length === 0) {
      const sequences = (d.sequences || d.designed_sequences || d.results) as
        | Array<Record<string, unknown>>
        | undefined;
      if (Array.isArray(sequences)) {
        const seqText = sequences
          .map((s, i) => {
            const seq = s.sequence || s.seq || '';
            const score = s.score ?? s.global_score ?? '';
            return `>designed_${i + 1}${score ? ` score=${Number(score).toFixed(3)}` : ''}\n${seq}`;
          })
          .join('\n');
        items.push({
          label: `Designed Sequences (${sequences.length})`,
          value: seqText,
          format: 'sequence',
          downloadFilename: 'proteinmpnn_sequences.fasta',
        });
      }
    }

    if (items.length === 0) {
      items.push({ label: 'Raw Response', value: JSON.stringify(data, null, 2), format: 'json' });
    }

    return { type: 'sequences', raw: data, items };
  },
};

// --------------------------------------------------------------------------
// 11. RFDiffusion (Protein Backbone Design)
// --------------------------------------------------------------------------

const RFDIFFUSION: NimPlaygroundDef = {
  id: 'rfdiffusion',
  name: 'RFDiffusion',
  category: 'Protein Design',
  categoryIcon: 'design',
  description: 'Generate de novo protein backbone structures using guided diffusion. Requires an input PDB — designs binders or scaffolds around the target.',
  resultType: 'structure',
  exampleResult: RFDIFFUSION_EXAMPLE,
  fields: [
    {
      id: 'inputPdb',
      label: 'Input PDB',
      type: 'textarea',
      group: 'input',
      required: true,
      rows: 10,
      default: OPENFOLD3_STRUCTURE,
      placeholder: 'Paste PDB structure here...',
      description: 'Target protein structure for binder/scaffold design',
    },
    {
      id: 'contigs',
      label: 'Contigs',
      type: 'text',
      group: 'input',
      required: true,
      default: 'A1-35/0 30-50',
      placeholder: 'A1-35/0 30-50',
      description: 'Contig specification. "A1-35/0 30-50" keeps chain A residues 1-35 as target, then generates a 30-50 residue binder on a new chain.',
    },
    {
      id: 'diffusionSteps',
      label: 'Diffusion Steps',
      type: 'number',
      group: 'parameters',
      default: 50,
      min: 1,
      max: 50,
      step: 1,
      description: 'Number of denoising steps (more = higher quality, slower). Max 50.',
    },
    {
      id: 'hotspotRes',
      label: 'Hotspot Residues',
      type: 'text',
      group: 'advanced',
      placeholder: 'A15,A18,A19',
      description: 'Comma-separated residue IDs the binder must contact (e.g. A15,A18,A19)',
    },
  ],
  buildRequest(values) {
    const request: Record<string, unknown> = {
      input_pdb: String(values.inputPdb || ''),
      contigs: String(values.contigs || 'A1-35/0 30-50'),
      diffusion_steps: Number(values.diffusionSteps ?? 50),
    };
    if (values.hotspotRes && String(values.hotspotRes).trim()) {
      request.hotspot_res = String(values.hotspotRes)
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
    }
    return request;
  },
  parseResponse(data: unknown): PlaygroundResult {
    const d = data as Record<string, unknown>;
    const items: PlaygroundResultItem[] = [];

    const structure = (d.output_pdb || d.pdb_string || d.output || '') as string;
    if (structure) {
      items.push({
        label: 'Generated Backbone',
        value: structure,
        format: 'structure',
        downloadFilename: 'rfdiffusion_backbone.pdb',
      });
    }

    if (items.length === 0) {
      items.push({ label: 'Raw Response', value: JSON.stringify(data, null, 2), format: 'json' });
    }

    return { type: 'structure', raw: data, items };
  },
};

// ============================================================================
// Registry
// ============================================================================

export const NIM_PLAYGROUND_CONFIGS: NimPlaygroundDef[] = [
  OPENFOLD3,
  BOLTZ2,
  OPENFOLD2,
  GENMOL,
  MOLMIM,
  DIFFDOCK,
  MSA_SEARCH,
  EVO2,
  PROTEINMPNN,
  RFDIFFUSION,
  QWEN3,
];

export function getPlaygroundConfig(nimId: string): NimPlaygroundDef | undefined {
  return NIM_PLAYGROUND_CONFIGS.find((c) => c.id === nimId);
}

export function getPlaygroundConfigsByCategory(): Record<string, NimPlaygroundDef[]> {
  const grouped: Record<string, NimPlaygroundDef[]> = {};
  for (const config of NIM_PLAYGROUND_CONFIGS) {
    if (!grouped[config.category]) grouped[config.category] = [];
    grouped[config.category].push(config);
  }
  return grouped;
}
