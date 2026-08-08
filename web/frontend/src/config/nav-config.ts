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
        title: 'Rankings',
        url: '/dashboard/rankings',
        icon: 'trendingUp',
        isActive: false,
        shortcut: ['k', 'k'],
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
        title: 'Scores',
        url: '/dashboard/games',
        icon: 'table',
        isActive: false,
        shortcut: ['s', 'c'],
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
        title: 'Matchups',
        url: '/dashboard/matchups',
        icon: 'shield',
        isActive: false,
        shortcut: ['m', 'm'],
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
        title: 'Draft Tool',
        url: '/dashboard/draft',
        icon: 'clipboardText',
        isActive: false,
        shortcut: ['r', 'r'],
        items: []
      },
      {
        title: 'Model Accuracy',
        url: '/dashboard/accuracy',
        icon: 'target',
        isActive: false,
        shortcut: ['a', 'a'],
        items: []
      },
      {
        title: 'AI Advisor',
        url: '/dashboard/advisor',
        icon: 'sparkles',
        isActive: false,
        shortcut: ['i', 'i'],
        items: []
      }
    ]
  },
  {
    label: 'Manager Tools',
    items: [
      {
        title: 'Your Leagues',
        url: '/dashboard/leagues',
        icon: 'teams',
        isActive: false,
        shortcut: ['y', 'l'],
        items: []
      },
      {
        title: 'Trade Analyzer',
        url: '/dashboard/trade',
        icon: 'billing',
        isActive: false,
        shortcut: ['t', 't'],
        items: []
      },
      {
        title: 'Start/Sit',
        url: '/dashboard/start-sit',
        icon: 'checks',
        isActive: false,
        shortcut: ['w', 'w'],
        items: []
      },
      {
        title: 'Player Value',
        url: '/dashboard/value',
        icon: 'trendingUp',
        isActive: false,
        shortcut: ['v', 'v'],
        items: []
      },
      {
        title: 'Matchup Grid',
        url: '/dashboard/sos',
        icon: 'table',
        isActive: false,
        shortcut: ['o', 'o'],
        items: []
      },
      {
        title: 'Injuries & Depth',
        url: '/dashboard/injuries',
        icon: 'alertCircle',
        isActive: false,
        shortcut: ['j', 'j'],
        items: []
      }
    ]
  }
];
