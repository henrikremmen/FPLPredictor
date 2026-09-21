/** Dark, mobile-first palette. The app only ships a dark theme for v1. */
export const colors = {
  background: "#0B0F14",
  surface: "#141A22",
  surfaceRaised: "#1C2531",
  border: "#28323F",
  textPrimary: "#EAF0F6",
  textSecondary: "#93A2B4",
  textMuted: "#5E6B7C",
  accent: "#38D08A",
  accentMuted: "#1F5B41",
  warning: "#E8B14C",
  danger: "#E5626B",
  captain: "#F2C744",
  viceCaptain: "#8FA6C2",
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radii = {
  sm: 8,
  md: 12,
  lg: 16,
  pill: 999,
} as const;

export const typography = {
  title: { fontSize: 24, fontWeight: "700" as const, color: colors.textPrimary },
  heading: { fontSize: 17, fontWeight: "600" as const, color: colors.textPrimary },
  body: { fontSize: 15, fontWeight: "400" as const, color: colors.textPrimary },
  caption: { fontSize: 12, fontWeight: "500" as const, color: colors.textSecondary },
  eyebrow: {
    fontSize: 11,
    fontWeight: "700" as const,
    color: colors.textMuted,
    letterSpacing: 0.6,
    textTransform: "uppercase" as const,
  },
};
