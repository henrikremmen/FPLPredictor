import { useEffect, useState } from "react";
import { Linking, Share, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import type { TeamResponse, ThisWeek } from "@fplmodell/api-client";
import { CHIP_LABELS, type Chip, adviceDiff, adviceSummary, formatMoney, formatPoints, fplChecklist } from "@fplmodell/shared";
import { Button, Card } from "../components/ui";
import { useThisWeek } from "../hooks/useFeatures";
import { colors, spacing, typography } from "../theme";

const STEPS = ["transfers", "lineup", "captain", "chip"] as const;
const names = (players: Array<{ name: string; price: number }>) => players.map(p => `${p.name} (${formatMoney(p.price)})`).join(", ");

/** W1: the same steps as the web This week page; ticks are kept on the device per team and Gameweek. */
export function ThisWeekPanel({ team }: { team: TeamResponse }) {
  const week = useThisWeek();
  const key = `fpl-this-week-v1-${team.entry_id}-${team.target_event}`;
  const [done, setDone] = useState<string[]>([]);
  useEffect(() => {
    AsyncStorage.getItem(key).then(value => setDone(value ? JSON.parse(value) : [])).catch(() => setDone([]));
  }, [key]);
  const [changed, setChanged] = useState<string[]>([]);
  useEffect(() => {  // L1: compare with what this phone showed last time for this team and Gameweek
    if (!week.data) return;
    const seen = `fpl-this-week-seen-v1-${team.entry_id}-${team.target_event}`;
    const now = adviceSummary(week.data);
    AsyncStorage.getItem(seen)
      .then(value => { setChanged(adviceDiff(value ? JSON.parse(value) : null, now)); return AsyncStorage.setItem(seen, JSON.stringify(now)); })
      .catch(() => undefined);
  }, [week.data, team.entry_id, team.target_event]);
  const toggle = (step: string) => {
    const next = done.includes(step) ? done.filter(s => s !== step) : [...done, step];
    setDone(next);
    AsyncStorage.setItem(key, JSON.stringify(next)).catch(() => undefined);
  };
  if (week.isError) return <Card><Text style={styles.error}>Could not work out this week's plan.</Text></Card>;
  if (!week.data) return <Card><Text style={styles.caption}>Working out this week's plan…</Text></Card>;
  return <ThisWeekView team={team} week={week.data} done={done} onToggle={toggle} changed={changed} />;
}

export function ThisWeekView({ team, week, done, onToggle, changed = [] }: { team: TeamResponse; week: ThisWeek; done: string[]; onToggle: (step: string) => void; changed?: string[] }) {
  const { strategy: s, lineup } = week;
  const captain = lineup.starters.find(p => p.role === "C")?.name ?? s.captain.captain.name;
  const vice = lineup.starters.find(p => p.role === "VC")?.name ?? s.captain.vice_captain.name;
  const play = week.chips.best_by_chip.filter(c => c.event === team.target_event && (c.decision === "PLAY" || c.decision === "CONSIDER"));
  const lines: Record<(typeof STEPS)[number], [string, string]> = {
    transfers: [s.transfer.title, week.sell.length
      ? `Sell ${names(week.sell)}. Buy ${names(week.buy)}.${s.transfer.hit ? ` −${s.transfer.hit} points hit.` : ""}`
      : `No transfer. Keep ${s.transfer.free_transfers_before} free transfer${s.transfer.free_transfers_before === 1 ? "" : "s"}.`],
    lineup: [`Lineup ${lineup.formation}`, `${lineup.starters.map(p => p.name).join(", ")}. Bench: ${lineup.bench.map(p => p.name).join(", ")}. With autosubs and VC: ${formatPoints(week.lineup_value.expected_with_autosubs)} xP.`],
    captain: [`Captain ${captain}`, `Vice-captain ${vice}. ${s.captain.reason}`],
    chip: [play.length ? `Consider ${play.map(c => CHIP_LABELS[c.chip as Chip] ?? c.chip).join(" or ")}` : "No chip this week", week.chips.recommendation],
  };
  return (
    <Card>
      <Text style={typography.eyebrow}>This week · GW{team.target_event}</Text>
      {changed.length > 0 ? <Text style={styles.warning}>Plan changed since you last looked: {changed.join(" · ")}</Text> : null}
      {STEPS.map((step, index) => (
        <View key={step} style={[styles.step, done.includes(step) && styles.done]}>
          <Text style={typography.heading}>{done.includes(step) ? "✓" : index + 1}. {lines[step][0]}</Text>
          <Text style={styles.caption}>{lines[step][1]}</Text>
          <Button label={done.includes(step) ? "Done" : "Mark done"} variant="secondary" onPress={() => onToggle(step)} />
        </View>
      ))}
      {s.squad_health.flagged_starters.map(p => <Text key={p.id} style={styles.caption}>Watch {p.name}: {p.news || "flagged by FPL"}</Text>)}
      {s.plan.weeks.slice(1).map(w => <Text key={w.event} style={styles.caption}>GW{w.event}: {w.transfers_out.length ? `${w.transfers_out.join(", ")} → ${w.transfers_in.join(", ")}` : "roll"}</Text>)}
      <Button label="Share as text" onPress={() => void Share.share({ message: fplChecklist(week).join("\n") })} />
      <Button label="Open FPL transfers" variant="secondary" onPress={() => void Linking.openURL("https://fantasy.premierleague.com/transfers")} />
      <Button label="Compare the options" variant="secondary" onPress={() => router.push("/plan")} />
    </Card>
  );
}

const styles = StyleSheet.create({
  step: { gap: spacing.xs, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  done: { opacity: 0.6 },
  caption: { ...typography.caption },
  error: { ...typography.caption, color: colors.danger },
  warning: { ...typography.caption, color: colors.warning },
});
