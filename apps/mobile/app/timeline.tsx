import { useMemo, useRef, useState } from "react";
import { PanResponder, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import type { TeamTimeline, TimelineWeek } from "@fplmodell/api-client";
import { formatMoney, formatRank, FPL_CHIP_NAMES, FPL_CHIP_SHORT, pitchRows, squadDiff } from "@fplmodell/shared";
import { Screen } from "../src/components/Screen";
import { QueryState } from "../src/components/QueryState";
import { PitchView } from "../src/components/PitchView";
import { Card, Section, Stat } from "../src/components/ui";
import { useTimeline } from "../src/hooks/useFeatures";
import { colors, radii, spacing, typography } from "../src/theme";

/** Season so far: step back through every Gameweek's squad, swipe or tap. */
export default function TimelineScreen() {
  const timeline = useTimeline();
  return (
    <Screen>
      <QueryState query={timeline} isEmpty={(data) => data.weeks.length === 0} emptyLabel="No Gameweeks played yet.">
        {(data) => <Season data={data} />}
      </QueryState>
    </Screen>
  );
}

export function Season({ data }: { data: TeamTimeline }) {
  const weeks = data.weeks;
  const [index, setIndex] = useState(weeks.length - 1);
  const week = weeks[index];
  const previous = weeks[index - 1];
  const step = (delta: number) => setIndex((current) => Math.min(weeks.length - 1, Math.max(0, current + delta)));
  const stepRef = useRef(step);
  stepRef.current = step;
  const swipe = useMemo(() => PanResponder.create({
    onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 15 && Math.abs(g.dx) > Math.abs(g.dy),
    onPanResponderRelease: (_, g) => {
      if (Math.abs(g.dx) > 50) stepRef.current(g.dx > 0 ? -1 : 1);
    },
  }), []);
  const { rows, bench } = pitchRows(week.picks);
  const joined = new Set(squadDiff(previous?.picks, week.picks).joined.map((player) => player.id));

  return (
    <>
      <Text style={typography.eyebrow}>Season so far · {weeks.at(-1)?.total_points} points</Text>
      <Ribbon weeks={weeks} selected={index} onSelect={setIndex} />

      <View style={styles.stepper}>
        <StepButton label={previous ? `‹ GW${previous.event}` : ""} onPress={() => step(-1)} disabled={!previous}
          accessibilityLabel={previous ? `Show GW${previous.event}` : "No earlier Gameweek"} />
        <View style={styles.stepperCenter} accessibilityLiveRegion="polite">
          <Text style={styles.gw}>GW{week.event}</Text>
          <Text style={styles.caption}>
            {week.points} pts{week.chip ? ` · ${FPL_CHIP_NAMES[week.chip] ?? week.chip}` : ""}{week.final ? "" : " · provisional"}
          </Text>
        </View>
        <StepButton label={weeks[index + 1] ? `GW${weeks[index + 1].event} ›` : ""} onPress={() => step(1)} disabled={!weeks[index + 1]}
          accessibilityLabel={weeks[index + 1] ? `Show GW${weeks[index + 1].event}` : "No later Gameweek"} />
      </View>

      <Card style={styles.stats}>
        <Stat label="Overall rank" value={formatRank(week.overall_rank)}
          tone={week.rank_change == null || week.rank_change === 0 ? "default" : week.rank_change > 0 ? "positive" : "negative"} />
        <Stat label="GW rank" value={formatRank(week.rank)} />
        <Stat label="Transfers" value={`${week.transfers_made}${week.transfer_cost ? ` (−${week.transfer_cost})` : ""}`}
          tone={week.transfer_cost ? "negative" : "default"} />
        <Stat label="Bank" value={formatMoney(week.bank)} />
      </Card>

      <View {...swipe.panHandlers} accessibilityHint="Swipe left or right to change Gameweek">
        <PitchView
          starters={rows.flat().map((pick) => ({ ...pick, role: pick.is_captain ? (pick.multiplier === 3 ? "TC" : "C") : pick.is_vice_captain ? "VC" : "" }))}
          valueOf={(pick) => pointsLabel(pick.points * Math.max(pick.multiplier, 1))}
          isNew={(pick) => joined.has(pick.id)}
        />
      </View>

      <Section title="Changes this round">
        <Changes week={week} previous={previous} />
      </Section>

      <Section title="Bench">
        {bench.map((pick) => (
          <View key={pick.id} style={styles.row}>
            <Text style={styles.rowName}>{pick.name}</Text>
            <Text style={styles.caption}>{pick.position} · {pick.minutes}′</Text>
            <Text style={styles.rowPoints}>{pick.points}</Text>
          </View>
        ))}
        {week.automatic_subs.map((sub) => (
          <Text key={sub.out.id} style={styles.caption}>
            Auto-sub: <Text style={styles.in}>↑ {sub.in.name}</Text>  <Text style={styles.out}>↓ {sub.out.name}</Text>
          </Text>
        ))}
      </Section>
      <Text style={styles.caption}>{data.caveat}</Text>
    </>
  );
}

const pointsLabel = (points: number) => `${points} pt${points === 1 ? "" : "s"}`;

function Ribbon({ weeks, selected, onSelect }: { weeks: TimelineWeek[]; selected: number; onSelect: (index: number) => void }) {
  const best = Math.max(...weeks.map((week) => week.points), 1);
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.ribbon}>
      {weeks.map((week, index) => {
        const active = index === selected;
        const rank = week.rank_change == null || week.rank_change === 0 ? "·" : week.rank_change > 0 ? "▲" : "▼";
        return (
          <Pressable key={week.event} onPress={() => onSelect(index)} style={styles.cell} accessibilityRole="button"
            accessibilityState={{ selected: active }}
            accessibilityLabel={`GW${week.event}: ${week.points} points${week.chip ? `, ${FPL_CHIP_NAMES[week.chip] ?? week.chip}` : ""}${week.transfer_cost ? `, −${week.transfer_cost} hit` : ""}`}>
            <Text style={[styles.chip, !week.chip && styles.hidden]}>{week.chip ? FPL_CHIP_SHORT[week.chip] ?? "★" : "–"}</Text>
            <View style={styles.barTrack}>
              <View style={[styles.bar, { height: `${Math.max(6, (week.points / best) * 100)}%` }, active && styles.barActive]} />
            </View>
            <Text style={[styles.cellLabel, active && styles.cellLabelActive]}>{week.event}</Text>
            <Text style={[styles.cellRank, rank === "▲" && styles.in, rank === "▼" && styles.out]}>{rank}</Text>
            <Text style={[styles.out, styles.cellHit]}>{week.transfer_cost ? `−${week.transfer_cost}` : " "}</Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

function Changes({ week, previous }: { week: TimelineWeek; previous?: TimelineWeek }) {
  if (!previous) return <Text style={styles.caption}>First Gameweek of the season.</Text>;
  const { joined, left } = squadDiff(previous.picks, week.picks);
  if (joined.length === 0) return <Text style={styles.caption}>Same squad as GW{previous.event}.</Text>;
  const bought = new Map(week.transfers.map((move) => [move.in.id, move.in.cost]));
  const sold = new Map(week.transfers.map((move) => [move.out.id, move.out.cost]));
  return (
    <View style={{ gap: spacing.xs }}>
      {joined.map((player) => (
        <Text key={player.id} style={styles.in}>↑ {player.name}{bought.has(player.id) ? `  ${formatMoney(bought.get(player.id))}` : ""}</Text>
      ))}
      {left.map((player) => (
        <Text key={player.id} style={styles.out}>↓ {player.name}{sold.has(player.id) ? `  ${formatMoney(sold.get(player.id))}` : ""}</Text>
      ))}
      {week.transfer_cost ? <Text style={styles.out}>Hit: −{week.transfer_cost} points</Text> : null}
    </View>
  );
}

function StepButton({ label, onPress, disabled, accessibilityLabel }: {
  label: string; onPress: () => void; disabled: boolean; accessibilityLabel: string;
}) {
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button" accessibilityLabel={accessibilityLabel}
      style={({ pressed }) => [styles.stepButton, disabled && styles.hidden, pressed && { opacity: 0.7 }]}>
      <Text style={styles.stepLabel}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  ribbon: { gap: 4, paddingVertical: spacing.sm },
  cell: { width: 30, alignItems: "center", gap: 2, minHeight: 44 },
  chip: { fontSize: 9, fontWeight: "800", color: colors.onAccent, backgroundColor: colors.captain, borderRadius: 3, paddingHorizontal: 2, overflow: "hidden" },
  hidden: { opacity: 0 },
  barTrack: { height: 64, width: 20, justifyContent: "flex-end" },
  bar: { width: "100%", borderTopLeftRadius: 4, borderTopRightRadius: 4, backgroundColor: colors.accentMuted },
  barActive: { backgroundColor: colors.accent },
  cellLabel: { fontSize: 11, fontWeight: "600", color: colors.textMuted },
  cellLabelActive: { color: colors.textPrimary },
  cellRank: { fontSize: 9, color: colors.textMuted },
  cellHit: { fontSize: 9, fontWeight: "700" },
  stepper: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  stepperCenter: { alignItems: "center" },
  gw: { fontSize: 34, fontWeight: "800", color: colors.textPrimary, letterSpacing: -1 },
  stepButton: { minWidth: 80, minHeight: 44, borderRadius: radii.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  stepLabel: { color: colors.textPrimary, fontWeight: "600" },
  stats: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.xs },
  rowName: { ...typography.body, flex: 1 },
  rowPoints: { color: colors.accent, fontWeight: "700" },
  caption: typography.caption,
  in: { color: colors.accent, fontWeight: "600" },
  out: { color: colors.danger, fontWeight: "600" },
});
