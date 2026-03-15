'use client';

import { useState, useEffect, useCallback } from 'react';
import { Check, ChevronRight, ChevronLeft, AlertCircle, Target, BarChart3, Layers } from 'lucide-react';
import { clsx } from 'clsx';
import { useToast } from '@/components/ui/Toast';
import { getScoringConfig, updateScoringConfig } from '@/lib/api';
import type { ScoringConfig, ScoringWeights, TierThresholds } from '@/lib/api';
import ProgressBar from '@/components/ui/ProgressBar';

const STEPS = [
  { title: 'Weights', description: 'Configure how leads are scored', icon: Target },
  { title: 'Tiers', description: 'Set score thresholds for lead tiers', icon: Layers },
  { title: 'Preview', description: 'Review and save your configuration', icon: BarChart3 },
];

const WEIGHT_LABELS: Record<keyof ScoringWeights, { label: string; description: string }> = {
  stage_match: { label: 'Stage Match', description: 'How well the fund stage matches your target' },
  sector_match: { label: 'Sector Match', description: 'Industry/vertical alignment score' },
  check_size_fit: { label: 'Check Size Fit', description: 'Investment size compatibility' },
  portfolio_relevance: { label: 'Portfolio Relevance', description: 'Relevance of existing portfolio companies' },
  recency: { label: 'Recency', description: 'How recently the data was verified' },
};

export default function ScoringWizard({ onClose }: { onClose?: () => void }) {
  const { toast } = useToast();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [weights, setWeights] = useState<ScoringWeights>({
    stage_match: 30,
    sector_match: 25,
    check_size_fit: 20,
    portfolio_relevance: 15,
    recency: 10,
  });

  const [tiers, setTiers] = useState<TierThresholds>({
    hot: 80,
    warm: 60,
    cool: 40,
  });

  useEffect(() => {
    getScoringConfig()
      .then((config) => {
        setWeights(config.weights);
        setTiers(config.tiers);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const totalWeight = Object.values(weights).reduce((sum, v) => sum + v, 0);
  const isWeightsValid = Math.abs(totalWeight - 100) < 0.01;
  const isTiersValid = tiers.hot > tiers.warm && tiers.warm > tiers.cool && tiers.cool > 0;

  const updateWeight = useCallback((key: keyof ScoringWeights, value: number) => {
    setWeights((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateScoringConfig({ weights, tiers });
      toast({ title: 'Scoring config saved', description: 'Your scoring weights and tiers have been updated.', variant: 'success' });
      onClose?.();
    } catch (e: unknown) {
      toast({
        title: 'Save failed',
        description: e instanceof Error ? e.message : 'Failed to save configuration',
        variant: 'error',
      });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse" role="status" aria-label="Loading scoring configuration">
        <div className="h-6 w-48 bg-white/10 rounded" />
        <div className="h-40 bg-white/5 rounded-xl" />
      </div>
    );
  }

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
                <span
                  className={clsx(
                    'text-xs mt-1.5 font-medium whitespace-nowrap',
                    isActive ? 'text-brand-400' : isCompleted ? 'text-gray-300' : 'text-gray-500',
                  )}
                >
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
            {(Object.entries(WEIGHT_LABELS) as [keyof ScoringWeights, { label: string; description: string }][]).map(([key, info]) => (
              <div key={key}>
                <div className="flex items-center justify-between mb-1.5">
                  <div>
                    <label htmlFor={`weight-${key}`} className="text-sm font-medium text-gray-200">{info.label}</label>
                    <p className="text-xs text-gray-500">{info.description}</p>
                  </div>
                  <span className="text-sm font-bold text-brand-400 tabular-nums w-12 text-right">{weights[key]}%</span>
                </div>
                <input
                  id={`weight-${key}`}
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={weights[key]}
                  onChange={(e) => updateWeight(key, Number(e.target.value))}
                  className="w-full h-2 bg-white/10 rounded-full appearance-none cursor-pointer accent-brand-500"
                  aria-label={`${info.label} weight`}
                />
              </div>
            ))}

            <div className={clsx(
              'p-3 rounded-lg border text-sm flex items-center gap-2',
              isWeightsValid
                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
                : 'bg-red-500/10 border-red-500/20 text-red-400',
            )}>
              <AlertCircle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
              {isWeightsValid
                ? 'Weights sum to 100% — valid configuration'
                : `Weights sum to ${totalWeight}% — must equal 100%`}
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-6">
            {(['hot', 'warm', 'cool'] as const).map((tier) => {
              const colors = { hot: 'text-red-400', warm: 'text-amber-400', cool: 'text-blue-400' };
              return (
                <div key={tier}>
                  <div className="flex items-center justify-between mb-1.5">
                    <label htmlFor={`tier-${tier}`} className={`text-sm font-medium ${colors[tier]} uppercase`}>
                      {tier} Threshold
                    </label>
                    <span className="text-sm font-bold text-gray-300 tabular-nums">{tiers[tier]}+</span>
                  </div>
                  <input
                    id={`tier-${tier}`}
                    type="range"
                    min={1}
                    max={99}
                    value={tiers[tier]}
                    onChange={(e) => setTiers((prev) => ({ ...prev, [tier]: Number(e.target.value) }))}
                    className="w-full h-2 bg-white/10 rounded-full appearance-none cursor-pointer accent-brand-500"
                    aria-label={`${tier} tier threshold`}
                  />
                </div>
              );
            })}

            {/* Preview bar */}
            <div className="space-y-2 mt-4">
              <p className="text-xs text-gray-400 font-medium">Score Distribution Preview</p>
              <div className="flex h-6 rounded-lg overflow-hidden">
                <div className="bg-red-500/40" style={{ width: `${100 - tiers.hot}%` }} title={`HOT: ${tiers.hot}–100`} />
                <div className="bg-amber-500/40" style={{ width: `${tiers.hot - tiers.warm}%` }} title={`WARM: ${tiers.warm}–${tiers.hot - 1}`} />
                <div className="bg-blue-500/40" style={{ width: `${tiers.warm - tiers.cool}%` }} title={`COOL: ${tiers.cool}–${tiers.warm - 1}`} />
                <div className="bg-gray-500/40" style={{ width: `${tiers.cool}%` }} title={`COLD: 0–${tiers.cool - 1}`} />
              </div>
              <div className="flex justify-between text-[10px] text-gray-500">
                <span>COLD (0–{tiers.cool - 1})</span>
                <span>COOL ({tiers.cool}–{tiers.warm - 1})</span>
                <span>WARM ({tiers.warm}–{tiers.hot - 1})</span>
                <span>HOT ({tiers.hot}–100)</span>
              </div>
            </div>

            {!isTiersValid && (
              <div className="p-3 rounded-lg border bg-red-500/10 border-red-500/20 text-sm text-red-400 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
                Tier thresholds must be ordered: HOT &gt; WARM &gt; COOL &gt; 0
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="border border-white/10 rounded-lg overflow-hidden">
              <div className="px-4 py-2 bg-white/5 border-b border-white/10">
                <h3 className="text-sm font-semibold text-gray-300">Scoring Weights</h3>
              </div>
              <div className="divide-y divide-white/5">
                {(Object.entries(WEIGHT_LABELS) as [keyof ScoringWeights, { label: string; description: string }][]).map(([key, info]) => (
                  <div key={key} className="flex items-center justify-between px-4 py-2.5">
                    <span className="text-sm text-gray-400">{info.label}</span>
                    <span className="text-sm font-medium text-gray-200">{weights[key]}%</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="border border-white/10 rounded-lg overflow-hidden">
              <div className="px-4 py-2 bg-white/5 border-b border-white/10">
                <h3 className="text-sm font-semibold text-gray-300">Tier Thresholds</h3>
              </div>
              <div className="divide-y divide-white/5">
                <div className="flex items-center justify-between px-4 py-2.5">
                  <span className="text-sm text-red-400">HOT</span>
                  <span className="text-sm font-medium text-gray-200">{tiers.hot}+ score</span>
                </div>
                <div className="flex items-center justify-between px-4 py-2.5">
                  <span className="text-sm text-amber-400">WARM</span>
                  <span className="text-sm font-medium text-gray-200">{tiers.warm}–{tiers.hot - 1} score</span>
                </div>
                <div className="flex items-center justify-between px-4 py-2.5">
                  <span className="text-sm text-blue-400">COOL</span>
                  <span className="text-sm font-medium text-gray-200">{tiers.cool}–{tiers.warm - 1} score</span>
                </div>
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
            <button
              type="button"
              onClick={onClose}
              className="px-5 py-2.5 text-sm font-medium text-gray-400 border border-white/10 rounded-lg hover:bg-white/5 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              Cancel
            </button>
          ) : null}
        </div>

        <div>
          {step < STEPS.length - 1 ? (
            <button
              type="button"
              onClick={() => setStep(step + 1)}
              disabled={step === 0 && !isWeightsValid}
              className="flex items-center gap-1.5 px-6 py-2.5 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              Next
              <ChevronRight className="w-4 h-4" aria-hidden="true" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !isWeightsValid || !isTiersValid}
              className="px-6 py-2.5 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              {saving ? 'Saving...' : 'Save Configuration'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
