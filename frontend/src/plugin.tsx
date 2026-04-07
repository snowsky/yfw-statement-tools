/**
 * Statement Tools — YourFinanceWORKS plugin entry point.
 *
 * Consumed by the main YFW app via:
 *   import.meta.glob("./plugins/[*]/index.ts", { eager: true })
 *
 * In sidecar mode, all API calls target /api/v1/statement-tools/* on
 * the same YFW origin — no separate service URL needed.
 */
import React from 'react'
import { FileSpreadsheet } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { PluginRouteConfig, PluginNavItem } from '@/types/plugin-routes'
import PluginLayout from './components/layout/PluginLayout'
import './index.css'

export const pluginMetadata = {
  name: 'statement-tools',
  displayName: 'Statement Tools',
  version: '1.0.0',
  licenseTier: 'agpl',
  description: 'Upload bank statements (CSV/PDF), extract transactions via YFW AI, and download a merged CSV.',
}

// Lazy-load pages
const UploadPage = React.lazy(() => import('./pages/UploadPage'))
const PublicDownloadPage = React.lazy(() => import('./pages/PublicDownloadPage'))

// Helper to wrap component with layout
const withLayout = (Component: React.ComponentType) => (props: unknown) => (
  <PluginLayout>
    <Component {...(props as object)} />
  </PluginLayout>
)

export const pluginRoutes: PluginRouteConfig[] = [
  {
    path: '/statement-tools',
    component: withLayout(UploadPage),
    pluginId: 'statement-tools',
    pluginName: 'Statement Tools',
    label: 'Statement Tools',
  },
  {
    path: '/statement-tools/public',
    component: withLayout(PublicDownloadPage),
    pluginId: 'statement-tools',
    pluginName: 'Statement Tools',
    label: 'Download Statement',
  },
]

export const navItems: PluginNavItem[] = [
  {
    id: 'statement-tools',
    path: '/statement-tools',
    label: 'Statement Tools',
    icon: 'FileSpreadsheet',
    priority: 5,
  },
]

export const pluginIcons: Record<string, LucideIcon> = {
  FileSpreadsheet,
}

export const pluginFeatures: string[] = [
  'bank-statement-upload',
  'ai-transaction-extraction',
  'csv-export',
  'batch-processing',
]
