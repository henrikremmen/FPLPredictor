import { useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { Screen } from "../src/components/Screen";
import { QueryState } from "../src/components/QueryState";
import { Segmented } from "../src/components/Segmented";
import { Card } from "../src/components/ui";
import { useSession } from "../src/context/session-context";
import { api } from "../src/lib/api";
import { colors, spacing, typography } from "../src/theme";

/** U16: same ticker as the web Players → Fixtures page; scrolls sideways per Gameweek. */
export default function FixturesScreen() {
  const { sessionId } = useSession();
  const [scope, setScope] = useState<"squad" | "market">("squad");
  const ticker = useQuery({
    queryKey: ["fixtures", sessionId, scope],
    queryFn: () => api.fixtures(sessionId as string, scope),
    enabled: Boolean(sessionId),
  });
  return (
    <Screen>
      <Segmented value={scope} onChange={setScope} options={[
        { value: "squad", label: "Your squad" }, { value: "market", label: "Best not owned" }]} />
      <QueryState query={ticker}>
        {(data) => (
          <Card>
            <ScrollView horizontal>
              <View>
                <View style={styles.row}>
                  <Text style={[styles.name, styles.head]}>Player</Text>
                  {data.events.map((gw) => <Text key={gw} style={[styles.cell, styles.head]}>GW{gw}</Text>)}
                </View>
                {data.players.map((player) => (
                  <View key={player.id} style={styles.row}>
                    <View style={styles.name}>
                      <Text style={typography.body} numberOfLines={1}>{player.name}</Text>
                      <Text style={styles.caption}>{player.position} · {player.team}</Text>
                    </View>
                    {player.weeks.map((week) => (
                      <View key={week.event} style={styles.cell}>
                        <Text style={[styles.opponent, week.fixtures === 0 && { color: colors.warning }]} numberOfLines={2}>
                          {week.fixtures === 0 ? "Blank" : week.opponent}
                        </Text>
                        {week.fixtures > 1 ? <Text style={styles.double}>Double</Text> : null}
                        {week.fixtures > 0 ? (
                          <Text style={styles.caption}>{week.xp.toFixed(1)} pts{week.p60 != null ? ` · 60+ ${(week.p60 * 100).toFixed(0)}%` : ""}</Text>
                        ) : null}
                      </View>
                    ))}
                  </View>
                ))}
              </View>
            </ScrollView>
            <Text style={styles.caption}>{data.note}</Text>
          </Card>
        )}
      </QueryState>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, paddingVertical: spacing.xs },
  name: { width: 120, paddingRight: spacing.sm },
  cell: { width: 96, paddingRight: spacing.sm, gap: 2 },
  head: { ...typography.caption, fontWeight: "700" },
  opponent: { ...typography.caption, color: colors.textPrimary },
  double: { ...typography.caption, color: colors.accent, fontWeight: "700" },
  caption: { ...typography.caption },
});
