import { StyleSheet, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { formatPercent } from "@fplmodell/shared";
import { Screen } from "../src/components/Screen";
import { QueryState } from "../src/components/QueryState";
import { Card, Section } from "../src/components/ui";
import { api } from "../src/lib/api";
import { colors, spacing, typography } from "../src/theme";

const percent = (value: number | null | undefined) => (value == null ? "–" : formatPercent(value * 100));
const signed = (value: number | null | undefined) => (value == null ? "–" : `${value > 0 ? "+" : ""}${value.toFixed(1)}`);

/** Plan E4 + O3: same content as the web History → Model and data page. */
export default function ModelScreen() {
  const card = useQuery({ queryKey: ["model-card"], queryFn: () => api.modelCard() });
  return (
    <Screen>
      <Text style={typography.title}>Model and data</Text>
      <QueryState query={card}>
        {(data) => {
          const quality = data.data_quality;
          const odds = Object.entries(quality.capture.odds_coverage ?? {});
          return (
            <>
              <Text style={styles.caption}>{data.claim}</Text>
              <Section title="Data quality">
                <Card>
                  {quality.consequences.length
                    ? quality.consequences.map((note) => <Text key={note} style={styles.note}>• {note}</Text>)
                    : <Text style={styles.note}>No known data issues affect this round.</Text>}
                  <Fact label="Odds coverage" value={odds.map(([gw, share]) => `GW${gw} ${percent(share)}`).join(" · ") || "–"} />
                  <Fact label="Forecasts without odds" value={percent(quality.capture.market_fallback_share)} />
                  <Fact label="Own data (fpl-data)" value={quality.fpl_data.age_hours != null ? `${quality.fpl_data.age_hours.toFixed(0)} h old` : "not found"} />
                  <Fact label="Last evaluated round" value={quality.last_evaluated_round ? `GW${quality.last_evaluated_round}` : "none yet"} />
                </Card>
              </Section>
              <Section title="Locked rounds" subtitle={`${data.rounds.counted_v1} of ${data.rounds.needed} counted (v1) · ${data.rounds.counted_v2} (v2)`}>
                <Card>
                  {data.leaderboard.map((row) => (
                    <View key={row.model} style={styles.row}>
                      <Text style={styles.model}>{row.model === "incumbent" ? "Production (incumbent)" : row.model}</Text>
                      <Text style={styles.caption}>{row.rounds_shown} ({row.rounds_counted}) rounds · Δ {signed(row.team_points_diff_mean)} pts · {row.criterion_met ? "met" : "not met"}</Text>
                    </View>
                  ))}
                </Card>
              </Section>
              <Section title="Calibration and limits">
                <Card>
                  <Fact label="Q10–Q90 hit rate" value={`${percent(data.calibration.interval_coverage)} (aim ${percent(data.calibration.interval_nominal)})`} />
                  <Fact label="Brier score, 60+ minutes" value={data.calibration.brier_60plus?.toFixed(3) ?? "–"} />
                  {data.limitations.map((item) => <Text key={item} style={styles.note}>• {item}</Text>)}
                </Card>
              </Section>
            </>
          );
        }}
      </QueryState>
    </Screen>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.fact}>
      <Text style={styles.caption}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  caption: { ...typography.caption },
  note: { ...typography.caption, color: colors.textSecondary },
  fact: { gap: spacing.xs },
  value: { ...typography.body },
  row: { paddingVertical: spacing.xs, gap: 2 },
  model: { ...typography.body },
});
