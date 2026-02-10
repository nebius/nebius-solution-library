/**
 * Step Assistant - A small AI helper for each workflow step
 * Can answer questions, interpret results, and suggest parameter modifications
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import Markdown from 'react-markdown';
import { streamChat } from '../services/nimApi';

export type StepType =
  | 'sequence'
  | 'structure'
  | 'molecules'
  | 'docking'
  | 'rediscovery'
  | 'protein-design'
  | 'sequence-design'
  | 'validation';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
}

interface StepAssistantProps {
  stepType: StepType;
  gatewayUrl: string;
  context: Record<string, unknown>; // Step-specific context (sequence, results, etc.)
  onParameterSuggestion?: (params: Record<string, unknown>) => void;
}

// System prompts for each step type
const STEP_PROMPTS: Record<StepType, string> = {
  sequence: `You are a helpful assistant for the Sequence Retrieval step in a drug discovery workflow.
You can help users:
- Understand protein sequences and their properties
- Explain UniProt accession IDs and how to find them
- Interpret sequence features (length, domains, etc.)
- Suggest alternative proteins or isoforms

Keep responses concise and focused on the current step.`,

  structure: `You are a helpful assistant for the Structure Prediction step in a drug discovery workflow.
You can help users:
- Explain the different structure prediction models (OpenFold3, Boltz2, OpenFold2)
- Interpret confidence scores (pLDDT, pTM, confidence)
- Understand structure quality metrics
- Suggest which model to use based on the protein
- Explain what the 3D structure visualization shows

Available models:
- OpenFold3: Best for most proteins, uses diffusion-based prediction
- Boltz2: Fast prediction, good for rapid prototyping
- OpenFold2: Uses MSA templates, best for well-characterized proteins

Keep responses concise and focused on structure prediction.`,

  molecules: `You are a helpful assistant for the Molecule Generation step in a drug discovery workflow.
You can help users:
- Understand SMILES notation and molecular structures
- Explain drug-likeness properties (Lipinski's rules, QED scores)
- Interpret generated molecule quality
- Suggest modifications to generation parameters
- Compare generated molecules to known drugs

Generation parameters:
- num_molecules: How many molecules to generate (default: 30)
- scaled_radius: Diversity of generated molecules (higher = more diverse)

Keep responses concise and focused on molecule generation.`,

  docking: `You are a helpful assistant for the Molecular Docking step in a drug discovery workflow.
You can help users:
- Understand docking scores and confidence values
- Interpret binding poses and interactions
- Explain what makes a good docking result
- Compare docking results across molecules
- Suggest which molecules look most promising

DiffDock returns:
- Confidence scores (0-1): Higher is better binding prediction
- Multiple poses per ligand: Different binding orientations
- Position confidence: Raw score from the model

Keep responses concise and focused on docking analysis.`,

  rediscovery: `You are a helpful assistant for the Drug Rediscovery step in a drug discovery workflow.
You can help users:
- Understand Tanimoto similarity scores
- Interpret how close generated molecules are to known drugs
- Explain what "rediscovery" means in this context
- Analyze scaffold similarity vs. exact matches

Similarity interpretation:
- >0.85: Very high similarity (near-identical)
- 0.7-0.85: High similarity (same scaffold)
- 0.5-0.7: Moderate similarity
- <0.5: Low similarity (different scaffold)

Keep responses concise and focused on similarity analysis.`,

  'protein-design': `You are a helpful assistant for the Protein Design step using RFDiffusion.
You can help users:
- Understand RFDiffusion parameters
- Explain different design modes (unconditional, binder, scaffold)
- Interpret designed backbone structures
- Suggest parameters for specific design goals

Design modes:
- Unconditional: Generate novel protein folds from scratch
- Binder: Design proteins that bind to a target
- Scaffold: Generate specific topology/geometry

Keep responses concise and focused on protein design.`,

  'sequence-design': `You are a helpful assistant for the Sequence Design step using ProteinMPNN.
You can help users:
- Understand ProteinMPNN parameters
- Interpret designed sequences and their scores
- Explain temperature effects on diversity
- Compare multiple sequence designs

Parameters:
- num_sequences: How many sequences to design
- temperature: Sampling temperature (higher = more diverse)
- fixed_positions: Residues to keep unchanged

Keep responses concise and focused on sequence design.`,

  validation: `You are a helpful assistant for the Validation step in protein design.
You can help users:
- Compare designed structure to predicted structure
- Interpret validation metrics (RMSD, pLDDT)
- Assess if the designed protein will fold correctly
- Suggest next steps based on validation results

Good validation signs:
- High pLDDT (>70): Confident structure prediction
- Low RMSD: Designed and predicted structures match
- Consistent secondary structure

Keep responses concise and focused on validation analysis.`,
};

// Quick suggestions for each step
const QUICK_SUGGESTIONS: Record<StepType, string[]> = {
  sequence: [
    'What does this protein do?',
    'Are there other isoforms?',
    'What domains does it have?',
  ],
  structure: [
    'Which model should I use?',
    'What do the confidence scores mean?',
    'Is this a good prediction?',
  ],
  molecules: [
    'How diverse are these molecules?',
    'Which ones look most drug-like?',
    'Explain the QED scores',
  ],
  docking: [
    'Which molecule binds best?',
    'What do the poses show?',
    'Are these good docking scores?',
  ],
  rediscovery: [
    'Did we rediscover the drug?',
    'What makes molecules similar?',
    'Which is the best candidate?',
  ],
  'protein-design': [
    'What parameters should I use?',
    'Explain the design modes',
    'Is this backbone realistic?',
  ],
  'sequence-design': [
    'Which sequence is best?',
    'What does temperature do?',
    'Are these sequences diverse?',
  ],
  validation: [
    'Will this protein fold?',
    'Is the RMSD acceptable?',
    'What should I do next?',
  ],
};

function generateId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

export function StepAssistant({
  stepType,
  gatewayUrl,
  context,
  onParameterSuggestion,
}: StepAssistantProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (isExpanded) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isExpanded]);

  const handleSendMessage = useCallback(async (content: string) => {
    if (!content.trim() || isProcessing) return;
    if (!gatewayUrl) return;

    // Add user message
    const userMsg: Message = {
      id: generateId(),
      role: 'user',
      content,
    };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsProcessing(true);

    // Build context string
    const contextStr = Object.entries(context)
      .filter(([_, v]) => v !== null && v !== undefined)
      .map(([k, v]) => {
        if (typeof v === 'string' && v.length > 500) {
          return `${k}: [${v.length} characters]`;
        }
        if (typeof v === 'object') {
          return `${k}: ${JSON.stringify(v).slice(0, 200)}...`;
        }
        return `${k}: ${v}`;
      })
      .join('\n');

    const systemPrompt = `${STEP_PROMPTS[stepType]}

Current context:
${contextStr}

If the user asks about modifying parameters, respond with a JSON block like:
\`\`\`json
{"suggest_params": {"param_name": "value"}}
\`\`\``;

    // Create assistant message for streaming
    const assistantMsgId = generateId();
    const assistantMsg: Message = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      isStreaming: true,
    };
    setMessages(prev => [...prev, assistantMsg]);

    try {
      const chatMessages = [
        { role: 'system' as const, content: systemPrompt },
        ...messages.map(m => ({ role: m.role as 'user' | 'assistant', content: m.content })),
        { role: 'user' as const, content },
      ];

      let fullResponse = '';
      for await (const chunk of streamChat(gatewayUrl, chatMessages, { maxTokens: 500 })) {
        fullResponse += chunk;
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantMsgId ? { ...m, content: fullResponse } : m
          )
        );
      }

      // Check for parameter suggestions
      const paramMatch = fullResponse.match(/```json\s*(\{[\s\S]*?"suggest_params"[\s\S]*?\})\s*```/);
      if (paramMatch && onParameterSuggestion) {
        try {
          const parsed = JSON.parse(paramMatch[1]);
          if (parsed.suggest_params) {
            onParameterSuggestion(parsed.suggest_params);
          }
        } catch {
          // Ignore parse errors
        }
      }

      // Update final state
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantMsgId ? { ...m, isStreaming: false } : m
        )
      );
    } catch (error) {
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantMsgId
            ? { ...m, content: 'Sorry, I encountered an error. Please try again.', isStreaming: false }
            : m
        )
      );
    } finally {
      setIsProcessing(false);
    }
  }, [gatewayUrl, context, stepType, messages, isProcessing, onParameterSuggestion]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(inputValue);
    }
  }, [inputValue, handleSendMessage]);

  const quickSuggestions = QUICK_SUGGESTIONS[stepType];

  return (
    <div className={`step-assistant ${isExpanded ? 'expanded' : 'collapsed'}`}>
      {/* Toggle Button */}
      <button
        className="step-assistant-toggle"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-label={isExpanded ? 'Collapse assistant' : 'Expand assistant'}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M8 2l6 4v4l-6 4-6-4V6l6-4z" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="8" cy="8" r="2" fill="currentColor" />
        </svg>
        <span>AI Assistant</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          className={`chevron ${isExpanded ? 'up' : 'down'}`}
        >
          <path d="M3 4.5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="step-assistant-content">
          {/* Messages */}
          <div className="step-assistant-messages">
            {messages.length === 0 ? (
              <div className="step-assistant-welcome">
                <p>Ask me about this step or the results.</p>
                <div className="step-assistant-suggestions">
                  {quickSuggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      className="suggestion-chip"
                      onClick={() => handleSendMessage(suggestion)}
                      disabled={isProcessing || !gatewayUrl}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((msg) => (
                  <div key={msg.id} className={`step-assistant-message ${msg.role}`}>
                    <div className="message-content">
                      {msg.role === 'assistant' ? (
                        <>
                          <Markdown>{msg.content || 'Thinking...'}</Markdown>
                          {msg.isStreaming && <span className="typing-cursor" />}
                        </>
                      ) : (
                        <p>{msg.content}</p>
                      )}
                    </div>
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Input */}
          <div className="step-assistant-input-area">
            <input
              type="text"
              className="step-assistant-input"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about this step..."
              disabled={isProcessing || !gatewayUrl}
            />
            <button
              className="step-assistant-send"
              onClick={() => handleSendMessage(inputValue)}
              disabled={!inputValue.trim() || isProcessing || !gatewayUrl}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M12 2L6 8M12 2l-4 10-2-4-4-2 10-4z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
