import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base(paths: ReactNode) {
  return function Icon({ size = 18, ...props }: IconProps) {
    return (
      <svg
        width={size} height={size} viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"
        aria-hidden="true" {...props}
      >
        {paths}
      </svg>
    );
  };
}

export const Icon = {
  Home: base(<path d="M4 11.5 12 4l8 7.5M6 10v9h12v-9M10 19v-5h4v5" />),
  Chart: base(<><path d="M4 20V10M11 20V4M18 20v-7" /></>),
  Edit: base(<><path d="M4 20h4l10.5-10.5a2 2 0 0 0-4-4L4 16v4Z" /><path d="M13 6l4 4" /></>),
  Compass: base(<><circle cx="12" cy="12" r="9" /><path d="M15 9l-2 6-6 2 2-6 6-2Z" /></>),
  Formation: base(<><circle cx="12" cy="5" r="1.6" /><circle cx="6" cy="12" r="1.6" /><circle cx="18" cy="12" r="1.6" /><circle cx="9" cy="19" r="1.6" /><circle cx="15" cy="19" r="1.6" /></>),
  Swap: base(<><path d="M4 8h13M13 4l4 4-4 4" /><path d="M20 16H7M11 12l-4 4 4 4" /></>),
  Trend: base(<><path d="M4 16l6-6 4 4 6-8" /><path d="M15 6h5v5" /></>),
  Shield: base(<path d="M12 3l8 3v6c0 4.5-3.2 7.7-8 9-4.8-1.3-8-4.5-8-9V6l8-3Z" />),
  Zap: base(<path d="M13 3 5 14h6l-1 7 8-11h-6l1-7Z" />),
  Search: base(<><circle cx="11" cy="11" r="7" /><path d="M20 20l-4.3-4.3" /></>),
  Alert: base(<><path d="M12 3 2 20h20L12 3Z" /><path d="M12 10v4M12 17.5v.01" /></>),
  Check: base(<path d="M4 12.5l5 5 11-11" />),
  Close: base(<path d="M5 5l14 14M19 5 5 19" />),
  Refresh: base(<><path d="M20 11a8 8 0 0 0-14.6-4.4M4 13a8 8 0 0 0 14.6 4.4" /><path d="M20 4v5h-5M4 20v-5h5" /></>),
  Star: base(<path d="M12 3.5l2.6 5.6 6.1.6-4.6 4.1 1.3 6-5.4-3.2L6.6 20l1.3-6-4.6-4.1 6.1-.6L12 3.5Z" />),
  Coins: base(<><ellipse cx="9" cy="7" rx="6" ry="3" /><path d="M3 7v5c0 1.7 2.7 3 6 3s6-1.3 6-3V7" /><path d="M15 11.2c2.9.3 6 1.5 6 3.3v5c0 1.7-2.7 3-6 3-2.6 0-4.8-.8-5.6-1.9" /></>),
  ArrowRight: base(<path d="M4 12h15M13 6l6 6-6 6" />),
  Info: base(<><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.01" /></>),
  Users: base(<><circle cx="9" cy="8" r="3.2" /><path d="M2.5 19c0-3.3 2.9-5.5 6.5-5.5s6.5 2.2 6.5 5.5" /><circle cx="17.5" cy="9" r="2.6" /><path d="M15.5 13.6c2.7.4 4.5 2.2 4.5 5.4" /></>),
  Calendar: base(<><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 9.5h17M8 3v4M16 3v4" /></>),
  Target: base(<><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><circle cx="12" cy="12" r=".6" fill="currentColor" /></>),
  Lock: base(<><rect x="5" y="10.5" width="14" height="9" rx="2" /><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" /></>),
  Bench: base(<><path d="M3 18V8h18v10" /><path d="M3 18l-1.5 3M21 18l1.5 3M3 13h18" /></>),
  Captain: base(<><circle cx="12" cy="12" r="9" /><path d="M8 13.5V9l4 3 4-3v4.5" /></>),
  ChevronDown: base(<path d="M6 9l6 6 6-6" />),
  Trash: base(<><path d="M5 7h14M9 7V5h6v2M7 7l1 12h8l1-12" /></>),
  Plus: base(<path d="M12 5v14M5 12h14" />),
  Menu: base(<path d="M4 7h16M4 12h16M4 17h16" />),
};

export type IconName = keyof typeof Icon;
