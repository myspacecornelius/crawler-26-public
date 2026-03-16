'use client';

import { useState, useCallback } from 'react';
import { Filter, X, Search, SlidersHorizontal } from 'lucide-react';

export interface LeadFilterValues {
  search: string;
  tier: string;
  min_score: string;
  has_email: string;
  email_status: string;
  fund: string;
  sector: string;
  stage: string;
  hq: string;
  sort_by: string;
  sort_dir: string;
}

const DEFAULT_FILTERS: LeadFilterValues = {
  search: '',
  tier: '',
  min_score: '',
  has_email: '',
  email_status: '',
  fund: '',
  sector: '',
  stage: '',
  hq: '',
  sort_by: 'score',
  sort_dir: 'desc',
};

interface LeadFiltersProps {
  filters: LeadFilterValues;
  onChange: (filters: LeadFilterValues) => void;
  totalResults?: number;
}

const TIERS = ['HOT', 'WARM', 'COOL'] as const;
const EMAIL_STATUSES = ['verified', 'scraped', 'guessed', 'undeliverable', 'catch_all'] as const;
const SORT_OPTIONS = [
  { value: 'score', label: 'Score' },
  { value: 'name', label: 'Name' },
  { value: 'fund', label: 'Fund' },
  { value: 'scraped_at', label: 'Date Added' },
] as const;

export function useLeadFilters() {
  const [filters, setFilters] = useState<LeadFilterValues>(DEFAULT_FILTERS);

  const updateFilter = useCallback((key: keyof LeadFilterValues, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }, []);

  const clearAll = useCallback(() => {
    setFilters(DEFAULT_FILTERS);
  }, []);

  const activeCount = Object.entries(filters).filter(
    ([key, val]) => val !== '' && key !== 'sort_by' && key !== 'sort_dir',
  ).length;

  const toParams = useCallback((): Record<string, string> => {
    const params: Record<string, string> = {};
    Object.entries(filters).forEach(([key, val]) => {
      if (val !== '' && val !== undefined) {
        params[key] = val;
      }
    });
    return params;
  }, [filters]);

  return { filters, setFilters, updateFilter, clearAll, activeCount, toParams };
}

export default function LeadFilters({ filters, onChange, totalResults }: LeadFiltersProps) {
  const [expanded, setExpanded] = useState(false);

  const activeCount = Object.entries(filters).filter(
    ([key, val]) => val !== '' && key !== 'sort_by' && key !== 'sort_dir',
  ).length;

  const update = (key: keyof LeadFilterValues, value: string) => {
    onChange({ ...filters, [key]: value });
  };

  const clearAll = () => {
    onChange(DEFAULT_FILTERS);
  };

  return (
    <div className="space-y-3">
      {/* Search and filter toggle row */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" aria-hidden="true" />
          <input
            type="search"
            value={filters.search}
            onChange={(e) => update('search', e.target.value)}
            placeholder="Search leads by name, fund, email, role..."
            aria-label="Search leads"
            className="w-full pl-10 pr-4 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
        </div>

        {/* Filter toggle */}
        <button
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
          aria-controls="lead-filter-panel"
          className={`inline-flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 ${
            expanded
              ? 'border-brand-500/30 bg-brand-500/10 text-brand-400'
              : 'border-white/10 text-gray-400 hover:bg-white/5'
          }`}
        >
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          Filters
          {activeCount > 0 && (
            <span className="ml-1 inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold rounded-full bg-brand-600 text-white">
              {activeCount}
            </span>
          )}
        </button>

        {/* Sort controls */}
        <div className="flex items-center gap-2">
          <label htmlFor="sort-by" className="sr-only">Sort by</label>
          <select
            id="sort-by"
            value={filters.sort_by}
            onChange={(e) => update('sort_by', e.target.value)}
            className="px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-500"
            aria-label="Sort by"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button
            onClick={() => update('sort_dir', filters.sort_dir === 'asc' ? 'desc' : 'asc')}
            aria-label={`Sort ${filters.sort_dir === 'asc' ? 'descending' : 'ascending'}`}
            className="px-2.5 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-400 hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            {filters.sort_dir === 'asc' ? '↑' : '↓'}
          </button>
        </div>
      </div>

      {/* Expanded filter panel */}
      {expanded && (
        <div
          id="lead-filter-panel"
          role="region"
          aria-label="Lead filters"
          className="p-4 bg-white/5 border border-white/10 rounded-lg"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {/* Tier */}
            <div>
              <label htmlFor="filter-tier" className="block text-xs font-medium text-gray-400 mb-1.5">Tier</label>
              <select
                id="filter-tier"
                value={filters.tier}
                onChange={(e) => update('tier', e.target.value)}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">All Tiers</option>
                {TIERS.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            {/* Min Score */}
            <div>
              <label htmlFor="filter-score" className="block text-xs font-medium text-gray-400 mb-1.5">
                Min Score {filters.min_score && <span className="text-brand-400">({filters.min_score})</span>}
              </label>
              <input
                id="filter-score"
                type="range"
                min={0}
                max={100}
                value={filters.min_score || '0'}
                onChange={(e) => update('min_score', e.target.value === '0' ? '' : e.target.value)}
                className="w-full h-2 bg-white/10 rounded-full appearance-none cursor-pointer accent-brand-500"
                aria-label="Minimum lead score"
              />
            </div>

            {/* Has Email */}
            <div>
              <label htmlFor="filter-email" className="block text-xs font-medium text-gray-400 mb-1.5">Has Email</label>
              <select
                id="filter-email"
                value={filters.has_email}
                onChange={(e) => update('has_email', e.target.value)}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">Any</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </div>

            {/* Email Status */}
            <div>
              <label htmlFor="filter-email-status" className="block text-xs font-medium text-gray-400 mb-1.5">Email Status</label>
              <select
                id="filter-email-status"
                value={filters.email_status}
                onChange={(e) => update('email_status', e.target.value)}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">All Statuses</option>
                {EMAIL_STATUSES.map((s) => (
                  <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1).replace('_', ' ')}</option>
                ))}
              </select>
            </div>

            {/* Fund */}
            <div>
              <label htmlFor="filter-fund" className="block text-xs font-medium text-gray-400 mb-1.5">Fund</label>
              <input
                id="filter-fund"
                type="text"
                value={filters.fund}
                onChange={(e) => update('fund', e.target.value)}
                placeholder="Search by fund..."
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-300 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>

            {/* Sector */}
            <div>
              <label htmlFor="filter-sector" className="block text-xs font-medium text-gray-400 mb-1.5">Sector</label>
              <input
                id="filter-sector"
                type="text"
                value={filters.sector}
                onChange={(e) => update('sector', e.target.value)}
                placeholder="e.g. AI, SaaS..."
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-300 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>

            {/* Stage */}
            <div>
              <label htmlFor="filter-stage" className="block text-xs font-medium text-gray-400 mb-1.5">Stage</label>
              <input
                id="filter-stage"
                type="text"
                value={filters.stage}
                onChange={(e) => update('stage', e.target.value)}
                placeholder="e.g. Series A..."
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-300 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>

            {/* Geography */}
            <div>
              <label htmlFor="filter-hq" className="block text-xs font-medium text-gray-400 mb-1.5">Geography</label>
              <input
                id="filter-hq"
                type="text"
                value={filters.hq}
                onChange={(e) => update('hq', e.target.value)}
                placeholder="e.g. US, SF..."
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-300 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
          </div>

          {/* Active filter summary and clear */}
          {activeCount > 0 && (
            <div className="mt-3 pt-3 border-t border-white/10 flex items-center justify-between">
              <p className="text-xs text-gray-400">
                {totalResults !== undefined
                  ? `${totalResults.toLocaleString()} results`
                  : `${activeCount} filter${activeCount > 1 ? 's' : ''} active`}
              </p>
              <button
                onClick={clearAll}
                className="inline-flex items-center gap-1 text-xs font-medium text-gray-400 hover:text-gray-200 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 rounded"
              >
                <X className="h-3 w-3" aria-hidden="true" />
                Clear all filters
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
