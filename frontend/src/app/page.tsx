import { AnalyticsPanel } from "@/components/cockpit/analytics-panel";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";

export default function Home() {
  return (
    <>
      <CockpitDashboard />
      <AnalyticsPanel />
    </>
  );
}
