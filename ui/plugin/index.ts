/**
 * Plugin frontend entry point for statement-tools.
 *
 * Consumed by YourFinanceWORKS's plugin system (ui/src/App.tsx glob import).
 * Pages are loaded from ui/shared/pages/ — DRY with the standalone SPA.
 */
import React from "react";
import type { PluginRouteConfig, PluginNavItem } from "@/types/plugin-routes";

export const pluginMetadata = {
  name: "statement-tools",
  displayName: "Statement Tools",
  version: "1.0.0",
  licenseTier: "agpl",
  description: "Merge, download, and manage bank statements.",
};

const MergeStatementsPage = React.lazy(() =>
  import("../shared/pages/MergeStatementsPage").then((m) => ({
    default: m.MergeStatementsPage,
  }))
);

export const pluginRoutes: PluginRouteConfig[] = [
  {
    path: "/statement-tools/merge",
    component: MergeStatementsPage,
    pluginId: "statement-tools",
    pluginName: "Statement Tools",
    label: "Merge Statements",
  },
];

export const navItems: PluginNavItem[] = [
  {
    id: "statement-tools",
    path: "/statement-tools/merge",
    label: "Merge Statements",
    icon: "GitMerge",
    priority: 45,
  },
];

export const pluginFeatures: string[] = ["merge_statements"];
