import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/apiClient";

/** Staff member as returned by GET /users (camelized UserRead, subset). */
export type ApiUser = {
  id: string;
  fullName: string;
  email: string;
  role: string;
  isActive: boolean;
};

/** List the tenant's staff members (assignee pickers). */
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
