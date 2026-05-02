// API Client for Backend Communication

import type {
  Journal,
  Issue,
  Article,
  PaginatedResponse,
  AllScrapersStatus,
  GeneralStats,
  ArticleStats,
  SearchResult,
  ElasticSearchResult,
  SearchSuggestion,
  SearchFacets,
  NlpSearchResponse,
  NlpBarChartData,
  NlpPieChartData,
  NlpScatterPoint,
  NlpStatus,
  JournalCitationMetrics,
} from './types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(response.status, `API Error: ${response.statusText}`);
  }

  return response.json();
}

// ==================== Stats ====================

export async function getGeneralStats(): Promise<GeneralStats> {
  return fetchApi<GeneralStats>('/stats');
}

export async function getArticleStats(): Promise<ArticleStats> {
  return fetchApi<ArticleStats>('/stats/articles');
}

export async function getCitationStats(): Promise<import('./types').CitationStats> {
  return fetchApi<import('./types').CitationStats>('/stats/citations');
}

export async function getScraperStats() {
  return fetchApi('/stats/scraper');
}

// ==================== Journals ====================

export interface YearRange {
  min_year: number;
  max_year: number;
}

export interface JournalFilters {
  page?: number;
  page_size?: number;
  source_website?: string;
  publisher?: string;
  open_access?: boolean;
  search?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  year_min?: number;
  year_max?: number;
}

export async function getJournals(filters: JournalFilters = {}): Promise<PaginatedResponse<Journal>> {
  const params = new URLSearchParams();

  if (filters.page) params.set('page', filters.page.toString());
  if (filters.page_size) params.set('page_size', filters.page_size.toString());
  if (filters.source_website) params.set('source_website', filters.source_website);
  if (filters.publisher) params.set('publisher', filters.publisher);
  if (filters.open_access !== undefined) params.set('open_access', filters.open_access.toString());
  if (filters.search) params.set('search', filters.search);
  if (filters.sort_by) params.set('sort_by', filters.sort_by);
  if (filters.sort_order) params.set('sort_order', filters.sort_order);
  if (filters.year_min !== undefined) params.set('year_min', filters.year_min.toString());
  if (filters.year_max !== undefined) params.set('year_max', filters.year_max.toString());

  return fetchApi<PaginatedResponse<Journal>>(`/journals?${params.toString()}`);
}

export async function getJournalYearRange(): Promise<YearRange> {
  return fetchApi<YearRange>('/journals/year-range');
}

export async function getJournal(id: string): Promise<Journal> {
  return fetchApi<Journal>(`/journals/${id}`);
}

export async function getJournalIssues(journalId: string, page = 1, pageSize = 20) {
  return fetchApi(`/journals/${journalId}/issues?page=${page}&page_size=${pageSize}`);
}

export async function getJournalArticles(journalId: string, page = 1, pageSize = 20) {
  return fetchApi(`/journals/${journalId}/articles?page=${page}&page_size=${pageSize}`);
}

export async function getJournalCitationMetrics(journalId: string): Promise<JournalCitationMetrics> {
  return fetchApi<JournalCitationMetrics>(`/journals/${journalId}/citation-metrics`);
}

// ==================== Articles ====================

export interface ArticleFilters {
  id?: string;
  page?: number;
  page_size?: number;
  journal_id?: string;
  issue_id?: string;
  source_website?: string;
  publication_year?: number;
  year_min?: number;
  year_max?: number;
  open_access?: boolean;
  article_type?: string;
  has_doi?: boolean;
  has_abstract?: boolean;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  include_no_date?: boolean;
}

export async function getArticles(filters: ArticleFilters = {}): Promise<PaginatedResponse<Article>> {
  const params = new URLSearchParams();

  if (filters.id) params.set('id', filters.id);
  if (filters.page) params.set('page', filters.page.toString());
  if (filters.page_size) params.set('page_size', filters.page_size.toString());
  if (filters.journal_id) params.set('journal_id', filters.journal_id);
  if (filters.issue_id) params.set('issue_id', filters.issue_id);
  if (filters.source_website) params.set('source_website', filters.source_website);
  if (filters.publication_year) params.set('publication_year', filters.publication_year.toString());
  if (filters.year_min !== undefined) params.set('year_min', filters.year_min.toString());
  if (filters.year_max !== undefined) params.set('year_max', filters.year_max.toString());
  if (filters.open_access !== undefined) params.set('open_access', filters.open_access.toString());
  if (filters.article_type) params.set('article_type', filters.article_type);
  if (filters.has_doi !== undefined) params.set('has_doi', filters.has_doi.toString());
  if (filters.has_abstract !== undefined) params.set('has_abstract', filters.has_abstract.toString());
  if (filters.sort_by) params.set('sort_by', filters.sort_by);
  if (filters.sort_order) params.set('sort_order', filters.sort_order);
  if (filters.include_no_date !== undefined) params.set('include_no_date', filters.include_no_date.toString());

  return fetchApi<PaginatedResponse<Article>>(`/articles?${params.toString()}`);
}

export async function getArticleYearRange(): Promise<YearRange> {
  return fetchApi<YearRange>('/articles/year-range');
}

export async function getArticle(id: string): Promise<Article> {
  return fetchApi<Article>(`/articles/${id}`);
}

export async function getArticleCitationMetrics(id: string) {
  return fetchApi(`/articles/${id}/citation-metrics`);
}

// ==================== OpenAlex ====================

export async function getOpenAlexStatus() {
  return fetchApi(`/openalex/status`);
}

export async function startOpenAlexScan() {
  return fetchApi(`/openalex/start`, { method: 'POST' });
}

export async function stopOpenAlexScan() {
  return fetchApi(`/openalex/stop`, { method: 'POST' });
}

export async function searchArticles(
  query: string,
  searchType: 'text' | 'title' | 'keyword' | 'author' = 'text',
  page = 1,
  pageSize = 20
): Promise<SearchResult> {
  const params = new URLSearchParams({
    q: query,
    search_type: searchType,
    page: page.toString(),
    page_size: pageSize.toString(),
  });

  return fetchApi<SearchResult>(`/articles/search?${params.toString()}`);
}

// ==================== Issues ====================

export interface IssueFilters {
  page?: number;
  page_size?: number;
  journal_id?: string;
  source_website?: string;
  year?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export async function getIssues(filters: IssueFilters = {}): Promise<PaginatedResponse<Issue>> {
  const params = new URLSearchParams();

  if (filters.page) params.set('page', filters.page.toString());
  if (filters.page_size) params.set('page_size', filters.page_size.toString());
  if (filters.journal_id) params.set('journal_id', filters.journal_id);
  if (filters.source_website) params.set('source_website', filters.source_website);
  if (filters.year) params.set('year', filters.year.toString());
  if (filters.sort_by) params.set('sort_by', filters.sort_by);
  if (filters.sort_order) params.set('sort_order', filters.sort_order);

  return fetchApi<PaginatedResponse<Issue>>(`/issues?${params.toString()}`);
}

// ==================== Scrapers ====================

export async function getScrapersStatus(): Promise<AllScrapersStatus> {
  return fetchApi<AllScrapersStatus>('/scrapers/status');
}

export async function startIeeeScraper(headless = true, maxArticles = 10, depth = 1, issueOrder = 'newest_first', continuous = false) {
  return fetchApi('/scrapers/ieee/start', {
    method: 'POST',
    body: JSON.stringify({ headless, max_articles: maxArticles, depth, issues_order: issueOrder, continuous }),
  });
}

export async function stopIeeeScraper() {
  return fetchApi('/scrapers/ieee/stop', { method: 'POST' });
}

export async function pauseIeeeScraper() {
  return fetchApi('/scrapers/ieee/pause', { method: 'POST' });
}

export async function resumeIeeeScraper() {
  return fetchApi('/scrapers/ieee/resume', { method: 'POST' });
}

export async function startScienceDirectScraper(headless = true, maxArticles = 5, depth = 1, issueOrder = 'newest_first', continuous = false) {
  return fetchApi('/scrapers/sciencedirect/start', {
    method: 'POST',
    body: JSON.stringify({ headless, max_articles: maxArticles, depth, issues_order: issueOrder, continuous }),
  });
}

export async function stopScienceDirectScraper() {
  return fetchApi('/scrapers/sciencedirect/stop', { method: 'POST' });
}

export async function pauseScienceDirectScraper() {
  return fetchApi('/scrapers/sciencedirect/pause', { method: 'POST' });
}

export async function resumeScienceDirectScraper() {
  return fetchApi('/scrapers/sciencedirect/resume', { method: 'POST' });
}

export async function startAcmScraper(headless = true, maxArticles = 10, depth = 1, issueOrder = 'newest_first', continuous = false) {
  return fetchApi('/scrapers/acm/start', {
    method: 'POST',
    body: JSON.stringify({ headless, max_articles: maxArticles, depth, issues_order: issueOrder, continuous }),
  });
}

export async function stopAcmScraper() {
  return fetchApi('/scrapers/acm/stop', { method: 'POST' });
}

export async function pauseAcmScraper() {
  return fetchApi('/scrapers/acm/pause', { method: 'POST' });
}

export async function resumeAcmScraper() {
  return fetchApi('/scrapers/acm/resume', { method: 'POST' });
}

export async function startWileyScraper(headless = true, maxArticles = 10, depth = 1, issueOrder = 'newest_first', continuous = false) {
  return fetchApi('/scrapers/wiley/start', {
    method: 'POST',
    body: JSON.stringify({ headless, max_articles: maxArticles, depth, issues_order: issueOrder, continuous }),
  });
}

export async function stopWileyScraper() {
  return fetchApi('/scrapers/wiley/stop', { method: 'POST' });
}

export async function pauseWileyScraper() {
  return fetchApi('/scrapers/wiley/pause', { method: 'POST' });
}

export async function resumeWileyScraper() {
  return fetchApi('/scrapers/wiley/resume', { method: 'POST' });
}

export async function startAllScrapers(headless = true) {
  return fetchApi('/scrapers/start-all', {
    method: 'POST',
    body: JSON.stringify({ headless }),
  });
}

export async function stopAllScrapers() {
  return fetchApi('/scrapers/stop-all', { method: 'POST' });
}

export interface ScraperLogsResponse {
  logs: Array<{
    timestamp: string;
    level: string;
    message: string;
    scraper_type: string;
    details?: Record<string, unknown>;
  }>;
}

export async function getScraperLogs(scraperType = 'all', limit = 50): Promise<ScraperLogsResponse> {
  return fetchApi<ScraperLogsResponse>(`/scrapers/logs?scraper_type=${scraperType}&limit=${limit}`);
}

// ==================== Journal URL Scraper ====================

export interface JournalUrlValidateResponse {
  valid: boolean;
  scraper_type: string | null;
  message: string;
}

export interface JournalExistsResponse {
  exists: boolean;
  journal: {
    id: string;
    name: string;
    url: string | null;
    source_website: string;
    article_count: number;
    issue_count: number;
    publisher: string | null;
    issn: string | null;
    updated_at: string | null;
    created_at: string | null;
  } | null;
}

export async function validateJournalUrl(url: string): Promise<JournalUrlValidateResponse> {
  return fetchApi<JournalUrlValidateResponse>('/scrapers/journal/validate', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export async function checkJournalExists(url: string): Promise<JournalExistsResponse> {
  const params = new URLSearchParams({ url });
  return fetchApi<JournalExistsResponse>(`/scrapers/journal/check-exists?${params.toString()}`);
}

export async function startSingleJournalScraper(
  url: string,
  scraperType: string,
  maxArticles = 50,
  depth = 1,
  headless = false,
) {
  return fetchApi('/scrapers/journal/start', {
    method: 'POST',
    body: JSON.stringify({
      url,
      scraper_type: scraperType,
      max_articles: maxArticles,
      depth,
      headless,
    }),
  });
}

export async function getSingleJournalScraperStatus(scraperType: string) {
  return fetchApi(`/scrapers/journal/status?scraper_type=${scraperType}`);
}

export async function stopSingleJournalScraper(scraperType: string): Promise<{ success: boolean }> {
  return fetchApi<{ success: boolean }>(`/scrapers/journal/stop?scraper_type=${scraperType}`, { method: 'POST' });
}

export interface AnalysisStep {
  status: 'pending' | 'running' | 'done' | 'error';
  message: string;
}

export interface AnalysisTaskProgress {
  task_id: string;
  status: 'running' | 'done' | 'done_with_errors' | 'error';
  error?: string;
  steps: {
    cluster_update: AnalysisStep;
    openalex: AnalysisStep;
    elasticsearch: AnalysisStep;
  };
  result: {
    model_version: string;
    new_articles_found: number;
    assigned: number;
    noise: number;
    total_embeddings_saved: number;
    status: string;
    affected_clusters: { cluster_id: number; topic_tag: string; article_count: number }[];
  } | null;
}

export interface ActiveJournalAnalysisResponse {
  found: boolean;
  task_id?: string;
  status?: string;
  journal_id?: string;
  model_version?: string | null;
  started_at?: string;
}

export async function startJournalAnalysis(
  journalId: string,
  modelVersion?: string | null,
): Promise<{ task_id: string; status: string }> {
  const params = new URLSearchParams({ journal_id: journalId });
  if (modelVersion) params.set('model_version', modelVersion);
  return fetchApi<{ task_id: string; status: string }>(`/nlp/assign_for_journal?${params.toString()}`, { method: 'POST' });
}

export async function getAnalysisProgress(taskId: string): Promise<AnalysisTaskProgress> {
  return fetchApi<AnalysisTaskProgress>(`/nlp/analysis_progress/${taskId}`);
}

export async function getActiveJournalAnalysisForJournal(
  journalId: string,
  modelVersion?: string | null,
): Promise<ActiveJournalAnalysisResponse> {
  const params = new URLSearchParams({ journal_id: journalId });
  if (modelVersion) params.set('model_version', modelVersion);
  return fetchApi<ActiveJournalAnalysisResponse>(`/nlp/analysis_active_for_journal?${params.toString()}`);
}


// ==================== Elasticsearch Search ====================

export interface ElasticSearchFilters {
  query: string;
  source_website?: string;
  year?: number;
  journal_name?: string;
  page?: number;
  page_size?: number;
}

export async function elasticSearch(filters: ElasticSearchFilters): Promise<ElasticSearchResult> {
  const params = new URLSearchParams();
  params.set('q', filters.query);
  if (filters.source_website) params.set('source_website', filters.source_website);
  if (filters.year) params.set('year', filters.year.toString());
  if (filters.journal_name) params.set('journal_name', filters.journal_name);
  if (filters.page) params.set('page', filters.page.toString());
  if (filters.page_size) params.set('page_size', filters.page_size.toString());

  return fetchApi<ElasticSearchResult>(`/search?${params.toString()}`);
}

export async function getSearchSuggestions(prefix: string, limit = 5): Promise<SearchSuggestion[]> {
  const params = new URLSearchParams({ q: prefix, limit: limit.toString() });
  const data = await fetchApi<{ query: string; items?: { id: string; text: string }[]; suggestions: string[] }>(`/search/suggest?${params.toString()}`);
  if (data.items?.length) {
    return data.items.map(({ id, text }) => ({ id, text }));
  }
  return (data.suggestions || []).map(text => ({ text }));
}

export async function getSearchFacets(): Promise<SearchFacets> {
  return fetchApi<SearchFacets>('/search/facets');
}

// ==================== Citation Graph ====================

export async function getCitationGraph(
  articleId: string,
  depth = 2,
  forceRefresh = false,
): Promise<import('./types').CitationGraphData> {
  const params = new URLSearchParams({
    article_id: articleId,
    depth: String(depth),
    force_refresh: String(forceRefresh),
  });
  return fetchApi<import('./types').CitationGraphData>(`/citation-graph?${params.toString()}`);
}

export async function expandCitationNode(
  openalexId: string,
  depth = 1,
): Promise<import('./types').CitationExpandData> {
  const params = new URLSearchParams({
    openalex_id: openalexId,
    depth: String(depth),
  });
  return fetchApi<import('./types').CitationExpandData>(`/citation-graph/expand?${params.toString()}`);
}

// ==================== Authors ====================

export interface AuthorFilters {
  page?: number;
  page_size?: number;
  sort_by?: string;
  search?: string;
  min_articles?: number;
}

export async function getAuthors(filters: AuthorFilters = {}) {
  const params = new URLSearchParams();
  if (filters.page) params.set('page', filters.page.toString());
  if (filters.page_size) params.set('page_size', filters.page_size.toString());
  if (filters.sort_by) params.set('sort_by', filters.sort_by);
  if (filters.search) params.set('search', filters.search);
  if (filters.min_articles) params.set('min_articles', filters.min_articles.toString());

  return fetchApi<any>(`/authors?${params.toString()}`);
}

export async function getAuthorProfile(name: string) {
  return fetchApi<any>(`/authors/${encodeURIComponent(name)}`);
}

// ==================== NLP / Topic Trends ====================

// ==================== Search / Autocomplete ====================

export async function suggestJournals(q: string, limit = 15): Promise<string[]> {
  if (!q.trim()) return [];
  const params = new URLSearchParams({ q: q.trim(), limit: String(limit) });
  const res = await fetchApi<{ query: string; suggestions: string[] }>(`/search/suggest/journals?${params.toString()}`);
  return res.suggestions ?? [];
}

export async function getAllTopicTrends(model_version: string, top_n = 10): Promise<import('./types').TopicTrendsData> {
  const params = new URLSearchParams({ model_version, top_n: String(top_n) });
  return fetchApi<import('./types').TopicTrendsData>(`/nlp/get_all_topic_trends?${params.toString()}`);
}

export async function getJournalTopicTrends(name: string, model_version: string, top_n = 10): Promise<import('./types').TopicTrendsData> {
  const params = new URLSearchParams({ name, model_version, top_n: String(top_n) });
  return fetchApi<import('./types').TopicTrendsData>(`/nlp/get_journal_topic_trends?${params.toString()}`);
}

export async function getPublisherTopicTrends(name: string, model_version: string, top_n = 10): Promise<import('./types').TopicTrendsData> {
  const params = new URLSearchParams({ name, model_version, top_n: String(top_n) });
  return fetchApi<import('./types').TopicTrendsData>(`/nlp/get_publisher_topic_trends?${params.toString()}`);
}

export async function listClusters(
  model_version: string,
  cluster_type: 'all' | 'journal' | 'publisher' = 'all',
  group_id?: string,
): Promise<{ clusters: import('./types').TopicCluster[] }> {
  const params = new URLSearchParams({ model_version, cluster_type });
  if (group_id) params.set('group_id', group_id);
  return fetchApi<{ clusters: import('./types').TopicCluster[] }>(`/nlp/list_clusters?${params.toString()}`);
}

export async function getClusterTrendSeries(
  cluster_id: number,
  model_version: string,
  cluster_type: 'all' | 'journal' | 'publisher' = 'all',
  group_id?: string,
): Promise<{ topic_tag: string; cluster_id: number; series: Array<{ date: string; count: number }> }> {
  const params = new URLSearchParams({ cluster_id: String(cluster_id), model_version, cluster_type });
  if (group_id) params.set('group_id', group_id);
  return fetchApi(`/nlp/cluster_trend_series?${params.toString()}`);
}

export async function getClusterArticles(
  cluster_id: number,
  model_version: string,
  options: { skip?: number; limit?: number; search?: string } = {},
): Promise<{ cluster_id: number; total_count: number; skip: number; limit: number; articles: Array<{ id: string; title: string; doi?: string; url?: string; publication_date?: string }> }> {
  const params = new URLSearchParams({ model_version });
  if (options.skip !== undefined) params.set('skip', String(options.skip));
  if (options.limit !== undefined) params.set('limit', String(options.limit));
  if (options.search) params.set('search', options.search);
  return fetchApi(`/nlp/clusters/${cluster_id}/articles?${params.toString()}`);
}

export async function getAuthorArticles(name: string, page: number = 1, page_size: number = 15) {
  const params = new URLSearchParams();
  params.set('page', page.toString());
  params.set('page_size', page_size.toString());
  return fetchApi<any>(`/authors/${encodeURIComponent(name)}/articles?${params.toString()}`);
}

// ==================== NLP / AI Analysis ====================

export async function nlpTrain(modelVersion?: string): Promise<{ status: string; message: string }> {
  return fetchApi('/nlp/train', {
    method: 'POST',
    body: JSON.stringify({ model_version: modelVersion }),
  });
}

export async function getNlpClusters() {
  return fetchApi<any[]>('/nlp/clusters');
}

export async function getNlpHistory() {
  return fetchApi<any>('/nlp/history');
}

export async function getCacheStats() {
  return fetchApi<any>('/stats/cache');
}

export async function clearCache(pattern?: string) {
  const params = pattern ? `?pattern=${encodeURIComponent(pattern)}` : '';
  return fetchApi<{ message: string }>(`/stats/cache${params}`, { method: 'DELETE' });
}

export async function syncElasticsearch() {
  return fetchApi<{ message: string }>('/search/sync', { method: 'POST' });
}

export async function getJournalStats() {
  return fetchApi<any>('/stats/journals');
}

export async function startAllScrapersSequential(headless = true) {
  return fetchApi('/scrapers/start-all-sequential', {
    method: 'POST',
    body: JSON.stringify({ headless }),
  });
}

export async function startAllScrapersRoundRobin(headless = true) {
  return fetchApi('/scrapers/start-all-round-robin', {
    method: 'POST',
    body: JSON.stringify({ headless }),
  });
}

export async function getNlpStatus(): Promise<NlpStatus> {
  return fetchApi<NlpStatus>('/nlp/status');
}

export async function getNlpModelVersions(): Promise<import('./types').NlpModelVersionsResponse> {
  return fetchApi<import('./types').NlpModelVersionsResponse>('/nlp/model_versions');
}

export async function nlpSearch(
  query: string,
  topK = 10,
  autoTrain = false,
): Promise<NlpSearchResponse> {
  const params = new URLSearchParams({
    query,
    top_k: topK.toString(),
    auto_train: autoTrain.toString(),
  });
  return fetchApi<NlpSearchResponse>(`/nlp/search?${params.toString()}`);
}

export async function getNlpBarChartInput(): Promise<NlpBarChartData> {
  return fetchApi<NlpBarChartData>('/nlp/get_bar_chart_input');
}

export async function getNlpPieChartInput(): Promise<NlpPieChartData> {
  return fetchApi<NlpPieChartData>('/nlp/get_pie_chart_input');
}

export async function getNlpScatterChartInput(): Promise<NlpScatterPoint[]> {
  return fetchApi<NlpScatterPoint[]>('/nlp/get_scatter_chart_input');
}
