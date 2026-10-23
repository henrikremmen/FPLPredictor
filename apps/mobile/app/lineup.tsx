import { StyleSheet, Text, View } from "react-native";
import { RISK_PROFILE_LABELS, RISK_PROFILE_SCORE, formatPoints } from "@fplmodell/shared";
import { Screen } from "../src/components/Screen";
import { QueryState } from "../src/components/QueryState";
import { Card, Stat } from "../src/components/ui";
import { BenchStrip, PitchView } from "../src/components/PitchView";
import { useTeam } from "../src/hooks/useTeam";
import { typography, spacing } from "../src/theme";

export default function Pitch() {
  const team = useTeam();
  return (
    <Screen>
      <QueryState query={team}>
        {(data) => {
          const captain = data.lineup.starters.find((player) => player.role === "C");
          const vice = data.lineup.starters.find((player) => player.role === "VC");
          // Stable/Upside rank by a decision score, not expected points: show the number that decided.
          const scored = data.risk_profile !== "balanced";
          const score = RISK_PROFILE_SCORE[data.risk_profile];
          return (
            <>
              <View style={styles.header}>
                <Text style={typography.title}>{data.lineup.formation}</Text>
                <Text style={styles.subtitle}>GW{data.target_event} · optimal lineup</Text>
              </View>
              <Card>
                <View style={styles.statRow}>
                  <Stat label="Expected incl. captain" value={formatPoints(data.lineup.expected_total)} tone="positive" />
                  {scored ? <Stat label={`${score.label} incl. captain`} value={formatPoints(data.lineup.projected_total)} /> : null}
                  <Stat label="Captain margin" value={formatPoints(data.lineup.captain_margin)} />
                </View>
                <Text style={styles.caption}>
                  C {captain?.name ?? "–"} · VC {vice?.name ?? "–"}
                </Text>
                {scored ? (
                  <Text style={styles.caption}>
                    {RISK_PROFILE_LABELS[data.risk_profile]} profile: players are ranked by {score.label.toLowerCase()} = {score.formula}. The pitch shows that score.
                  </Text>
                ) : null}
              </Card>
              <PitchView starters={data.lineup.starters} valueOf={(player) => formatPoints(scored ? player.decision_points ?? player.recommended_points : player.recommended_points, 1)} />
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
