import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

export function useSession() {
  return useQuery({
    queryKey: ["session"],
    queryFn: api.getSession,
  });
}
