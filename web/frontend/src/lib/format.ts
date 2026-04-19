import { format, formatDistanceToNow, isValid, parseISO } from 'date-fns';

function toDate(input: Date | string | number | null | undefined): Date | null {
  if (input == null) return null;
  if (input instanceof Date) return isValid(input) ? input : null;
  if (typeof input === 'number') {
    const d = new Date(input);
    return isValid(d) ? d : null;
  }
  const parsed = parseISO(input);
  if (isValid(parsed)) return parsed;
  const fallback = new Date(input);
  return isValid(fallback) ? fallback : null;
}

export function formatDate(
  input: Date | string | number | null | undefined,
  pattern = 'MMM d, yyyy'
): string {
  const d = toDate(input);
  return d ? format(d, pattern) : '';
}

export function formatDateTime(
  input: Date | string | number | null | undefined,
  pattern = 'MMM d, yyyy h:mm a'
): string {
  const d = toDate(input);
  return d ? format(d, pattern) : '';
}

export function formatRelativeTime(
  input: Date | string | number | null | undefined
): string {
  const d = toDate(input);
  return d ? formatDistanceToNow(d, { addSuffix: true }) : '';
}
