import { colors, contrastRatio, cssVariables } from "@fplmodell/shared";

const surfaces = ["background", "surface", "surfaceRaised", "field"] as const;
const text = ["textPrimary", "textSecondary", "textMuted", "accent", "warning", "danger", "captain", "viceCaptain"] as const;

describe("design tokens", () => {
  it.each(text.flatMap((fg) => surfaces.map((bg) => [fg, bg] as const)))("%s on %s meets WCAG AA", (fg, bg) => {
    expect(contrastRatio(colors[fg], colors[bg])).toBeGreaterThanOrEqual(4.5);
  });

  it("dark text on accent and warning chips meets AA", () => {
    expect(contrastRatio(colors.onAccent, colors.accent)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(colors.onAccent, colors.warning)).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(colors.textPrimary, colors.pitch)).toBeGreaterThanOrEqual(4.5);
  });

  it("matches the known ratio for black on white and exposes CSS variables", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(cssVariables()["--text-primary"]).toBe(colors.textPrimary);
    expect(cssVariables()["--radius-md"]).toBe("12px");
  });
});
