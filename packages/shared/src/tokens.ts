/**
 * One design system for web (CSS variables via `cssVariables`) and mobile
 * (`apps/mobile/src/theme`). Dark only: managers decide in the evening before
 * deadlines, and the pitch reads best on a dark ground. Every text colour is at
 * least WCAG AA (4.5:1) on every surface; `__tests__/tokens.test.ts` checks it.
 */
export const colors = {
  background: "#07110D",
  surface: "#111D18",
  surfaceRaised: "#17251F",
  field: "#0D1913",
  border: "#2A3932",
  textPrimary: "#F1F4E9",
  textSecondary: "#93A399",
  textMuted: "#7F9087",
  accent: "#64F58D",
  accentStrong: "#1BD860",
  accentMuted: "#1D3D2B",
  onAccent: "#08120E",
  warning: "#F3CF64",
  danger: "#F08A7A",
  dangerSurface: "#321D1B",
  captain: "#F4DC58",
  viceCaptain: "#B9C8BF",
  pitch: "#155733",
  pitchStripe: "#175E37",
  pitchLine: "#2E7A4E",
} as const;

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;
export const radii = { sm: 8, md: 12, lg: 16, pill: 999 } as const;
export const fontSizes = { caption: 12, body: 15, heading: 17, title: 24, display: 34 } as const;
/** Web loads these from Google Fonts; mobile uses the platform font at the same sizes. */
export const fonts = { display: '"Space Grotesk", sans-serif', body: '"DM Sans", sans-serif' } as const;
/** Apple HIG and Material both ask for at least 44 pt/dp touch targets. */
export const MIN_TOUCH_TARGET = 44;

const kebab = (name: string) => name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);

/** `--text-primary: #F1F4E9`, … for every colour, radius and font token. */
export function cssVariables(): Record<string, string> {
  return {
    ...Object.fromEntries(Object.entries(colors).map(([name, value]) => [`--${kebab(name)}`, value])),
    ...Object.fromEntries(Object.entries(radii).map(([name, value]) => [`--radius-${name}`, `${value}px`])),
    "--font-display": fonts.display,
    "--font-body": fonts.body,
    "--touch": `${MIN_TOUCH_TARGET}px`,
  };
}

/** WCAG 2.x contrast ratio between two `#RRGGBB` colours. */
export function contrastRatio(foreground: string, background: string): number {
  const luminance = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}
