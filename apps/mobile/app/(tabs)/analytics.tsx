import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { formatPercent, formatRank } from "@fplmodell/shared";
import type { AnalyticsDecisionPlayer, ManagerAnalytics } from "@fplmodell/api-client";
import { Screen } from "../../src/components/Screen";
import { QueryState } from "../../src/components/QueryState";
import { Segmented } from "../../src/components/Segmented";
import { Badge, Card, Section, Stat } from "../../src/components/ui";
import { useAnalytics } from "../../src/hooks/useFeatures";
import { colors, radii, spacing, typography } from "../../src/theme";

type Tab = "manager" | "gameweek" | "league" | "decisions";

export default function Analytics() {
  const [tab, setTab] = useState<Tab>("manager");
  const [event, setEvent] = useState<number | undefined>(undefined);
  const analytics = useAnalytics(event, null);

  return (
    <Screen>
      <Text style={typography.title}>Analyse</Text>
      <Segmented
        value={tab}
        onChange={setTab}
        options={[
          { value: "manager", label: "Manager" },
          { value: "gameweek", label: "GW" },
          { value: "league", label: "Miniliga" },
          { value: "decisions", label: "EO/Differensial" },
        ]}
      />
      <QueryState query={analytics}>
        {(data) => (
          <>
            <EventPicker data={data} selected={event} onSelect={setEvent} />
            {tab === "manager" ? <ManagerTab data={data} /> : null}
            {tab === "gameweek" ? <GameweekTab data={data} /> : null}
            {tab === "league" ? <LeagueTab data={data} /> : null}
            {tab === "decisions" ? <DecisionsTab data={data} /> : null}
          </>
        )}
      </QueryState>
    </Screen>
  );
}

function EventPicker({
  data,
  selected,
  onSelect,
}: {
  data: ManagerAnalytics;
  selected: number | undefined;
  onSelect: (event: number | undefined) => void;
}) {
  return (
    <View style={styles.eventRow}>
      {data.completed_events.slice(-8).map((event) => (
        <Pressable
          key={event}
          onPress={() => onSelect(event)}
          style={[styles.eventChip, (selected ?? data.selected_event) === event && styles.eventChipActive]}
        >
          <Text
            style={[
              styles.eventChipLabel,
              (selected ?? data.selected_event) === event && styles.eventChipLabelActive,
            ]}
          >
            GW{event}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

function ManagerTab({ data }: { data: ManagerAnalytics }) {
  return (
    <>
      <Card>
        <Text style={typography.eyebrow}>{data.team_name}</Text>
        <View style={styles.statRow}>
          <Stat label="Totalpoeng" value={String(data.summary.total_points)} />
          <Stat label="Rank" value={formatRank(data.summary.overall_rank)} />
          <Stat label="Persentil" value={data.summary.percentile != null ? formatPercent(100 - data.summary.percentile) : "–"} />
        </View>
        <View style={styles.statRow}>
          <Stat label="Snitt/GW" value={data.summary.average_points.toFixed(1)} />
          <Stat label="Mot globalt snitt" value={data.summary.points_vs_global_average.toFixed(1)} tone={data.summary.points_vs_global_average >= 0 ? "positive" : "negative"} />
        </View>
      </Card>
      <Section title="Global benchmark" subtitle={data.global_benchmark.sample_label}>
        <Card>
          <Text style={styles.caption}>
            {data.global_benchmark.sample_size} lag i utvalget · snitt {data.global_benchmark.sample_average_total ?? "–"}
          </Text>
          {data.global_benchmark.ownership.slice(0, 6).map((row) => (
            <View key={row.id} style={styles.watchRow}>
              <Text style={styles.body}>{row.name}</Text>
              <Text style={styles.caption}>{formatPercent(row.effective_ownership)} EO</Text>
            </View>
          ))}
        </Card>
      </Section>
      <Section title="Gameweek-logg">
        <Card>
          {data.timeline.slice(-8).map((row) => (
            <View key={row.event} style={styles.timelineRow}>
              <Text style={styles.body}>GW{row.event}</Text>
              <Text style={styles.body}>{row.points}p</Text>
              <Text style={[styles.caption, { color: row.vs_average >= 0 ? colors.accent : colors.danger }]}>
                {row.vs_average >= 0 ? "+" : ""}
                {row.vs_average.toFixed(0)} vs snitt
              </Text>
            </View>
          ))}
        </Card>
      </Section>
    </>
  );
}

function GameweekTab({ data }: { data: ManagerAnalytics }) {
  const gw = data.gameweek;
  return (
    <>
      <Card>
        <Text style={typography.eyebrow}>GW{gw.event}</Text>
        <Text style={typography.heading}>{gw.points} poeng</Text>
        <Text style={styles.caption}>Tapt benkpoeng: {gw.missed_bench_points}</Text>
      </Card>
      <Section title="Beste bidragsytere">
        <Card>
          {gw.best_contributors.map((player) => (
            <View key={player.id} style={styles.watchRow}>
              <Text style={styles.body}>{player.name}</Text>
              <Text style={styles.caption}>{player.effective_points}p</Text>
            </View>
          ))}
        </Card>
      </Section>
      <Section title="Gevinst mot liga">
        <Card>
          {gw.top_gains.map((row) => (
            <View key={row.id} style={styles.watchRow}>
              <Text style={styles.body}>{row.name}</Text>
              <Text style={[styles.caption, { color: colors.accent }]}>+{row.league_swing.toFixed(1)}</Text>
            </View>
          ))}
          {gw.top_losses.map((row) => (
            <View key={row.id} style={styles.watchRow}>
              <Text style={styles.body}>{row.name}</Text>
              <Text style={[styles.caption, { color: colors.danger }]}>{row.league_swing.toFixed(1)}</Text>
            </View>
          ))}
        </Card>
      </Section>
    </>
  );
}

function LeagueTab({ data }: { data: ManagerAnalytics }) {
  if (!data.league) {
    return (
      <Card>
        <Text style={styles.caption}>Ingen miniliga tilgjengelig for dette laget ennå.</Text>
      </Card>
    );
  }
  const league = data.league;
  return (
    <>
      <Card>
        <Text style={typography.eyebrow}>{league.name}</Text>
        <View style={styles.statRow}>
          <Stat label="Din rank" value={formatRank(league.your_rank)} />
          <Stat label="Gap til leder" value={league.gap_to_leader != null ? String(league.gap_to_leader) : "–"} />
          <Badge label={league.mode} />
        </View>
        <Text style={styles.caption}>{league.advice}</Text>
      </Card>
      <Section title="Tabell">
        <Card>
          {league.standings.slice(0, 10).map((row) => (
            <View key={row.entry} style={styles.watchRow}>
              <Text style={[styles.body, row.is_you && { color: colors.accent }]}>
                {row.rank ?? "–"}. {row.team_name}
              </Text>
              <Text style={styles.caption}>{row.total_points}p</Text>
            </View>
          ))}
        </Card>
      </Section>
    </>
  );
}

function DecisionRow({ player }: { player: AnalyticsDecisionPlayer }) {
  return (
    <View style={styles.watchRow}>
      <Text style={styles.body}>{player.name}</Text>
      <Text style={styles.caption}>
        Liga-EO {formatPercent(player.league_effective_ownership)} · Topp-EO {formatPercent(player.top10k_effective_ownership)}
      </Text>
    </View>
  );
}

function DecisionsTab({ data }: { data: ManagerAnalytics }) {
  const decisions = data.decisions;
  return (
    <>
      <Section title="Differensialer">
        <Card>
          {decisions.differentials.map((player) => (
            <DecisionRow key={player.id} player={player} />
          ))}
        </Card>
      </Section>
      <Section title="Rank-trusler">
        <Card>
          {decisions.threats.map((player) => (
            <DecisionRow key={player.id} player={player} />
          ))}
        </Card>
      </Section>
      <Section title="Kapteinsmatrise">
        <Card>
          {decisions.captain_matrix.map((player) => (
            <DecisionRow key={player.id} player={player} />
          ))}
        </Card>
      </Section>
    </>
  );
}

const styles = StyleSheet.create({
  eventRow: { flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" },
  eventChip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: radii.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  eventChipActive: { backgroundColor: colors.accent, borderColor: colors.accent },
  eventChipLabel: { fontSize: 12, fontWeight: "700", color: colors.textSecondary },
  eventChipLabelActive: { color: "#06231A" },
  statRow: { flexDirection: "row", gap: spacing.lg, flexWrap: "wrap" },
  caption: { ...typography.caption },
  body: { ...typography.body },
  watchRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
  timelineRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
});
