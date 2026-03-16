'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import * as Tooltip from '@radix-ui/react-tooltip';
import {
  LayoutDashboard,
  Rocket,
  Send,
  Link as LinkIcon,
  Building2,
  Briefcase,
  Settings,
  Settings2,
  ChevronsLeft,
  ChevronsRight,
  Search,
  LogOut,
} from 'lucide-react';
import { useSidebar } from '@/contexts/SidebarContext';
import type { LucideIcon } from 'lucide-react';

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

const mainNav: NavItem[] = [
  { href: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { href: '/dashboard/campaigns', label: 'Campaigns', icon: Rocket },
  { href: '/dashboard/outreach', label: 'Outreach', icon: Send },
  { href: '/dashboard/crm', label: 'CRM', icon: LinkIcon },
  { href: '/dashboard/verticals', label: 'Verticals', icon: Building2 },
  { href: '/dashboard/portfolio', label: 'Portfolio', icon: Briefcase },
  { href: '/dashboard/config', label: 'Configuration', icon: Settings2 },
];

const bottomNav: NavItem[] = [
  { href: '/dashboard/settings', label: 'Settings', icon: Settings },
];

function NavLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const pathname = usePathname();
  const isActive =
    item.href === '/dashboard'
      ? pathname === '/dashboard'
      : pathname === item.href || pathname?.startsWith(item.href + '/');

  const Icon = item.icon;

  const link = (
    <Link
      href={item.href}
      className={clsx(
        'group relative flex items-center gap-3 rounded-lg text-sm font-medium transition-all duration-150',
        collapsed ? 'justify-center px-2 py-2.5' : 'px-3 py-2.5',
        isActive
          ? 'bg-brand-600/20 text-brand-300'
          : 'text-gray-400 hover:text-white hover:bg-gray-800'
      )}
    >
      {/* Active indicator bar */}
      {isActive && (
        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-brand-500" />
      )}
      <Icon size={20} className="shrink-0" />
      {!collapsed && <span>{item.label}</span>}
    </Link>
  );

  if (collapsed) {
    return (
      <Tooltip.Root delayDuration={0}>
        <Tooltip.Trigger asChild>{link}</Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side="right"
            sideOffset={8}
            className="z-50 rounded-md bg-gray-900 px-3 py-1.5 text-xs text-white shadow-lg border border-gray-700"
          >
            {item.label}
            <Tooltip.Arrow className="fill-gray-900" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    );
  }

  return link;
}

export default function AppSidebar() {
  const { collapsed, toggle } = useSidebar();

  return (
    <Tooltip.Provider>
      <aside
        className={clsx(
          'fixed left-0 top-0 h-screen bg-gray-900 text-white flex flex-col transition-all duration-200 z-20',
          'hidden md:flex',
          collapsed ? 'w-16' : 'w-60'
        )}
      >
        {/* Brand area */}
        <div className={clsx('flex items-center border-b border-gray-800', collapsed ? 'px-3 py-5 justify-center' : 'px-6 py-5 justify-between')}>
          <Link href="/dashboard" className="flex items-center gap-2 min-w-0">
            {collapsed ? (
              <span className="text-lg font-bold text-brand-400">L</span>
            ) : (
              <div>
                <h1 className="text-xl font-bold tracking-tight">
                  <span className="text-brand-400">Lead</span>Factory
                </h1>
                <p className="text-xs text-gray-500 mt-0.5">Multi-vertical lead gen</p>
              </div>
            )}
          </Link>
          <button
            onClick={toggle}
            className={clsx(
              'text-gray-500 hover:text-white transition-colors rounded-md p-1 hover:bg-gray-800',
              collapsed && 'hidden'
            )}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <ChevronsLeft size={18} />
          </button>
        </div>

        {/* Expand button when collapsed */}
        {collapsed && (
          <button
            onClick={toggle}
            className="mx-auto mt-2 text-gray-500 hover:text-white transition-colors rounded-md p-1.5 hover:bg-gray-800"
            aria-label="Expand sidebar"
          >
            <ChevronsRight size={18} />
          </button>
        )}

        {/* Search shortcut */}
        <div className={clsx('px-3', collapsed ? 'mt-2' : 'mt-3')}>
          <button
            onClick={() => {
              // Dispatch custom event to open CommandPalette
              window.dispatchEvent(new CustomEvent('open-command-palette'));
            }}
            className={clsx(
              'w-full flex items-center gap-2 rounded-lg border border-gray-700 text-gray-500 hover:text-gray-300 hover:border-gray-600 transition-colors text-sm',
              collapsed ? 'justify-center px-2 py-2' : 'px-3 py-2'
            )}
          >
            <Search size={16} className="shrink-0" />
            {!collapsed && (
              <>
                <span className="flex-1 text-left">Search...</span>
                <kbd className="text-[10px] font-mono bg-gray-800 px-1.5 py-0.5 rounded text-gray-500">⌘K</kbd>
              </>
            )}
          </button>
        </div>

        {/* Main nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {mainNav.map((item) => (
            <NavLink key={item.href} item={item} collapsed={collapsed} />
          ))}
        </nav>

        {/* Bottom section */}
        <div className="px-3 pb-2 space-y-1">
          <div className="border-t border-gray-800 mb-2" />
          {bottomNav.map((item) => (
            <NavLink key={item.href} item={item} collapsed={collapsed} />
          ))}
        </div>

        {/* Sign out */}
        <div className={clsx('px-3 pb-4', collapsed && 'flex justify-center')}>
          <button
            onClick={() => {
              localStorage.removeItem('token');
              window.location.href = '/login';
            }}
            className={clsx(
              'flex items-center gap-3 text-sm text-gray-500 hover:text-white transition-colors rounded-lg hover:bg-gray-800',
              collapsed ? 'justify-center p-2.5' : 'w-full text-left px-3 py-2'
            )}
          >
            <LogOut size={18} className="shrink-0" />
            {!collapsed && <span>Sign out</span>}
          </button>
        </div>
      </aside>
    </Tooltip.Provider>
  );
}
