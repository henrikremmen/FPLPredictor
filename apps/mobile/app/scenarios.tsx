import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { JournalEntry } from "@fplmodell/api-client";
import { formatPoints } from "@fplmodell/shared";
import { Screen } from "../src/components/Screen";
import { QueryState } from "../src/components/QueryState";
import { Segmented } from "../src/components/Segmented";
import { Button, Card, Section } from "../src/components/ui";
import { useSession } from "../src/context/session-context";
import { useWorkspace } from "../src/context/workspace-context";
import { api } from "../src/lib/api";
import { colors, spacing, typography } from "../src/theme";

/** P5 + U19: same comparison and journal as the web Scenarios and Decision journal pages. */
export default function ScenariosScreen() {
  const { sessionId } = useSession();
  const { constraints } = useWorkspace();
  const queryClient = useQueryClient();
  const [choice, setChoice] = useState<JournalEntry["choice"]["kind"]>("follow");
  const [note, setNote] = useState("");
  const comparison = useQuery({
    queryKey: ["scenarios", sessionId, constraints],
    queryFn: () => api.scenarios(sessionId as string, constraints),
    enabled: Boolean(sessionId),
  });
  const journal = useQuery({
    queryKey: ["journal", sessionId],
    queryFn: () => api.journal(sessionId as string),
    enabled: Boolean(sessionId),
  });
  const record = useMutation({
    mutationFn: () => api.recordDecision(sessionId as string, choice, note, constraints),
    onSuccess: (data) => { queryClient.setQueryData(["journal", sessionId], data); setNote(""); },
  });
  return (
    <Screen>
      <QueryState query={comparison}>
        {(data) => (
          <Card>
            {data.plans.map((plan) => (
              <View key={plan.name} style={styles.row}>
                <Text style={typography.heading}>{plan.name}</Text>
                <Text style={styles.caption}>
                  {plan.first_week_out.length ? `${plan.first_week_out.join(", ")} → ${plan.first_week_in.join(", ")}` : "No transfer"}
                </Text>
                <Text style={styles.caption}>
                  {formatPoints(plan.net_points)} pts · vs hold {formatPoints(plan.gain_vs_hold)} · hits {plan.hits} · chosen in {Math.round((data.robustness.chosen_share[plan.name] ?? 0) * 100)}% of scenarios
                </Text>
              </View>
            ))}
            <Text style={styles.caption}>{data.robustness.note} {data.robustness.scenarios} scenarios, seed {data.robustness.seed}.</Text>
          </Card>
        )}
      </QueryState>
      <Section title="Record my decision" subtitle="Frozen before the deadline with the advice and alternatives">
        <Card>
          <Segmented value={choice} onChange={setChoice} options={[
            { value: "follow", label: "Follow" }, { value: "roll", label: "Roll" }, { value: "other", label: "Other" }]} />
          <TextInput value={note} onChangeText={setNote} placeholder="Note (optional)" placeholderTextColor={colors.textMuted}
            accessibilityLabel="Note" style={styles.input} maxLength={500} />
          <Button label="Save to journal" loading={record.isPending} onPress={() => record.mutate()} />
          {record.isError ? <Text style={styles.error}>{(record.error as Error).message}</Text> : null}
        </Card>
      </Section>
      <Section title="Decision journal">
        <QueryState query={journal}>
          {({ entries }) => (
            <Card>
              {entries.length ? entries.map((entry) => (
                <View key={entry.file} style={styles.row}>
                  <Text style={typography.body}>GW{entry.event} · {entry.choice.label}{entry.counts ? "" : " (replaced)"}</Text>
                  <Text style={styles.caption}>Advice: {entry.advice.title} · captain {entry.advice.captain}</Text>
                  <Text style={styles.caption}>
                    {entry.outcome ? `Advised XI ${formatPoints(entry.outcome.advised_xi_points)} · hold XI ${formatPoints(entry.outcome.hold_xi_points)}` : "Outcome after FPL checks the round"}
                  </Text>
                </View>
              )) : <Text style={styles.caption}>No decisions recorded yet.</Text>}
            </Card>
          )}
        </QueryState>
      </Section>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { paddingVertical: spacing.sm, gap: 2, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  caption: { ...typography.caption },
  error: { ...typography.caption, color: colors.danger },
  input: { ...typography.body, minHeight: 44, borderWidth: 1, borderColor: colors.border, borderRadius: 8, paddingHorizontal: spacing.md },
});
