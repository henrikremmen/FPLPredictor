import { useState } from "react";
import { Text } from "react-native";
import { Screen } from "../../src/components/Screen";
import { usePullToRefresh } from "../../src/hooks/useFeatures";
import { Segmented } from "../../src/components/Segmented";
import { ComparePanel } from "../../src/panels/ComparePanel";
import { MarketPanel } from "../../src/panels/MarketPanel";
import { PreferencesPanel } from "../../src/panels/PreferencesPanel";
import { typography } from "../../src/theme";

type Panel = "market" | "compare" | "preferences";

export default function Players() {
  const pull = usePullToRefresh();
  const [panel, setPanel] = useState<Panel>("market");
  return (
    <Screen onRefresh={pull.onRefresh} refreshing={pull.refreshing}>
      <Text style={typography.title}>Players</Text>
      <Segmented value={panel} onChange={setPanel} options={[
        { value: "market", label: "Market" },
        { value: "compare", label: "Compare" },
        { value: "preferences", label: "Preferences" },
      ]} />
      {panel === "market" ? <MarketPanel /> : null}
      {panel === "compare" ? <ComparePanel /> : null}
      {panel === "preferences" ? <PreferencesPanel /> : null}
    </Screen>
  );
}
