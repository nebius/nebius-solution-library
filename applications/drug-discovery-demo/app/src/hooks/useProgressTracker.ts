import { useState, useCallback, useRef, useMemo } from 'react';

interface ProgressState {
  completed: number;
  total: number;
  startTime: number | null;
  completionTimes: number[]; // Time taken for each completed item
}

interface ProgressInfo {
  completed: number;
  total: number;
  percentage: number;
  elapsedMs: number;
  etaMs: number | null;
  avgTimePerItem: number | null;
  isRunning: boolean;
}

export function useProgressTracker() {
  const [state, setState] = useState<ProgressState>({
    completed: 0,
    total: 0,
    startTime: null,
    completionTimes: [],
  });

  const lastCompletionTime = useRef<number | null>(null);

  const start = useCallback((total: number) => {
    const now = Date.now();
    setState({
      completed: 0,
      total,
      startTime: now,
      completionTimes: [],
    });
    lastCompletionTime.current = now;
  }, []);

  const recordCompletion = useCallback(() => {
    const now = Date.now();
    setState((prev) => {
      const timeSinceLast = lastCompletionTime.current
        ? now - lastCompletionTime.current
        : prev.startTime
          ? now - prev.startTime
          : 0;

      lastCompletionTime.current = now;

      return {
        ...prev,
        completed: prev.completed + 1,
        completionTimes: [...prev.completionTimes, timeSinceLast],
      };
    });
  }, []);

  const setProgress = useCallback((completed: number, total?: number) => {
    const now = Date.now();
    setState((prev) => {
      // Calculate time for all new completions
      const newCompletions = completed - prev.completed;
      const timeSinceStart = prev.startTime ? now - prev.startTime : 0;
      const avgTime = completed > 0 ? timeSinceStart / completed : 0;

      // Update completion times array
      const newCompletionTimes = [...prev.completionTimes];
      for (let i = 0; i < newCompletions; i++) {
        newCompletionTimes.push(avgTime);
      }

      lastCompletionTime.current = now;

      return {
        ...prev,
        completed,
        total: total ?? prev.total,
        completionTimes: newCompletionTimes,
      };
    });
  }, []);

  const reset = useCallback(() => {
    setState({
      completed: 0,
      total: 0,
      startTime: null,
      completionTimes: [],
    });
    lastCompletionTime.current = null;
  }, []);

  const info = useMemo((): ProgressInfo => {
    const { completed, total, startTime, completionTimes } = state;
    const now = Date.now();
    const elapsedMs = startTime ? now - startTime : 0;
    const percentage = total > 0 ? (completed / total) * 100 : 0;
    const isRunning = startTime !== null && completed < total;

    // Calculate average time per item
    let avgTimePerItem: number | null = null;
    if (completionTimes.length > 0) {
      avgTimePerItem = completionTimes.reduce((a, b) => a + b, 0) / completionTimes.length;
    } else if (completed > 0 && elapsedMs > 0) {
      avgTimePerItem = elapsedMs / completed;
    }

    // Calculate ETA
    let etaMs: number | null = null;
    if (avgTimePerItem !== null && completed < total) {
      const remaining = total - completed;
      etaMs = avgTimePerItem * remaining;
    }

    return {
      completed,
      total,
      percentage,
      elapsedMs,
      etaMs,
      avgTimePerItem,
      isRunning,
    };
  }, [state]);

  return {
    start,
    recordCompletion,
    setProgress,
    reset,
    info,
  };
}

// Utility to format time for display
export function formatDuration(ms: number | null): string {
  if (ms === null || ms < 0) return '-';
  if (ms < 1000) return '<1s';

  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    const remainingMinutes = minutes % 60;
    return `${hours}h ${remainingMinutes}m`;
  }
  if (minutes > 0) {
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  }
  return `${seconds}s`;
}

// Utility to format ETA specifically
export function formatEta(ms: number | null): string {
  if (ms === null || ms < 0) return 'calculating...';
  if (ms < 1000) return '<1s remaining';

  const seconds = Math.ceil(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    const remainingMinutes = minutes % 60;
    return `~${hours}h ${remainingMinutes}m remaining`;
  }
  if (minutes > 0) {
    const remainingSeconds = seconds % 60;
    return `~${minutes}m ${remainingSeconds}s remaining`;
  }
  return `~${seconds}s remaining`;
}
