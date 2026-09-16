import type { components } from './schema';

// FastAPI serializes defaults and null fields; derive every response shape from OpenAPI.
type Complete<T> = T extends (infer U)[] ? Complete<U>[] : T extends object ? {
  [K in keyof T]-?: Complete<Exclude<T[K], undefined>>;
} : T;
type Model<K extends keyof components['schemas']> = Complete<components['schemas'][K]>;
export type Timeframe = '1D' | '5D' | '1M' | '1Y';
export type Metadata = Model<'Metadata'>;
export type Status = Metadata['status'];
export type Instrument = Model<'Instrument'>;
export type Bar = Model<'Bar'>;
export type PriceResponse = Model<'PriceResponse'>;
export type Distribution = Model<'Distribution'>;
export type Analytics = Model<'AnalyticsResponse'>;
export type Fundamentals = Model<'FundamentalsResponse'>;
export type Quarter = Model<'Quarter'>;
export type StatementRow = Model<'StatementRow'>;
export type Position = Model<'Position'>;
export type Portfolio = Model<'PortfolioRecord'>;
export type PortfolioAnalytics = Model<'PortfolioAnalyticsResponse'>;
export type Auth = Model<'AuthResponse'>;
