// Mirrors the backend response models (backend/app/schemas.py, backend/app/analysis/models.py).

export type TrendDirection = 'increasing' | 'decreasing' | 'stable' | 'insufficient_data'

export interface CountBucket {
  period_start: string
  commits: number
}

export interface AverageBucket {
  period_start: string
  value: number
}

export interface CommitTrend {
  direction: TrendDirection
  slope_per_week: number
  last_4_weeks: number
  previous_4_weeks: number
  change_percent: number | null
}

export interface ActiveAuthor {
  name: string
  login: string | null
  is_bot: boolean
  commits: number
  percentage: number
  first_commit_at: string
  last_commit_at: string
}

export interface RecentActivity {
  last_commit_at: string | null
  days_since_last_commit: number | null
  commits_last_7_days: number
  commits_last_30_days: number
  active_authors_last_30_days: number
}

export interface CommitStats {
  window_days: number
  since: string
  effective_since: string
  commits_analyzed: number
  truncated: boolean
  average_weekly_commits: number
  weekly: CountBucket[]
  monthly: CountBucket[]
  rolling_weekly_average: AverageBucket[]
  by_weekday: number[]
  trend: CommitTrend
  active_authors: ActiveAuthor[]
  recent_activity: RecentActivity
}

export interface ContributorShare {
  login: string
  is_bot: boolean
  contributions: number
  percentage: number
  avatar_url: string | null
  html_url: string | null
}

export interface ContributorStats {
  available: boolean
  listed: number
  total_contributions: number
  top_contributor_share: number | null
  top_5_share: number | null
  gini_coefficient: number | null
  bus_factor: number | null
}

export interface LanguageShare {
  language: string
  bytes: number
  percentage: number
}

export interface RecentCommit {
  sha: string
  message: string
  author_name: string
  author_login: string | null
  authored_at: string
  html_url: string | null
}

export interface RepositoryInfo {
  full_name: string
  owner: string
  name: string
  html_url: string
  owner_avatar_url: string | null
  description: string | null
  homepage: string | null
  default_branch: string
  primary_language: string | null
  license: string | null
  topics: string[]
  is_fork: boolean
  is_archived: boolean
  created_at: string
  updated_at: string
  pushed_at: string | null
}

export interface RepositoryMetrics {
  stars: number
  forks: number
  open_issues: number
  watchers: number | null
  size_kb: number
  contributors_count: number | null
  total_commits: number | null
}

export interface AnalysisDetail {
  id: number
  analyzed_at: string
  from_cache: boolean
  repository: RepositoryInfo
  metrics: RepositoryMetrics
  languages: LanguageShare[]
  contributors: ContributorShare[]
  contributor_stats: ContributorStats
  commit_stats: CommitStats
  recent_commits: RecentCommit[]
}

export interface AnalysisSummary {
  id: number
  analyzed_at: string
  full_name: string
  html_url: string
  description: string | null
  primary_language: string | null
  stars: number
  forks: number
  open_issues: number
  contributors_count: number | null
  commits_last_30_days: number
  average_weekly_commits: number
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface TrackedRepository {
  full_name: string
  html_url: string
  analyses_count: number
  first_analyzed_at: string
  last_analyzed_at: string
  latest: AnalysisSummary
}

export interface HistoryPoint {
  analysis_id: number
  analyzed_at: string
  stars: number
  forks: number
  open_issues: number
  watchers: number | null
  contributors_count: number | null
  total_commits: number | null
  commits_last_30_days: number
  average_weekly_commits: number
}

export interface MetricChange {
  first: number | null
  last: number | null
  absolute: number | null
  percent: number | null
}

export interface RepositoryHistory {
  full_name: string
  html_url: string
  points: HistoryPoint[]
  changes: Record<string, MetricChange>
}

export interface ComparedRepository {
  analysis_id: number
  full_name: string
  html_url: string
  analyzed_at: string
  primary_language: string | null
  stars: number
  forks: number
  open_issues: number
  contributors_count: number | null
  total_commits: number | null
  commits_analyzed: number
  average_weekly_commits: number
  commits_last_30_days: number
  days_since_last_commit: number | null
  bus_factor: number | null
  trend: TrendDirection
  repo_created_at: string
}

export interface Comparison {
  repositories: ComparedRepository[]
  languages: { language: string; shares: Record<string, number> }[]
  weekly_activity: { weeks: string[]; series: Record<string, (number | null)[]> }
}

export interface RateLimitInfo {
  limit: number
  remaining: number
  used: number
  reset_at: string
  authenticated: boolean
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: Record<string, unknown>
  }
}
