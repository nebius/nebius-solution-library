/**
 * Formatting Utilities
 *
 * Common formatting functions used across the application.
 * These extract duplicated formatting logic from step components.
 */

/**
 * Format a duration in milliseconds to a human-readable string.
 *
 * @param ms - Duration in milliseconds (can be null/undefined)
 * @returns Formatted string like "1.5s", "2m 30s", "1h 15m"
 *
 * @example
 * formatDuration(500) // "<1s"
 * formatDuration(1500) // "1s"
 * formatDuration(90000) // "1m 30s"
 * formatDuration(3900000) // "1h 5m"
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || ms < 0) return '-';
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

/**
 * Format elapsed time with decimal precision for shorter durations.
 *
 * @param ms - Duration in milliseconds
 * @returns Formatted string like "500ms", "1.5s"
 */
export function formatElapsedTime(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Format an ETA (estimated time of arrival) for display.
 *
 * @param ms - Estimated remaining time in milliseconds
 * @returns Formatted string like "~30s remaining"
 */
export function formatEta(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || ms < 0) return 'calculating...';
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

/**
 * Truncate a SMILES string for display while preserving readability.
 *
 * @param smiles - SMILES string to truncate
 * @param maxLen - Maximum length (default: 40)
 * @returns Truncated string with ellipsis if needed
 *
 * @example
 * truncateSmiles("CC(C)Cc1ccc(C(C)C(=O)O)cc1", 30) // "CC(C)Cc1ccc(C(C)C(=O)O)cc..."
 */
export function truncateSmiles(smiles: string, maxLen: number = 40): string {
  if (!smiles) return '';
  if (smiles.length <= maxLen) return smiles;
  return smiles.substring(0, maxLen) + '...';
}

/**
 * Format a confidence score for display.
 *
 * @param score - Score between 0 and 1 (or 0-100)
 * @param options - Formatting options
 * @returns Formatted percentage string
 *
 * @example
 * formatConfidenceScore(0.856) // "85.6%"
 * formatConfidenceScore(85.6, { isPercent: true }) // "85.6%"
 * formatConfidenceScore(0.856, { decimals: 0 }) // "86%"
 */
export function formatConfidenceScore(
  score: number,
  options: { isPercent?: boolean; decimals?: number } = {}
): string {
  const { isPercent = false, decimals = 1 } = options;
  const percentage = isPercent ? score : score * 100;
  return `${percentage.toFixed(decimals)}%`;
}

/**
 * Format a protein sequence length for display.
 *
 * @param length - Number of residues
 * @returns Formatted string like "350 residues"
 */
export function formatSequenceLength(length: number): string {
  return `${length.toLocaleString()} residue${length !== 1 ? 's' : ''}`;
}

/**
 * Format a file size for display.
 *
 * @param bytes - Size in bytes
 * @returns Formatted string like "1.5 MB"
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

/**
 * Get a CSS class name for a confidence score level.
 *
 * @param score - Score between 0 and 1
 * @param thresholds - Custom thresholds (default: high >= 0.7, medium >= 0.4)
 * @returns CSS class suffix: "high", "medium", or "low"
 *
 * @example
 * getScoreLevel(0.85) // "high"
 * getScoreLevel(0.5) // "medium"
 * getScoreLevel(0.2) // "low"
 */
export function getScoreLevel(
  score: number,
  thresholds: { high?: number; medium?: number } = {}
): 'high' | 'medium' | 'low' {
  const { high = 0.7, medium = 0.4 } = thresholds;
  if (score >= high) return 'high';
  if (score >= medium) return 'medium';
  return 'low';
}

/**
 * Get a CSS class name for a confidence score with "score-" prefix.
 *
 * @param score - Score value
 * @param max - Maximum possible score (for normalization)
 * @returns CSS class name like "score-high"
 */
export function getScoreColorClass(score: number, max: number = 1): string {
  const normalized = score / max;
  return `score-${getScoreLevel(normalized)}`;
}

/**
 * Format a number with thousands separators.
 *
 * @param num - Number to format
 * @param locale - Locale for formatting (default: user's locale)
 * @returns Formatted string like "1,234,567"
 */
export function formatNumber(num: number, locale?: string): string {
  return num.toLocaleString(locale);
}

/**
 * Format a scientific notation number.
 *
 * @param num - Number to format
 * @param precision - Significant digits (default: 3)
 * @returns Formatted string like "1.23e-4"
 */
export function formatScientific(num: number, precision: number = 3): string {
  if (num === 0) return '0';
  return num.toExponential(precision - 1);
}
