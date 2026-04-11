/**
 * Public usage tracking for iframe-embedded public pages.
 *
 * When the statement-tools public download page is embedded in the main YFW
 * app via an iframe, this module posts a message to the parent window so
 * the platform can track usage for billing/metering.
 */

export function recordPublicUsage(endpointKey: string, quantity = 1): void {
  if (window.parent === window) return // not in an iframe
  window.parent.postMessage(
    {
      type: 'plugin-public-usage',
      pluginId: 'statement-tools',
      endpointKey,
      quantity,
    },
    '*',
  )
}
