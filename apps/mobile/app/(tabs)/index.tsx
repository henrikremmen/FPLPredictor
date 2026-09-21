import { useState } from "react";
import { RefreshControl, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import { ApiError, type TeamResponse } from "@fplmodell/api-client";
import { formatDeadline, formatMoney, formatPoints, formatRank } from "@fplmodell/shared";
import { Screen } from "../../src/components/Screen";
import { QueryState } from "../../src/components/QueryState";
import { Badge, Button, Card, Section, Stat } from "../../src/components/ui";
import { PlayerRow } from "../../src/components/PlayerRow";
import { useRefreshTeam, useTeam } from "../../src/hooks/useTeam";
import { colors, spacing, typography } from "../../src/theme";

export default function Overview() {
  const team = useTeam();
  const refresh = useRefreshTeam();
  const [refreshError, setRefreshError] = useState<string | null>(null);

  const onRefresh = () => {
    setRefreshError(null);
    refresh.mutate(undefined, {
      onError: (error) => {
        setRefreshError(error instanceof ApiError ? error.message : "Kunne ikke oppdatere prognosen.");
      },
    });
  };

  return (
    <Screen
      refreshControl={
        <RefreshControl refreshing={refresh.isPending} onRefresh={onRefresh} tintColor={colors.accent} />
      }
    >
      <QueryState query={team}>
        {(data) => <OverviewContent team={data} refreshing={refresh.isPending} refreshError={refreshError} />}
      </QueryState>
    </Screen>
  );
}

function OverviewContent({
  team,
  refreshing,
  refreshError,
}: {
  team: TeamResponse;
  refreshing: boolean;
  refreshError: string | null;
}) {
  return (
    <>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={typography.title}>{team.team_name}</Text>
          <Text style={styles.subtitle}>
            {team.manager_name} · GW{team.target_event}
          </Text>
        </View>
        {team.squad_source === "manual_override" ? <Badge label="Korrigert" tone="warning" /> : null}
      </View>

      {refreshError ? <Text style={styles.error}>{refreshError}</Text> : null}
      {refreshing ? <Text style={styles.caption}>Henter nytt offentlig snapshot, kan ta rundt ett minutt…</Text> : null}

      <Card>
        <Text style={typography.eyebrow}>Deadline GW{team.target_event}</Text>
        <Text style={typography.heading}>{formatDeadline(team.deadline)}</Text>
        <View style={styles.statRow}>
          <Stat label="Bank" value={formatMoney(team.bank)} />
          <Stat label="Gratisbytter" value={String(team.free_transfers)} />
          <Stat label="Lagverdi" value={formatMoney(team.team_value ?? null)} />
        </View>
        <View style={styles.statRow}>
          <Stat label="Poeng" value={team.overall_points != null ? String(team.overall_points) : "–"} />
          <Stat label="Rank" value={formatRank(team.overall_rank)} />
        </View>
      </Card>

      <Card>
        <Text style={typography.eyebrow}>Anbefalt laguttak</Text>
        <Text style={typography.heading}>{team.lineup.formation}</Text>
        <View style={styles.statRow}>
          <Stat label="Forventet" value={formatPoints(team.lineup.expected_total)} tone="positive" />
          <Stat label="Kapteinsmargin" value={formatPoints(team.lineup.captain_margin)} />
        </View>
        <Button label="Se pitch og benk" variant="secondary" onPress={() => router.push("/(tabs)/pitch")} />
      </Card>

      <Section title="Tropp" subtitle={`${team.squad.length} spillere`}>
        <Card>
          {team.squad.map((player) => (
            <PlayerRow key={player.id} player={player} />
          ))}
        </Card>
      </Section>

      <Button label="Korriger lag, bank eller bytter" variant="secondary" onPress={() => router.push("/correction")} />
    </>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  subtitle: { ...typography.caption },
  caption: { ...typography.caption },
  error: { ...typography.caption, color: colors.danger },
  statRow: { flexDirection: "row", gap: spacing.lg },
});
