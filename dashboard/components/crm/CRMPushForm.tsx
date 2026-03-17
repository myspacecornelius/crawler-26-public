'use client';

import { useState, useEffect, useCallback } from 'react';
import { CircleDot, Cloud, X, ArrowRight } from 'lucide-react';
import CollapsibleSection from '@/components/ui/CollapsibleSection';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { pushToCRM, getCRMFields, getDefaultFieldMapping } from '@/lib/api';

interface Campaign {
  id: string;
  name: string;
  vertical: string;
  status: string;
  total_leads: number;
}

interface CRMPushRecord {
  provider: string;
  campaign_id: string;
  campaign_name: string;
  pushed_at: string;
  total: number;
  created: number;
  updated: number;
  failed: number;
  crm_ids: string[];
}

const TIERS = ['HOT', 'WARM', 'COOL'] as const;

interface CRMPushFormProps {
  campaigns: Campaign[];
  hubspotKey: string;
  sfAccessToken: string;
  sfInstanceUrl: string;
  sfClientId: string;
  sfClientSecret: string;
  onPushComplete: (record: CRMPushRecord) => void;
}

export default function CRMPushForm({
  campaigns,
  hubspotKey,
  sfAccessToken,
  sfInstanceUrl,
  sfClientId,
  sfClientSecret,
  onPushComplete,
}: CRMPushFormProps) {
  const [selectedProvider, setSelectedProvider] = useState<'hubspot' | 'salesforce'>('hubspot');
  const [campaignId, setCampaignId] = useState('');
  const [minScore, setMinScore] = useState(0);
  const [selectedTiers, setSelectedTiers] = useState<string[]>(['HOT', 'WARM']);
  const [testMode, setTestMode] = useState(false);
  const [fieldMapping, setFieldMapping] = useState<Record<string, string>>({});
  const [defaultMapping, setDefaultMapping] = useState<Record<string, string>>({});
  const [crmFields, setCrmFields] = useState<string[]>([]);
  const [customFields, setCustomFields] = useState<{ key: string; value: string }[]>([]);
  const [pushing, setPushing] = useState(false);
  const [pushError, setPushError] = useState('');
  const [pushResult, setPushResult] = useState<{ created: number; updated: number; failed: number } | null>(null);

  const loadFieldConfig = useCallback(async (provider: string) => {
    try {
      const [defaults, fields] = await Promise.all([
        getDefaultFieldMapping().catch(() => ({})),
        getCRMFields(provider, true).catch(() => ({ fields: [] })),
      ]);
      setDefaultMapping(defaults.mapping || defaults || {});
      setFieldMapping(defaults.mapping || defaults || {});
      const fieldList = Array.isArray(fields) ? fields : (fields.fields || []);
      setCrmFields(fieldList.map((f: string | { name: string }) => typeof f === 'string' ? f : f.name));
    } catch {
      setDefaultMapping({});
      setFieldMapping({});
      setCrmFields([]);
    }
  }, []);

  useEffect(() => {
    loadFieldConfig(selectedProvider);
  }, [selectedProvider, loadFieldConfig]);

  const handleTierToggle = (tier: string) => {
    setSelectedTiers((prev) =>
      prev.includes(tier) ? prev.filter((t) => t !== tier) : [...prev, tier]
    );
  };

  const addCustomField = () => setCustomFields([...customFields, { key: '', value: '' }]);

  const updateCustomField = (idx: number, field: 'key' | 'value', val: string) => {
    const updated = [...customFields];
    updated[idx][field] = val;
    setCustomFields(updated);
  };

  const removeCustomField = (idx: number) => setCustomFields(customFields.filter((_, i) => i !== idx));

  const handlePush = async () => {
    setPushError('');
    setPushResult(null);
    if (!campaignId) { setPushError('Select a source campaign'); return; }

    setPushing(true);
    try {
      const customFieldsObj: Record<string, string> = {};
      customFields.forEach((cf) => { if (cf.key) customFieldsObj[cf.key] = cf.value; });

      const payload: Parameters<typeof pushToCRM>[0] = {
        provider: selectedProvider,
        campaign_id: campaignId,
        test_mode: testMode,
        min_score: minScore > 0 ? minScore : undefined,
        tiers: selectedTiers.length > 0 ? selectedTiers : undefined,
        field_mapping: Object.keys(fieldMapping).length > 0 ? fieldMapping : undefined,
        custom_fields: Object.keys(customFieldsObj).length > 0 ? customFieldsObj : undefined,
      };

      if (selectedProvider === 'hubspot' && hubspotKey) {
        payload.api_key = hubspotKey;
      } else if (selectedProvider === 'salesforce') {
        if (sfAccessToken) payload.sf_access_token = sfAccessToken;
        if (sfInstanceUrl) payload.sf_instance_url = sfInstanceUrl;
        if (sfClientId) payload.sf_client_id = sfClientId;
        if (sfClientSecret) payload.sf_client_secret = sfClientSecret;
      }

      const result = await pushToCRM(payload);
      const campaign = campaigns.find((c) => c.id === campaignId);
      const record: CRMPushRecord = {
        provider: selectedProvider,
        campaign_id: campaignId,
        campaign_name: campaign?.name || campaignId,
        pushed_at: new Date().toISOString(),
        total: (result.created || 0) + (result.updated || 0) + (result.failed || 0),
        created: result.created || 0,
        updated: result.updated || 0,
        failed: result.failed || 0,
        crm_ids: result.crm_ids || [],
      };

      onPushComplete(record);
      setPushResult({ created: record.created, updated: record.updated, failed: record.failed });
    } catch (err: unknown) {
      setPushError(err instanceof Error ? err.message : 'Push failed');
    }
    setPushing(false);
  };

  return (
    <Card className="mb-8">
      <CardHeader>
        <CardTitle>Push Leads to CRM</CardTitle>
        <CardDescription>Select a campaign and configure targeting options to sync.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Provider Toggle */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Provider</label>
          <div className="flex gap-2">
            <Button
              onClick={() => setSelectedProvider('hubspot')}
              className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                selectedProvider === 'hubspot'
                  ? 'bg-orange-100 text-orange-700 ring-1 ring-orange-300'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
              variant={selectedProvider === 'hubspot' ? 'default' : 'outline'}
            >
              <CircleDot className="w-4 h-4" />
              HubSpot
            </Button>
            <Button
              onClick={() => setSelectedProvider('salesforce')}
              className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                selectedProvider === 'salesforce'
                  ? 'bg-blue-100 text-blue-700 ring-1 ring-blue-300'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
              variant={selectedProvider === 'salesforce' ? 'default' : 'outline'}
            >
              <Cloud className="w-4 h-4" />
              Salesforce
            </Button>
          </div>
        </div>

        {/* Source Campaign */}
        <div>
          <label htmlFor="crm-campaign" className="block text-sm font-medium text-gray-700 mb-2">
            Source Campaign
          </label>
          <select
            id="crm-campaign"
            value={campaignId}
            onChange={(e) => setCampaignId(e.target.value)}
            className="flex h-9 w-full rounded-md border border-[hsl(var(--input))] bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] focus-visible:ring-offset-1"
          >
            <option value="">Select a campaign...</option>
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} — {c.total_leads} leads ({c.status})
              </option>
            ))}
          </select>
        </div>

        {/* Targeting */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Targeting</label>
          <div className="bg-gray-50 rounded-lg p-4 space-y-4">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm text-gray-600">Minimum Score</span>
                <span className="text-sm font-medium text-gray-900">{minScore}</span>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full accent-brand-600"
                aria-label="Minimum Score"
              />
            </div>
            <div>
              <span className="text-sm text-gray-600 block mb-2">Tiers</span>
              <div className="flex gap-2">
                {TIERS.map((tier) => (
                  <button
                    key={tier}
                    onClick={() => handleTierToggle(tier)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                      selectedTiers.includes(tier)
                        ? tier === 'HOT'
                          ? 'bg-red-100 text-red-700 ring-1 ring-red-300'
                          : tier === 'WARM'
                          ? 'bg-amber-100 text-amber-700 ring-1 ring-amber-300'
                          : 'bg-blue-100 text-blue-700 ring-1 ring-blue-300'
                        : 'bg-gray-100 text-gray-500'
                    }`}
                  >
                    {tier}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Advanced — Field Mapping + Custom Fields */}
        <CollapsibleSection
          title="Advanced Settings"
          badge={`${Object.keys(fieldMapping).length} fields`}
          defaultOpen={false}
        >
          {/* Field Mapping */}
          <div className="mb-4">
            <h4 className="text-sm font-medium text-gray-700 mb-2">Field Mapping</h4>
            <div className="border border-gray-200 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left px-4 py-2 font-medium text-gray-500 text-xs">LeadFactory Field</th>
                    <th className="text-left px-4 py-2 font-medium text-gray-500 text-xs">CRM Field</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {Object.entries(fieldMapping).map(([lfField, crmField]) => (
                    <tr key={lfField} className="hover:bg-gray-50">
                      <td className="px-4 py-2 font-mono text-xs text-gray-700">{lfField}</td>
                      <td className="px-4 py-2">
                        {crmFields.length > 0 ? (
                          <select
                            value={crmField}
                            onChange={(e) => setFieldMapping({ ...fieldMapping, [lfField]: e.target.value })}
                            aria-label={`CRM field mapping for ${lfField}`}
                            className="flex h-8 w-full rounded-md border border-[hsl(var(--input))] bg-transparent px-2 py-1 text-xs shadow-sm"
                          >
                            <option value="">— unmapped —</option>
                            {crmFields.map((f) => (
                              <option key={f} value={f}>{f}</option>
                            ))}
                          </select>
                        ) : (
                          <Input
                            type="text"
                            value={crmField}
                            onChange={(e) => setFieldMapping({ ...fieldMapping, [lfField]: e.target.value })}
                            placeholder="CRM field name"
                            aria-label={`CRM field mapping for ${lfField}`}
                            className="w-full px-2 py-1 text-xs font-mono"
                          />
                        )}
                      </td>
                    </tr>
                  ))}
                  {Object.keys(fieldMapping).length === 0 && (
                    <tr>
                      <td colSpan={2} className="px-4 py-4 text-center text-xs text-gray-400">
                        No field mapping loaded. Connect a provider and defaults will appear.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              {Object.keys(defaultMapping).length > 0 && (
                <div className="px-4 py-2 border-t border-gray-200 bg-gray-50">
                  <button
                    onClick={() => setFieldMapping({ ...defaultMapping })}
                    className="text-xs text-blue-600 hover:text-blue-700 font-medium"
                  >
                    Reset to defaults
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Custom Fields */}
          <div>
            <h4 className="text-sm font-medium text-gray-700 mb-2">Custom Fields</h4>
            {customFields.map((cf, idx) => (
              <div key={idx} className="flex gap-2 mb-2">
                <Input
                  type="text"
                  value={cf.key}
                  onChange={(e) => updateCustomField(idx, 'key', e.target.value)}
                  placeholder="Field name"
                  className="font-mono"
                />
                <Input
                  type="text"
                  value={cf.value}
                  onChange={(e) => updateCustomField(idx, 'value', e.target.value)}
                  placeholder="Value"
                />
                <Button
                  onClick={() => removeCustomField(idx)}
                  variant="ghost"
                  size="icon"
                  title="Remove field"
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>
            ))}
            <button
              onClick={addCustomField}
              className="text-sm text-blue-600 hover:text-blue-700 font-medium"
            >
              + Add field
            </button>
          </div>
        </CollapsibleSection>

        {/* Error / Success */}
        {pushError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
            {pushError}
          </div>
        )}
        {pushResult && (
          <div className={`p-4 rounded-lg border text-sm ${
            pushResult.failed === 0
              ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
              : (pushResult.created > 0 || pushResult.updated > 0)
              ? 'bg-amber-50 border-amber-200 text-amber-700'
              : 'bg-red-50 border-red-200 text-red-600'
          }`}>
            <div className="font-medium mb-1">
              {pushResult.failed === 0
                ? 'Push Successful'
                : (pushResult.created > 0 || pushResult.updated > 0)
                ? 'Push Completed with Errors'
                : 'Push Failed'}
            </div>
            <div className="flex gap-6 text-xs">
              <span><strong>{pushResult.created}</strong> created</span>
              <span><strong>{pushResult.updated}</strong> updated</span>
              <span><strong>{pushResult.failed}</strong> failed</span>
            </div>
          </div>
        )}
      </CardContent>

      <CardFooter className="flex items-center justify-between gap-4 border-t">
        <label className="flex items-center gap-3 cursor-pointer">
          <div className="relative">
            <input
              type="checkbox"
              checked={testMode}
              onChange={(e) => setTestMode(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-10 h-5 bg-gray-200 peer-focus:ring-2 peer-focus:ring-brand-300 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-brand-600" />
          </div>
          <span className="text-sm font-medium text-gray-700">Test Mode</span>
          {testMode && (
            <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-amber-100 text-amber-700">
              Validates without pushing
            </span>
          )}
        </label>
        <Button
          onClick={handlePush}
          disabled={pushing || !campaignId}
          loading={pushing}
          size="lg"
        >
          {testMode ? 'Validate Mapping (Test Mode)' : 'Push to CRM'}
          {!pushing && <ArrowRight className="w-4 h-4" />}
        </Button>
      </CardFooter>
    </Card>
  );
}
