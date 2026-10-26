export type UiIconName =
  | "home"
  | "bell"
  | "user"
  | "settings"
  | "logout"
  | "chevron-down"
  | "chevron-right"
  | "sidebar"
  | "eye"
  | "eye-off"
  | "check"
  | "alert"
  | "info"
  | "arrow-right"
  | "menu"
  | "close"
  | "mail"
  | "lock"
  | "search"
  | "plus"
  | "pencil"
  | "trash"
  | "phone"
  | "chevron-left"
  | "calendar"
  | "activity"
  | "help"
  | "shield"
  | "layers";

const paths: Record<UiIconName, string[]> = {
  activity: ["M3 12h4l3-7 4 14 3-7h4"],
  help: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.4", "M12 17h.01"],
  shield: ["M12 3.5 19 6v5.5c0 4.2-2.9 7.6-7 9-4.1-1.4-7-4.8-7-9V6l7-2.5Z", "m9 12 2 2 4-4"],
  home: ["M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1v-8.5Z"],
  bell: ["M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 2H4.5l1.5-2Z", "M10 20.5a2.2 2.2 0 0 0 4 0"],
  user: ["M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z", "M4.5 20c1.2-3.4 4-5 7.5-5s6.3 1.6 7.5 5"],
  settings: [
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    "M19 12a7 7 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7 7 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 2 1.2L10 21h4l.5-2.6a7 7 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.07-.4.1-.8.1-1.2Z",
  ],
  logout: ["M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3", "M10 16.5 5.5 12 10 7.5", "M5.5 12H15"],
  "chevron-down": ["m6 9 6 6 6-6"],
  "chevron-right": ["m9 6 6 6-6 6"],
  sidebar: ["M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z", "M9.5 4v16"],
  eye: ["M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"],
  "eye-off": [
    "M10.6 5.6A9.7 9.7 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-2.6 3.4",
    "M6.4 6.9C3.9 8.6 2.5 12 2.5 12S6 18.5 12 18.5a9 9 0 0 0 4.6-1.3",
    "M9.9 9.9a3 3 0 0 0 4.2 4.2",
    "m3 3 18 18",
  ],
  check: ["m5 12.5 4.5 4.5L19 7.5"],
  alert: ["M12 3.5 21.5 20h-19L12 3.5Z", "M12 10v4", "M12 17h.01"],
  info: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 11v5", "M12 8h.01"],
  "arrow-right": ["M4.5 12h14.5", "M13.5 6.5 19 12l-5.5 5.5"],
  menu: ["M4 7h16", "M4 12h16", "M4 17h16"],
  close: ["m6 6 12 12", "M18 6 6 18"],
  mail: ["M4 6h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z", "m3.5 7 8.5 6 8.5-6"],
  lock: ["M6 11h12a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1Z", "M8 11V8a4 4 0 1 1 8 0v3"],
  search: ["M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z", "m20 20-3.5-3.5"],
  plus: ["M12 5v14", "M5 12h14"],
  calendar: ["M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z", "M4 10h16", "M8 4v4", "M16 4v4"],
  pencil: ["M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z", "m13.5 6.5 4 4"],
  trash: ["M4 7h16", "M10 11v6", "M14 11v6", "M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12", "M9 7V4h6v3"],
  phone: ["M5 4h3l2 5-2.5 1.5a11 11 0 0 0 6 6L15 14l5 2v3a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1Z"],
  "chevron-left": ["m15 6-6 6 6 6"],
  layers: ["m12 4 8.5 4.5L12 13 3.5 8.5 12 4Z", "m3.5 12.5 8.5 4.5 8.5-4.5", "m3.5 16 8.5 4.5 8.5-4.5"],
};

export function Icon({ name, className = "h-5 w-5", strokeWidth = 1.6 }: { name: UiIconName; className?: string; strokeWidth?: number }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      {paths[name].map((d) => (
        <path key={d} d={d} stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
      ))}
    </svg>
  );
}
