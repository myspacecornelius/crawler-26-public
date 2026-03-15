'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Menu } from 'lucide-react';
import { SidebarProvider, useSidebar } from '@/contexts/SidebarContext';
import AppSidebar from '@/components/layout/AppSidebar';
import MobileNav from '@/components/layout/MobileNav';
import Breadcrumbs from '@/components/layout/Breadcrumbs';
import CommandPalette from '@/components/layout/CommandPalette';
import NotificationBell from '@/components/layout/NotificationBell';
import UserMenu from '@/components/layout/UserMenu';
import { Toaster } from '@/components/ui/Toast';
import SkipLink from '@/components/ui/SkipLink';
import { getProfile } from '@/lib/api';

type User = { name: string; email: string; plan: string; credits_remaining: number };

function MobileMenuButton() {
  const { setMobileOpen } = useSidebar();
  return (
    <button
      onClick={() => setMobileOpen(true)}
      className="md:hidden p-2 -ml-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors"
      aria-label="Open navigation"
    >
      <Menu size={20} />
    </button>
  );
}

function DashboardShell({ children, user }: { children: React.ReactNode; user: User | null }) {
  const { collapsed } = useSidebar();

  return (
    <div className="min-h-screen bg-gray-50">
      <AppSidebar />
      <MobileNav />
      <SkipLink targetId="main-content" />
      <main className="transition-all duration-200 max-md:!ml-0" style={{ marginLeft: collapsed ? '4rem' : '15rem' }}>
        <header className="sticky top-0 z-10 bg-white/80 backdrop-blur border-b border-gray-200 px-6 py-3 flex items-center justify-between" role="banner">
          <div className="flex items-center gap-4">
            <MobileMenuButton />
            <Breadcrumbs />
          </div>
          <div className="flex items-center gap-3">
            <NotificationBell />
            <UserMenu user={user} />
          </div>
        </header>
        <div id="main-content" className="p-4 sm:p-6 lg:p-8" tabIndex={-1}>{children}</div>
      </main>
      <CommandPalette />
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      router.push('/login');
      return;
    }
    getProfile()
      .then((u) => { setUser(u); setReady(true); })
      .catch(() => { router.push('/login'); });
  }, [router]);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    );
  }

  return (
    <SidebarProvider>
      <Toaster>
        <DashboardShell user={user}>{children}</DashboardShell>
      </Toaster>
    </SidebarProvider>
  );
}
