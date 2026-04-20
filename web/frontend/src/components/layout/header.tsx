import React from 'react';
import { SidebarTrigger } from '../ui/sidebar';
import { Separator } from '../ui/separator';
import { Breadcrumbs } from '../breadcrumbs';
import SearchInput from '../search-input';
import { ThemeSelector } from '../themes/theme-selector';
import { ThemeModeToggle } from '../themes/theme-mode-toggle';

export default function Header() {
  return (
    <header className='bg-background sticky top-0 z-20 flex h-[var(--size-header)] shrink-0 items-center justify-between gap-[var(--space-2)]'>
      <div className='flex items-center gap-[var(--space-2)] px-[var(--space-4)]'>
        <SidebarTrigger className='-ml-[var(--space-1)]' />
        <Separator orientation='vertical' className='mr-[var(--space-2)] h-[var(--space-4)]' />
        <Breadcrumbs />
      </div>

      <div className='flex items-center gap-[var(--space-2)] px-[var(--space-4)]'>
        <div className='hidden md:flex'>
          <SearchInput />
        </div>
        <ThemeModeToggle />
        <div className='hidden sm:block'>
          <ThemeSelector />
        </div>
      </div>
    </header>
  );
}
