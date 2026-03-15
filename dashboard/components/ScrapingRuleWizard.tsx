'use client';

import { useState } from 'react';
import { Check, ChevronRight, ChevronLeft, Globe, Code, Eye, AlertCircle } from 'lucide-react';
import { clsx } from 'clsx';
import { useToast } from '@/components/ui/Toast';
import { addScrapingRule } from '@/lib/api';
import type { ScrapingRule } from '@/lib/api';

const STEPS = [
  { title: 'Target', description: 'Specify the website domain and team page', icon: Globe },
  { title: 'Selectors', description: 'Define CSS selectors for data extraction', icon: Code },
  { title: 'Review', description: 'Preview and save the scraping rule', icon: Eye },
];

const PAGINATION_TYPES = [
  { value: 'none', label: 'None', description: 'Single page, no pagination' },
  { value: 'click', label: 'Click', description: 'Click a "next" button to load more' },
  { value: 'scroll', label: 'Infinite Scroll', description: 'Scroll to load more content' },
  { value: 'url', label: 'URL Pattern', description: 'Increment page number in URL' },
];

export default function ScrapingRuleWizard({ onClose, onSaved }: { onClose?: () => void; onSaved?: () => void }) {
  const { toast } = useToast();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);

  const [rule, setRule] = useState<ScrapingRule>({
    domain: '',
    team_page_selector: '',
    name_selector: '',
    role_selector: '',
    email_selector: '',
    pagination_type: 'none',
    pagination_selector: '',
    enabled: true,
  });

  const update = (key: keyof ScrapingRule, value: string | boolean) => {
    setRule((prev) => ({ ...prev, [key]: value }));
  };

  const canAdvance = (): boolean => {
    if (step === 0) return rule.domain.trim().length > 0;
    return true;
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await addScrapingRule(rule);
      toast({ title: 'Scraping rule added', description: `Rule for ${rule.domain} has been saved.`, variant: 'success' });
      onSaved?.();
      onClose?.();
    } catch (e: unknown) {
      toast({
        title: 'Save failed',
        description: e instanceof Error ? e.message : 'Failed to save scraping rule',
        variant: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl">
      {/* Step indicator */}
      <nav aria-label="Wizard steps" className="flex items-center justify-center gap-0 mb-8">
        {STEPS.map((s, i) => {
          const isActive = i === step;
          const isCompleted = i < step;
          const Icon = s.icon;
          return (
            <div key={s.title} className="flex items-center">
              <div className="flex flex-col items-center">
                <div
                  className={clsx(
                    'w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold transition-all',
                    isCompleted && 'bg-brand-600 text-white',
                    isActive && 'bg-brand-600 text-white ring-4 ring-brand-500/20',
                    !isActive && !isCompleted && 'bg-white/10 text-gray-500',
                  )}
                  aria-current={isActive ? 'step' : undefined}
                >
                  {isCompleted ? <Check className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
                </div>
                <span className={clsx('text-xs mt-1.5 font-medium whitespace-nowrap', isActive ? 'text-brand-400' : isCompleted ? 'text-gray-300' : 'text-gray-500')}>
                  {s.title}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={clsx('w-16 sm:w-24 h-0.5 mx-2 mt-[-18px]', i < step ? 'bg-brand-600' : 'bg-white/10')} />
              )}
            </div>
          );
        })}
      </nav>

      {/* Step content */}
      <div className="glass-card hive-border rounded-xl p-6">
        <h2 className="text-lg font-semibold text-gray-100 mb-1">{STEPS[step].title}</h2>
        <p className="text-sm text-gray-400 mb-6">{STEPS[step].description}</p>

        {step === 0 && (
          <div className="space-y-5">
            <div>
              <label htmlFor="rule-domain" className="block text-sm font-medium text-gray-300 mb-1.5">Domain</label>
              <input
                id="rule-domain"
                type="text"
                value={rule.domain}
                onChange={(e) => update('domain', e.target.value)}
                placeholder="e.g. example.com"
                className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>

            <div>
              <label htmlFor="rule-team-page" className="block text-sm font-medium text-gray-300 mb-1.5">Team Page Selector</label>
              <input
                id="rule-team-page"
                type="text"
                value={rule.team_page_selector}
                onChange={(e) => update('team_page_selector', e.target.value)}
                placeholder='e.g. a[href*="team"], a[href*="about"]'
                className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
              <p className="text-xs text-gray-500 mt-1">CSS selector to find links to team/about pages</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-3">Pagination Type</label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {PAGINATION_TYPES.map((pt) => (
                  <button
                    key={pt.value}
                    type="button"
                    onClick={() => update('pagination_type', pt.value)}
                    className={clsx(
                      'text-left p-3 rounded-lg border transition-all',
                      rule.pagination_type === pt.value
                        ? 'border-brand-500/50 bg-brand-500/10'
                        : 'border-white/10 hover:border-white/20',
                    )}
                  >
                    <div className="text-sm font-medium text-gray-200">{pt.label}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{pt.description}</div>
                  </button>
                ))}
              </div>
            </div>

            {rule.pagination_type !== 'none' && (
              <div>
                <label htmlFor="rule-pagination-selector" className="block text-sm font-medium text-gray-300 mb-1.5">
                  Pagination Selector
                </label>
                <input
                  id="rule-pagination-selector"
                  type="text"
                  value={rule.pagination_selector}
                  onChange={(e) => update('pagination_selector', e.target.value)}
                  placeholder='e.g. button.next-page, a[rel="next"]'
                  className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
              </div>
            )}
          </div>
        )}

        {step === 1 && (
          <div className="space-y-5">
            <div className="p-3 rounded-lg border bg-blue-500/10 border-blue-500/20 text-sm text-blue-400 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
              <div>
                Enter CSS selectors to extract data from the team page. Leave blank to use auto-detection.
              </div>
            </div>

            <div>
              <label htmlFor="rule-name-sel" className="block text-sm font-medium text-gray-300 mb-1.5">Name Selector</label>
              <input
                id="rule-name-sel"
                type="text"
                value={rule.name_selector}
                onChange={(e) => update('name_selector', e.target.value)}
                placeholder='e.g. .team-member h3, .person-name'
                className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 font-mono"
              />
            </div>

            <div>
              <label htmlFor="rule-role-sel" className="block text-sm font-medium text-gray-300 mb-1.5">Role Selector</label>
              <input
                id="rule-role-sel"
                type="text"
                value={rule.role_selector}
                onChange={(e) => update('role_selector', e.target.value)}
                placeholder='e.g. .team-member p.role, .person-title'
                className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 font-mono"
              />
            </div>

            <div>
              <label htmlFor="rule-email-sel" className="block text-sm font-medium text-gray-300 mb-1.5">Email Selector</label>
              <input
                id="rule-email-sel"
                type="text"
                value={rule.email_selector}
                onChange={(e) => update('email_selector', e.target.value)}
                placeholder='e.g. a[href^="mailto:"], .email-link'
                className="w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 font-mono"
              />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="border border-white/10 rounded-lg overflow-hidden">
              <div className="px-4 py-2 bg-white/5 border-b border-white/10">
                <h3 className="text-sm font-semibold text-gray-300">Scraping Rule Summary</h3>
              </div>
              <div className="divide-y divide-white/5">
                <SummaryRow label="Domain" value={rule.domain || '(not set)'} />
                <SummaryRow label="Team Page Selector" value={rule.team_page_selector || '(auto-detect)'} />
                <SummaryRow label="Pagination" value={rule.pagination_type} />
                {rule.pagination_selector && <SummaryRow label="Pagination Selector" value={rule.pagination_selector} />}
                <SummaryRow label="Name Selector" value={rule.name_selector || '(auto-detect)'} />
                <SummaryRow label="Role Selector" value={rule.role_selector || '(auto-detect)'} />
                <SummaryRow label="Email Selector" value={rule.email_selector || '(auto-detect)'} />
                <SummaryRow label="Enabled" value={rule.enabled ? 'Yes' : 'No'} />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between mt-6">
        <div>
          {step > 0 ? (
            <button
              type="button"
              onClick={() => setStep(step - 1)}
              className="flex items-center gap-1.5 px-5 py-2.5 text-sm font-medium text-gray-400 border border-white/10 rounded-lg hover:bg-white/5 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <ChevronLeft className="w-4 h-4" aria-hidden="true" />
              Back
            </button>
          ) : onClose ? (
            <button type="button" onClick={onClose} className="px-5 py-2.5 text-sm font-medium text-gray-400 border border-white/10 rounded-lg hover:bg-white/5 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500">
              Cancel
            </button>
          ) : null}
        </div>

        <div>
          {step < STEPS.length - 1 ? (
            <button
              type="button"
              onClick={() => setStep(step + 1)}
              disabled={!canAdvance()}
              className="flex items-center gap-1.5 px-6 py-2.5 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              Next
              <ChevronRight className="w-4 h-4" aria-hidden="true" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !rule.domain.trim()}
              className="px-6 py-2.5 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              {saving ? 'Saving...' : 'Save Rule'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <span className="text-sm text-gray-400">{label}</span>
      <span className="text-sm font-medium text-gray-200 text-right max-w-[60%] truncate font-mono">{value}</span>
    </div>
  );
}
