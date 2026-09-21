import { StyleSheet, Text, View } from "react-native";
import { formatPoints } from "@fplmodell/shared";
import { Screen } from "../../src/components/Screen";
import { QueryState } from "../../src/components/QueryState";
import { Card, Stat } from "../../src/components/ui";
import { BenchStrip, PitchView } from "../../src/components/PitchView";
import { useTeam } from "../../src/hooks/useTeam";
import { typography, spacing } from "../../src/theme";

export default function Pitch() {
  const team = useTeam();
  return (
    <Screen>
      <QueryState query={team}>
        {(data) => {
          const captain = data.lineup.starters.find((player) => player.role === "C");
          const vice = data.lineup.starters.find((player) => player.role === "VC");
          return (
            <>
              <View style={styles.header}>
                <Text style={typography.title}>{data.lineup.formation}</Text>
                <Text style={styles.subtitle}>GW{data.target_event} · optimalt laguttak</Text>
              </View>
              <Card>
                <View style={styles.statRow}>
                  <Stat label="Forventet" value={formatPoints(data.lineup.expected_total)} tone="positive" />
                  <Stat label="Prognose (m/ kaptein)" value={formatPoints(data.lineup.projected_total)} />
                  <Stat label="Kapteinsmargin" value={formatPoints(data.lineup.captain_margin)} />
                </View>
                <Text style={styles.caption}>
                  C {captain?.name ?? "–"} · VC {vice?.name ?? "–"}
                </Text>
              </Card>
              <PitchView starters={data.lineup.starters} />
              <BenchStrip bench={data.lineup.bench} />
            </>
          );
        }}
      </QueryState>
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { gap: 2 },
  subtitle: { ...typography.caption },
  statRow: { flexDirection: "row", gap: spacing.lg, flexWrap: "wrap" },
  caption: { ...typography.caption },
});
