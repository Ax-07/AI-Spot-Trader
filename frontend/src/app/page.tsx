import { CockpitShell } from "@/components/cockpit/cockpit-shell";
import { MarketAttentionDock } from "@/components/cockpit/market-attention-dock";

export default function Home() {
  return (
    <>
      <CockpitShell />
      <MarketAttentionDock />
    </>
  );
}
