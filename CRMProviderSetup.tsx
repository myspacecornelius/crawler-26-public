import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { CircleDot, Cloud, Check, AlertCircle } from 'lucide-react';
import { getCRMFields } from '@/lib/api';

export function CRMProviderSetup() {
  const [hubspotKey, setHubspotKey] = useState('');
  const [sfInstance, setSfInstance] = useState('');
  const [sfToken, setSfToken] = useState('');
  
  const [hubspotStatus, setHubspotStatus] = useState<'idle' | 'connected' | 'error'>('idle');
  const [sfStatus, setSfStatus] = useState<'idle' | 'connected' | 'error'>('idle');
  const [loading, setLoading] = useState<string | null>(null);

  useEffect(() => {
    const storedHs = localStorage.getItem('crm_hubspot_api_key');
    if (storedHs) {
      setHubspotKey(storedHs);
      setHubspotStatus('connected'); // Assume connected if key exists
    }
    
    const storedSfUrl = localStorage.getItem('crm_sf_instance_url');
    const storedSfToken = localStorage.getItem('crm_sf_access_token');
    if (storedSfUrl && storedSfToken) {
      setSfInstance(storedSfUrl);
      setSfToken(storedSfToken);
      setSfStatus('connected');
    }
  }, []);

  const testConnection = async (provider: 'hubspot' | 'salesforce') => {
    setLoading(provider);
    try {
      // In a real app, we'd pass the key to the test endpoint. 
      // Here we simulate by fetching fields which requires auth.
      // Note: The backend might need the key in headers if not env var.
      // For this demo, we assume the backend handles it or we'd pass it in headers.
      await getCRMFields(provider, true);
      
      if (provider === 'hubspot') {
        localStorage.setItem('crm_hubspot_api_key', hubspotKey);
        setHubspotStatus('connected');
      } else {
        localStorage.setItem('crm_sf_instance_url', sfInstance);
        localStorage.setItem('crm_sf_access_token', sfToken);
        setSfStatus('connected');
      }
    } catch (err) {
      console.error(err);
      if (provider === 'hubspot') setHubspotStatus('error');
      else setSfStatus('error');
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
      {/* HubSpot */}
      <Card className="border-l-4 border-l-[#ff7a59]">
        <CardHeader>
          <div className="flex justify-between items-start">
            <div className="flex items-center gap-2">
              <CircleDot className="h-6 w-6 text-[#ff7a59]" />
              <CardTitle>HubSpot</CardTitle>
            </div>
            {hubspotStatus === 'connected' && <Badge variant="success">Connected</Badge>}
            {hubspotStatus === 'error' && <Badge variant="destructive">Error</Badge>}
          </div>
          <CardDescription>Connect via Private App Access Token</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Access Token</label>
            <Input 
              type="password" 
              placeholder="pat-na1-..." 
              value={hubspotKey}
              onChange={(e) => setHubspotKey(e.target.value)}
            />
          </div>
          <Button 
            variant="outline" 
            className="w-full"
            onClick={() => testConnection('hubspot')}
            isLoading={loading === 'hubspot'}
            disabled={!hubspotKey}
          >
            {hubspotStatus === 'connected' ? 'Test Again' : 'Connect HubSpot'}
          </Button>
        </CardContent>
      </Card>

      {/* Salesforce */}
      <Card className="border-l-4 border-l-[#00a1e0]">
        <CardHeader>
          <div className="flex justify-between items-start">
            <div className="flex items-center gap-2">
              <Cloud className="h-6 w-6 text-[#00a1e0]" />
              <CardTitle>Salesforce</CardTitle>
            </div>
            {sfStatus === 'connected' && <Badge variant="success">Connected</Badge>}
            {sfStatus === 'error' && <Badge variant="destructive">Error</Badge>}
          </div>
          <CardDescription>Connect via Instance URL & Access Token</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Instance URL</label>
            <Input 
              placeholder="https://your-domain.my.salesforce.com" 
              value={sfInstance}
              onChange={(e) => setSfInstance(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Access Token</label>
            <Input 
              type="password" 
              placeholder="Session ID or OAuth Token" 
              value={sfToken}
              onChange={(e) => setSfToken(e.target.value)}
            />
          </div>
          <Button 
            variant="outline" 
            className="w-full"
            onClick={() => testConnection('salesforce')}
            isLoading={loading === 'salesforce'}
            disabled={!sfInstance || !sfToken}
          >
            {sfStatus === 'connected' ? 'Test Again' : 'Connect Salesforce'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}