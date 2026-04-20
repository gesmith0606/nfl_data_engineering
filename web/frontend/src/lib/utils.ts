import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format a byte count as a human-readable string with binary or decimal units.
 * @param bytes Raw byte count
 * @param opts.decimals Number of fractional digits (default 1)
 * @param opts.binary Use 1024 base with KiB/MiB units (default false = 1000 base)
 */
export function formatBytes(
  bytes: number,
  opts: { decimals?: number; binary?: boolean } = {}
): string {
  const { decimals = 1, binary = false } = opts;
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const base = binary ? 1024 : 1000;
  const units = binary
    ? ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
    : ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(base)),
    units.length - 1
  );
  const value = bytes / Math.pow(base, exponent);
  return `${value.toFixed(decimals)} ${units[exponent]}`;
}
