import { useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import type { CopyCheck, TopCohort, TopManagers } from "@fplmodell/api-client";
import { formatRank, FPL_CHIP_NAMES } from "@fplmodell/shared";
import { Screen } from "../src/components/Screen";
import { QueryState } from "../src/components/QueryState";
import { Segmented } from "../src/components/Segmented";
import { Card, Section, Stat } from "../src/components/ui";
import { useCopyCheck, useTopManagers } from "../src/hooks/useFeatures";
import { colors, spacing, typography } from "../src/theme";

const TARGET: Record<TopCohort, string> = { top100: "top 100", legacy: "legacy median", top1pct: "top 1%", youtubers: "YouTuber median" };
const role = (m: number | null) => (m == null ? "–" : m >= 3 ? "TC" : m === 2 ? "C" : m === 1 ? "XI" : "Bench");

/** Top 100, the all-time legacy 100 and the top 1%: what they did and how close your squad is. */
export default function TopManagersScreen() {
  const [cohort, setCohort] = useState<TopCohort | "copy">("top100");
  return (
    <Screen>
      <Segmented
        value={cohort}
        onChange={setCohort}
        options={[
          { value: "top100", label: "Top 100" },
          { value: "legacy", label: "Legacy" },
          { value: "top1pct", label: "Top 1%" },
          { value: "youtubers", label: "YouTubers" },
          { value: "copy", label: "Copy check" },
        ]}
      />
      {cohort === "copy" ? <CopyCheckTab /> : <CohortTab cohort={cohort} />}
    </Screen>
  );
}

function CohortTab({ cohort }: { cohort: TopCohort }) {
  const query = useTopManagers(cohort);
  return <QueryState query={query}>{(data) => <TopManagersView data={data} />}</QueryState>;
}

function CopyCheckTab() {
  const query = useCopyCheck();
  return <QueryState query={query}>{(data) => <CopyCheckView data={data} />}</QueryState>;
}

/** Each mini-league member's closest YouTuber, the signal against random managers and the best evidence. */
export function CopyCheckView({ data }: { data: CopyCheck }) {
  if (!data.available || !data.members) {
    return (
      <Card>
        <Text style={styles.body}>No copy check yet. Update from the web app (Top managers → Update) or run src/copy_check.py collect.</Text>
      </Card>
    );
  }
  return (
    <>
      <Card>
        <Text style={typography.eyebrow}>{data.league?.name} · GW1–GW{data.event_through}</Text>
        <Text style={styles.caption}>Similarity, not proof: rare shared players and same-round buys, measured against {data.baseline_size} random top-1M managers. Strong = more alike than 95% of them.</Text>
      </Card>
      {data.members.map((row) => (
        <Card key={row.entry}>
          <View style={styles.row}>
            <Text style={styles.rowName}>{row.name}{row.is_you ? " (you)" : ""}</Text>
            <Text style={[styles.match, row.signal.label === "Normal" ? styles.normal : null]}>{row.signal.label}</Text>
          </View>
          <Text style={styles.caption}>Closest: {row.closest.name} · overlap {Math.round(row.overlap * 100)}% (typical {Math.round((row.overlap_typical ?? 0) * 100)}%) · {row.same_buys} same-round buys</Text>
          {row.evidence.slice(0, 3).map((e) => (
            <Text key={`${e.event}-${e.player}`} style={styles.caption}>GW{e.event}: both bought {e.player} ({e.share}% did)</Text>
          ))}
          {row.closest_friend ? <Text style={styles.caption}>Closest friend: {row.closest_friend.name}</Text> : null}
        </Card>
      ))}
    </>
  );
}

function explainer(data: TopManagers): string {
  const meta = data.meta!;
  if (data.cohort === "top1pct") {
    return `The top 1% is ${meta.population.toLocaleString("en-GB")} managers. We read a random ${meta.size.toLocaleString("en-GB")} (${meta.sample_pages} random pages of the overall table); ownership lands within ±${meta.margin_pp} percentage points 19 times out of 20. The points cutoff is exact.`;
  }
  if (data.cohort === "youtubers") {
    return `${meta.size} well-known FPL YouTubers and experts; their FPL ids are checked every season. Squads become public after the deadline.`;
  }
  if (data.cohort === "legacy") {
    return "All-time best managers who still play: candidates from Fantasy Football Pundit's all-time table, ranked by us on past overall ranks (latest season weighs most, at least five seasons).";
  }
  return "Today's overall top 100, read in full. A good run this season, not a long record.";
}

export function TopManagersView({ data }: { data: TopManagers }) {
  if (!data.available || !data.meta || !data.catch_up || !data.moves) {
    return (
      <Card>
        <Text style={styles.body}>No top-manager data yet. Update it from the web app (Top managers → Update) or run src/top_managers.py collect.</Text>
      </Card>
    );
  }
  const { meta, catch_up: gap, moves } = data;
  const behind = gap.gap != null && gap.gap > 0;
  return (
    <>
      <Card>
        <Text style={typography.eyebrow}>GW{meta.event} squads · {meta.size.toLocaleString("en-GB")} managers</Text>
        <Text style={styles.caption}>{explainer(data)}</Text>
        {meta.stale ? <Text style={[styles.caption, { color: colors.danger }]}>Older round; update for the latest squads.</Text> : null}
      </Card>
      <Card>
        <View style={styles.stats}>
          <Stat label={`Gap to ${TARGET[data.cohort]}`} value={gap.gap == null ? "–" : behind ? `${gap.gap} pts` : `+${-gap.gap} pts`} tone={behind ? "negative" : "positive"} />
          <Stat label="Per round" value={behind ? `${gap.per_gameweek} pts` : "–"} />
          <Stat label="Squad match" value={`${data.match?.cohort.toFixed(0)}%`} />
        </View>
      </Card>
      <Section title="What they did" subtitle={moves.basis ?? undefined}>
        <Card>
          {moves.bought.slice(0, 5).map((row) => (
            <Text key={`in-${row.id}`} style={styles.in}>↑ {row.name}  +{row.share.toFixed(1)}%</Text>
          ))}
          {moves.sold.slice(0, 5).map((row) => (
            <Text key={`out-${row.id}`} style={styles.out}>↓ {row.name}  {row.share.toFixed(1)}%</Text>
          ))}
          <Text style={styles.caption}>
            Captains: {moves.captains.slice(0, 3).map((row) => `${row.name} ${row.share}%`).join(" · ") || "–"}
          </Text>
          <Text style={styles.caption}>
            Chips: {Object.entries(moves.chips).map(([chip, share]) => `${FPL_CHIP_NAMES[chip] ?? chip} ${share}%`).join(" · ") || "none"}
          </Text>
        </Card>
      </Section>
      <Section title="Template vs you" subtitle="EO = average multiplier × 100">
        <Card>
          {data.template!.slice(0, 12).map((row) => (
            <View key={row.id} style={styles.row}>
              <Text style={styles.rowName}>{row.name}</Text>
              <Text style={styles.caption}>{row.effective_ownership.toFixed(0)}% EO</Text>
              <Text style={[styles.role, row.your_multiplier ? styles.mine : null]}>{role(row.your_multiplier)}</Text>
            </View>
          ))}
        </Card>
      </Section>
      {data.managers?.length ? (
        <Section title="Managers" subtitle="Match = squad overlap weighted by multiplier">
          <Card>
            {data.managers.slice(0, 30).map((row) => (
              <Pressable key={row.entry} onPress={() => void Linking.openURL(row.fpl_url)} style={styles.row} accessibilityRole="link">
                <Text style={styles.rank}>{data.cohort === "legacy" ? formatRank(row.typical_rank) : data.cohort === "youtubers" ? formatRank(row.overall_rank) : row.rank}</Text>
                <View style={styles.rowName}>
                  <Text style={styles.body}>{row.name}</Text>
                  <Text style={styles.caption}>{row.total} pts · C {row.captain_name ?? "–"}{row.chip ? ` · ${FPL_CHIP_NAMES[row.chip] ?? row.chip}` : ""}</Text>
                </View>
                <Text style={styles.match}>{row.match.toFixed(0)}%</Text>
              </Pressable>
            ))}
          </Card>
        </Section>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  stats: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.xs, minHeight: 44 },
  rowName: { ...typography.body, flex: 1 },
  rank: { width: 52, color: colors.textMuted, fontWeight: "600" },
  role: { width: 44, textAlign: "right", color: colors.textMuted, fontWeight: "700" },
  mine: { color: colors.accent },
  match: { color: colors.accent, fontWeight: "700" },
  normal: { color: colors.textMuted },
  body: typography.body,
  caption: typography.caption,
  in: { color: colors.accent, fontWeight: "600" },
  out: { color: colors.danger, fontWeight: "600" },
});
