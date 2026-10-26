import { useOutletContext } from "react-router";
import type { CurrentUser } from "./auth.ts";
import type { WorkspaceModule } from "./modules.ts";
import type { NotificationFeed } from "./notifications.ts";

export type WorkspaceContext = {
  user: CurrentUser;
  modules: WorkspaceModule[];
  replaceModules: (next: WorkspaceModule[]) => void;
  feed: NotificationFeed;
  refreshFeed: () => Promise<void>;
};

export function initials(user: CurrentUser): string {
  return `${user.first_name.charAt(0)}${user.last_name.charAt(0)}`.toLocaleUpperCase("tr");
}

export function useWorkspace(): WorkspaceContext {
  return useOutletContext<WorkspaceContext>();
}
