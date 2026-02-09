/**
 * Agent Service
 *
 * This module implements the AI agent that powers the dynamic drug discovery workflow.
 * It uses Qwen3-80B as the "brain" that decides which tools to call and in what order.
 *
 * ## Architecture Overview
 *
 * The agent operates in a loop:
 * 1. User provides a drug discovery goal
 * 2. LLM receives the goal + available tools in system prompt
 * 3. LLM responds with text and/or a tool call: <tool_call>{"tool": "...", "arguments": {...}}</tool_call>
 * 4. If tool call detected, executeTool() handles it
 * 5. Tool result is summarized and fed back to LLM
 * 6. Loop continues until LLM calls "complete" tool
 *
 * ## Tool Execution Flow
 *
 * ```
 * User Message → LLM → Parse Response → Execute Tool → Summarize → Feed Back → LLM → ...
 *                                              ↓
 *                                      Update AgentResults
 *                                              ↓
 *                                      Render in AgentChat
 * ```
 *
 * ## Key Functions
 *
 * - `executeTool()` - Routes tool calls to appropriate handlers
 * - `runAgent()` - Main agent loop with streaming
 * - `summarizeToolResult()` - Compresses large results (structures, molecules) for LLM context
 *
 * ## State Management
 *
 * - `AgentState` - Tracks messages, results, and workflow status
 * - `AgentResults` - Accumulated data from tool executions (protein, structure, molecules, etc.)
 * - Results are stored in full fidelity but summarized when sent to LLM
 *
 * @see agentTools.ts for tool definitions and parsing
 * @see AgentChat.tsx for the UI component
 */

import { streamChat, type ChatMessage } from './nimApi';
import { formatToolsForPrompt, parseToolCall, type ParsedToolCall, AVAILABLE_MODELS } from './agentTools';
import { fetchSequence, searchProteins } from './uniprot';
import { predictStructure, type StructurePredictionResult } from './structurePrediction';
import { generateWithMolMIM, buildMolMIMRequest, type GeneratedMolecule } from './moleculeGeneration';
import { dockLigand, type DockingResult } from './docking';
import { calculateSimilarity } from './similarity';
import { type DrugTarget, getNumCopiesFromOligomericState } from '../data/drugs';

// Alias for protein type used in results
export type UniProtProtein = {
  accession: string;
  name: string;
  organism: string;
  sequence: string;
  length: number;
};

// Agent message types
export type AgentMessageRole = 'user' | 'assistant' | 'tool_result' | 'system';

export interface AgentMessage {
  id: string;
  role: AgentMessageRole;
  content: string;
  timestamp: number;
  toolCall?: ParsedToolCall;
  toolResult?: ToolResult;
  isStreaming?: boolean;
  isInternal?: boolean; // Internal messages shouldn't be shown in UI
}

export interface ToolResult {
  success: boolean;
  data?: unknown;
  error?: string;
  displayType?: 'text' | 'structure' | 'molecules' | 'docking' | 'similarity' | 'question';
}

// Collected results from agent actions
export interface AgentResults {
  protein?: UniProtProtein;
  structure?: StructurePredictionResult;
  molecules?: GeneratedMolecule[];
  dockingResults?: DockingResult[];
  similarityScores?: Array<{ smiles: string; similarity: number }>;
}

// Agent state
export interface AgentState {
  messages: AgentMessage[];
  results: AgentResults;
  isProcessing: boolean;
  pendingQuestion?: {
    question: string;
    options?: string[];
  };
  isComplete: boolean;
  summary?: string;
}

// System prompt for the agent
const AGENT_SYSTEM_PROMPT = `You are an expert computational drug discovery and protein design scientist with access to powerful AI tools. Your role is to help users with drug discovery, protein design, and related computational biology tasks.

${AVAILABLE_MODELS}

## Your Tools
${formatToolsForPrompt()}

## How to Use Tools
When you want to use a tool, respond with a tool call in this format:
<tool_call>{"tool": "tool_name", "arguments": {"param1": "value1", "param2": "value2"}}</tool_call>

## Guidelines
1. **Analyze the problem first**: Determine what type of task this is (small molecule discovery, protein design, binder design, etc.)
2. **Design the workflow**: Based on the task type, plan which tools and models you'll need
3. **Explain your reasoning**: Before calling a tool, briefly explain why you're using it
4. **Adapt dynamically**: If results suggest a different approach, adjust your workflow
5. **Ask when needed**: If requirements are unclear, use the ask_user tool
6. **Be efficient**: Don't repeat tool calls unnecessarily

## Common Workflow Patterns

### Small Molecule Drug Discovery
Best for: Finding drug candidates that bind to a protein target
1. search_uniprot → Find target protein
2. predict_structure → Get 3D structure (OpenFold3 recommended)
3. generate_molecules → Create candidates (MolMIM for analogs, GenMol for novel)
4. dock_molecules → Predict binding (DiffDock)
5. calculate_similarity → Compare to known drugs
6. complete → Summarize findings

### De Novo Protein Design
Best for: Creating new proteins with desired structures
1. design_protein → Generate backbone (RFDiffusion)
2. design_sequence → Design amino acids (ProteinMPNN)
3. predict_structure → Validate fold (OpenFold3)
4. complete → Report designed sequences

### Protein Binder Design
Best for: Designing proteins that bind to a specific target
1. search_uniprot → Find target protein
2. predict_structure → Get target structure
3. design_protein (mode: "binder") → Design binder backbone
4. design_sequence → Design binder sequence
5. predict_structure → Validate complex
6. complete → Report binder designs

### Lead Optimization
Best for: Improving existing drug candidates
1. generate_molecules (around seed) → Create analogs
2. predict_structure → Get target structure if needed
3. dock_molecules → Score all variants
4. calculate_similarity → Analyze diversity
5. complete → Rank and recommend

## Decision Guide
- **User wants to find drugs for a disease** → Small Molecule Discovery workflow
- **User wants to design a new protein** → De Novo Protein Design workflow
- **User wants proteins that bind something** → Protein Binder Design workflow
- **User has an existing drug to improve** → Lead Optimization workflow
- **User mentions "vaccine" or "antibody alternative"** → Protein Binder Design workflow
- **User mentions "enzyme"** → Could be structure prediction or protein redesign

## When to Use execute_raw_request
**IMPORTANT**: If the user provides a raw JSON payload and asks you to "run this query", "execute this request", or "test this API call", you MUST use the execute_raw_request tool with their exact JSON body. Do NOT convert it to predict_structure or other tools.

Example: If user says "run this query in openfold3: {\"queries\": {...}}", use:
<tool_call>{"tool": "execute_raw_request", "arguments": {"endpoint": "openfold3", "body": <their exact JSON>}}</tool_call>

The execute_raw_request tool is for:
- Testing specific API formats
- Debugging API calls
- Running custom/experimental requests
- When the user explicitly provides JSON payload

**CRITICAL**: When execute_raw_request fails with an API error:
1. Report the error to the user clearly
2. Do NOT try to "fix" or modify the user's JSON payload
3. Do NOT retry with different formats
4. The user is testing a specific format intentionally - they want to see the error
5. Simply explain what the error means and stop

Remember: You design the workflow based on the user's specific needs. Ask clarifying questions if the best approach is unclear.`;

// Generate unique ID
function generateId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Execute a tool and return the result
 *
 * This is the main tool dispatcher. It routes tool calls from the LLM to the appropriate
 * service handlers and formats the results consistently.
 *
 * Tool categories:
 * - Data retrieval: search_uniprot
 * - Structure prediction: predict_structure (with fallback)
 * - Molecule operations: generate_molecules, dock_molecules, calculate_similarity
 * - Protein design: design_protein, design_sequence
 * - User interaction: ask_user, complete
 * - Advanced: execute_raw_request (for API testing)
 *
 * @param toolCall - Parsed tool call from LLM response
 * @param gatewayUrl - Backend gateway URL (e.g., "46.243.144.128")
 * @param currentResults - Accumulated results from previous tools (for context)
 * @param drugTarget - Optional drug target info for auto-detecting oligomeric state
 */
export async function executeTool(
  toolCall: ParsedToolCall,
  gatewayUrl: string,
  currentResults: AgentResults,
  drugTarget?: DrugTarget | null
): Promise<ToolResult> {
  const { tool, arguments: args } = toolCall;

  try {
    switch (tool) {
      case 'search_uniprot': {
        const query = args.query as string;
        // Try as accession ID first
        if (/^[A-Z][A-Z0-9]{5,9}$/i.test(query)) {
          try {
            const entry = await fetchSequence(query);
            const protein: UniProtProtein = {
              accession: entry.accession,
              name: entry.proteinName,
              organism: entry.organism,
              sequence: entry.sequence,
              length: entry.length,
            };
            return {
              success: true,
              data: protein,
              displayType: 'text',
            };
          } catch {
            // Fall through to search
          }
        }
        // Try as search query
        const results = await searchProteins(query, 1);
        if (results.length > 0) {
          // Fetch full details for the first result
          const entry = await fetchSequence(results[0].accession);
          const protein: UniProtProtein = {
            accession: entry.accession,
            name: entry.proteinName,
            organism: entry.organism,
            sequence: entry.sequence,
            length: entry.length,
          };
          return {
            success: true,
            data: protein,
            displayType: 'text',
          };
        }
        return {
          success: false,
          error: `No protein found for query: ${query}`,
        };
      }

      case 'predict_structure': {
        const sequence = args.sequence as string;
        const requestedModel = (args.model as string) || 'openfold3';
        // Use num_copies from args, or auto-detect from drug target's oligomeric state
        const numCopiesFromArgs = args.num_copies as number | undefined;
        const numCopiesFromTarget = drugTarget?.targetProtein?.oligomericState
          ? getNumCopiesFromOligomericState(drugTarget.targetProtein.oligomericState)
          : 1;
        const numCopies = numCopiesFromArgs ?? numCopiesFromTarget;
        const result = await predictStructure(gatewayUrl, sequence, requestedModel as 'openfold3' | 'boltz2' | 'openfold2', { numCopies });

        // Check if fallback occurred (requested model differs from model used)
        const modelUsedLower = result.modelUsed.toLowerCase().replace(/\s/g, '');
        const requestedModelLower = requestedModel.toLowerCase();
        const fallbackOccurred = modelUsedLower !== requestedModelLower;

        return {
          success: true,
          data: {
            ...result,
            requestedModel,
            fallbackOccurred,
            fallbackNote: fallbackOccurred
              ? `Note: ${requestedModel.toUpperCase()} was unavailable (server error), so ${result.modelUsed} was used instead.`
              : undefined,
          },
          displayType: 'structure',
        };
      }

      case 'generate_molecules': {
        const seedSmiles = args.seed_smiles as string;
        const numMolecules = (args.num_molecules as number) || 30;
        const request = buildMolMIMRequest(seedSmiles, numMolecules);
        if (args.diversity) {
          request.scaled_radius = args.diversity as number;
        }
        const result = await generateWithMolMIM(gatewayUrl, request);
        return {
          success: true,
          data: result.molecules,
          displayType: 'molecules',
        };
      }

      case 'dock_molecules': {
        const proteinStructure = args.protein_structure as string || currentResults.structure?.structure;
        const structureFormat = currentResults.structure?.format || 'cif';
        const ligandSmiles = args.ligand_smiles as string;

        if (!proteinStructure) {
          return {
            success: false,
            error: 'No protein structure available. Run predict_structure first.',
          };
        }

        const smilesList = ligandSmiles.split(',').map((s) => s.trim()).slice(0, 10);
        const results: DockingResult[] = [];

        for (const smiles of smilesList) {
          try {
            const dockingResult = await dockLigand(gatewayUrl, proteinStructure, structureFormat, smiles, 5);
            results.push(dockingResult);
          } catch (err) {
            console.error(`Docking failed for ${smiles}:`, err);
          }
        }

        return {
          success: results.length > 0,
          data: results,
          displayType: 'docking',
          error: results.length === 0 ? 'All docking attempts failed' : undefined,
        };
      }

      case 'calculate_similarity': {
        const smilesList = (args.smiles_list as string).split(',').map((s) => s.trim());
        const referenceSmiles = args.reference_smiles as string;

        const results = smilesList.map((smiles) => ({
          smiles,
          similarity: calculateSimilarity(smiles, referenceSmiles),
        }));

        return {
          success: true,
          data: results,
          displayType: 'similarity',
        };
      }

      case 'design_protein': {
        const mode = args.mode as string;
        const length = args.length as number;
        const targetStructure = args.target_structure as string | undefined;
        const hotspotResidues = args.hotspot_residues as string | undefined;

        // Build RFDiffusion request based on mode
        const rfdiffusionUrl = `http://${gatewayUrl}:8010/biology/ipd/rfdiffusion/generate`;

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const requestBody: any = {
          contigs: [`${length}`], // e.g., ["100"] for 100 residue protein
          num_designs: 1,
        };

        if (mode === 'binder' && targetStructure) {
          requestBody.pdb = targetStructure;
          requestBody.contigs = [`A1-${length}`, `B1-100`]; // Target chain A, binder chain B
          if (hotspotResidues) {
            requestBody.hotspot_res = hotspotResidues.split(',').map(r => `A${r.trim()}`);
          }
        }

        try {
          const response = await fetch(rfdiffusionUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
          });

          if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`RFDiffusion failed: ${response.status} - ${errorText}`);
          }

          const data = await response.json();
          return {
            success: true,
            data: {
              structure: data.structure || data.pdb,
              mode,
              length,
            },
            displayType: 'structure',
          };
        } catch (err) {
          return {
            success: false,
            error: `RFDiffusion error: ${err instanceof Error ? err.message : 'Unknown error'}`,
          };
        }
      }

      case 'design_sequence': {
        const structure = args.structure as string;
        const numSequences = (args.num_sequences as number) || 4;
        const temperature = (args.temperature as number) || 0.1;
        const fixedPositions = args.fixed_positions as string | undefined;

        const proteinmpnnUrl = `http://${gatewayUrl}:8009/biology/ipd/proteinmpnn/predict`;

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const requestBody: any = {
          pdb: structure,
          num_seq_per_target: numSequences,
          sampling_temp: temperature,
        };

        if (fixedPositions) {
          requestBody.fixed_positions = fixedPositions.split(',').map(p => parseInt(p.trim()));
        }

        try {
          const response = await fetch(proteinmpnnUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
          });

          if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`ProteinMPNN failed: ${response.status} - ${errorText}`);
          }

          const data = await response.json();
          return {
            success: true,
            data: {
              sequences: data.sequences || data.designed_sequences,
              scores: data.scores || data.sequence_scores,
              numDesigns: numSequences,
            },
            displayType: 'text',
          };
        } catch (err) {
          return {
            success: false,
            error: `ProteinMPNN error: ${err instanceof Error ? err.message : 'Unknown error'}`,
          };
        }
      }

      case 'ask_user': {
        const question = args.question as string;
        const options = args.options ? (args.options as string).split(',').map((o) => o.trim()) : undefined;
        return {
          success: true,
          data: { question, options },
          displayType: 'question',
        };
      }

      case 'show_results': {
        return {
          success: true,
          data: args.data,
          displayType: args.result_type as 'structure' | 'molecules' | 'docking' | 'similarity',
        };
      }

      case 'complete': {
        return {
          success: true,
          data: { summary: args.summary },
          displayType: 'text',
        };
      }

      case 'execute_raw_request': {
        const endpoint = args.endpoint as string;
        const body = args.body as Record<string, unknown>;

        // Map endpoint names to URLs
        const endpointMap: Record<string, { port: number; path: string }> = {
          openfold3: { port: 8000, path: '/biology/openfold/openfold3/predict' },
          boltz2: { port: 8001, path: '/biology/boltz/boltz2/predict' },
          openfold2: { port: 8004, path: '/biology/openfold/openfold2/predict' },
          molmim: { port: 8006, path: '/biology/nvidia/molmim/generate' },
          diffdock: { port: 8007, path: '/biology/nvidia/diffdock/predict' },
          rfdiffusion: { port: 8010, path: '/biology/ipd/rfdiffusion/generate' },
          proteinmpnn: { port: 8009, path: '/biology/ipd/proteinmpnn/predict' },
        };

        let url: string;
        if (endpoint.startsWith('http')) {
          // Full URL provided - extract host/port/path and use proxy
          const parsed = new URL(endpoint);
          url = `/api/nim-proxy/${parsed.hostname}/${parsed.port || 80}${parsed.pathname}`;
        } else {
          // Map endpoint name to URL via proxy to avoid CORS
          const config = endpointMap[endpoint.toLowerCase()];
          if (!config) {
            return {
              success: false,
              error: `Unknown endpoint: ${endpoint}. Available: ${Object.keys(endpointMap).join(', ')}`,
            };
          }
          // Use the Vite proxy to avoid CORS issues
          url = `/api/nim-proxy/${gatewayUrl}/${config.port}${config.path}`;
        }

        try {
          const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          });

          if (!response.ok) {
            const errorText = await response.text();
            return {
              success: false,
              error: `API request failed: ${response.status} - ${errorText}`,
            };
          }

          const data = await response.json();

          // Check if response contains a structure
          let structure: string | undefined;
          let format: 'cif' | 'pdb' = 'cif';

          // OpenFold3 response format
          if (data.outputs?.[0]?.structures_with_scores?.[0]) {
            const structData = data.outputs[0].structures_with_scores[0];
            structure = structData.cif || structData.pdb || structData.structure;
            format = structData.cif ? 'cif' : 'pdb';
          }
          // Boltz2 / other formats
          else if (data.structure || data.pdb || data.cif) {
            structure = data.structure || data.pdb || data.cif;
            format = data.cif ? 'cif' : 'pdb';
          }

          if (structure) {
            return {
              success: true,
              data: {
                structure,
                format,
                confidenceScore: data.outputs?.[0]?.structures_with_scores?.[0]?.score || 0,
                plddt: data.outputs?.[0]?.structures_with_scores?.[0]?.plddt || 0,
                ptm: data.outputs?.[0]?.structures_with_scores?.[0]?.ptm || 0,
                modelUsed: endpoint,
                rawResponse: data,
              },
              displayType: 'structure',
            };
          }

          // Return raw response if no structure detected
          return {
            success: true,
            data: {
              rawResponse: data,
              endpoint,
            },
            displayType: 'text',
          };
        } catch (err) {
          return {
            success: false,
            error: `Request error: ${err instanceof Error ? err.message : 'Unknown error'}`,
          };
        }
      }

      default:
        return {
          success: false,
          error: `Unknown tool: ${tool}`,
        };
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Tool execution failed';
    return {
      success: false,
      error: message,
    };
  }
}

/**
 * Callbacks for the agent runner
 *
 * These callbacks allow the UI to react to agent events in real-time:
 * - onMessage: New message to display (user, assistant, or tool result)
 * - onResultsUpdate: Accumulated results changed (triggers visualization updates)
 * - onStreamChunk: Partial response for streaming display
 * - onComplete: Workflow finished with summary
 * - onQuestion: Agent is asking user for clarification
 */
export interface AgentRunnerCallbacks {
  onMessage: (message: AgentMessage) => void;
  onResultsUpdate: (results: AgentResults) => void;
  onStreamChunk: (messageId: string, chunk: string) => void;
  onComplete: (summary: string) => void;
  onQuestion: (question: string, options?: string[]) => void;
}

/**
 * Main agent loop - handles the conversation and tool execution
 *
 * This is the core agent runner that:
 * 1. Sends user message to LLM with conversation history
 * 2. Streams the response back for real-time display
 * 3. Parses any tool calls from the response
 * 4. Executes tools and collects results
 * 5. Recursively continues until workflow completes
 *
 * ## Recursion Pattern
 *
 * When a tool is executed, the result is fed back to the LLM as a new
 * "user" message (marked as internal). This allows the LLM to:
 * - Decide if more tools are needed
 * - Interpret results and explain to user
 * - Call the "complete" tool when finished
 *
 * ## Message Visibility
 *
 * - User messages: Visible (unless isInternalCall=true)
 * - Assistant messages: Always visible
 * - Tool results: Visible (shows success/error status)
 * - Internal messages: Hidden (tool result summaries sent to LLM)
 *
 * @param gatewayUrl - Backend gateway URL
 * @param userMessage - User's message or tool result summary
 * @param previousMessages - Conversation history for context
 * @param currentResults - Accumulated workflow results
 * @param callbacks - UI event handlers
 * @param isInternalCall - If true, user message is hidden (used for tool result feedback)
 * @param drugTarget - Drug target for oligomeric state detection
 */
export async function runAgent(
  gatewayUrl: string,
  userMessage: string,
  previousMessages: AgentMessage[],
  currentResults: AgentResults,
  callbacks: AgentRunnerCallbacks,
  isInternalCall = false,
  drugTarget?: DrugTarget | null
): Promise<void> {
  // Add user message (but mark it as internal if this is a recursive tool-result call)
  const userMsg: AgentMessage = {
    id: generateId(),
    role: 'user',
    content: userMessage,
    timestamp: Date.now(),
    isInternal: isInternalCall, // Don't show internal tool result messages in UI
  };
  // Only add to UI if not internal
  if (!isInternalCall) {
    callbacks.onMessage(userMsg);
  }

  // Build conversation history for LLM
  const chatMessages: ChatMessage[] = [
    { role: 'system', content: AGENT_SYSTEM_PROMPT },
    ...previousMessages.map((m) => ({
      role: (m.role === 'tool_result' ? 'user' : m.role) as 'system' | 'user' | 'assistant',
      content: m.role === 'tool_result'
        ? `Tool Result: ${JSON.stringify(m.toolResult)}`
        : m.content,
    })),
    { role: 'user', content: userMessage },
  ];

  // Get agent response with streaming
  const assistantMsgId = generateId();
  const assistantMsg: AgentMessage = {
    id: assistantMsgId,
    role: 'assistant',
    content: '',
    timestamp: Date.now(),
    isStreaming: true,
  };
  callbacks.onMessage(assistantMsg);

  let fullResponse = '';
  for await (const chunk of streamChat(gatewayUrl, chatMessages, { maxTokens: 2048 })) {
    fullResponse += chunk;
    callbacks.onStreamChunk(assistantMsgId, fullResponse);
  }

  // Update with final content
  assistantMsg.content = fullResponse;
  assistantMsg.isStreaming = false;

  // Check for tool call
  const toolCall = parseToolCall(fullResponse);
  if (toolCall) {
    assistantMsg.toolCall = toolCall;
  }

  // Always update the message in UI (to set isStreaming=false and add toolCall if present)
  callbacks.onMessage({ ...assistantMsg });

  // If no tool call, we're done - the response has been shown
  if (!toolCall) {
    return;
  }

  // Execute the tool
  const toolResult = await executeTool(toolCall, gatewayUrl, currentResults, drugTarget);

    // Handle special cases
    if (toolCall.tool === 'complete' && toolResult.success) {
      const summary = (toolResult.data as { summary: string }).summary;
      callbacks.onComplete(summary);
      return;
    }

    if (toolCall.tool === 'ask_user' && toolResult.success) {
      const { question, options } = toolResult.data as { question: string; options?: string[] };
      callbacks.onQuestion(question, options);
      return;
    }

    // Update results based on tool
    const updatedResults = { ...currentResults };
    if (toolCall.tool === 'search_uniprot' && toolResult.success) {
      updatedResults.protein = toolResult.data as UniProtProtein;
    } else if (toolCall.tool === 'predict_structure' && toolResult.success) {
      updatedResults.structure = toolResult.data as StructurePredictionResult;
    } else if (toolCall.tool === 'generate_molecules' && toolResult.success) {
      updatedResults.molecules = toolResult.data as GeneratedMolecule[];
    } else if (toolCall.tool === 'dock_molecules' && toolResult.success) {
      updatedResults.dockingResults = toolResult.data as DockingResult[];
    } else if (toolCall.tool === 'calculate_similarity' && toolResult.success) {
      updatedResults.similarityScores = toolResult.data as Array<{ smiles: string; similarity: number }>;
    } else if (toolCall.tool === 'execute_raw_request' && toolResult.success && toolResult.displayType === 'structure') {
      // Store structure from raw request
      const data = toolResult.data as { structure: string; format: 'cif' | 'pdb'; confidenceScore: number; plddt: number; ptm: number; modelUsed: string };
      updatedResults.structure = {
        structure: data.structure,
        format: data.format,
        confidenceScore: data.confidenceScore,
        plddt: data.plddt,
        ptm: data.ptm,
        modelUsed: data.modelUsed,
      };
    }
    callbacks.onResultsUpdate(updatedResults);

    // Add tool result message - include fallback note if present
    let toolResultContent = toolResult.success
      ? `Tool "${toolCall.tool}" completed successfully.`
      : `Tool "${toolCall.tool}" failed: ${toolResult.error}`;

    // Add fallback note for structure prediction
    if (toolCall.tool === 'predict_structure' && toolResult.success) {
      const data = toolResult.data as { fallbackNote?: string; modelUsed: string };
      if (data.fallbackNote) {
        toolResultContent += ` ${data.fallbackNote}`;
      } else {
        toolResultContent += ` Model used: ${data.modelUsed}.`;
      }
    }

    const toolResultMsg: AgentMessage = {
      id: generateId(),
      role: 'tool_result',
      content: toolResultContent,
      timestamp: Date.now(),
      toolResult,
    };
    callbacks.onMessage(toolResultMsg);

  // Continue the agent loop with the tool result (as an internal call)
  // Summarize the result to avoid sending massive data (like PDB structures) to the LLM
  const summarizedResult = summarizeToolResult(toolCall.tool, toolResult);

  await runAgent(
    gatewayUrl,
    `Tool result for ${toolCall.tool}: ${JSON.stringify(summarizedResult)}`,
    [...previousMessages, userMsg, assistantMsg, toolResultMsg],
    updatedResults,
    callbacks,
    true, // Mark as internal call so user message isn't shown in UI
    drugTarget // Pass drug target for oligomeric state detection
  );
}

/**
 * Summarize tool results to avoid sending massive data to the LLM
 * Full data is stored in updatedResults, this just provides a summary for the LLM
 */
function summarizeToolResult(tool: string, result: ToolResult): unknown {
  if (!result.success) {
    return { success: false, error: result.error };
  }

  switch (tool) {
    case 'predict_structure': {
      const data = result.data as {
        confidenceScore: number;
        plddt: number;
        ptm: number;
        modelUsed: string;
        format: string;
        requestedModel?: string;
        fallbackOccurred?: boolean;
        fallbackNote?: string;
      };
      return {
        success: true,
        modelUsed: data.modelUsed,
        confidenceScore: data.confidenceScore,
        plddt: data.plddt,
        ptm: data.ptm,
        format: data.format,
        fallbackOccurred: data.fallbackOccurred,
        fallbackNote: data.fallbackNote,
        note: 'Structure data stored - use show_results to display',
      };
    }

    case 'generate_molecules': {
      const molecules = result.data as Array<{ smiles: string; score: number }>;
      return {
        success: true,
        count: molecules.length,
        topMolecules: molecules.slice(0, 5).map(m => ({
          smiles: m.smiles.substring(0, 50) + (m.smiles.length > 50 ? '...' : ''),
          score: m.score,
        })),
        note: 'Full molecule data stored - use show_results to display',
      };
    }

    case 'dock_molecules': {
      const dockingResults = result.data as Array<{ ligandSmiles: string; bestConfidence: number }>;
      return {
        success: true,
        count: dockingResults.length,
        topResults: dockingResults.slice(0, 5).map(d => ({
          smiles: d.ligandSmiles.substring(0, 30) + '...',
          confidence: d.bestConfidence,
        })),
        note: 'Full docking data stored - use show_results to display',
      };
    }

    case 'search_uniprot': {
      const protein = result.data as { accession: string; name: string; organism: string; length: number };
      return {
        success: true,
        accession: protein.accession,
        name: protein.name,
        organism: protein.organism,
        length: protein.length,
        note: 'Full sequence stored',
      };
    }

    case 'execute_raw_request': {
      const data = result.data as {
        structure?: string;
        format?: string;
        confidenceScore?: number;
        modelUsed?: string;
        endpoint?: string;
        rawResponse?: unknown;
      };
      if (data.structure) {
        return {
          success: true,
          endpoint: data.modelUsed || data.endpoint,
          hasStructure: true,
          format: data.format,
          confidenceScore: data.confidenceScore,
          note: 'Structure data stored - use show_results to display',
        };
      }
      return {
        success: true,
        endpoint: data.endpoint,
        note: 'Raw response received',
        responsePreview: JSON.stringify(data.rawResponse).substring(0, 200) + '...',
      };
    }

    default:
      // For other tools, return a simplified version
      const stringified = JSON.stringify(result.data);
      if (stringified.length > 2000) {
        return {
          success: result.success,
          note: 'Result data stored (too large to display in summary)',
        };
      }
      return {
        success: result.success,
        data: result.data,
      };
  }
}
