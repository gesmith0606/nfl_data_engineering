import { NavGroup } from '@/types';

export const navGroups: NavGroup[] = [
  {
    label: 'NFL Analytics',
    items: [
      {
        title: 'Dashboard',
        url: '/dashboard',
        icon: 'dashboard',
        isActive: false,
        shortcut: ['d', 'd'],
        items: []
      },
      {
        title: 'Projections',
        url: '/dashboard/projections',
        icon: 'target',
        isActive: false,
        shortcut: ['p', 'p'],
        items: []
      },
      {
        title: 'Predictions',
        url: '/dashboard/predictions',
        icon: 'chartBar',
        isActive: false,
        shortcut: ['g', 'g'],
        items: []
      },
      {
        title: 'Lineups',
        url: '/dashboard/lineups',
        icon: 'football',
        isActive: false,
        shortcut: ['l', 'l'],
        items: []
      },
      {
        title: 'Players',
        url: '/dashboard/players',
        icon: 'user',
        isActive: false,
        shortcut: ['s', 's'],
        items: []
      },
      {
        title: 'News',
        url: '/dashboard/news',
        icon: 'news',
        isActive: false,
        shortcut: ['n', 'n'],
        items: []
      },
      {
        title: 'Model Accuracy',
        url: '/dashboard/accuracy',
        icon: 'target',
        isActive: false,
        shortcut: ['a', 'a'],
        items: []
      }
    ]
  }
];
