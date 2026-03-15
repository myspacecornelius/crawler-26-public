'use client';

import { useState, useEffect } from 'react';
import { Settings2, Globe, Target, Plus } from 'lucide-react';
import ScoringWizard from '@/components/ScoringWizard';
import ScrapingRuleWizard from '@/components/ScrapingRuleWizard';
import { getScrapingRules } from '@/lib/api';
import type { ScrapingRule } from '@/lib/api';

type Tab = 'scoring' | 'scraping';

export default function ConfigPage() {
  const [activeTab, setActiveTab] = useState<Tab>('scoring');
  const [showAddRule, setShowAddRule] = useState(false);
  const [rules, setRules] = useState<ScrapingRule[]>([]);
  const [loadingRules, setLoadingRules] = useState(true);

  const loadRules = () => {
    setLoadingRules(true);
    getScrapingRules()
      .then((data) => setRules(data.rules))
      .catch(() => {})
      .finally(() => setLoadingRules(false));
  };

  useEffect(() => {
    loadRules();
  }, []);

  const tabs = [
    { id: 'scoring' as Tab, label: 'Scoring Weights', icon: Target },
    { id: 'scraping' as Tab, label: 'Scraping Rules', icon: Globe },
  ];

  return (
    <div>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-100 flex items-center gap-2">
            <Settings2 className="w-6 h-6 text-brand-500" aria-hidden="true" />
            Configuration
          </h1>
          <p className="text-sm text-gray-400 mt-1">Manage scoring weights, tier thresholds, and scraping rules</p>
        </div>
      </div>

      {/* Tab navigation */}
      <div className="flex gap-1 p-1 bg-white/5 rounded-lg w-fit mb-8" role="tablist" aria-label="Configuration sections">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              aria-controls={`tab-panel-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 ${
                activeTab === tab.id
                  ? 'bg-white/10 text-gray-100 shadow-sm'
                  : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              <Icon className="w-4 h-4" aria-hidden="true" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div
        id={`tab-panel-${activeTab}`}
        role="tabpanel"
        aria-label={tabs.find((t) => t.id === activeTab)?.label}
      >
        {activeTab === 'scoring' && <ScoringWizard />}

        {activeTab === 'scraping' && (
          <div>
            {showAddRule ? (
              <ScrapingRuleWizard
                onClose={() => setShowAddRule(false)}
                onSaved={() => {
                  setShowAddRule(false);
                  loadRules();
                }}
              />
            ) : (
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-gray-100">Existing Rules</h2>
                  <button
                    onClick={() => setShowAddRule(true)}
                    className="flex items-center gap-1.5 px-4 py-2 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-500 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500"
                  >
                    <Plus className="w-4 h-4" aria-hidden="true" />
                    Add Rule
                  </button>
                </div>

                {loadingRules ? (
                  <div className="space-y-3 animate-pulse" role="status" aria-label="Loading scraping rules">
                    {[...Array(3)].map((_, i) => (
                      <div key={i} className="h-16 bg-white/5 rounded-lg" />
                    ))}
                  </div>
                ) : rules.length === 0 ? (
                  <div className="text-center py-12 text-gray-500">
                    <Globe className="w-10 h-10 mx-auto mb-3 text-gray-600" aria-hidden="true" />
                    <p className="text-sm">No scraping rules configured yet.</p>
                    <p className="text-xs mt-1">Add a rule to start extracting contacts from websites.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {rules.map((rule) => (
                      <div
                        key={rule.domain}
                        className="glass-card hive-border rounded-lg p-4 flex items-center justify-between"
                      >
                        <div>
                          <p className="text-sm font-medium text-gray-200">{rule.domain}</p>
                          <p className="text-xs text-gray-500 mt-0.5">
                            Pagination: {rule.pagination_type}
                            {rule.name_selector && ` | Name: ${rule.name_selector}`}
                          </p>
                        </div>
                        <span
                          className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                            rule.enabled
                              ? 'bg-emerald-500/20 text-emerald-400'
                              : 'bg-gray-500/20 text-gray-400'
                          }`}
                        >
                          {rule.enabled ? 'Active' : 'Disabled'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
