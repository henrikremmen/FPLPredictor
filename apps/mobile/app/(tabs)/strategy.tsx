import { useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { formatMoney, formatPoints } from "@fplmodell/shared";
import type { ChipCandidate, PlanWeek, StrategyAction } from "@fplmodell/api-client";
import { Screen } from "../../src/components/Screen";
import { QueryState } from "../../src/components/QueryState";
import { Segmented } from "../../src/components/Segmented";
import { Badge, Card, Section } from "../../src/components/ui";
import { useChipStrategy, useMultiweekPlan, useRecommendedSquads, useStrategyAdvice } from "../../src/hooks/useFeatures";
import { colors, spacing, typography } from "../../src/theme";

type PanelView = "strategy" | "plan" | "chips";

export default function Strategy() {
  const [view, setView] = useState<PanelView>("strategy");
  return (
    <Screen>
      <Text style={typography.title}>Strategisenter</Text>
      <Segmented
        value={view}
        onChange={setView}
        options={[
          { value: "strategy", label: "Strategi" },
          { value: "plan", label: "Flerukersplan" },
          { value: "chips", label: "Chips" },
        ]}
      />
      {view === "strategy" ? <StrategyPanel /> : null}
      {view === "plan" ? <PlanPanel /> : null}
      {view === "chips" ? <ChipsPanel /> : null}
    </Screen>
  );
}

function severityTone(severity: StrategyAction["severity"]): "warning" | "negative" | "default" {
  if (severity === "urgent") return "negative";
  if (severity === "decision") return "warning";
  return "default";
}

function StrategyPanel() {
  const advice = useStrategyAdvice();
  return (
    <QueryState query={advice}>
      {(data) => (
        <>
          <Card>
            <Text style={typography.eyebrow}>GW{data.target_event}</Text>
            <Text style={typography.heading}>{data.headline}</Text>
            <Text style={styles.caption}>
              Deadline om {data.deadline.hours_remaining != null ? `${data.deadline.hours_remaining.toFixed(1)} t` : "ukjent tid"}
            </Text>
          </Card>

          {data.actions.length > 0 ? (
            <Section title="Anbefalte handlinger">
              <View style={{ gap: spacing.sm }}>
                {data.actions.map((action, index) => (
                  <Card key={index}>
                    <View style={styles.actionHeader}>
                      <Text style={styles.actionTitle}>{action.title}</Text>
                      <Badge label={action.severity} tone={severityTone(action.severity)} />
                    </View>
                    <Text style={styles.caption}>{action.detail}</Text>
                  </Card>
                ))}
              </View>
            </Section>
          ) : null}

          <Section title="Bytteanbefaling">
            <Card>
              <Text style={styles.actionTitle}>{data.transfer.title}</Text>
              <Text style={styles.caption}>{data.transfer.reason}</Text>
              {data.transfer.transfers_out.length > 0 ? (
                <Text style={styles.body}>
                  {data.transfer.transfers_out.join(", ")} → {data.transfer.transfers_in.join(", ")}
                </Text>
              ) : null}
              <View style={styles.statRow}>
                <Text style={styles.caption}>Kostnad: {data.transfer.hit ? `−${data.transfer.hit}` : "0"}</Text>
                <Text style={styles.caption}>Tillit: {data.transfer.confidence}</Text>
              </View>
              {data.transfer.warnings.map((warning, index) => (
                <Text key={index} style={styles.warning}>
                  ⚠ {warning}
                </Text>
              ))}
            </Card>
          </Section>

          <Section title="Kaptein">
            <Card>
              <Text style={styles.actionTitle}>
                C {data.captain.captain.name} · VC {data.captain.vice_captain.name}
              </Text>
              <Text style={styles.caption}>{data.captain.reason}</Text>
            </Card>
          </Section>

          <Section title="Troppshelse" subtitle={data.squad_health.rating}>
            <Card>
              <Text style={styles.caption}>
                {data.squad_health.playable_players} spillbare · {data.squad_health.flagged_players.length} flagget
              </Text>
              {data.squad_health.flagged_starters.map((player) => (
                <Text key={player.id} style={styles.warning}>
                  {player.name}: {player.news || player.status}
                </Text>
              ))}
            </Card>
          </Section>

          {data.price_alerts.available ? (
            <Section title="Prisvarsler">
              <Card>
                {data.price_alerts.owned_at_risk.map((player) => (
                  <Text key={player.id} style={styles.warning}>
                    Fallende: {player.name}
                  </Text>
                ))}
                {data.price_alerts.targets_rising.map((player) => (
                  <Text key={player.id} style={styles.body}>
                    Stigende: {player.name}
                  </Text>
                ))}
              </Card>
            </Section>
          ) : null}

          <Section title="Watchlist" subtitle="Topp mål">
            <Card>
              {data.watchlists.top_targets.slice(0, 8).map((player) => (
                <View key={player.id} style={styles.watchRow}>
                  <Text style={styles.body}>{player.name}</Text>
                  <Text style={styles.caption}>{formatPoints(player.decision_points)}p</Text>
                </View>
              ))}
            </Card>
          </Section>
        </>
      )}
    </QueryState>
  );
}

function PlanPanel() {
  const [weeks, setWeeks] = useState(4);
  const plan = useMultiweekPlan(weeks);
  return (
    <>
      <Segmented
        value={String(weeks)}
        onChange={(value) => setWeeks(Number(value))}
        options={[2, 3, 4, 5, 6, 8].map((value) => ({ value: String(value), label: `${value} GW` }))}
      />
      <QueryState query={plan}>
        {(data) => (
          <>
            <Card>
              <View style={styles.statRow}>
                <Text style={styles.caption}>Total: {formatPoints(data.total_projected_points)}p</Text>
                {data.global_optimum ? <Badge label="Global optimum" tone="positive" /> : null}
              </View>
              <Text style={styles.caption}>{data.caveat}</Text>
            </Card>
            {data.weeks.map((week) => (
              <PlanWeekCard key={week.event} week={week} />
            ))}
          </>
        )}
      </QueryState>
    </>
  );
}

function PlanWeekCard({ week }: { week: PlanWeek }) {
  return (
    <Card>
      <View style={styles.actionHeader}>
        <Text style={styles.actionTitle}>GW{week.event}</Text>
        <Text style={styles.caption}>{week.formation}</Text>
      </View>
      {week.transfers_out.length > 0 ? (
        <Text style={styles.body}>
          {week.transfers_out.join(", ")} → {week.transfers_in.join(", ")}
        </Text>
      ) : (
        <Text style={styles.caption}>Ingen bytter (rull)</Text>
      )}
      <View style={styles.statRow}>
        <Text style={styles.caption}>Bank {formatMoney(week.bank)}</Text>
        <Text style={styles.caption}>FT {week.free_transfers_before}</Text>
        <Text style={styles.caption}>{week.hit ? `Hit −${week.hit}` : "Ingen hit"}</Text>
      </View>
      <Text style={styles.caption}>Kaptein: {week.captain}</Text>
      <Text style={styles.body}>{formatPoints(week.projected_points)}p</Text>
    </Card>
  );
}

function decisionTone(decision: ChipCandidate["decision"]): "positive" | "warning" | "default" | "negative" {
  if (decision === "PLAY") return "positive";
  if (decision === "CONSIDER") return "warning";
  if (decision === "UNAVAILABLE") return "negative";
  return "default";
}

function ChipsPanel() {
  const chips = useChipStrategy();
  const squads = useRecommendedSquads();
  return (
    <>
      <QueryState query={chips}>
        {(data) => (
          <>
            <Card>
              <Text style={typography.eyebrow}>Anbefaling</Text>
              <Text style={typography.heading}>{data.recommendation}</Text>
              <Text style={styles.caption}>{data.summary}</Text>
            </Card>
            <Section title="Chip-for-chip">
              <View style={{ gap: spacing.sm }}>
                {data.best_by_chip.map((candidate) => (
                  <Card key={candidate.chip}>
                    <View style={styles.actionHeader}>
                      <Text style={styles.actionTitle}>{candidate.label}</Text>
                      <Badge label={candidate.decision} tone={decisionTone(candidate.decision)} />
                    </View>
                    <Text style={styles.caption}>{candidate.reason}</Text>
                    <Text style={styles.caption}>
                      GW{candidate.event} · gevinst {formatPoints(candidate.gain)}p · terskel {formatPoints(candidate.threshold, 1)}
                    </Text>
                  </Card>
                ))}
              </View>
            </Section>
          </>
        )}
      </QueryState>

      <Section title="Wildcard-tropp" subtitle="Foreslått fullopptrukket lag">
        <QueryState query={squads}>
          {(data) => (
            <Card>
              <Text style={styles.actionTitle}>
                {data.wildcard.formation} · C {data.wildcard.captain}
              </Text>
              <Text style={styles.caption}>
                {formatMoney(data.wildcard.money_left)} igjen · {formatPoints(data.wildcard.projected_points)}p
              </Text>
              <Text style={styles.body}>{data.wildcard.squad.map((player) => player.name).join(", ")}</Text>
            </Card>
          )}
        </QueryState>
      </Section>
    </>
  );
}

const styles = StyleSheet.create({
  caption: { ...typography.caption },
  body: { ...typography.body },
  warning: { ...typography.caption, color: colors.warning },
  actionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  actionTitle: { ...typography.body, fontWeight: "700", flexShrink: 1 },
  statRow: { flexDirection: "row", gap: spacing.md, flexWrap: "wrap" },
  watchRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
});
