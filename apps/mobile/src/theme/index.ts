/** Mobile theme from the shared design tokens (same palette as the web app). */
import { colors, fontSizes, radii, spacing } from "@fplmodell/shared";

export { colors, radii, spacing };

export const typography = {
  title: { fontSize: fontSizes.title, fontWeight: "700" as const, color: colors.textPrimary },
  heading: { fontSize: fontSizes.heading, fontWeight: "600" as const, color: colors.textPrimary },
  body: { fontSize: fontSizes.body, fontWeight: "400" as const, color: colors.textPrimary },
  caption: { fontSize: fontSizes.caption, fontWeight: "500" as const, color: colors.textSecondary },
  eyebrow: {
    fontSize: 11,
    fontWeight: "700" as const,
    color: colors.textMuted,
    letterSpacing: 0.6,
    textTransform: "uppercase" as const,
  },
};
