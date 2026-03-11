import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { ArrowRight, Settings2 } from 'lucide-react';
import { pushToCRM, getDefaultFieldMapping } from '@/lib/api';

// Mock campaign type
interface Campaign {
  id: string;
  name: string;
  lead_count: number;
}

export function CRMPushForm() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]); // Would fetch from API
  const [selectedCampaign, setSelectedCampaign] = useState('');
  const [provider, setProvider] = useState('hubspot');
  const [testMode, setTestMode] = useState(true);
  const [loading, setLoading] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Mock fetching campaigns
  useEffect(() => {
    // In real app: listCampaigns().then(setCampaigns)
    setCampaigns([
      { id: '1', name: 'Q1 VC Outreach', lead_count: 5108 },
      { id: '2', name: 'SaaS Founders', lead_count: 1204 },
    ]);
  }, []);

  const handlePush = async () => {
    if (!selectedCampaign) return;
    
    setLoading(true);
    try {
      const campaign = campaigns.find(c => c.id === selectedCampaign);
      
      const result = await pushToCRM({
        provider,
        campaign_id: selectedCampaign,
        test_mode: testMode,
        // In real app, we'd pass field_mapping and custom_fields here
      });

      // Save to history
      const historyItem = {
        provider,
        campaign_id: selectedCampaign,
        campaign_name: campaign?.name || 'Unknown',
        pushed_at: new Date().toISOString(),
        total: result.total || 0,
        created: result.created || 0,
        updated: result.updated || 0,
        failed: result.failed || 0,
        crm_ids: result.crm_ids || []
      };

      const existing = JSON.parse(localStorage.getItem('crm_push_history') || '[]');
      localStorage.setItem('crm_push_history', JSON.stringify([historyItem, ...existing]));
      
      // Trigger a reload of history (in a real app, use context or event bus)
      window.location.reload(); 

    } catch (e) {
      console.error(e);
      alert('Push failed. Check console.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="mb-8">
      <CardHeader>
        <CardTitle>Push Leads</CardTitle>
        <CardDescription>Sync campaign data to your CRM</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-sm font-medium">Source Campaign</label>
            <select 
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
              value={selectedCampaign}
              onChange={(e) => setSelectedCampaign(e.target.value)}
            >
              <option value="">Select a campaign...</option>
              {campaigns.map(c => (
                <option key={c.id} value={c.id}>{c.name} ({c.lead_count} leads)</option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Target Provider</label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 border rounded-md p-2 px-4 cursor-pointer hover:bg-gray-50 flex-1">
                <input 
                  type="radio" 
                  name="provider" 
                  value="hubspot" 
                  checked={provider === 'hubspot'}
                  onChange={(e) => setProvider(e.target.value)}
                />
                HubSpot
              </label>
              <label className="flex items-center gap-2 border rounded-md p-2 px-4 cursor-pointer hover:bg-gray-50 flex-1">
                <input 
                  type="radio" 
                  name="provider" 
                  value="salesforce" 
                  checked={provider === 'salesforce'}
                  onChange={(e) => setProvider(e.target.value)}
                />
                Salesforce
              </label>
            </div>
          </div>
        </div>

        <div className="pt-2">
          <Button 
            variant="ghost" 
            size="sm" 
            className="text-gray-500"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            <Settings2 className="h-4 w-4 mr-2" />
            {showAdvanced ? 'Hide' : 'Show'} Advanced Mapping
          </Button>
          
          {showAdvanced && (
            <div className="mt-4 p-4 bg-gray-50 rounded-md border border-gray-200 text-sm text-gray-500">
              Field mapping configuration would go here (collapsed for brevity).
            </div>
          )}
        </div>
      </CardContent>
      <CardFooter className="flex justify-between border-t bg-gray-50/50 p-6">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={testMode} onChange={(e) => setTestMode(e.target.checked)} />
          Test Mode (Validate only)
        </label>
        <Button onClick={handlePush} disabled={!selectedCampaign || loading} isLoading={loading}>
          Push to {provider === 'hubspot' ? 'HubSpot' : 'Salesforce'}
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </CardFooter>
    </Card>
  );
}