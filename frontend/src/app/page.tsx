import { AnalyticsPanel } from "@/components/cockpit/analytics-panel";
import { ChatPanel } from "@/components/cockpit/chat-panel";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";
import { ControlPlanePanel } from "@/components/cockpit/control-plane-panel";

export default function Home() {
  return (
    <>
      <CockpitDashboard />
      <ControlPlanePanel />
      <ChatPanel />
      <AnalyticsPanel />
    </>
  );
}
