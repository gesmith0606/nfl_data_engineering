import type { ColumnSort } from '@tanstack/react-table';
import { createParser } from 'nuqs/server';
import { z } from 'zod';

const sortingItemSchema = z.object({
  id: z.string(),
  desc: z.boolean(),
});

export function getSortingStateParser<TData>(columnIds?: string[] | Set<string>) {
  const validIds = columnIds instanceof Set ? columnIds : new Set(columnIds ?? []);

  return createParser<ColumnSort[]>({
    parse: (value) => {
      try {
        const parsed = JSON.parse(value) as unknown;
        const result = z.array(sortingItemSchema).safeParse(parsed);
        if (!result.success) return null;
        if (validIds.size > 0) {
          const invalid = result.data.some((item) => !validIds.has(item.id));
          if (invalid) return null;
        }
        return result.data as ColumnSort[];
      } catch {
        return null;
      }
    },
    serialize: (value) => JSON.stringify(value),
    eq: (a, b) =>
      a.length === b.length &&
      a.every((item, i) => item.id === b[i]?.id && item.desc === b[i]?.desc),
  });
}

export const filterItemSchema = z.object({
  id: z.string(),
  value: z.union([z.string(), z.array(z.string())]),
  variant: z.enum([
    'text',
    'number',
    'range',
    'date',
    'dateRange',
    'boolean',
    'select',
    'multiSelect',
  ]),
  operator: z.enum([
    'iLike',
    'notILike',
    'eq',
    'ne',
    'lt',
    'lte',
    'gt',
    'gte',
    'inArray',
    'notInArray',
    'isEmpty',
    'isNotEmpty',
    'isBetween',
    'isRelativeToToday',
  ]),
  filterId: z.string(),
});

export type FilterItemSchema = z.infer<typeof filterItemSchema>;
