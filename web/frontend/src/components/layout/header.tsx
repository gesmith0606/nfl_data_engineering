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
      <div className='flex min-w-0 items-center gap-[var(--space-2)] px-[var(--space-3)] md:px-[var(--space-4)]'>
        {/* SidebarTrigger at base is ~28px (size-7); bump to 44px min tap target
         * on mobile so hamburger meets iOS 44px rule without altering the
         * desktop icon-button density. */}
        <SidebarTrigger className='size-[var(--tap-min)] md:size-8 -ml-[var(--space-1)] shrink-0' />
        <Separator
          orientation='vertical'
          className='mr-[var(--space-2)] h-[var(--space-4)] hidden sm:block'
        />
        <div className='min-w-0 truncate'>
          <Breadcrumbs />
        </div>
      </div>

      <div className='flex shrink-0 items-center gap-[var(--space-2)] px-[var(--space-3)] md:px-[var(--space-4)]'>
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
