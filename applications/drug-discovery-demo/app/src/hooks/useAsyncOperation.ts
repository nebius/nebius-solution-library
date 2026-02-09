/**
 * useAsyncOperation Hook
 *
 * A reusable hook for managing async operations with loading, error, and result states.
 * Commonly used in step components for API calls like structure prediction, molecule generation, etc.
 *
 * Features:
 * - Tracks processing/loading state
 * - Stores operation result
 * - Captures and stores errors
 * - Provides reset functionality
 * - Tracks elapsed time
 *
 * @example
 * ```tsx
 * const { isProcessing, result, error, elapsedTime, execute, reset } = useAsyncOperation<StructurePredictionResult>();
 *
 * const handlePredict = async () => {
 *   await execute(async () => {
 *     return await predictStructure(gatewayUrl, sequence, model);
 *   });
 * };
 * ```
 */

import { useState, useCallback, useRef, useEffect } from 'react';

export interface AsyncOperationState<T> {
  isProcessing: boolean;
  result: T | null;
  error: string | null;
  elapsedTime: number;
}

export interface AsyncOperationActions<T> {
  execute: (fn: () => Promise<T>) => Promise<T | null>;
  reset: () => void;
  setResult: (result: T | null) => void;
  setError: (error: string | null) => void;
}

export type UseAsyncOperationReturn<T> = AsyncOperationState<T> & AsyncOperationActions<T>;

export function useAsyncOperation<T>(): UseAsyncOperationReturn<T> {
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsedTime, setElapsedTime] = useState(0);

  const startTimeRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Clear timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  const execute = useCallback(async (fn: () => Promise<T>): Promise<T | null> => {
    setIsProcessing(true);
    setError(null);
    setElapsedTime(0);
    startTimeRef.current = Date.now();

    // Start elapsed time timer
    timerRef.current = setInterval(() => {
      setElapsedTime(Date.now() - startTimeRef.current);
    }, 100);

    try {
      const operationResult = await fn();
      setResult(operationResult);
      return operationResult;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Operation failed';
      setError(message);
      return null;
    } finally {
      setIsProcessing(false);
      setElapsedTime(Date.now() - startTimeRef.current);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  }, []);

  const reset = useCallback(() => {
    setIsProcessing(false);
    setResult(null);
    setError(null);
    setElapsedTime(0);
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  return {
    isProcessing,
    result,
    error,
    elapsedTime,
    execute,
    reset,
    setResult,
    setError,
  };
}

/**
 * useAsyncOperationWithProgress Hook
 *
 * Extended version with progress tracking for multi-step operations.
 *
 * @example
 * ```tsx
 * const { isProcessing, progress, execute } = useAsyncOperationWithProgress<DockingResult[]>();
 *
 * await execute(async (updateProgress) => {
 *   for (let i = 0; i < molecules.length; i++) {
 *     await dockMolecule(molecules[i]);
 *     updateProgress(i + 1, molecules.length);
 *   }
 *   return results;
 * });
 * ```
 */

export interface ProgressInfo {
  completed: number;
  total: number;
  percentage: number;
}

export interface AsyncOperationWithProgressState<T> extends AsyncOperationState<T> {
  progress: ProgressInfo;
}

export interface AsyncOperationWithProgressActions<T> {
  execute: (fn: (updateProgress: (completed: number, total: number) => void) => Promise<T>) => Promise<T | null>;
  reset: () => void;
}

export type UseAsyncOperationWithProgressReturn<T> = AsyncOperationWithProgressState<T> & AsyncOperationWithProgressActions<T>;

export function useAsyncOperationWithProgress<T>(): UseAsyncOperationWithProgressReturn<T> {
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [progress, setProgress] = useState<ProgressInfo>({ completed: 0, total: 0, percentage: 0 });

  const startTimeRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  const execute = useCallback(async (
    fn: (updateProgress: (completed: number, total: number) => void) => Promise<T>
  ): Promise<T | null> => {
    setIsProcessing(true);
    setError(null);
    setElapsedTime(0);
    setProgress({ completed: 0, total: 0, percentage: 0 });
    startTimeRef.current = Date.now();

    timerRef.current = setInterval(() => {
      setElapsedTime(Date.now() - startTimeRef.current);
    }, 100);

    const updateProgress = (completed: number, total: number) => {
      setProgress({
        completed,
        total,
        percentage: total > 0 ? (completed / total) * 100 : 0,
      });
    };

    try {
      const operationResult = await fn(updateProgress);
      setResult(operationResult);
      return operationResult;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Operation failed';
      setError(message);
      return null;
    } finally {
      setIsProcessing(false);
      setElapsedTime(Date.now() - startTimeRef.current);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  }, []);

  const reset = useCallback(() => {
    setIsProcessing(false);
    setResult(null);
    setError(null);
    setElapsedTime(0);
    setProgress({ completed: 0, total: 0, percentage: 0 });
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  return {
    isProcessing,
    result,
    error,
    elapsedTime,
    progress,
    execute,
    reset,
  };
}
