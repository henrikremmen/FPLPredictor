import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { MAX_TRANSFERS, formatMoney, formatPoints } from "@fplmodell/shared";
import { Screen } from "../../src/components/Screen";
import { QueryState } from "../../src/components/QueryState";
import { Badge, Card, Section } from "../../src/components/ui";
import { useTeam } from "../../src/hooks/useTeam";
import { useTransfers } from "../../src/hooks/useFeatures";
import { colors, radii, spacing, typography } from "../../src/theme";

const COUNTS = Array.from({ length: MAX_TRANSFERS }, (_, index) => index + 1);

export default function Transfers() {
  const team = useTeam();
  const [number, setNumber] = useState(1);
  const [targeted, setTargeted] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);

  const ready = !targeted || selected.length === number;
  const outgoingIds = targeted && ready ? selected : [];
  const plans = useTransfers(number, outgoingIds, ready);

  const toggleTargeted = (value: boolean) => {
    setTargeted(value);
    setSelected([]);
  };

  const toggleSelected = (id: number) => {
    setSelected((previous) => {
      if (previous.includes(id)) return previous.filter((value) => value !== id);
      if (previous.length >= number) return previous;
      return [...previous, id];
    });
  };

  return (
    <Screen>
      <Text style={typography.title}>Bytter</Text>

      <View style={styles.countRow}>
        {COUNTS.map((count) => (
          <Pressable
            key={count}
            onPress={() => {
              setNumber(count);
              setSelected([]);
            }}
            style={[styles.countChip, count === number && styles.countChipActive]}
            accessibilityRole="button"
            accessibilityState={{ selected: count === number }}
          >
            <Text style={[styles.countChipLabel, count === number && styles.countChipLabelActive]}>{count}</Text>
          </Pressable>
        ))}
      </View>

      <View style={styles.modeRow}>
        <ModeButton label="Fri optimering" active={!targeted} onPress={() => toggleTargeted(false)} />
        <ModeButton label="Målrettet salg" active={targeted} onPress={() => toggleTargeted(true)} />
      </View>

      {targeted ? (
        <QueryState query={team}>
          {(data) => (
            <Section title="Velg spillere som skal selges" subtitle={`${selected.length}/${number} valgt`}>
              <Card>
                {data.squad.map((player) => {
                  const isSelected = selected.includes(player.id);
                  return (
                    <Pressable
                      key={player.id}
                      onPress={() => toggleSelected(player.id)}
                      style={styles.selectRow}
                      accessibilityRole="button"
                      accessibilityState={{ selected: isSelected }}
                    >
                      <Text style={[styles.selectName, isSelected && { color: colors.accent }]}>{player.name}</Text>
                      <Text style={styles.selectMeta}>{player.position}</Text>
                      {isSelected ? <Badge label="Valgt" tone="positive" /> : null}
                    </Pressable>
                  );
                })}
              </Card>
            </Section>
          )}
        </QueryState>
      ) : null}

      {ready ? (
        <Section title="Byttealternativer">
          <QueryState query={plans} isEmpty={(data) => data.plans.length === 0} emptyLabel="Fant ingen lovlige byttealternativer.">
            {(data) => (
              <View style={{ gap: spacing.sm }}>
                {data.plans.slice(0, 10).map((plan, index) => (
                  <Card key={index}>
                    <View style={styles.planHeader}>
                      <Text style={styles.planTitle}>
                        {plan.out} → {plan.in}
                      </Text>
                      {plan.is_global_optimum ? <Badge label="Global optimum" tone="positive" /> : null}
                    </View>
                    <View style={styles.planStats}>
                      <PlanStat label="Netto gevinst" value={formatPoints(plan.net_gain)} />
                      <PlanStat label="Kostnad" value={plan.hit ? `−${plan.hit}` : "0"} />
                      <PlanStat label="Penger igjen" value={formatMoney(plan.money_left)} />
                    </View>
                  </Card>
                ))}
              </View>
            )}
          </QueryState>
        </Section>
      ) : (
        <Text style={styles.caption}>Velg {number} spiller(e) som skal selges for å se forslag.</Text>
      )}
    </Screen>
  );
}

function ModeButton({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.modeButton, active && styles.modeButtonActive]}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
    >
      <Text style={[styles.modeButtonLabel, active && styles.modeButtonLabelActive]}>{label}</Text>
    </Pressable>
  );
}

function PlanStat({ label, value }: { label: string; value: string }) {
  return (
    <View>
      <Text style={styles.planStatLabel}>{label}</Text>
      <Text style={styles.planStatValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  countRow: { flexDirection: "row", gap: spacing.sm },
  countChip: {
    width: 36,
    height: 36,
    borderRadius: radii.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  countChipActive: { backgroundColor: colors.accent, borderColor: colors.accent },
  countChipLabel: { ...typography.body, fontWeight: "700" },
  countChipLabelActive: { color: "#06231A" },
  modeRow: { flexDirection: "row", gap: spacing.sm },
  modeButton: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    alignItems: "center",
  },
  modeButtonActive: { borderColor: colors.accent },
  modeButtonLabel: { ...typography.body, fontWeight: "600" },
  modeButtonLabelActive: { color: colors.accent },
  selectRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  selectName: { ...typography.body, flex: 1 },
  selectMeta: { ...typography.caption },
  planHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  planTitle: { ...typography.body, fontWeight: "700", flexShrink: 1 },
  planStats: { flexDirection: "row", gap: spacing.lg },
  planStatLabel: { ...typography.caption },
  planStatValue: { ...typography.body, fontWeight: "700" },
  caption: { ...typography.caption },
});
