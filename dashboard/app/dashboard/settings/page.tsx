'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import {
  User,
  Key,
  CreditCard,
  Shield,
  Copy,
  Check,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  AlertTriangle,
} from 'lucide-react';
import { useToast } from '@/components/ui/Toast';
import {
  getProfile,
  getCredits,
  createCheckout,
  getBillingPortal,
  getBillingHistory,
  listApiKeys,
  createApiKey,
  revokeApiKey,
} from '@/lib/api';
import type { ApiKeyInfo, ApiKeyCreated } from '@/lib/api';
import ProgressBar from '@/components/ui/ProgressBar';

type Tab = 'account' | 'api-keys' | 'billing' | 'preferences';

interface UserProfile {
  name: string;
  email: string;
  company?: string;
  created_at: string;
}

interface Credits {
  credits_remaining: number;
  credits_monthly: number;
  plan: string;
}

interface Transaction {
  id: string;
  amount: number;
  reason: string;
  balance_after: number;
  created_at: string;
}

export default function SettingsPage() {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<Tab>('account');
  const [user, setUser] = useState<UserProfile | null>(null);
  const [credits, setCredits] = useState<Credits | null>(null);
  const [history, setHistory] = useState<{ transactions: Transaction[] } | null>(null);
  const [loading, setLoading] = useState<string | null>(null);

  // API Keys state
  const [apiKeys, setApiKeys] = useState<ApiKeyInfo[]>([]);
  const [loadingKeys, setLoadingKeys] = useState(true);
  const [newKeyName, setNewKeyName] = useState('');
  const [createdKey, setCreatedKey] = useState<ApiKeyCreated | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [showKeyWarning, setShowKeyWarning] = useState(false);
  const [keyToRevoke, setKeyToRevoke] = useState<string | null>(null);

  // Preferences state
  const [highContrast, setHighContrast] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    Promise.all([
      getProfile().catch(() => null),
      getCredits().catch(() => null),
      getBillingHistory().catch(() => null),
    ]).then(([u, c, h]) => {
      setUser(u);
      setCredits(c);
      setHistory(h);
    });
  }, []);

  const loadApiKeys = useCallback(() => {
    setLoadingKeys(true);
    listApiKeys()
      .then(setApiKeys)
      .catch(() => {})
      .finally(() => setLoadingKeys(false));
  }, []);

  useEffect(() => {
    loadApiKeys();
  }, [loadApiKeys]);

  // Check saved preferences
  useEffect(() => {
    if (typeof window !== 'undefined') {
      setHighContrast(localStorage.getItem('lf-high-contrast') === 'true');
      setReducedMotion(localStorage.getItem('lf-reduced-motion') === 'true');
    }
  }, []);

  const handleCreateKey = async () => {
    if (!newKeyName.trim()) return;
    setLoading('create-key');
    try {
      const key = await createApiKey(newKeyName.trim());
      setCreatedKey(key);
      setNewKeyName('');
      loadApiKeys();
      toast({ title: 'API key created', description: 'Copy the key now — it won\'t be shown again.', variant: 'success' });
    } catch (e: unknown) {
      toast({ title: 'Failed to create key', description: e instanceof Error ? e.message : 'Unknown error', variant: 'error' });
    } finally {
      setLoading(null);
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    setLoading(`revoke-${keyId}`);
    try {
      await revokeApiKey(keyId);
      loadApiKeys();
      setKeyToRevoke(null);
      toast({ title: 'API key revoked', variant: 'success' });
    } catch (e: unknown) {
      toast({ title: 'Failed to revoke key', description: e instanceof Error ? e.message : 'Unknown error', variant: 'error' });
    } finally {
      setLoading(null);
    }
  };

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
  };

  const toggleHighContrast = () => {
    const next = !highContrast;
    setHighContrast(next);
    localStorage.setItem('lf-high-contrast', String(next));
    document.documentElement.classList.toggle('high-contrast', next);
    toast({ title: next ? 'High contrast enabled' : 'High contrast disabled', variant: 'success' });
  };

  const toggleReducedMotion = () => {
    const next = !reducedMotion;
    setReducedMotion(next);
    localStorage.setItem('lf-reduced-motion', String(next));
    document.documentElement.classList.toggle('reduce-motion', next);
    toast({ title: next ? 'Reduced motion enabled' : 'Reduced motion disabled', variant: 'success' });
  };

  const plans = [
    { slug: 'starter', name: 'Starter', price: '$0/mo', credits: 500, features: ['500 credits/month', '1 vertical', 'CSV export'] },
    { slug: 'pro', name: 'Pro', price: '$49/mo', credits: 5000, features: ['5,000 credits/month', 'All verticals', 'CSV + API export', 'Email verification'] },
    { slug: 'scale', name: 'Scale', price: '$149/mo', credits: 25000, features: ['25,000 credits/month', 'All verticals', 'Priority crawling', 'Outreach integration', 'Dedicated support'] },
    { slug: 'enterprise', name: 'Enterprise', price: 'Custom', credits: -1, features: ['Unlimited credits', 'Custom verticals', 'White-label', 'SLA guarantee', 'Dedicated infrastructure'] },
  ];

  const creditPacks = [
    { slug: '1k', name: '1,000 Credits', price: '$19' },
    { slug: '5k', name: '5,000 Credits', price: '$79' },
    { slug: '10k', name: '10,000 Credits', price: '$129' },
  ];

  const handleUpgrade = async (planSlug: string) => {
    if (planSlug === 'enterprise') {
      window.location.href = 'mailto:sales@leadfactory.io?subject=Enterprise%20Plan%20Inquiry';
      return;
    }
    setLoading(planSlug);
    try {
      const { checkout_url } = await createCheckout(planSlug);
      window.location.href = checkout_url;
    } catch (e: unknown) {
      toast({ title: 'Checkout failed', description: e instanceof Error ? e.message : 'Failed to start checkout', variant: 'error' });
    } finally {
      setLoading(null);
    }
  };

  const handleBuyCredits = async (packSlug: string) => {
    setLoading(`pack-${packSlug}`);
    try {
      const { checkout_url } = await createCheckout(undefined, packSlug);
      window.location.href = checkout_url;
    } catch (e: unknown) {
      toast({ title: 'Checkout failed', description: e instanceof Error ? e.message : 'Failed to start checkout', variant: 'error' });
    } finally {
      setLoading(null);
    }
  };

  const handleManageSubscription = async () => {
    setLoading('portal');
    try {
      const { portal_url } = await getBillingPortal();
      window.location.href = portal_url;
    } catch (e: unknown) {
      toast({ title: 'Portal error', description: e instanceof Error ? e.message : 'Failed to open billing portal', variant: 'error' });
    } finally {
      setLoading(null);
    }
  };

  const formatReason = (reason: string) => {
    const map: Record<string, string> = {
      monthly_refill: 'Monthly refill',
      subscription_cancelled: 'Subscription cancelled',
    };
    if (map[reason]) return map[reason];
    if (reason.startsWith('purchase:')) return `Purchased ${reason.split(':')[1]}`;
    if (reason.startsWith('plan_upgrade:')) return `Upgraded to ${reason.split(':')[1]}`;
    if (reason === 'campaign_run') return 'Campaign run';
    return reason;
  };

  const tabs = [
    { id: 'account' as Tab, label: 'Account', icon: User },
    { id: 'api-keys' as Tab, label: 'API Keys', icon: Key },
    { id: 'billing' as Tab, label: 'Billing', icon: CreditCard },
    { id: 'preferences' as Tab, label: 'Preferences', icon: Shield },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-100 mb-2">Settings</h1>
      <p className="text-sm text-gray-400 mb-8">Manage your account, API keys, billing, and preferences</p>

      {/* Tab navigation */}
      <div className="flex gap-1 p-1 bg-white/5 rounded-lg w-fit mb-8 overflow-x-auto" role="tablist" aria-label="Settings sections">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              aria-controls={`panel-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap focus:outline-none focus:ring-2 focus:ring-brand-500 ${
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

      <div id={`panel-${activeTab}`} role="tabpanel" aria-label={tabs.find((t) => t.id === activeTab)?.label}>
        {/* ── Account Tab ─────────────────────────── */}
        {activeTab === 'account' && (
          <div className="space-y-6 max-w-2xl">
            <div className="glass-card hive-border rounded-xl p-6">
              <h2 className="text-lg font-semibold text-gray-100 mb-4">Profile</h2>
              {user ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                  <div>
                    <label className="block text-gray-500 mb-1">Name</label>
                    <p className="font-medium text-gray-200">{user.name}</p>
                  </div>
                  <div>
                    <label className="block text-gray-500 mb-1">Email</label>
                    <p className="font-medium text-gray-200">{user.email}</p>
                  </div>
                  <div>
                    <label className="block text-gray-500 mb-1">Company</label>
                    <p className="font-medium text-gray-200">{user.company || '—'}</p>
                  </div>
                  <div>
                    <label className="block text-gray-500 mb-1">Member since</label>
                    <p className="font-medium text-gray-200">
                      <time dateTime={user.created_at}>{new Date(user.created_at).toLocaleDateString()}</time>
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-3 animate-pulse" role="status" aria-label="Loading profile">
                  <div className="h-4 w-32 bg-white/10 rounded" />
                  <div className="h-4 w-48 bg-white/10 rounded" />
                </div>
              )}
            </div>

            {credits && (
              <div className="glass-card hive-border rounded-xl p-6">
                <h2 className="text-lg font-semibold text-gray-100 mb-4">Credits Overview</h2>
                <div className="flex items-end gap-2 mb-3">
                  <span className="text-3xl font-bold text-gray-100">{credits.credits_remaining.toLocaleString()}</span>
                  <span className="text-gray-500 mb-1">/ {credits.credits_monthly.toLocaleString()} monthly</span>
                </div>
                <ProgressBar
                  value={credits.credits_remaining}
                  max={credits.credits_monthly}
                  variant={credits.credits_remaining / credits.credits_monthly > 0.2 ? 'success' : 'warning'}
                  label="Credit usage"
                />
                <p className="text-xs text-gray-500 mt-2">
                  Current plan: <strong className="text-gray-300">{credits.plan}</strong>. Credits refill monthly.
                </p>
              </div>
            )}
          </div>
        )}

        {/* ── API Keys Tab ────────────────────────── */}
        {activeTab === 'api-keys' && (
          <div className="space-y-6 max-w-2xl">
            {/* Create key */}
            <div className="glass-card hive-border rounded-xl p-6">
              <h2 className="text-lg font-semibold text-gray-100 mb-2">Create API Key</h2>
              <p className="text-sm text-gray-400 mb-4">
                API keys allow external applications to access your LeadFactory data programmatically.
              </p>
              <div className="flex gap-3">
                <label htmlFor="key-name" className="sr-only">Key name</label>
                <input
                  id="key-name"
                  type="text"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="Key name, e.g. Production API"
                  className="flex-1 px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
                  onKeyDown={(e) => e.key === 'Enter' && handleCreateKey()}
                />
                <button
                  onClick={handleCreateKey}
                  disabled={!newKeyName.trim() || loading === 'create-key'}
                  className="flex items-center gap-1.5 px-4 py-2.5 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-500 transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  <Plus className="w-4 h-4" aria-hidden="true" />
                  {loading === 'create-key' ? 'Creating...' : 'Create'}
                </button>
              </div>
            </div>

            {/* Newly created key */}
            {createdKey && (
              <div className="glass-card rounded-xl p-6 border-2 border-brand-500/30 bg-brand-500/5" role="alert">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-brand-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-brand-400 mb-1">Copy your API key now</h3>
                    <p className="text-xs text-gray-400 mb-3">
                      This key will only be shown once. Store it in a secure location.
                    </p>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 px-3 py-2 bg-gray-900 rounded-lg text-xs text-gray-200 font-mono overflow-hidden text-ellipsis">
                        {createdKey.key}
                      </code>
                      <button
                        onClick={() => copyToClipboard(createdKey.key)}
                        className="p-2 rounded-lg border border-white/10 hover:bg-white/5 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500"
                        aria-label="Copy API key to clipboard"
                      >
                        {copiedKey ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4 text-gray-400" />}
                      </button>
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => setCreatedKey(null)}
                  className="mt-3 text-xs text-gray-500 hover:text-gray-300 transition-colors"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* Existing keys */}
            <div className="glass-card hive-border rounded-xl p-6">
              <h2 className="text-lg font-semibold text-gray-100 mb-4">Active Keys</h2>
              {loadingKeys ? (
                <div className="space-y-3 animate-pulse" role="status" aria-label="Loading API keys">
                  {[...Array(2)].map((_, i) => (
                    <div key={i} className="h-14 bg-white/5 rounded-lg" />
                  ))}
                </div>
              ) : apiKeys.filter((k) => k.is_active).length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-6">No API keys created yet.</p>
              ) : (
                <div className="space-y-2" role="list" aria-label="API keys">
                  {apiKeys
                    .filter((k) => k.is_active)
                    .map((key) => (
                      <div
                        key={key.id}
                        role="listitem"
                        className="flex items-center justify-between p-3 bg-white/5 rounded-lg border border-white/5 hover:border-white/10 transition-colors"
                      >
                        <div>
                          <p className="text-sm font-medium text-gray-200">{key.name}</p>
                          <p className="text-xs text-gray-500">
                            Created <time dateTime={key.created_at}>{new Date(key.created_at).toLocaleDateString()}</time>
                            {key.last_used && (
                              <> · Last used <time dateTime={key.last_used}>{new Date(key.last_used).toLocaleDateString()}</time></>
                            )}
                          </p>
                        </div>
                        {keyToRevoke === key.id ? (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-red-400">Revoke?</span>
                            <button
                              onClick={() => handleRevokeKey(key.id)}
                              disabled={loading === `revoke-${key.id}`}
                              className="px-2.5 py-1 text-xs font-medium text-red-400 border border-red-500/30 rounded-md hover:bg-red-500/10 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500"
                            >
                              {loading === `revoke-${key.id}` ? '...' : 'Yes'}
                            </button>
                            <button
                              onClick={() => setKeyToRevoke(null)}
                              className="px-2.5 py-1 text-xs font-medium text-gray-400 border border-white/10 rounded-md hover:bg-white/5 transition-colors"
                            >
                              No
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setKeyToRevoke(key.id)}
                            className="p-1.5 text-gray-500 hover:text-red-400 transition-colors rounded-md hover:bg-white/5 focus:outline-none focus:ring-2 focus:ring-red-500"
                            aria-label={`Revoke API key ${key.name}`}
                          >
                            <Trash2 className="w-4 h-4" aria-hidden="true" />
                          </button>
                        )}
                      </div>
                    ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Billing Tab ─────────────────────────── */}
        {activeTab === 'billing' && (
          <div className="space-y-8">
            {/* Credits bar */}
            {credits && (
              <div className="glass-card hive-border rounded-xl p-6 max-w-2xl">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-gray-100">Credits</h2>
                  {credits.plan !== 'starter' && (
                    <button
                      onClick={handleManageSubscription}
                      disabled={loading === 'portal'}
                      className="text-sm text-brand-400 hover:text-brand-300 font-medium disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-brand-500 rounded"
                    >
                      {loading === 'portal' ? 'Loading...' : 'Manage Subscription'}
                    </button>
                  )}
                </div>
                <div className="flex items-end gap-2 mb-3">
                  <span className="text-3xl font-bold text-gray-100">{credits.credits_remaining.toLocaleString()}</span>
                  <span className="text-gray-500 mb-1">/ {credits.credits_monthly.toLocaleString()} monthly</span>
                </div>
                <ProgressBar
                  value={credits.credits_remaining}
                  max={credits.credits_monthly}
                  variant={credits.credits_remaining / credits.credits_monthly > 0.2 ? 'success' : 'warning'}
                />
                <p className="text-xs text-gray-500 mt-2">1 credit = 1 lead with verified email.</p>
              </div>
            )}

            {/* Credit Packs */}
            <div>
              <h2 className="text-lg font-semibold text-gray-100 mb-4">Buy Credit Packs</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 max-w-2xl">
                {creditPacks.map((pack) => (
                  <div key={pack.slug} className="glass-card hive-border rounded-xl p-5 flex flex-col items-center">
                    <p className="font-semibold text-gray-200">{pack.name}</p>
                    <p className="text-2xl font-bold text-gray-100 my-2">{pack.price}</p>
                    <button
                      onClick={() => handleBuyCredits(pack.slug)}
                      disabled={loading === `pack-${pack.slug}`}
                      className="w-full mt-2 px-4 py-2 text-sm font-medium bg-white/10 text-gray-200 rounded-lg border border-white/10 hover:bg-white/20 transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-brand-500"
                    >
                      {loading === `pack-${pack.slug}` ? 'Loading...' : 'Buy Now'}
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* Plans */}
            <div>
              <h2 className="text-lg font-semibold text-gray-100 mb-4">Plans</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {plans.map((plan) => {
                  const isActive = credits?.plan?.toLowerCase() === plan.slug;
                  return (
                    <div
                      key={plan.name}
                      className={`rounded-xl border-2 p-5 transition-all ${
                        isActive ? 'border-brand-500 bg-brand-500/5' : 'border-white/10 bg-white/5 hover:border-white/20'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="font-semibold text-gray-100">{plan.name}</h3>
                        {isActive && (
                          <span className="text-xs font-medium text-brand-400 bg-brand-500/20 px-2 py-0.5 rounded-full">Current</span>
                        )}
                      </div>
                      <p className="text-2xl font-bold text-gray-100 mb-4">{plan.price}</p>
                      <ul className="space-y-2" role="list">
                        {plan.features.map((f) => (
                          <li key={f} className="text-sm text-gray-400 flex items-center gap-2">
                            <Check className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" aria-hidden="true" />
                            {f}
                          </li>
                        ))}
                      </ul>
                      {!isActive && (
                        <button
                          onClick={() => handleUpgrade(plan.slug)}
                          disabled={loading === plan.slug}
                          className="w-full mt-4 px-4 py-2 text-sm font-medium border border-white/10 rounded-lg text-gray-300 hover:bg-white/5 transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-brand-500"
                        >
                          {loading === plan.slug
                            ? 'Loading...'
                            : plan.slug === 'enterprise'
                              ? 'Contact Sales'
                              : 'Upgrade'}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Credit History */}
            {history?.transactions && history.transactions.length > 0 && (
              <div className="glass-card hive-border rounded-xl p-6">
                <h2 className="text-lg font-semibold text-gray-100 mb-4">Credit History</h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" aria-label="Credit transaction history">
                    <thead>
                      <tr className="text-left text-gray-500 border-b border-white/10">
                        <th scope="col" className="pb-2 font-medium">Date</th>
                        <th scope="col" className="pb-2 font-medium">Description</th>
                        <th scope="col" className="pb-2 font-medium text-right">Amount</th>
                        <th scope="col" className="pb-2 font-medium text-right">Balance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.transactions.map((tx) => (
                        <tr key={tx.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                          <td className="py-2 text-gray-400">
                            <time dateTime={tx.created_at}>{new Date(tx.created_at).toLocaleDateString()}</time>
                          </td>
                          <td className="py-2 text-gray-200">{formatReason(tx.reason)}</td>
                          <td className={`py-2 text-right font-medium tabular-nums ${tx.amount >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {tx.amount >= 0 ? '+' : ''}{tx.amount.toLocaleString()}
                          </td>
                          <td className="py-2 text-right text-gray-400 tabular-nums">{tx.balance_after.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Preferences Tab ────────────────────── */}
        {activeTab === 'preferences' && (
          <div className="space-y-6 max-w-2xl">
            <div className="glass-card hive-border rounded-xl p-6">
              <h2 className="text-lg font-semibold text-gray-100 mb-4">Accessibility</h2>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-200">High Contrast Mode</p>
                    <p className="text-xs text-gray-500">Increase contrast for better readability</p>
                  </div>
                  <button
                    role="switch"
                    aria-checked={highContrast}
                    onClick={toggleHighContrast}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 ${
                      highContrast ? 'bg-brand-600' : 'bg-white/20'
                    }`}
                    aria-label="Toggle high contrast mode"
                  >
                    <span
                      className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                        highContrast ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-200">Reduced Motion</p>
                    <p className="text-xs text-gray-500">Minimize animations throughout the dashboard</p>
                  </div>
                  <button
                    role="switch"
                    aria-checked={reducedMotion}
                    onClick={toggleReducedMotion}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 ${
                      reducedMotion ? 'bg-brand-600' : 'bg-white/20'
                    }`}
                    aria-label="Toggle reduced motion"
                  >
                    <span
                      className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                        reducedMotion ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>
            </div>

            <div className="glass-card hive-border rounded-xl p-6">
              <h2 className="text-lg font-semibold text-gray-100 mb-4">Data & Privacy</h2>
              <div className="space-y-3">
                <button
                  onClick={() => {
                    localStorage.removeItem('token');
                    window.location.href = '/login';
                  }}
                  className="w-full text-left px-4 py-3 bg-white/5 rounded-lg border border-white/10 text-sm text-gray-300 hover:bg-white/10 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  Sign out of all sessions
                </button>
              </div>
            </div>

            {/* Legal Links */}
            <div className="border-t border-white/10 pt-6 flex gap-6 text-sm text-gray-500">
              <Link href="/terms" className="hover:text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-500 rounded transition-colors">Terms of Service</Link>
              <Link href="/privacy" className="hover:text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-500 rounded transition-colors">Privacy Policy</Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
