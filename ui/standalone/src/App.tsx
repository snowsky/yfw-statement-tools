/**
 * Standalone app router for statement-tools.
 *
 * Routes:
 *   /        → redirect to /setup or /upload depending on config
 *   /setup   → SetupPage (configure API URL + key)
 *   /upload  → UploadStatementsPage
 */
import { Navigate, Route, Routes } from "react-router-dom";
import { UploadStatementsPage } from "@shared/pages/UploadStatementsPage";
import { SetupPage } from "@shared/pages/SetupPage";
import { loadSetupConfig } from "@shared/api";

function Root() {
  const { apiKey } = loadSetupConfig();
  return <Navigate to={apiKey ? "/upload" : "/setup"} replace />;
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Root />} />
      <Route
        path="/setup"
        element={<SetupPage onSaved={() => (window.location.href = "/upload")} />}
      />
      <Route path="/upload" element={<UploadStatementsPage />} />
    </Routes>
  );
}
