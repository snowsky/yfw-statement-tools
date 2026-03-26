/**
 * Standalone app router for statement-tools.
 *
 * Routes:
 *   /        → redirect to /setup or /merge depending on config
 *   /setup   → SetupPage (configure API URL + key)
 *   /merge   → MergeStatementsPage
 */
import { Navigate, Route, Routes } from "react-router-dom";
import { MergeStatementsPage } from "@shared/pages/MergeStatementsPage";
import { SetupPage } from "@shared/pages/SetupPage";
import { loadSetupConfig } from "@shared/api";

function Root() {
  const { apiKey } = loadSetupConfig();
  return <Navigate to={apiKey ? "/merge" : "/setup"} replace />;
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Root />} />
      <Route
        path="/setup"
        element={<SetupPage onSaved={() => (window.location.href = "/merge")} />}
      />
      <Route path="/merge" element={<MergeStatementsPage />} />
    </Routes>
  );
}
