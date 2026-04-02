/**
 * Statement Tools — plugin page for YourFinanceWORKS.
 * 
 * This component acts as a wrapper for the shared UploadStatementsPage,
 * ensuring the plugin remains DRY while being self-contained.
 */

import React from "react";
import { UploadStatementsPage } from "../../shared/ui/pages/UploadStatementsPage";

export default function StatementToolsPage() {
  return <UploadStatementsPage />;
}
