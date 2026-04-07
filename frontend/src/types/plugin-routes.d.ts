/**
 * Types for the YFW plugin route/nav integration contract.
 * These mirror the shapes expected by the main app's PluginContext.
 */

export interface PluginRouteConfig {
  path: string;
  component: (props: any) => React.ReactElement | null;
  pluginId: string;
  pluginName: string;
  label?: string;
}

export interface PluginNavItem {
  id: string;
  path: string;
  label: string;
  icon?: string;
  priority?: number;
}
