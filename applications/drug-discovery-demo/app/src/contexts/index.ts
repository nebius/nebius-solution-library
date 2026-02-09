/**
 * Contexts Index
 *
 * Central export point for all React context providers and hooks.
 */

// Gateway context - connection settings
export {
  GatewayProvider,
  useGateway,
  useGatewayUrl,
  useIsConnected,
  type GatewayContextValue,
  type GatewayProviderProps,
} from './GatewayContext';

// Workflow context - navigation and state
export {
  WorkflowProvider,
  useWorkflow,
  useSelectedDrug,
  useWorkflowNavigation,
  type WorkflowMode,
  type WorkflowContextValue,
  type WorkflowProviderProps,
} from './WorkflowContext';

// Workflow data context - results storage
export {
  WorkflowDataProvider,
  useWorkflowData,
  useProteinInfo,
  useStructureResult,
  useMolecules,
  useDockingResults,
  type ProteinInfo,
  type ProteinDesignResult,
  type SequenceDesignResult,
  type ValidationResult,
  type WorkflowDataContextValue,
  type WorkflowDataProviderProps,
} from './WorkflowDataContext';

// Combined provider
export { AppProvider, type AppProviderProps } from './AppProvider';
