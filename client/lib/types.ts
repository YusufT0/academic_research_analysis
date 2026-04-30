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
  openalex_id?: string | null;
  h_index?: number | null;
  i10_index?: number | null;
  average_citation_count?: number | null;
  total_citation_count?: number;
  last_citation_update_date?: string | null;
  aims_and_scope?: string | null;
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
  introduction: string | null;
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
  openalex_id?: string | null;
  is_openalex_indexed?: boolean;
  citation_percentile?: number | null;
  fwci?: number | null;
  last_citation_update_date?: string | null;
  references?: string[];
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

export interface IssueProgress {
  title: string;
  articles_count: number;
  article_list?: string[];
}

export interface CompletedJournal {
  name: string;
  articles_count: number;
  issues?: IssueProgress[];
}

export interface ScraperStatus {
  scraper_type: string;
  status: 'idle' | 'starting' | 'running' | 'paused' | 'stopping' | 'stopped' | 'error' | 'completed';
  current_journal: string | null;
  current_journal_index: number;
  total_journals: number;
  pending_journals: string[];
  completed_journals: CompletedJournal[];
  current_issue: string | null;
  current_issue_index: number;
  total_issues: number;
  completed_issues: IssueProgress[];
  pending_issues: string[];
  article_list: string[];
  current_article: string | null;
  current_article_index: number;
  total_articles: number;
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
  is_single_journal_mode?: boolean;
}

export interface AllScrapersStatus {
  ieee: ScraperStatus;
  sciencedirect: ScraperStatus;
  acm: ScraperStatus;
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
    acm_status: string;
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
  unique_keywords_count: number;
  unique_authors_count: number;
  unique_years_count: number;
}

export interface CitationStats {
  citation_distribution: Array<{ _id: number | string; count: number }>;
  top_cited_articles: Array<{
    _id: string;
    title: string;
    authors: string[];
    citation_count: number;
    publication_year: number | null;
  }>;
  citations_by_pub_year: Array<{
    _id: number;
    total_citations: number;
    article_count: number;
  }>;
  top_h_index_journals: Array<{
    _id: string;
    name: string;
    h_index: number;
    i10_index: number;
    total_citation_count: number;
  }>;
}

export interface SearchResult {
  query: string;
  search_type: string;
  count: number;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
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
    source_website?: string;
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

// ==================== Citation Graph Types ====================

export interface CitationGraphNode {
  id: string;
  title: string | null;
  doi: string | null;
  cited_by_count: number | null;
  publication_year: number | null;
  is_root: boolean;
  is_internal: boolean;
  internal_article_id: string | null;
  depth: number;
}

export interface CitationGraphEdge {
  source: string;
  target: string;
  depth: number;
}

export interface CitationGraphData {
  root_article_id: string;
  root_openalex_id: string;
  max_depth: number;
  node_count: number;
  edge_count: number;
  computed_at: string;
  nodes: CitationGraphNode[];
  edges: CitationGraphEdge[];
}

export interface CitationExpandData {
  expanded_node_id: string;
  node_count: number;
  edge_count: number;
  nodes: CitationGraphNode[];
  edges: CitationGraphEdge[];
}

// ==================== NLP / Topic Trends Types ====================

export interface TopicCluster {
  cluster_id: number;
  topic_tag: string;
  article_count: number;
}

export interface TopicTrendsData {
  graph_data: Array<Record<string, string | number>>;
  clusters: TopicCluster[];
}

export interface NlpStatus {
  has_trained_model: boolean;
  latest_model_version: string | null;
  latest_training_date: string | null;
  is_training: boolean;
  cache_loaded: boolean;
  cached_version: string | null;
  pkl_model_available?: boolean;
}

// ==================== NLP Search Types ====================

export interface NlpSearchArticle {
  id: string;
  title: string;
  abstract?: string;
  doi?: string;
  url?: string;
  keywords?: string[];
  similarity_score?: number;
  cluster_id?: number;
}

export interface NlpSearchResponse {
  query: string;
  model_version: string;
  similarity_score: number;
  cluster_id: number | null;
  cluster_label: string | null;
  total_in_cluster: number | null;
  articles: NlpSearchArticle[];
}

export type NlpBarChartData = Record<string, number>;
export type NlpPieChartData = Record<string, number>;

export interface NlpScatterPoint {
  x: number;
  y: number;
}

// ==================== Journal Citation Metrics ====================

export interface JournalCitationMetrics {
  id: string;
  name: string;
  openalex_id: string | null;
  h_index: number | null;
  i10_index: number | null;
  average_citation_count: number | null;
  total_citation_count: number;
  historical_citation_data: Record<string, number>;
  last_citation_update_date: string | null;
}

// ==================== WebSocket Types ====================

export interface ScraperEvent {
  type: 'status_update' | 'progress' | 'log' | 'error' | 'completed' | 'started' | 'stopped' | 'pong' | 'connected' | 'subscribed';
  scraper_type: string;
  timestamp: string;
  data: Record<string, unknown>;
}

