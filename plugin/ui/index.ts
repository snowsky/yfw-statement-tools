/**
 * Statement Tools — YourFinanceWORKS plugin entry point.
 *
 * Consumed by App.tsx via:
 *   import.meta.glob("./plugins/*/index.ts", { eager: true })
 *
 * The component is a lazy-loaded default export from StatementToolsPage.tsx.
 * All API calls target /api/v1/statement-tools/* on the same YFW origin —
 * no separate service URL needed when running in plugin mode.
 */
import React from "react";
import { FileSpreadsheet } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { PluginRouteConfig, PluginNavItem } from "@/types/plugin-routes";

// ---------------------------------------------------------------------------
// Page component (lazy — loaded only when the user navigates to the route)
// ---------------------------------------------------------------------------
const StatementToolsPage = React.lazy(() => import("./StatementToolsPage"));

// ---------------------------------------------------------------------------
// Plugin metadata
// ---------------------------------------------------------------------------
export const pluginMetadata = {
  name: "statement-tools",
  displayName: "Statement Tools",
  version: "1.0.0",
  licenseTier: "agpl",
  description: "Upload bank statements (CSV/PDF), extract transactions via YFW AI, and download a merged CSV.",
};

// ---------------------------------------------------------------------------
// Route configuration
// ---------------------------------------------------------------------------
export const pluginRoutes: PluginRouteConfig[] = [
  {
    path: "/statement-tools",
    component: StatementToolsPage,
    pluginId: "statement-tools",
    pluginName: "Statement Tools",
    label: "Statement Tools",
  },
];

// ---------------------------------------------------------------------------
// Sidebar nav item
// ---------------------------------------------------------------------------
export const navItems: PluginNavItem[] = [
  {
    id: "statement-tools",
    path: "/statement-tools",
    label: "Statement Tools",
    icon: "FileSpreadsheet",
    priority: 5,
    tourId: "nav-statement-tools",
  },
];

// ---------------------------------------------------------------------------
// Plugin icons — merged into the main app's icon registry at runtime so
// this plugin never requires changes to plugin-icons.ts.
// ---------------------------------------------------------------------------
export const pluginIcons: Record<string, LucideIcon> = {
  FileSpreadsheet,
};

// ---------------------------------------------------------------------------
// Plugin features
// ---------------------------------------------------------------------------
export const pluginFeatures = [
  "bank-statement-upload",
  "ai-transaction-extraction",
  "csv-export",
  "batch-processing",
];
