'use client';

import { CRMProviderSetup } from '@/components/crm/CRMProviderSetup';
import { CRMPushForm } from '@/components/crm/CRMPushForm';
import { CRMPushHistory } from '@/components/crm/CRMPushHistory';

export default function CRMPage() {
  return (
    <div className="max-w-5xl mx-auto py-8 px-4 space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-gray-900">CRM Integration</h1>
        <p className="text-gray-500 mt-1">Sync your leads to HubSpot or Salesforce.</p>
      </div>

      <CRMProviderSetup />
      
      <CRMPushForm />
      
      <CRMPushHistory />
    </div>
  );
}