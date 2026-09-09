import type { components } from "./schema";

export type Schema = components["schemas"];

export type User = Schema["User"];
export type Strategy = Schema["Strategy"];
export type AdminStrategy = Schema["AdminStrategy"];
export type StrategyXSourceRequest = Schema["StrategyXSourceRequest"];
export type InvestmentTier = Schema["InvestmentTier"];
export type AccessUser = Schema["AccessUser"];
export type AdminUser = Schema["AdminUser"];
export type UserGroup = Schema["UserGroup"];
export type UserGroupBrief = Schema["UserGroupBrief"];
export type Visibility = Schema["VisibilityEnum"];

export type SignalSourceOption = {
  value: string;
  label: string;
  description: string;
  config_fields: string[];
  available: boolean;
};

export type StrategyTypeOption = {
  value: string;
  label: string;
  description: string;
  config_fields: string[];
  signal_sources?: SignalSourceOption[];
};

export type StrategyWrite = {
  name: string;
  description?: string;
  strategy_type: string;
  signal_source?: string;
  visibility?: Visibility;
  is_active?: boolean;
  x_source?: StrategyXSourceRequest | null;
  allowed_user_ids?: number[];
  allowed_group_ids?: number[];
};

export type UserGroupWrite = {
  name: string;
  description?: string;
  is_active?: boolean;
  member_ids?: number[];
};

export type Assignment = Schema["Assignment"] & {
  broker_account_id?: string;
};
export type Signal = Schema["Signal"];
export type BrokerConnection = Schema["BrokerConnection"];
export type BrokerConnectRequest = Schema["BrokerConnectRequest"];
export type RobinhoodOAuthStart = Schema["RobinhoodOAuthStart"];
export type RobinhoodOAuthComplete = Schema["RobinhoodOAuthCompleteResponse"];
export type RobinhoodAccount = Schema["BrokerAccount"] & {
  equity?: string | null;
  cash?: string | null;
  buying_power?: string | null;
};
export type AgentTool = {
  name: string;
  description: string;
  category: string;
  available: boolean;
};
export type Position = Schema["Position"];
export type Trade = Schema["Trade"] & {
  broker_account_id?: string;
};
export type TradeEvent = Schema["TradeEvent"];
export type BrokerOrder = Schema["BrokerOrder"];
export type Decision = Schema["Decision"];
export type Notification = Schema["Notification"] & {
  broker_account_id?: string;
  decision_id?: number | null;
};
export type PersonalPerformance = Schema["PersonalPerformance"];
export type AccountPerformance = {
  lifetime_realized_pnl: string;
  lifetime_unrealized_pnl: string;
  lifetime_total_pnl: string;
  daily_realized_pnl: string;
  weekly_realized_pnl: string;
  open_positions: number;
  closed_trades: number;
};
export type BrokerAccountDetail = {
  connection: BrokerConnection;
  account: RobinhoodAccount;
  trading_enabled: boolean;
  assignment: Assignment | null;
  performance: AccountPerformance;
};
export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type RegisterResponse = {
  user: User;
  access: string;
  refresh: string;
};

export type TokenPair = {
  access: string;
  refresh: string;
};

export function pageFromNext(url: string | null | undefined): number | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    const page = parsed.searchParams.get("page");
    return page ? Number(page) : 1;
  } catch {
    return null;
  }
}
