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

export async function getScraperStats() {
  return fetchApi('/stats/scraper');
}

// ==================== Journals ====================

export interface JournalFilters {
  page?: number;
  page_size?: number;
  source_website?: string;
  publisher?: string;
  open_access?: boolean;
  search?: string;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
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
  
  return fetchApi<PaginatedResponse<Journal>>(`/journals?${params.toString()}`);
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

// ==================== Articles ====================

export interface ArticleFilters {
  page?: number;
  page_size?: number;
  journal_id?: string;
  issue_id?: string;
  source_website?: string;
  publication_year?: number;
  open_access?: boolean;
  article_type?: string;
  has_doi?: boolean;
  has_abstract?: boolean;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export async function getArticles(filters: ArticleFilters = {}): Promise<PaginatedResponse<Article>> {
  const params = new URLSearchParams();
  
  if (filters.page) params.set('page', filters.page.toString());
  if (filters.page_size) params.set('page_size', filters.page_size.toString());
  if (filters.journal_id) params.set('journal_id', filters.journal_id);
  if (filters.issue_id) params.set('issue_id', filters.issue_id);
  if (filters.source_website) params.set('source_website', filters.source_website);
  if (filters.publication_year) params.set('publication_year', filters.publication_year.toString());
  if (filters.open_access !== undefined) params.set('open_access', filters.open_access.toString());
  if (filters.article_type) params.set('article_type', filters.article_type);
  if (filters.has_doi !== undefined) params.set('has_doi', filters.has_doi.toString());
  if (filters.has_abstract !== undefined) params.set('has_abstract', filters.has_abstract.toString());
  if (filters.sort_by) params.set('sort_by', filters.sort_by);
  if (filters.sort_order) params.set('sort_order', filters.sort_order);
  
  return fetchApi<PaginatedResponse<Article>>(`/articles?${params.toString()}`);
}

export async function getArticle(id: string): Promise<Article> {
  return fetchApi<Article>(`/articles/${id}`);
}

export async function searchArticles(
  query: string,
  searchType: 'text' | 'title' | 'keyword' | 'author' = 'text',
  limit = 50
): Promise<SearchResult> {
  const params = new URLSearchParams({
    q: query,
    search_type: searchType,
    limit: limit.toString(),
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

export async function startIeeeScraper(headless = true, maxArticles = 10) {
  return fetchApi('/scrapers/ieee/start', {
    method: 'POST',
    body: JSON.stringify({ headless, max_articles: maxArticles }),
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

export async function startScienceDirectScraper(headless = true, maxArticles = 5) {
  return fetchApi('/scrapers/sciencedirect/start', {
    method: 'POST',
    body: JSON.stringify({ headless, max_articles: maxArticles }),
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

