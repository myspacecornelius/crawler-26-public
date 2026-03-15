'use client';

import { Globe, Mail, Rocket, Link2, Send } from 'lucide-react';
import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

type EventType = 'crawl_complete' | 'enrichment_complete' | 'campaign_created' | 'crm_push' | 'outreach_launched';

export interface ActivityEvent {
  id: string;
  type: EventType;
  message: string;
  timestamp: string;
}

interface ActivityFeedProps {
  events?: ActivityEvent[];
  isLoading?: boolean;
}

const EVENT_ICON: Record<EventType, ReactNode> = {
  crawl_complete: <Globe className="w-4 h-4 text-brand-400 group-hover:text-brand-300 transition-colors" aria-hidden="true" />,
  enrichment_complete: <Mail className="w-4 h-4 text-emerald-400 group-hover:text-emerald-300 transition-colors" aria-hidden="true" />,
  campaign_created: <Rocket className="w-4 h-4 text-brand-500 group-hover:text-brand-400 transition-colors" aria-hidden="true" />,
  crm_push: <Link2 className="w-4 h-4 text-violet-400 group-hover:text-violet-300 transition-colors" aria-hidden="true" />,
  outreach_launched: <Send className="w-4 h-4 text-amber-500 group-hover:text-amber-400 transition-colors" aria-hidden="true" />,
};

const EVENT_BG: Record<EventType, string> = {
  crawl_complete: 'bg-brand-500/10 border-brand-500/20 group-hover:border-brand-500/50',
  enrichment_complete: 'bg-emerald-500/10 border-emerald-500/20 group-hover:border-emerald-500/50',
  campaign_created: 'bg-brand-500/20 border-brand-500/30 group-hover:border-brand-500/60 shadow-[0_0_10px_-2px_rgba(245,158,11,0.3)]',
  crm_push: 'bg-violet-500/10 border-violet-500/20 group-hover:border-violet-500/50',
  outreach_launched: 'bg-amber-500/10 border-amber-500/20 group-hover:border-amber-500/50',
};

const EVENT_LABELS: Record<EventType, string> = {
  crawl_complete: 'Crawl completed',
  enrichment_complete: 'Enrichment completed',
  campaign_created: 'Campaign created',
  crm_push: 'CRM push',
  outreach_launched: 'Outreach launched',
};

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return 'Yesterday';
  return `${days}d ago`;
}

export default function ActivityFeed({ events, isLoading }: ActivityFeedProps) {
  if (isLoading) {
    return (
      <div className="glass-card hive-border rounded-xl p-6" role="status" aria-label="Loading activity feed">
        <div className="h-4 w-36 bg-white/10 rounded mb-5 animate-pulse" />
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex items-start gap-4 animate-pulse">
              <div className="w-9 h-9 rounded-xl bg-white/10" />
              <div className="flex-1 space-y-2 pt-1">
                <div className="h-3 w-3/4 bg-white/10 rounded" />
                <div className="h-2 w-16 bg-white/5 rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const items = events ?? [];

  return (
    <div
      className="glass-card hive-border rounded-xl p-6 relative overflow-hidden"
      role="log"
      aria-label="Activity feed"
      aria-live="polite"
    >
      <div className="absolute top-0 right-0 w-32 h-32 bg-brand-500/5 rounded-full blur-[50px] pointer-events-none" />

      <h3 className="font-semibold text-gray-100 mb-5 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-brand-500 animate-pulseGlow" aria-hidden="true" />
        Activity Log
      </h3>

      <div className="space-y-4 relative z-10" role="list">
        {items.map((ev, i) => (
          <motion.div
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.1 }}
            key={ev.id}
            role="listitem"
            className="flex items-start gap-4 group p-2 -mx-2 rounded-lg hover:bg-white/5 cursor-default transition-colors"
          >
            <div
              className={`flex-shrink-0 w-9 h-9 border rounded-[0.8rem] flex items-center justify-center transition-all duration-300 ${EVENT_BG[ev.type]}`}
              title={EVENT_LABELS[ev.type]}
            >
              {EVENT_ICON[ev.type]}
            </div>
            <div className="flex-1 min-w-0 pt-0.5">
              <p className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">{ev.message}</p>
              <time
                dateTime={ev.timestamp}
                className="text-xs font-mono text-gray-500 mt-1 block"
              >
                {relativeTime(ev.timestamp)}
              </time>
            </div>
          </motion.div>
        ))}
        {items.length === 0 && (
          <p className="text-sm text-gray-500 text-center py-6">No recent activity</p>
        )}
      </div>
    </div>
  );
}
