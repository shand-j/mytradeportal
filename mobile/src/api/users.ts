import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";

/** Staff member as returned by GET /users (camelized UserRead, subset). */
export type ApiUser = {
  id: string;
  fullName: string;
  email: string;
  role: string;
  isActive: boolean;
  /** True while the user was invited but has not yet set a password. */
  invitePending?: boolean;
};

/** List the tenant's staff members (assignee pickers, team management). */
export async function fetchUsers(): Promise<ApiUser[]> {
  return api.get<ApiUser[]>("/users");
}

/** Active staff members for assignee selection on jobs. */
export function useUsersList() {
  const query = useQuery({
    queryKey: ["users"],
    queryFn: fetchUsers,
  });

  return {
    users: (query.data ?? []).filter((u) => u.isActive),
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
  };
}

/** Everyone on the tenant, including pending invites (Settings → Team). */
export function useTeamUsers() {
  const query = useQuery({
    queryKey: ["users"],
    queryFn: fetchUsers,
  });

  return {
    users: query.data ?? [],
    isConnected: query.isSuccess,
    isLoading: query.isLoading,
    refetch: query.refetch,
  };
}

export type InviteUserInput = {
  fullName: string;
  email: string;
  role?: string;
};

/**
 * Invite a team member (admin/manager only). The API creates an unactivated
 * account and emails a set-password link; it 403s with a structured
 * seat_limit_reached payload when the plan has no seats left.
 */
export async function inviteUser(input: InviteUserInput): Promise<ApiUser> {
  return api.post<ApiUser>("/users/invite", input);
}

/**
 * Ask the API to email a fresh invite set-password link (pending invites
 * only). Always answers the same generic message, safe to call pre-auth.
 */
export async function requestInviteMagicLink(email: string): Promise<void> {
  await api.post("/users/invite/magic-link", { email }, { auth: false });
}
