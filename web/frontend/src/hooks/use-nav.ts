'use client';

import { useMemo } from 'react';
import type { NavItem, NavGroup } from '@/types';

/**
 * Simplified nav filter (no auth/RBAC -- show all items).
 */
export function useFilteredNavItems(items: NavItem[]) {
  return useMemo(() => items, [items]);
}

export function useFilteredNavGroups(groups: NavGroup[]) {
  return useMemo(() => groups.filter((g) => g.items.length > 0), [groups]);
}
