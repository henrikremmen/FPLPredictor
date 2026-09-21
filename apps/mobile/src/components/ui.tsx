import { Pressable, StyleSheet, Text, View, type PressableProps } from "react-native";
import { colors, radii, spacing, typography } from "../theme";

export function Card({ children, style }: { children: React.ReactNode; style?: object }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <Text style={typography.eyebrow}>{title}</Text>
        {subtitle ? <Text style={styles.sectionSubtitle}>{subtitle}</Text> : null}
      </View>
      {children}
    </View>
  );
}

export function Stat({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "positive" | "negative" }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text
        style={[
          styles.statValue,
          tone === "positive" && { color: colors.accent },
          tone === "negative" && { color: colors.danger },
        ]}
      >
        {value}
      </Text>
    </View>
  );
}

interface ButtonProps extends PressableProps {
  label: string;
  variant?: "primary" | "secondary" | "danger";
  loading?: boolean;
}

export function Button({ label, variant = "primary", loading, disabled, style, ...rest }: ButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.button,
        variant === "primary" && styles.buttonPrimary,
        variant === "secondary" && styles.buttonSecondary,
        variant === "danger" && styles.buttonDanger,
        (disabled || loading) && styles.buttonDisabled,
        pressed && !disabled && !loading && styles.buttonPressed,
        typeof style === "function" ? undefined : style,
      ]}
      {...rest}
    >
      <Text
        style={[
          styles.buttonLabel,
          variant === "secondary" && { color: colors.textPrimary },
          variant === "danger" && { color: "#fff" },
        ]}
      >
        {loading ? "…" : label}
      </Text>
    </Pressable>
  );
}

export function Badge({ label, tone = "default" }: { label: string; tone?: "default" | "positive" | "warning" | "negative" }) {
  return (
    <View
      style={[
        styles.badge,
        tone === "positive" && { backgroundColor: colors.accentMuted },
        tone === "warning" && { backgroundColor: "#3D2E12" },
        tone === "negative" && { backgroundColor: "#3A1E22" },
      ]}
    >
      <Text
        style={[
          styles.badgeLabel,
          tone === "positive" && { color: colors.accent },
          tone === "warning" && { color: colors.warning },
          tone === "negative" && { color: colors.danger },
        ]}
      >
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  section: { gap: spacing.sm },
  sectionHeader: { gap: 2 },
  sectionSubtitle: { ...typography.caption },
  stat: { gap: 2, minWidth: 88 },
  statLabel: { ...typography.caption },
  statValue: { ...typography.heading },
  button: {
    borderRadius: radii.pill,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonPrimary: { backgroundColor: colors.accent },
  buttonSecondary: { backgroundColor: colors.surfaceRaised, borderWidth: 1, borderColor: colors.border },
  buttonDanger: { backgroundColor: colors.danger },
  buttonDisabled: { opacity: 0.5 },
  buttonPressed: { opacity: 0.85 },
  buttonLabel: { fontSize: 15, fontWeight: "700", color: "#06231A" },
  badge: { paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radii.pill, backgroundColor: colors.surfaceRaised },
  badgeLabel: { fontSize: 11, fontWeight: "700", color: colors.textSecondary },
});
