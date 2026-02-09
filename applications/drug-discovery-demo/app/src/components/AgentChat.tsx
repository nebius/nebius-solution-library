// Agent Chat Component
// Dynamic conversational interface for the drug discovery agent

import { useState, useCallback, useRef, useEffect } from 'react';
import Markdown from 'react-markdown';
import {
  runAgent,
  type AgentMessage,
  type AgentResults,
  type AgentRunnerCallbacks,
} from '../services/agent';
import { StructureViewer } from './StructureViewer';
import type { DrugTarget } from '../data/drugs';

// Prepared prompts for common tasks
const PREPARED_PROMPTS = [
  {
    category: 'Structure Prediction',
    icon: 'structure',
    prompts: [
      {
        title: 'Predict COX-2 structure',
        description: 'Run OpenFold3 for P35354 (COX-2)',
        prompt: 'Run OpenFold3 for P35354. Give me all metrics from the result including pLDDT, pTM, and confidence scores.',
      },
      {
        title: 'Compare structure models',
        description: 'Run multiple models and compare results',
        prompt: 'Predict the structure of P35354 (COX-2) using both OpenFold3 and Boltz2. Compare the confidence scores and show me both structures.',
      },
    ],
  },
  {
    category: 'Small Molecule Discovery',
    icon: 'pill',
    prompts: [
      {
        title: 'Discover COX-2 inhibitors',
        description: 'Find drug candidates similar to Celebrex for inflammation',
        prompt: 'I want to discover drugs targeting COX-2 (cyclooxygenase-2) similar to Celecoxib. Help me find and validate potential inhibitors.',
      },
      {
        title: 'Optimize a lead compound',
        description: 'Generate analogs of an existing molecule',
        prompt: 'I have a lead compound and want to optimize it. Help me generate analogs with potentially improved properties.',
      },
      {
        title: 'Target-based drug discovery',
        description: 'Find drugs for a specific protein target',
        prompt: 'I want to find drug candidates for a specific protein target. Help me with the full workflow from target identification to docking validation.',
      },
    ],
  },
  {
    category: 'Protein Design',
    icon: 'protein',
    prompts: [
      {
        title: 'Design a novel protein',
        description: 'Create a new protein fold from scratch',
        prompt: 'I want to design a novel protein structure from scratch. Help me generate a new protein backbone and design a sequence that folds into it.',
      },
      {
        title: 'Design a protein binder',
        description: 'Create a protein that binds to a target',
        prompt: 'I want to design a protein binder that can bind to a specific target protein. Help me through the binder design workflow.',
      },
      {
        title: 'Validate protein folding',
        description: 'Check if a designed sequence folds correctly',
        prompt: 'I have a designed protein sequence and want to validate that it folds into the intended structure. Help me run structure prediction and analysis.',
      },
    ],
  },
  {
    category: 'Structure Analysis',
    icon: 'structure',
    prompts: [
      {
        title: 'Predict protein structure',
        description: 'Get 3D structure from sequence',
        prompt: 'I have a protein sequence and want to predict its 3D structure. Help me choose the best model and analyze the results.',
      },
      {
        title: 'Analyze binding site',
        description: 'Study protein-ligand interactions',
        prompt: 'I want to analyze the binding site of a protein and understand how small molecules interact with it.',
      },
    ],
  },
];

interface AgentChatProps {
  gatewayUrl: string;
  selectedDrug: DrugTarget | null;
  onBack: () => void;
}

export function AgentChat({ gatewayUrl, selectedDrug, onBack }: AgentChatProps) {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [results, setResults] = useState<AgentResults>({});
  const [inputValue, setInputValue] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<{
    question: string;
    options?: string[];
  } | null>(null);
  const [activeResultTab, setActiveResultTab] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const autoStartedRef = useRef<string | null>(null); // Track which drug we auto-started for
  const previousDrugIdRef = useRef<string | null>(null); // Track previous drug to detect changes

  // Reset state when drug changes
  useEffect(() => {
    const currentDrugId = selectedDrug?.id || null;
    if (previousDrugIdRef.current !== currentDrugId) {
      // Drug changed - reset everything
      setMessages([]);
      setResults({});
      setInputValue('');
      setIsProcessing(false);
      setIsComplete(false);
      setSummary(null);
      setPendingQuestion(null);
      setActiveResultTab(null);
      autoStartedRef.current = null;
      previousDrugIdRef.current = currentDrugId;
    }
  }, [selectedDrug?.id]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleStreamChunk = useCallback((messageId: string, content: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === messageId ? { ...m, content } : m
      )
    );
  }, []);

  const handleSendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || !gatewayUrl || isProcessing) return;

      setIsProcessing(true);
      setPendingQuestion(null);

      const callbacks: AgentRunnerCallbacks = {
        onMessage: (message) => {
          setMessages((prev) => {
            const existing = prev.find((m) => m.id === message.id);
            if (existing) {
              return prev.map((m) => (m.id === message.id ? message : m));
            }
            return [...prev, message];
          });
        },
        onResultsUpdate: (newResults) => {
          setResults(newResults);
          // Auto-open result tabs
          if (newResults.structure && !activeResultTab) {
            setActiveResultTab('structure');
          } else if (newResults.molecules && !activeResultTab) {
            setActiveResultTab('molecules');
          } else if (newResults.dockingResults && !activeResultTab) {
            setActiveResultTab('docking');
          }
        },
        onStreamChunk: handleStreamChunk,
        onComplete: (completionSummary) => {
          setIsComplete(true);
          setSummary(completionSummary);
          setIsProcessing(false);
        },
        onQuestion: (question, options) => {
          setPendingQuestion({ question, options });
          setIsProcessing(false);
        },
      };

      try {
        await runAgent(gatewayUrl, content, messages, results, callbacks, false, selectedDrug);
      } catch (error) {
        console.error('Agent error:', error);
        setMessages((prev) => [
          ...prev,
          {
            id: `error_${Date.now()}`,
            role: 'assistant',
            content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
            timestamp: Date.now(),
          },
        ]);
      } finally {
        setIsProcessing(false);
      }
    },
    [gatewayUrl, isProcessing, messages, results, activeResultTab, handleStreamChunk, selectedDrug]
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      handleSendMessage(inputValue);
      setInputValue('');
    },
    [inputValue, handleSendMessage]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage(inputValue);
        setInputValue('');
      }
    },
    [inputValue, handleSendMessage]
  );

  const handleQuestionOption = useCallback(
    (option: string) => {
      handleSendMessage(option);
    },
    [handleSendMessage]
  );

  // Handle clicking a prepared prompt
  const handlePreparedPrompt = useCallback((prompt: string) => {
    handleSendMessage(prompt);
  }, [handleSendMessage]);

  // Auto-start with the drug discovery prompt when a drug is selected
  // Use refs to prevent re-running and avoid dependency on handleSendMessage
  useEffect(() => {
    // Only auto-start if:
    // 1. There's a selected drug that's not custom
    // 2. We haven't already auto-started for this drug
    // 3. There are no messages yet
    // 4. We have a gateway URL
    if (
      selectedDrug &&
      !selectedDrug.isCustom &&
      autoStartedRef.current !== selectedDrug.id &&
      messages.length === 0 &&
      gatewayUrl
    ) {
      autoStartedRef.current = selectedDrug.id;
      // Oligomeric state is now auto-detected from drugTarget in executeTool
      const initialPrompt = `I want to discover a drug similar to ${selectedDrug.name}. ${selectedDrug.description}\n\nTarget: ${selectedDrug.targetProtein.name}\nMechanism: ${selectedDrug.mechanism}`;
      // Use setTimeout to avoid calling during render
      setTimeout(() => {
        handleSendMessage(initialPrompt);
      }, 100);
    }
  }, [selectedDrug, gatewayUrl]); // Deliberately exclude handleSendMessage and messages.length to prevent loops

  // Determine which result tabs to show
  const availableTabs = [];
  if (results.protein) availableTabs.push({ id: 'protein', label: 'Protein Info' });
  if (results.structure) availableTabs.push({ id: 'structure', label: '3D Structure' });
  if (results.molecules) availableTabs.push({ id: 'molecules', label: `Molecules (${results.molecules.length})` });
  if (results.dockingResults) availableTabs.push({ id: 'docking', label: 'Docking Results' });
  if (results.similarityScores) availableTabs.push({ id: 'similarity', label: 'Similarity' });

  return (
    <div className="agent-chat-container">
      {/* Header */}
      <div className="agent-chat-header">
        <button className="btn btn-ghost" onClick={onBack}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path
              d="M12.5 15l-5-5 5-5"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Back
        </button>
        <div className="agent-chat-title">
          <h2>AI Drug Discovery Agent</h2>
          <span className="agent-chat-subtitle">
            {selectedDrug ? `Working on: ${selectedDrug.name}` : 'Dynamic Workflow'}
          </span>
        </div>
        {isProcessing && (
          <div className="agent-status">
            <span className="spinner spinner-sm" />
            <span>Agent thinking...</span>
          </div>
        )}
      </div>

      <div className="agent-chat-main">
        {/* Messages Panel */}
        <div className="agent-messages-panel">
          <div className="agent-messages">
            {/* Show prepared prompts when no conversation has started */}
            {messages.length === 0 && !selectedDrug && (
              <div className="agent-welcome">
                <div className="agent-welcome-header">
                  <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                    <path d="M16 4l12 8v8l-12 8-12-8V12l12-8z" stroke="currentColor" strokeWidth="2" />
                    <circle cx="16" cy="16" r="4" fill="currentColor" />
                  </svg>
                  <h3>AI Drug Discovery Agent</h3>
                  <p>I can help you with drug discovery, protein design, and structure analysis. Choose a task below or describe what you want to accomplish.</p>
                </div>
                <div className="prepared-prompts">
                  {PREPARED_PROMPTS.map((category) => (
                    <div key={category.category} className="prompt-category">
                      <h4 className="prompt-category-title">{category.category}</h4>
                      <div className="prompt-cards">
                        {category.prompts.map((item) => (
                          <button
                            key={item.title}
                            className="prompt-card"
                            onClick={() => handlePreparedPrompt(item.prompt)}
                            disabled={isProcessing || !gatewayUrl}
                          >
                            <span className="prompt-card-title">{item.title}</span>
                            <span className="prompt-card-description">{item.description}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {messages.filter(m => !m.isInternal).map((message) => (
              <div
                key={message.id}
                className={`agent-message agent-message-${message.role}`}
              >
                {message.role === 'user' && (
                  <div className="agent-message-avatar user">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <circle cx="8" cy="5" r="3" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M2 14c0-3 2.5-5 6-5s6 2 6 5" stroke="currentColor" strokeWidth="1.5" />
                    </svg>
                  </div>
                )}
                {message.role === 'assistant' && (
                  <div className="agent-message-avatar assistant">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M8 2l6 4v4l-6 4-6-4V6l6-4z" stroke="currentColor" strokeWidth="1.5" />
                      <circle cx="8" cy="8" r="2" fill="currentColor" />
                    </svg>
                  </div>
                )}
                {message.role === 'tool_result' && (
                  <div className="agent-message-avatar tool">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M4 8l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                )}

                <div className="agent-message-content">
                  {message.role === 'assistant' ? (
                    <>
                      <Markdown>{message.content}</Markdown>
                      {message.toolCall && (
                        <div className="agent-tool-call">
                          <span className="tool-call-badge">
                            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                              <path d="M6 2v4l2 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                              <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.5" />
                            </svg>
                            Calling: {message.toolCall.tool}
                          </span>
                        </div>
                      )}
                      {message.isStreaming && <span className="typing-cursor" />}
                    </>
                  ) : message.role === 'tool_result' ? (
                    <div className="tool-result-message">
                      <span className={`tool-result-status ${message.toolResult?.success ? 'success' : 'error'}`}>
                        {message.toolResult?.success ? (
                          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                            <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        ) : (
                          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                            <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                          </svg>
                        )}
                      </span>
                      {message.content}
                    </div>
                  ) : (
                    <p>{message.content}</p>
                  )}
                </div>
              </div>
            ))}

            {/* Pending Question */}
            {pendingQuestion && (
              <div className="agent-question-panel">
                <p className="agent-question-text">{pendingQuestion.question}</p>
                {pendingQuestion.options && (
                  <div className="agent-question-options">
                    {pendingQuestion.options.map((option) => (
                      <button
                        key={option}
                        className="btn btn-outline"
                        onClick={() => handleQuestionOption(option)}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Completion Summary */}
            {isComplete && summary && (
              <div className="agent-completion">
                <div className="agent-completion-header">
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <circle cx="10" cy="10" r="8" fill="var(--color-lime)" />
                    <path d="M6 10l3 3 5-5" stroke="var(--color-deep-blue)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>Task Complete</span>
                </div>
                <Markdown>{summary}</Markdown>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <form className="agent-input-area" onSubmit={handleSubmit}>
            <textarea
              ref={inputRef}
              className="agent-input"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={pendingQuestion ? 'Type your answer or select an option above...' : 'Ask the agent or provide instructions...'}
              disabled={isProcessing}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!inputValue.trim() || isProcessing}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M14 2L7 9M14 2l-5 12-2-5-5-2 12-5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </form>
        </div>

        {/* Results Panel */}
        {availableTabs.length > 0 && (
          <div className="agent-results-panel">
            <div className="agent-results-tabs">
              {availableTabs.map((tab) => (
                <button
                  key={tab.id}
                  className={`agent-results-tab ${activeResultTab === tab.id ? 'active' : ''}`}
                  onClick={() => setActiveResultTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="agent-results-content">
              {activeResultTab === 'protein' && results.protein && (
                <div className="agent-result-protein">
                  <h4>{results.protein.name}</h4>
                  <p className="protein-accession">{results.protein.accession}</p>
                  <p className="protein-organism">{results.protein.organism}</p>
                  <div className="protein-sequence-preview">
                    <code>{results.protein.sequence.slice(0, 100)}...</code>
                    <span className="sequence-length">{results.protein.sequence.length} residues</span>
                  </div>
                </div>
              )}

              {activeResultTab === 'structure' && results.structure && (
                <div className="agent-result-structure">
                  <StructureViewer
                    structure={results.structure.structure}
                    format={results.structure.format}
                    height={400}
                    colorScheme="confidence"
                  />
                  <div className="structure-scores">
                    <div className="structure-score">
                      <span className="score-label">Confidence</span>
                      <span className="score-value">{(results.structure.confidenceScore * 100).toFixed(1)}%</span>
                    </div>
                    <div className="structure-score">
                      <span className="score-label">pLDDT</span>
                      <span className="score-value">{results.structure.plddt.toFixed(1)}</span>
                    </div>
                    <div className="structure-score">
                      <span className="score-label">Model</span>
                      <span className="score-value">{results.structure.modelUsed}</span>
                    </div>
                  </div>
                </div>
              )}

              {activeResultTab === 'molecules' && results.molecules && (
                <div className="agent-result-molecules">
                  <div className="molecules-mini-grid">
                    {results.molecules.slice(0, 20).map((mol, i) => (
                      <div key={i} className="molecule-mini-card">
                        <span className="molecule-mini-rank">#{i + 1}</span>
                        <code className="molecule-mini-smiles">{mol.smiles.slice(0, 30)}...</code>
                        <span className="molecule-mini-score">{mol.score.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                  {results.molecules.length > 20 && (
                    <p className="molecules-more">+{results.molecules.length - 20} more molecules</p>
                  )}
                </div>
              )}

              {activeResultTab === 'docking' && results.dockingResults && (
                <div className="agent-result-docking">
                  {results.dockingResults.map((result, i) => (
                    <div key={i} className="docking-result-mini">
                      <span className="docking-rank">#{i + 1}</span>
                      <code className="docking-smiles">{result.ligandSmiles.slice(0, 25)}...</code>
                      <span className="docking-confidence">{(result.bestConfidence * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              )}

              {activeResultTab === 'similarity' && results.similarityScores && (
                <div className="agent-result-similarity">
                  {results.similarityScores.map((item, i) => (
                    <div key={i} className="similarity-item">
                      <code className="similarity-smiles">{item.smiles.slice(0, 30)}...</code>
                      <span className={`similarity-score ${item.similarity > 0.7 ? 'high' : item.similarity > 0.4 ? 'medium' : 'low'}`}>
                        {(item.similarity * 100).toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
