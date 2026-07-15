'use client';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail
} from '@/components/ui/sidebar';
import { navGroups } from '@/config/nav-config';
import { useMediaQuery } from '@/hooks/use-media-query';
import { useFilteredNavGroups } from '@/hooks/use-nav';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import * as React from 'react';
import { Icons } from '../icons';
import { Gx01Head } from '../gx01';

export default function AppSidebar() {
  const pathname = usePathname();
  const { isOpen } = useMediaQuery();
  const filteredGroups = useFilteredNavGroups(navGroups);

  React.useEffect(() => {
    // Side effects based on sidebar state changes
  }, [isOpen]);

  return (
    <Sidebar collapsible='icon'>
      <SidebarHeader className='group-data-[collapsible=icon]:pt-[var(--space-4)]'>
        <SidebarMenu>
          <SidebarMenuItem>
            {/* Brand → marketing home (web convention: logo goes to /). The
             * dashboard itself stays one click away via the Dashboard nav item. */}
            <SidebarMenuButton size='lg' asChild>
              <Link href='/'>
                <div className='flex items-center gap-[var(--space-2)]'>
                  <div className='wc-rail h-[var(--space-8)] w-[3px] shrink-0 rounded-full group-data-[collapsible=icon]:hidden' />
                  <div className='flex aspect-square size-[var(--space-8)] shrink-0 items-center justify-center rounded-lg bg-[var(--wc-bar,#05070d)] border border-[rgba(255,216,77,0.4)]'>
                    <Gx01Head className='scale-[0.55]' />
                  </div>
                </div>
                <div className='grid flex-1 text-left text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                  <span className='wc-display truncate text-[length:var(--fs-lg)] leading-[var(--lh-sm)] tracking-[0.14em]'>
                    G<span className='text-[var(--wc-mint,#91edd0)]'>IQ</span>
                  </span>
                  <span className='text-sidebar-foreground/70 truncate text-[length:var(--fs-xs)] leading-[var(--lh-xs)] tracking-[0.08em] uppercase'>
                    NFL Analytics
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent className='overflow-x-hidden'>
        {filteredGroups.map((group) => (
          <SidebarGroup key={group.label || 'ungrouped'} className='py-0'>
            {group.label && <SidebarGroupLabel>{group.label}</SidebarGroupLabel>}
            <SidebarMenu>
              {group.items.map((item) => {
                const Icon = item.icon ? Icons[item.icon] : Icons.logo;
                return item?.items && item?.items?.length > 0 ? (
                  <Collapsible
                    key={item.title}
                    asChild
                    defaultOpen={item.isActive}
                    className='group/collapsible'
                  >
                    <SidebarMenuItem>
                      <CollapsibleTrigger asChild>
                        <SidebarMenuButton
                          tooltip={item.title}
                          isActive={pathname === item.url}
                          className='h-[var(--tap-min)] md:h-8'
                        >
                          {item.icon && <Icon />}
                          <span>{item.title}</span>
                          <Icons.chevronRight className='ml-auto transition-transform duration-[var(--motion-base)] ease-[var(--ease-out-standard)] group-data-[state=open]/collapsible:rotate-90' />
                        </SidebarMenuButton>
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <SidebarMenuSub>
                          {item.items?.map((subItem) => (
                            <SidebarMenuSubItem key={subItem.title}>
                              <SidebarMenuSubButton
                                asChild
                                isActive={pathname === subItem.url}
                                className='h-[var(--tap-min)] md:h-7'
                              >
                                <Link href={subItem.url}>
                                  <span>{subItem.title}</span>
                                </Link>
                              </SidebarMenuSubButton>
                            </SidebarMenuSubItem>
                          ))}
                        </SidebarMenuSub>
                      </CollapsibleContent>
                    </SidebarMenuItem>
                  </Collapsible>
                ) : (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton
                      asChild
                      tooltip={item.title}
                      isActive={pathname === item.url}
                      className='h-[var(--tap-min)] md:h-8'
                    >
                      <Link href={item.url}>
                        <Icon />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size='lg'>
              <div className='bg-sidebar-accent text-sidebar-accent-foreground flex aspect-square size-[var(--space-8)] items-center justify-center rounded-lg'>
                <Icons.settings className='size-[var(--space-4)]' />
              </div>
              <div className='grid flex-1 text-left text-[length:var(--fs-sm)] leading-[var(--lh-sm)]'>
                <span className='truncate font-semibold'>Settings</span>
                <span className='text-sidebar-foreground/70 truncate text-[length:var(--fs-xs)] leading-[var(--lh-xs)]'>
                  v3.0
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
