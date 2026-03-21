'use client';

import { useSWRFetch } from './useSWR';
import type { SWROptions } from './useSWR';
import {
  listCampaigns,
  getCredits,
  getProfile,
  getLeadStats,
  listLeads,
  getFreshness,
  getBillingHistory,
  listVerticals,
  getCampaign,
} from '@/lib/api';

/* ── Type definitions ───────────────────────────────── */

export interface Campaign {
  id: string;
  name: string;
  vertical: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  config: Record<string, unknown>;
  total_leads: number;
  total_emails: number;
  credits_used: number;
  error_message?: string;
  task_id?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

export interface CampaignList {
  campaigns: Campaign[];
  total: number;
}

export interface Credits {
  credits_remaining: number;
  credits_monthly: number;
  plan: string;
}

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  company?: string;
  plan: string;
  credits_remaining: number;
  credits_monthly: number;
  is_active: boolean;
  created_at: string;
}

export interface LeadStats {
  total_leads: number;
  with_email: number;
  email_rate: number;
  verified_emails: number;
  hot_leads: number;
  warm_leads: number;
  cool_leads: number;
  avg_score: number;
  top_funds: Array<{ fund: string; count: number }>;
}

export interface Lead {
  id: string;
  name: string;
  email?: string;
  email_verified: boolean;
  email_source?: string;
  email_status?: string;
  linkedin?: string;
  phone?: string;
  fund: string;
  role?: string;
  website?: string;
  /** Semicolon-separated string from backend. Split on ";" before display. */
  sectors?: string;
  check_size?: string;
  stage?: string;
  hq?: string;
  score: number;
  /** HOT | WARM | COOL | COLD */
  tier: string;
  source?: string;
  opted_out: boolean;
  scraped_at: string;
}

export interface LeadList {
  leads: Lead[];
  total: number;
  page: number;
  per_page: number;
}

export interface Freshness {
  total_leads: number;
  verified_last_7d: number;
  verified_last_14d: number;
  never_verified: number;
  crawled_last_7d: number;
  stale_leads: number;
  freshness_pct: number;
}

export interface BillingTransaction {
  id: string;
  amount: number;
  reason: string;
  balance_after: number;
  created_at: string;
}

export interface BillingHistory {
  transactions: BillingTransaction[];
  total: number;
}

export interface Vertical {
  slug: string;
  name: string;
  description: string;
  seed_count: number;
  search_queries?: string[];
}

export interface ScoringWeights {
  stage_match: number;
  sector_match: number;
  check_size_fit: number;
  portfolio_relevance: number;
  recency: number;
}

export interface TierThresholds {
  hot: number;
  warm: number;
  cool: number;
}

export interface ScoringConfig {
  weights: ScoringWeights;
  tiers: TierThresholds;
}

export interface ScrapingRule {
  domain: string;
  team_page_selector: string;
  name_selector: string;
  role_selector: string;
  email_selector: string;
  pagination_type: string;
  pagination_selector: string;
  enabled: boolean;
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
  last_used?: string;
}

export interface ApiKeyCreated {
  id: string;
  name: string;
  key: string;
  created_at: string;
}

/* ── Hooks ──────────────────────────────────────────── */

const DEFAULT_CREDITS: Credits = { credits_remaining: 0, credits_monthly: 0, plan: 'starter' };

export function useCampaigns(page = 1, status?: string, opts?: SWROptions<CampaignList>) {
  return useSWRFetch<CampaignList>(
    `campaigns-${page}-${status || 'all'}`,
    () => listCampaigns(page, status),
    { fallbackData: { campaigns: [], total: 0 }, refreshInterval: 30000, ...opts },
  );
}

export function useCampaign(id: string, opts?: SWROptions<Campaign>) {
  return useSWRFetch<Campaign>(
    id ? `campaign-${id}` : null,
    () => getCampaign(id),
    { refreshInterval: 10000, ...opts },
  );
}

export function useCredits(opts?: SWROptions<Credits>) {
  return useSWRFetch<Credits>(
    'credits',
    () => getCredits(),
    { fallbackData: DEFAULT_CREDITS, refreshInterval: 60000, ...opts },
  );
}

export function useProfile(opts?: SWROptions<UserProfile>) {
  return useSWRFetch<UserProfile>(
    'profile',
    () => getProfile(),
    opts,
  );
}

export function useLeadStats(campaignId: string, opts?: SWROptions<LeadStats>) {
  return useSWRFetch<LeadStats>(
    campaignId ? `lead-stats-${campaignId}` : null,
    () => getLeadStats(campaignId),
    { refreshInterval: 30000, ...opts },
  );
}

export function useLeads(campaignId: string, params: Record<string, string> = {}, opts?: SWROptions<LeadList>) {
  const paramKey = Object.entries(params).sort().map(([k, v]) => `${k}=${v}`).join('&');
  return useSWRFetch<LeadList>(
    campaignId ? `leads-${campaignId}-${paramKey}` : null,
    () => listLeads(campaignId, params),
    { fallbackData: { leads: [], total: 0, page: 1, per_page: 50 }, ...opts },
  );
}

export function useFreshness(campaignId: string, opts?: SWROptions<Freshness>) {
  return useSWRFetch<Freshness>(
    campaignId ? `freshness-${campaignId}` : null,
    () => getFreshness(campaignId),
    opts,
  );
}

export function useBillingHistory(page = 1, opts?: SWROptions<BillingHistory>) {
  return useSWRFetch<BillingHistory>(
    `billing-history-${page}`,
    () => getBillingHistory(page),
    opts,
  );
}

export function useVerticals(opts?: SWROptions<Vertical[]>) {
  return useSWRFetch<Vertical[]>(
    'verticals',
    () => listVerticals(),
    { fallbackData: [], ...opts },
  );
}
