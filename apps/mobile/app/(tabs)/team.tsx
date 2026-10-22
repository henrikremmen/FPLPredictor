import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { router } from "expo-router";
import { formatMoney } from "@fplmodell/shared";
import { Screen } from "../../src/components/Screen";
import { usePullToRefresh } from "../../src/hooks/useFeatures";
import { QueryState } from "../../src/components/QueryState";
import { Button, Card, Section, Stat } from "../../src/components/ui";
import { useWorkspace, type SavedPlan } from "../../src/context/workspace-context";
import { useTeam } from "../../src/hooks/useTeam";
import { colors, radii, spacing, typography } from "../../src/theme";

/** My team: correct the squad when public FPL data lags, and review saved plans. */
export default function MyTeam() {
  const pull = usePullToRefresh();
  const team = useTeam();
  const { plans } = useWorkspace();
  return (
    <Screen onRefresh={pull.onRefresh} refreshing={pull.refreshing}>
      <Text style={typography.title}>My team</Text>
      <QueryState query={team}>
        {(data) => (
          <Card>
            <Text style={typography.heading}>{data.team_name}</Text>
            <View style={styles.stats}>
              <Stat label="Bank" value={formatMoney(data.bank)} />
              <Stat label="Free transfers" value={String(data.free_transfers)} />
              <Stat label="Squad source" value={data.squad_source === "manual_override" ? "Edited" : "FPL"} />
            </View>
            <Button label="Edit squad, bank or transfers" variant="secondary" onPress={() => router.push("/correction")} />
          </Card>
        )}
      </QueryState>
      <Section title="Saved plans" subtitle={plans.length ? `${plans.length} on this device` : undefined}>
        {plans.length === 0 ? (
          <Text style={typography.caption}>Save a transfer plan or a player comparison to keep it here.</Text>
        ) : plans.map((plan) => <PlanCard key={plan.id} plan={plan} />)}
      </Section>
    </Screen>
  );
}

function PlanCard({ plan }: { plan: SavedPlan }) {
  const { renamePlan, deletePlan } = useWorkspace();
  const [name, setName] = useState(plan.name);
  return (
    <Card>
      <TextInput value={name} onChangeText={setName} onEndEditing={() => renamePlan(plan.id, name.trim() || plan.name)}
        accessibilityLabel="Plan name" style={styles.name} />
      <Text style={typography.caption}>
        {plan.kind === "transfer" ? "Transfer plan" : "Player comparison"} · {plan.horizon} GW · {new Date(plan.created_at).toLocaleDateString("en-GB")}
      </Text>
      <Text style={[styles.summary, { color: (plan.net_gain ?? 0) < 0 ? colors.danger : colors.accent }]}>{plan.summary}</Text>
      {plan.lines.map((line) => <Text key={line} style={typography.caption}>{line}</Text>)}
      <Pressable onPress={() => deletePlan(plan.id)} accessibilityRole="button" accessibilityLabel={`Delete ${plan.name}`} style={styles.delete}>
        <Text style={{ color: colors.danger, fontWeight: "600" }}>Delete</Text>
      </Pressable>
    </Card>
  );
}

const styles = StyleSheet.create({
  stats: { flexDirection: "row", flexWrap: "wrap", gap: spacing.lg, marginVertical: spacing.sm },
  name: { ...typography.heading, minHeight: 44, borderBottomWidth: 1, borderBottomColor: colors.border, borderRadius: radii.sm },
  summary: { ...typography.body, color: colors.accent, fontWeight: "700", marginVertical: spacing.xs },
  delete: { minHeight: 44, justifyContent: "center", alignSelf: "flex-start" },
});
