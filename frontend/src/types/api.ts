// ── Auth ──────────────────────────────────────────────────────────────────────

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserOut {
  id: string;
  email: string;
}

// ── Stock ─────────────────────────────────────────────────────────────────────

export interface StockInfo {
  ticker: string;
  name?: string;
  sector?: string;
  industry?: string;
  market_cap?: number;
  current_price?: number;
  currency?: string;
}

// ── Watchlist ─────────────────────────────────────────────────────────────────

export interface WatchlistItemCreate {
  ticker: string;
  memo?: string;
}

export interface WatchlistItemOut {
  id: string;
  ticker: string;
  memo?: string;
  added_at: string;
}

// ── Prediction ────────────────────────────────────────────────────────────────

export interface PredictionOut {
  id: string;
  ticker: string;
  signal: string;
  up_prob: number;
  model_type?: string;
  complexity?: number;
  xgb_weight?: number;
  lstm_weight?: number;
  created_at: string;
}

// ── Scanner ───────────────────────────────────────────────────────────────────

export interface ScanJobCreate {
  sector?: string;
}

export interface ScanJobOut {
  id: string;
  status: string;
  total?: number;
  processed: number;
  sector?: string;
  started_at?: string;
  finished_at?: string;
  created_at: string;
}

export interface ScanResultOut {
  id: string;
  job_id: string;
  ticker: string;
  composite_score?: number;
  up_prob?: number;
  signal?: string;
  sector?: string;
  est_upside?: number;
  cached_at: string;
}

// ── ML — Technical ────────────────────────────────────────────────────────────

export interface SignalItem {
  action: string;
  description: string;
  color: string;
}

export interface TechnicalResponse {
  ticker: string;
  period_days: number;
  data_points: number;
  signals: Record<string, SignalItem>;
  support_resistance: Record<string, number>;
  latest_indicators: Record<string, number | null>;
  ma_trend: string;
  overall_signal: string;
}

// ── ML — Sentiment ────────────────────────────────────────────────────────────

export interface SentimentResponse {
  ticker: string;
  overall_sentiment: string;
  sentiment_score: number;
  news_count: number;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
}

// ── ML — Predict ──────────────────────────────────────────────────────────────

export interface PredictRequest {
  ticker: string;
  period_days?: number;
}

export interface PredictResponse {
  ticker: string;
  signal: string;
  up_prob: number;
  model_type: string;
  complexity?: number;
  xgb_weight?: number;
  lstm_weight?: number;
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

export interface ScanProgressMessage {
  type: "progress" | "complete" | "error";
  job_id: string;
  processed?: number;
  total?: number;
  ticker?: string;
  message?: string;
}

// ── Common ────────────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string;
}
