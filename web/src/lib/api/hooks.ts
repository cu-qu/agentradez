import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "./client";
import type {
  AdminStrategy,
  AdminUser,
  Assignment,
  BrokerAccountDetail,
  BrokerConnectRequest,
  BrokerConnection,
  Notification,
  Paginated,
  PersonalPerformance,
  Position,
  AgentTool,
  RobinhoodAccount,
  RobinhoodOAuthComplete,
  RobinhoodOAuthStart,
  Signal,
  Strategy,
  StrategyTypeOption,
  StrategyWrite,
  Trade,
  User,
  UserGroup,
  UserGroupWrite,
  InvestmentTier,
  Decision,
} from "./types";

export const queryKeys = {
  me: ["me"] as const,
  brokers: ["brokers"] as const,
  assignment: ["assignment"] as const,
  strategies: ["strategies"] as const,
  adminStrategySignals: (id: number, page?: number) =>
    ["admin", "strategy", id, "signals", page ?? 1] as const,
  tiers: ["tiers"] as const,
  performance: ["performance"] as const,
  positions: (accountId?: string) => ["positions", accountId ?? "all"] as const,
  trades: (filters: Record<string, unknown>) => ["trades", filters] as const,
  trade: (id: number) => ["trade", id] as const,
  decisions: (filters: Record<string, unknown>) => ["decisions", filters] as const,
  decision: (id: number) => ["decision", id] as const,
  notifications: (filters: Record<string, unknown>) =>
    ["notifications", filters] as const,
  brokerAccount: (connectionId: number, accountNumber: string) =>
    ["brokers", connectionId, "account", accountNumber] as const,
  adminStrategyTypes: ["admin", "strategy-types"] as const,
  adminStrategies: (filters: Record<string, unknown>) =>
    ["admin", "strategies", filters] as const,
  adminStrategy: (id: number) => ["admin", "strategy", id] as const,
  adminUserGroups: (filters: Record<string, unknown>) =>
    ["admin", "user-groups", filters] as const,
  adminUserGroup: (id: number) => ["admin", "user-group", id] as const,
  adminUsers: (filters: Record<string, unknown>) =>
    ["admin", "users", filters] as const,
};

export function useMeQuery(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: () => api.get<User>("/api/auth/me/"),
    enabled,
  });
}

export function useBrokersQuery(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.brokers,
    queryFn: async () => {
      const data = await api.get<BrokerConnection[] | BrokerConnection>(
        "/api/broker-connections/",
      );
      return Array.isArray(data) ? data : data ? [data] : [];
    },
    enabled,
  });
}

export function useAssignmentQuery(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.assignment,
    queryFn: async () => {
      try {
        return await api.get<Assignment>("/api/assignment/");
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled,
  });
}

export function useStrategiesQuery(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.strategies,
    queryFn: async () => {
      const page = await api.get<Paginated<Strategy>>("/api/strategies/");
      return page.results;
    },
    enabled,
  });
}

export function useTiersQuery(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.tiers,
    queryFn: async () => {
      const page = await api.get<Paginated<InvestmentTier>>("/api/investment-tiers/");
      return page.results;
    },
    enabled,
  });
}

export function usePerformanceQuery(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.performance,
    queryFn: () => api.get<PersonalPerformance>("/api/performance/"),
    enabled,
    refetchInterval: 12_000,
  });
}

export function usePositionsQuery(enabled: boolean, brokerAccountId?: string) {
  return useQuery({
    queryKey: queryKeys.positions(brokerAccountId),
    queryFn: async () => {
      const page = await api.get<Paginated<Position>>("/api/positions/", {
        broker_account_id: brokerAccountId,
      });
      return page.results;
    },
    enabled,
    refetchInterval: 12_000,
  });
}

export function useTradesQuery(
  enabled: boolean,
  filters: {
    status?: string;
    ticker?: string;
    page?: number;
    broker_account_id?: string;
  },
) {
  return useQuery({
    queryKey: queryKeys.trades(filters),
    queryFn: () =>
      api.get<Paginated<Trade>>("/api/trades/", {
        status: filters.status,
        ticker: filters.ticker,
        page: filters.page,
        broker_account_id: filters.broker_account_id,
      }),
    enabled,
  });
}

export function useTradeQuery(enabled: boolean, id: number) {
  return useQuery({
    queryKey: queryKeys.trade(id),
    queryFn: () => api.get<Trade>(`/api/trades/${id}/`),
    enabled: enabled && Number.isInteger(id) && id > 0,
  });
}

export function useDecisionsQuery(
  enabled: boolean,
  filters: {
    action?: string;
    outcome?: string;
    ticker?: string;
    page?: number;
    broker_account_id?: string;
  },
) {
  return useQuery({
    queryKey: queryKeys.decisions(filters),
    queryFn: () =>
      api.get<Paginated<Decision>>("/api/decisions/", {
        action: filters.action,
        outcome: filters.outcome,
        ticker: filters.ticker,
        page: filters.page,
        broker_account_id: filters.broker_account_id,
      }),
    enabled,
  });
}

export function useDecisionQuery(enabled: boolean, id: number) {
  return useQuery({
    queryKey: queryKeys.decision(id),
    queryFn: () => api.get<Decision>(`/api/decisions/${id}/`),
    enabled: enabled && Number.isInteger(id) && id > 0,
  });
}

export function useNotificationsQuery(
  enabled: boolean,
  unread?: boolean,
  brokerAccountId?: string,
) {
  return useQuery({
    queryKey: queryKeys.notifications({
      unread: unread ?? false,
      broker_account_id: brokerAccountId,
    }),
    queryFn: () =>
      api.get<Paginated<Notification>>("/api/notifications/", {
        unread: unread ? true : undefined,
        broker_account_id: brokerAccountId,
      }),
    enabled,
    refetchInterval: 15_000,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.post<Notification>(`/api/notifications/${id}/read/`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ updated: number }>("/api/notifications/read-all/"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useSaveAssignment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      strategy_id: number;
      investment_tier_id: number;
      broker_account_id?: string;
    }) => api.put<Assignment>("/api/assignment/", body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.assignment });
      void queryClient.invalidateQueries({ queryKey: queryKeys.brokers });
    },
  });
}

export function useBrokerAccountDetailQuery(
  connectionId: number | null,
  accountNumber: string | null,
) {
  return useQuery({
    queryKey: queryKeys.brokerAccount(connectionId ?? 0, accountNumber ?? ""),
    queryFn: () =>
      api.get<BrokerAccountDetail>(
        `/api/broker-connections/${connectionId}/accounts/${encodeURIComponent(accountNumber ?? "")}/`,
      ),
    enabled: connectionId != null && Boolean(accountNumber),
  });
}

export function useConnectBroker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: BrokerConnectRequest) =>
      api.post<BrokerConnection>("/api/broker-connections/", body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.brokers });
    },
  });
}

export function useDisconnectBroker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      api.post<{ detail: string }>(`/api/broker-connections/${id}/disconnect/`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.brokers });
      void queryClient.invalidateQueries({ queryKey: queryKeys.assignment });
    },
  });
}

export function useStartRobinhoodOAuth() {
  return useMutation({
    mutationFn: () =>
      api.post<RobinhoodOAuthStart>(
        "/api/broker-connections/robinhood/oauth/start/",
      ),
  });
}

export function useCompleteRobinhoodOAuth() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (callback_url: string) =>
      api.post<RobinhoodOAuthComplete>(
        "/api/broker-connections/robinhood/oauth/complete/",
        { callback_url },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.brokers });
      void queryClient.invalidateQueries({ queryKey: queryKeys.assignment });
    },
  });
}

export function useBrokerAccountsQuery(id: number | null) {
  return useQuery({
    queryKey: [...queryKeys.brokers, id, "accounts"] as const,
    queryFn: () =>
      api.get<RobinhoodAccount[]>(`/api/broker-connections/${id}/accounts/`),
    enabled: id != null,
  });
}

export function useSelectBrokerAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, account_number }: { id: number; account_number: string }) =>
      api.post<BrokerConnection>(`/api/broker-connections/${id}/select-account/`, {
        account_number,
      }),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.brokers });
      void queryClient.invalidateQueries({
        queryKey: [...queryKeys.brokers, variables.id, "accounts"],
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.assignment });
    },
  });
}

export function useBrokerAgentToolsQuery(id: number | null) {
  return useQuery({
    queryKey: [...queryKeys.brokers, id, "agent-tools"] as const,
    queryFn: () =>
      api.get<AgentTool[]>(`/api/broker-connections/${id}/agent-tools/`),
    enabled: id != null,
  });
}

export function useUpdateMe() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { preferred_language: string }) =>
      api.patch<User>("/api/auth/me/", body),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.me, user);
    },
  });
}

export type AdminStrategyFilters = {
  search?: string;
  is_active?: boolean;
  strategy_type?: string;
  visibility?: string;
  ordering?: string;
  page?: number;
};

export type AdminUserGroupFilters = {
  search?: string;
  is_active?: boolean;
  ordering?: string;
  page?: number;
};

export type AdminUserFilters = {
  search?: string;
  page?: number;
};

export function useAdminStrategyTypesQuery(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.adminStrategyTypes,
    queryFn: async () => {
      const data = await api.get<{ results: StrategyTypeOption[] }>(
        "/api/admin/strategy-types/",
      );
      return data.results ?? [];
    },
    enabled,
    retry: (count, error) => {
      if (error instanceof ApiError && error.status === 403) return false;
      return count < 1;
    },
  });
}

export function useAdminStrategiesQuery(
  enabled: boolean,
  filters: AdminStrategyFilters,
) {
  return useQuery({
    queryKey: queryKeys.adminStrategies(filters),
    queryFn: () =>
      api.get<Paginated<AdminStrategy>>("/api/admin/strategies/", {
        search: filters.search,
        is_active: filters.is_active,
        strategy_type: filters.strategy_type,
        visibility: filters.visibility,
        ordering: filters.ordering,
        page: filters.page,
      }),
    enabled,
  });
}

export function useAdminStrategyQuery(enabled: boolean, id: number) {
  return useQuery({
    queryKey: queryKeys.adminStrategy(id),
    queryFn: () => api.get<AdminStrategy>(`/api/admin/strategies/${id}/`),
    enabled: enabled && Number.isInteger(id) && id > 0,
  });
}

export function useAdminStrategySignalsQuery(
  enabled: boolean,
  strategyId: number,
  page = 1,
) {
  return useQuery({
    queryKey: queryKeys.adminStrategySignals(strategyId, page),
    queryFn: () =>
      api.get<Paginated<Signal>>(`/api/admin/strategies/${strategyId}/signals/`, {
        page,
      }),
    enabled: enabled && Number.isInteger(strategyId) && strategyId > 0,
  });
}

export type StrategyLookbackResult = {
  strategy_id?: number;
  source_id: number;
  handle: string;
  days: number;
  tweets_seen: number;
  tweets_ingested: number;
  tweets_duplicate: number;
  signals_created: number;
  error?: string;
};

export function useStrategyLookback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, days }: { id: number; days: number }) =>
      api.post<StrategyLookbackResult>(`/api/admin/strategies/${id}/lookback/`, {
        days,
      }),
    onSettled: (_data, _error, variables) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.adminStrategy(variables.id),
      });
      void queryClient.invalidateQueries({
        queryKey: ["admin", "strategy", variables.id, "signals"],
      });
    },
  });
}

function invalidateAdminStrategies(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["admin", "strategies"] });
  void queryClient.invalidateQueries({ queryKey: ["admin", "strategy"] });
  void queryClient.invalidateQueries({ queryKey: queryKeys.strategies });
}

export function useCreateAdminStrategy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: StrategyWrite) =>
      api.post<AdminStrategy>("/api/admin/strategies/", body),
    onSuccess: (strategy) => {
      queryClient.setQueryData(queryKeys.adminStrategy(strategy.id), strategy);
      invalidateAdminStrategies(queryClient);
    },
  });
}

export function useUpdateAdminStrategy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: StrategyWrite }) =>
      api.patch<AdminStrategy>(`/api/admin/strategies/${id}/`, body),
    onSuccess: (strategy) => {
      queryClient.setQueryData(queryKeys.adminStrategy(strategy.id), strategy);
      invalidateAdminStrategies(queryClient);
    },
  });
}

export function useDeactivateAdminStrategy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      api.delete<AdminStrategy>(`/api/admin/strategies/${id}/`),
    onSuccess: (strategy) => {
      queryClient.setQueryData(queryKeys.adminStrategy(strategy.id), strategy);
      invalidateAdminStrategies(queryClient);
    },
  });
}

export function useAdminUserGroupsQuery(
  enabled: boolean,
  filters: AdminUserGroupFilters,
) {
  return useQuery({
    queryKey: queryKeys.adminUserGroups(filters),
    queryFn: () =>
      api.get<Paginated<UserGroup>>("/api/admin/user-groups/", {
        search: filters.search,
        is_active: filters.is_active,
        ordering: filters.ordering,
        page: filters.page,
      }),
    enabled,
  });
}

export function useAdminUserGroupQuery(enabled: boolean, id: number) {
  return useQuery({
    queryKey: queryKeys.adminUserGroup(id),
    queryFn: () => api.get<UserGroup>(`/api/admin/user-groups/${id}/`),
    enabled: enabled && Number.isInteger(id) && id > 0,
  });
}

function invalidateAdminUserGroups(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["admin", "user-groups"] });
  void queryClient.invalidateQueries({ queryKey: ["admin", "user-group"] });
  invalidateAdminStrategies(queryClient);
}

export function useCreateAdminUserGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UserGroupWrite) =>
      api.post<UserGroup>("/api/admin/user-groups/", body),
    onSuccess: (group) => {
      queryClient.setQueryData(queryKeys.adminUserGroup(group.id), group);
      invalidateAdminUserGroups(queryClient);
    },
  });
}

export function useUpdateAdminUserGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: UserGroupWrite }) =>
      api.patch<UserGroup>(`/api/admin/user-groups/${id}/`, body),
    onSuccess: (group) => {
      queryClient.setQueryData(queryKeys.adminUserGroup(group.id), group);
      invalidateAdminUserGroups(queryClient);
    },
  });
}

export function useDeactivateAdminUserGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const result = await api.delete<UserGroup | null>(
        `/api/admin/user-groups/${id}/`,
      );
      if (result && typeof result === "object" && "id" in result) return result;
      return api.get<UserGroup>(`/api/admin/user-groups/${id}/`);
    },
    onSuccess: (group) => {
      queryClient.setQueryData(queryKeys.adminUserGroup(group.id), group);
      invalidateAdminUserGroups(queryClient);
    },
  });
}

export function useAdminUsersQuery(enabled: boolean, filters: AdminUserFilters) {
  return useQuery({
    queryKey: queryKeys.adminUsers(filters),
    queryFn: () =>
      api.get<Paginated<AdminUser>>("/api/admin/users/", {
        search: filters.search,
        page: filters.page,
      }),
    enabled,
  });
}
