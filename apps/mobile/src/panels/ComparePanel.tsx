import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { Player } from "@fplmodell/api-client";
import { formatMoney, formatPoints, formatSigned } from "@fplmodell/shared";
import { QueryState } from "../components/QueryState";
import { Button, Card, Section } from "../components/ui";
import { useWorkspace } from "../context/workspace-context";
import { useComparePlayers } from "../hooks/useFeatures";
import { useSquadOptions, useTeam } from "../hooks/useTeam";
import { colors, spacing, typography } from "../theme";

/** Keep one player or buy another in the same position, after selling price, bank and hits. */
export function ComparePanel() {
  const team = useTeam();
  const options = useSquadOptions();
  const workspace = useWorkspace();
  const compare = useComparePlayers();
  const [outId, setOutId] = useState<number | null>(null);
  const [inId, setInId] = useState<number | null>(null);

  return (
    <QueryState query={team}>
      {(data) => {
        const out = data.squad.find((player) => player.id === outId);
        const owned = new Set(data.squad.map((player) => player.id));
        const result = compare.data;
        return (
          <>
            <Section title="Player to keep or sell">
              <Card>
                {data.squad.map((player) => (
                  <Choice key={player.id} player={player} selected={player.id === outId}
                    onPress={() => { setOutId(player.id); setInId(null); compare.reset(); }} />
                ))}
              </Card>
            </Section>
            {out ? (
              <Section title={`Player to buy (${out.position})`} subtitle="Top forecasts not in your squad">
                <QueryState query={options}>
                  {({ players }) => (
                    <Card>
                      {players
                        .filter((player) => player.position === out.position && !owned.has(player.id)
                          && !workspace.constraints.excluded_ids.includes(player.id))
                        .sort((a, b) => b.recommended_points - a.recommended_points)
                        .slice(0, 12)
                        .map((player) => (
                          <Choice key={player.id} player={player} selected={player.id === inId}
                            onPress={() => { setInId(player.id); compare.reset(); }} />
                        ))}
                    </Card>
                  )}
                </QueryState>
              </Section>
            ) : null}
            <Button label="Compare after hits" disabled={!outId || !inId} loading={compare.isPending}
              onPress={() => outId && inId && compare.mutate({ outId, inId })} />
            {compare.isError ? <Text style={styles.error}>{(compare.error as Error).message}</Text> : null}
            {result ? (
              <Card>
                <Text style={typography.eyebrow}>{result.out} → {result.in}</Text>
                <Text style={[styles.net, { color: result.net_gain >= 0 ? colors.accent : colors.danger }]}>
                  {formatSigned(result.net_gain, 2)} net expected points
                </Text>
                <Text style={styles.caption}>
                  Keep {formatPoints(result.hold_points)} · Buy {formatPoints(result.buy_points)} · Hit −{result.hit} · Bank after {formatMoney(result.bank_after)}
                </Text>
                {result.weeks.map((week) => (
                  <View key={week.event} style={styles.week}>
                    <Text style={styles.weekLabel}>GW{week.event}</Text>
                    <Text style={styles.caption}>{formatPoints(week.hold)} → {formatPoints(week.buy)}</Text>
                    <Text style={styles.weekGain}>{formatSigned(week.gain, 2)}</Text>
                  </View>
                ))}
                <Text style={styles.caption}>{result.caveat}</Text>
                <Button label="Save plan" variant="secondary" onPress={() => workspace.savePlan({
                  kind: "comparison", name: `${result.out} → ${result.in}`, horizon: data.horizon, net_gain: result.net_gain,
                  summary: `Net ${formatSigned(result.net_gain, 2)} after ${result.hit ? `−${result.hit} hit` : "no hit"}`,
                  lines: [`Keep: ${formatPoints(result.hold_points)}`, `Buy: ${formatPoints(result.buy_points)}`,
                    `Bank after: ${formatMoney(result.bank_after)}`],
                })} />
              </Card>
            ) : null}
          </>
        );
      }}
    </QueryState>
  );
}

function Choice({ player, selected, onPress }: { player: Player; selected: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={styles.choice} accessibilityRole="radio" accessibilityState={{ checked: selected }}
      accessibilityLabel={`${player.name}, ${player.position}, ${formatMoney(player.price)}`}>
      <Text style={[styles.choiceName, selected && { color: colors.accent }]}>{selected ? "● " : "○ "}{player.name}</Text>
      <Text style={styles.caption}>{player.team} · {formatMoney(player.price)}</Text>
      <Text style={styles.points}>{formatPoints(player.recommended_points, 1)}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  choice: { minHeight: 44, flexDirection: "row", alignItems: "center", gap: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  choiceName: { ...typography.body, flex: 1 },
  points: { color: colors.accent, fontWeight: "700", minWidth: 36, textAlign: "right" },
  caption: typography.caption,
  net: { fontSize: 22, fontWeight: "800", marginVertical: spacing.xs },
  week: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.xs },
  weekLabel: { ...typography.body, fontWeight: "700", width: 48 },
  weekGain: { ...typography.body, marginLeft: "auto", fontWeight: "700" },
  error: { color: colors.danger },
});
