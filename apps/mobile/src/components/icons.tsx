import Svg, { Circle, Path, Rect } from "react-native-svg";

/** Same outline icons as the web app (frontend/src/icons.tsx), drawn with react-native-svg. */
function icon(children: React.ReactNode) {
  return function Icon({ color, size = 22 }: { color: string; size?: number }) {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={1.8}
        strokeLinecap="round" strokeLinejoin="round">
        {children}
      </Svg>
    );
  };
}

export const Icons = {
  Home: icon(<Path d="M4 11.5 12 4l8 7.5M6 10v9h12v-9M10 19v-5h4v5" />),
  Swap: icon(<><Path d="M4 8h13M13 4l4 4-4 4" /><Path d="M20 16H7M11 12l-4 4 4 4" /></>),
  Users: icon(<><Circle cx="9" cy="8" r="3.2" /><Path d="M2.5 19c0-3.3 2.9-5.5 6.5-5.5s6.5 2.2 6.5 5.5" /><Circle cx="17.5" cy="9" r="2.6" /><Path d="M15.5 13.6c2.7.4 4.5 2.2 4.5 5.4" /></>),
  Calendar: icon(<><Rect x="3.5" y="5" width="17" height="15" rx="2" /><Path d="M3.5 9.5h17M8 3v4M16 3v4" /></>),
  Shield: icon(<Path d="M12 3l8 3v6c0 4.5-3.2 7.7-8 9-4.8-1.3-8-4.5-8-9V6l8-3Z" />),
};
