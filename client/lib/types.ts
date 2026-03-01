// API Response Types

export interface Journal {
  id: string;
  name: string;
  url: string | null;
  source_website: string;
  type: string;
  open_access: boolean;
  letter_group: string | null;
  publisher: string | null;
  issue_count: number;
  article_count: number;
  issn: string | null;
  eissn: string | null;
  impact_factor: number | null;
  subjects: string[];
  created_at: string;
  updated_at: string;
}

export interface Issue {
  id: string;
  journal_id: string;
  journal_name: string;
  issue_number: string | null;
  volume: string | null;
  number: string | null;
  date: string | null;
  year: number | null;
  month: number | null;
  url: string | null;
  status: string | null;
  article_count: number;
}

export interface Article {
  id: string;
  journal_id: string;
  journal_name: string;
  issue_id: string;
  issue_number: string | null;
  source_website: string;
  title: string;
  url: string;
  doi: string | null;
  abstract: string | null;
  keywords: string[];
  authors: string[];
  publication_date: string | null;
  publication_year: number | null;
  pages: string | null;
  publisher: string | null;
  article_type: string | null;
  open_access: boolean;
  pdf_url: string | null;
  citation_count: number;
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ScraperStatus {
  scraper_type: string;
  status: 'idle' | 'starting' | 'running' | 'paused' | 'stopping' | 'stopped' | 'error' | 'completed';
  current_journal: string | null;
  current_journal_index: number;
  total_journals: number;
  journals_scraped: number;
  issues_scraped: number;
  articles_scraped: number;
  articles_updated: number;
  errors_count: number;
  started_at: string | null;
  last_activity: string | null;
  elapsed_seconds: number;
  progress_percent: number;
  last_error: string | null;
}

export interface AllScrapersStatus {
  ieee: ScraperStatus;
  sciencedirect: ScraperStatus;
  any_running: boolean;
  all_completed: boolean;
}

export interface GeneralStats {
  database: {
    journals: number;
    issues: number;
    articles: number;
    data_size_mb: number;
    storage_size_mb: number;
  };
  scrapers: {
    ieee_status: string;
    sciencedirect_status: string;
    any_running: boolean;
  };
}

export interface ArticleStats {
  total: number;
  by_source: Record<string, {
    _id: string;
    count: number;
    with_abstract: number;
    with_doi: number;
    open_access: number;
  }>;
  by_year: Record<string, number>;
  top_keywords: Array<{ _id: string; count: number }>;
  top_authors: Array<{ _id: string; count: number }>;
}

export interface SearchResult {
  query: string;
  search_type: string;
  count: number;
  items: Array<{
    id: string;
    title: string;
    journal_name: string;
    authors: string[];
    publication_year: number | null;
    doi: string | null;
    url: string;
    abstract: string | null;
    keywords: string[];
  }>;
}

// ==================== Elasticsearch Types ====================

export interface ElasticSearchHit {
  id: string;
  title: string;
  journal_name: string;
  authors: string[];
  publication_year: number | null;
  doi: string | null;
  url: string;
  abstract: string | null;
  keywords: string[];
  source_website: string;
  score: number;
  highlights?: {
    title?: string[];
    abstract?: string[];
    keywords?: string[];
    authors?: string[];
  };
}

export interface SearchFacetBucket {
  key: string;
  count: number;
}

export interface SearchFacets {
  sources: SearchFacetBucket[];
  years: SearchFacetBucket[];
  journals: SearchFacetBucket[];
  keywords: SearchFacetBucket[];
}

export interface ElasticSearchResult {
  query: string;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  items: ElasticSearchHit[];
  facets?: SearchFacets;
}

export interface SearchSuggestion {
  text: string;
  score?: number;
}

// ==================== WebSocket Types ====================

export interface ScraperEvent {
  type: 'status_update' | 'progress' | 'log' | 'error' | 'completed' | 'started' | 'stopped' | 'pong';
  scraper_type: string;
  timestamp: string;
  data: Record<string, unknown>;
}

