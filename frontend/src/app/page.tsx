import { AnalyticsPanel } from "@/components/cockpit/analytics-panel";
import { ChatPanel } from "@/components/cockpit/chat-panel";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";

export default function Home() {
  return (
    <>
      <CockpitDashboard />
      <ChatPanel />
      <AnalyticsPanel />
    </>
  );
}
