import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { router } from "expo-router";
import { ApiError } from "@fplmodell/api-client";
import { MAX_HORIZON, MIN_HORIZON, RISK_PROFILES, RISK_PROFILE_LABELS, type RiskProfile } from "@fplmodell/shared";
import { Screen } from "../src/components/Screen";
import { Button, Card, Section } from "../src/components/ui";
import { useImportTeam } from "../src/hooks/useTeam";
import { colors, radii, spacing, typography } from "../src/theme";

const HORIZONS = Array.from({ length: MAX_HORIZON - MIN_HORIZON + 1 }, (_, index) => MIN_HORIZON + index);

export default function Onboarding() {
  const [reference, setReference] = useState("");
  const [horizon, setHorizon] = useState(3);
  const [riskProfile, setRiskProfile] = useState<RiskProfile>("balanced");
  const importTeam = useImportTeam();

  const onSubmit = () => {
    if (!reference.trim()) return;
    importTeam.mutate(
      { reference: reference.trim(), horizon, riskProfile },
      { onSuccess: () => router.replace("/(tabs)") },
    );
  };

  return (
    <Screen>
      <View style={styles.header}>
        <Text style={typography.title}>FPL Model</Text>
        <Text style={styles.lead}>
          Paste your FPL team link to get forecasts, lineups and transfer suggestions. The app never logs in or changes your actual team.
        </Text>
        <Text style={styles.disclaimer}>
          Independent third party app. Not affiliated with, approved or sponsored by the Premier League or Fantasy Premier League.
        </Text>
      </View>

      <Section title="Team reference">
        <TextInput
          value={reference}
          onChangeText={setReference}
          placeholder="FPL link or team ID, e.g. 5139814"
          placeholderTextColor={colors.textMuted}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="default"
          style={styles.input}
        />
      </Section>

      <Section title="Forecast horizon" subtitle={`${horizon} Gameweek${horizon > 1 ? "s" : ""}`}>
        <View style={styles.horizonRow}>
          {HORIZONS.map((value) => (
            <Pressable
              key={value}
              onPress={() => setHorizon(value)}
              style={[styles.horizonChip, value === horizon && styles.horizonChipActive]}
              accessibilityRole="button"
              accessibilityState={{ selected: value === horizon }}
            >
              <Text style={[styles.horizonChipLabel, value === horizon && styles.horizonChipLabelActive]}>
                {value}
              </Text>
            </Pressable>
          ))}
        </View>
      </Section>

      <Section title="Risk profile">
        <View style={{ gap: spacing.sm }}>
          {RISK_PROFILES.map((profile) => (
            <Pressable
              key={profile}
              onPress={() => setRiskProfile(profile)}
              accessibilityRole="button"
              accessibilityState={{ selected: profile === riskProfile }}
            >
              <Card style={profile === riskProfile ? styles.profileCardActive : undefined}>
                <Text style={styles.profileTitle}>{RISK_PROFILE_LABELS[profile]}</Text>
                <Text style={styles.profileCopy}>{profileCopy(profile)}</Text>
              </Card>
            </Pressable>
          ))}
        </View>
      </Section>

      {importTeam.isError ? (
        <Text style={styles.error}>
          {importTeam.error instanceof ApiError ? importTeam.error.message : "Could not import the team."}
        </Text>
      ) : null}

      <Button
        label={importTeam.isPending ? "Importing..." : "Load team"}
        onPress={onSubmit}
        disabled={!reference.trim()}
        loading={importTeam.isPending}
      />
    </Screen>
  );
}

function profileCopy(profile: RiskProfile): string {
  if (profile === "stable") return "Penalises the model's uncertainty range. Prefers narrower, more stable outcomes.";
  if (profile === "upside") return "Gives more weight to the upper tail. Targets a higher ceiling with more variation.";
  return "Uses the model's expected points directly. Default choice.";
}

const styles = StyleSheet.create({
  header: { gap: spacing.sm, marginBottom: spacing.md },
  lead: { ...typography.body, color: colors.textSecondary },
  disclaimer: { ...typography.caption },
  input: {
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    color: colors.textPrimary,
    fontSize: 16,
  },
  horizonRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  horizonChip: {
    width: 40,
    height: 40,
    borderRadius: radii.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  horizonChipActive: { backgroundColor: colors.accent, borderColor: colors.accent },
  horizonChipLabel: { ...typography.body, fontWeight: "700" },
  horizonChipLabelActive: { color: "#06231A" },
  profileCardActive: { borderColor: colors.accent },
  profileTitle: { ...typography.heading },
  profileCopy: { ...typography.caption },
  error: { ...typography.caption, color: colors.danger },
});
