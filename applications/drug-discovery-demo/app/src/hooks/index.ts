/**
 * Hooks Index
 *
 * Central export point for all custom hooks.
 */

// Progress tracking
export { useProgressTracker, formatDuration, formatEta } from './useProgressTracker';

// Async operations
export {
  useAsyncOperation,
  useAsyncOperationWithProgress,
  type AsyncOperationState,
  type AsyncOperationActions,
  type UseAsyncOperationReturn,
  type ProgressInfo,
  type AsyncOperationWithProgressState,
  type AsyncOperationWithProgressActions,
  type UseAsyncOperationWithProgressReturn,
} from './useAsyncOperation';

// Selection management
export {
  useSelectionToggle,
  useSelectionToggleWithFilter,
  type SelectionToggleState,
  type SelectionToggleActions,
  type UseSelectionToggleReturn,
  type SelectionToggleWithFilterActions,
  type UseSelectionToggleWithFilterReturn,
} from './useSelectionToggle';
