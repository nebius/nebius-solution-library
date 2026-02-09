/**
 * useSelectionToggle Hook
 *
 * A reusable hook for managing selection state across lists of items.
 * Used in step components for selecting molecules, models, or results.
 *
 * Features:
 * - Toggle individual items on/off
 * - Select all items
 * - Clear all selections
 * - Select top N items
 * - Get selected items directly
 *
 * @example
 * ```tsx
 * const molecules = [...];
 * const { selected, toggle, selectAll, selectNone, selectTop, getSelectedItems } = useSelectionToggle(molecules.length);
 *
 * // Toggle single item
 * <div onClick={() => toggle(index)} className={selected.has(index) ? 'selected' : ''}>
 *
 * // Bulk selection buttons
 * <button onClick={selectAll}>Select All</button>
 * <button onClick={() => selectTop(10)}>Top 10</button>
 * <button onClick={selectNone}>Clear</button>
 *
 * // Get selected items
 * const selectedMolecules = getSelectedItems(molecules);
 * ```
 */

import { useState, useCallback, useMemo } from 'react';

export interface SelectionToggleState {
  selected: Set<number>;
  selectedCount: number;
}

export interface SelectionToggleActions<T = unknown> {
  toggle: (index: number) => void;
  select: (index: number) => void;
  deselect: (index: number) => void;
  selectAll: () => void;
  selectNone: () => void;
  selectTop: (n: number) => void;
  selectIndices: (indices: number[]) => void;
  setSelected: (indices: Set<number> | number[]) => void;
  isSelected: (index: number) => boolean;
  getSelectedItems: <I extends T>(items: I[]) => I[];
  getSelectedIndices: () => number[];
}

export type UseSelectionToggleReturn<T = unknown> = SelectionToggleState & SelectionToggleActions<T>;

/**
 * Hook for managing selection state
 *
 * @param totalItems - Total number of items that can be selected
 * @param initialSelected - Optional initial selection (array of indices or Set)
 */
export function useSelectionToggle<T = unknown>(
  totalItems: number,
  initialSelected?: number[] | Set<number>
): UseSelectionToggleReturn<T> {
  const [selected, setSelectedState] = useState<Set<number>>(() => {
    if (initialSelected instanceof Set) {
      return initialSelected;
    }
    if (Array.isArray(initialSelected)) {
      return new Set(initialSelected);
    }
    return new Set();
  });

  const selectedCount = useMemo(() => selected.size, [selected]);

  const toggle = useCallback((index: number) => {
    setSelectedState((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }, []);

  const select = useCallback((index: number) => {
    setSelectedState((prev) => {
      if (prev.has(index)) return prev;
      const next = new Set(prev);
      next.add(index);
      return next;
    });
  }, []);

  const deselect = useCallback((index: number) => {
    setSelectedState((prev) => {
      if (!prev.has(index)) return prev;
      const next = new Set(prev);
      next.delete(index);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedState(new Set(Array.from({ length: totalItems }, (_, i) => i)));
  }, [totalItems]);

  const selectNone = useCallback(() => {
    setSelectedState(new Set());
  }, []);

  const selectTop = useCallback((n: number) => {
    setSelectedState(new Set(Array.from({ length: Math.min(n, totalItems) }, (_, i) => i)));
  }, [totalItems]);

  const selectIndices = useCallback((indices: number[]) => {
    setSelectedState((prev) => {
      const next = new Set(prev);
      indices.forEach((i) => {
        if (i >= 0 && i < totalItems) {
          next.add(i);
        }
      });
      return next;
    });
  }, [totalItems]);

  const setSelected = useCallback((indices: Set<number> | number[]) => {
    if (indices instanceof Set) {
      setSelectedState(indices);
    } else {
      setSelectedState(new Set(indices));
    }
  }, []);

  const isSelected = useCallback((index: number) => selected.has(index), [selected]);

  const getSelectedItems = useCallback(<I extends T>(items: I[]): I[] => {
    return items.filter((_, i) => selected.has(i));
  }, [selected]);

  const getSelectedIndices = useCallback(() => Array.from(selected).sort((a, b) => a - b), [selected]);

  return {
    selected,
    selectedCount,
    toggle,
    select,
    deselect,
    selectAll,
    selectNone,
    selectTop,
    selectIndices,
    setSelected,
    isSelected,
    getSelectedItems,
    getSelectedIndices,
  };
}

/**
 * useSelectionToggleWithFilter Hook
 *
 * Extended version that supports filtering selected items by a predicate.
 * Useful when you need to auto-select items matching certain criteria.
 *
 * @example
 * ```tsx
 * const { selected, selectWhere } = useSelectionToggleWithFilter(molecules);
 *
 * // Select all molecules with QED > 0.7
 * selectWhere((mol) => mol.score > 0.7);
 * ```
 */

export interface SelectionToggleWithFilterActions<T> extends SelectionToggleActions<T> {
  selectWhere: (predicate: (item: T, index: number) => boolean) => void;
}

export type UseSelectionToggleWithFilterReturn<T> = SelectionToggleState & SelectionToggleWithFilterActions<T>;

export function useSelectionToggleWithFilter<T>(
  items: T[],
  initialSelected?: number[] | Set<number>
): UseSelectionToggleWithFilterReturn<T> {
  const baseHook = useSelectionToggle<T>(items.length, initialSelected);

  const selectWhere = useCallback((predicate: (item: T, index: number) => boolean) => {
    const indices = items
      .map((item, index) => (predicate(item, index) ? index : -1))
      .filter((i) => i !== -1);
    baseHook.setSelected(new Set(indices));
  }, [items, baseHook]);

  return {
    ...baseHook,
    selectWhere,
  };
}
