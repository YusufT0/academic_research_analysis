import { useState, useEffect, useRef } from 'react';
import { ExternalLink, BookOpen, FileText, ChevronDown, ChevronUp, Unlock, Star, Presentation, Activity } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import type { Journal, Issue, Article, PaginatedResponse } from '@/lib/types';
import { getJournalIssues, getArticles } from '@/lib/api';
import Link from 'next/link';

interface JournalCardProps {
  journal: Journal;
  getFullUrl: (url: string, source: string) => string;
  defaultExpandedIssueId?: string | null;
  highlightArticleId?: string | null;
}

export function JournalCard({ journal, getFullUrl, defaultExpandedIssueId, highlightArticleId }: JournalCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [aimsExpanded, setAimsExpanded] = useState(false);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [loadingIssues, setLoadingIssues] = useState(false);
  const [expandedIssueId, setExpandedIssueId] = useState<string | null>(null);
  const [articles, setArticles] = useState<Record<string, Article[]>>({});
  const [loadingArticles, setLoadingArticles] = useState<Record<string, boolean>>({});
  const processedIssueId = useRef<string | null>(null);

  useEffect(() => {
    if (!defaultExpandedIssueId) return;
    const issueId = defaultExpandedIssueId as string;

    if (processedIssueId.current === issueId) return;

    processedIssueId.current = issueId;

    async function initAutoExpand() {
      setExpanded(true);
      setLoadingIssues(true);
      try {
        const data = await getJournalIssues(journal.id, 1, 100) as any;
        const loadedIssues = Array.isArray(data) ? data : data?.items || [];
        setIssues(loadedIssues);
      } catch (err) {
        console.error(err);
      } finally {
        setLoadingIssues(false);
      }

      setExpandedIssueId(issueId);
      setLoadingArticles(prev => ({ ...prev, [issueId]: true }));
      try {
        const articlesData = await getArticles({ issue_id: issueId, page: 1, page_size: 100 });
        setArticles(prev => ({ ...prev, [issueId]: articlesData.items || [] }));

        if (highlightArticleId) {
          setTimeout(() => {
            const el = document.getElementById(`article-${highlightArticleId}`);
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }, 800);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoadingArticles(prev => ({ ...prev, [issueId]: false }));
      }
    }

    initAutoExpand();
  }, [defaultExpandedIssueId, highlightArticleId, journal.id]);

  const handleExpand = async () => {
    if (!expanded && issues.length === 0) {
      setLoadingIssues(true);
      try {
        const data = await getJournalIssues(journal.id, 1, 100) as any;
        // Assuming data is { items: Issue[], ... }
        setIssues(Array.isArray(data) ? data : data?.items || []);
      } catch (err) {
        console.error("Failed to load issues:", err);
      } finally {
        setLoadingIssues(false);
      }
    }
    setExpanded(!expanded);
  };

  const handleExpandIssue = async (issueId: string) => {
    if (expandedIssueId === issueId) {
      setExpandedIssueId(null);
      return;
    }
    
    setExpandedIssueId(issueId);
    if (!articles[issueId]) {
      setLoadingArticles(prev => ({ ...prev, [issueId]: true }));
      try {
        const data = await getArticles({ issue_id: issueId, page: 1, page_size: 100 });
        setArticles(prev => ({ ...prev, [issueId]: data.items || [] }));
      } catch (err) {
        console.error("Failed to load articles:", err);
      } finally {
        setLoadingArticles(prev => ({ ...prev, [issueId]: false }));
      }
    }
  };

  return (
    <Card className={`hover:shadow-md transition-shadow ${expanded ? 'col-span-full' : ''}`}>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-slate-900 line-clamp-2">{journal.name}</h3>
            <div className="flex items-center gap-2 mt-2">
              <Badge variant={journal.source_website === 'ieeexplore' ? 'info' : journal.source_website === 'acm' ? 'warning' : 'success'}>
                {journal.source_website === 'ieeexplore' ? 'IEEE' : journal.source_website === 'acm' ? 'ACM' : 'ScienceDirect'}
              </Badge>
              {journal.open_access && (
                <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200" title="Açık Erişim Dergi">
                  <Unlock className="h-3.5 w-3.5" />
                  <span>Açık Erişim</span>
                </div>
              )}
            </div>
          </div>
          {journal.url && (
            <a
              href={getFullUrl(journal.url, journal.source_website)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-400 hover:text-emerald-600"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
          )}
        </div>
        
        <div className="flex flex-col gap-3 mt-4 pt-4 border-t border-slate-100">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5 text-sm">
                <BookOpen className="h-4 w-4 text-slate-400" />
                <span className="font-medium">{journal.issue_count}</span>
                <span className="text-slate-500">sayı</span>
              </div>
              <div className="flex items-center gap-1.5 text-sm">
                <FileText className="h-4 w-4 text-slate-400" />
                <span className="font-medium">{journal.article_count}</span>
                <span className="text-slate-500">makale</span>
              </div>
            </div>
            
            <Button variant="secondary" size="sm" onClick={handleExpand} className="text-xs h-8">
              {expanded ? (
                <><ChevronUp className="h-4 w-4 mr-1" /> Sayıları Gizle</>
              ) : (
                <><ChevronDown className="h-4 w-4 mr-1" /> Sayıları Göster</>
              )}
            </Button>
          </div>

          {(journal.h_index != null || (journal.total_citation_count != null && journal.total_citation_count > 0) || journal.i10_index != null) && (
            <div className="flex items-center gap-3 text-xs font-medium bg-gradient-to-r from-indigo-50 to-purple-50 text-indigo-900 px-3 py-1.5 rounded-md border border-indigo-100 shadow-sm w-fit flex-wrap">
              {journal.total_citation_count != null && journal.total_citation_count > 0 && (
                <div className="flex items-center gap-1.5 font-bold" title="Dergiye ait toplam atıf sayısı">
                   <Star className="h-3.5 w-3.5 text-yellow-500 fill-yellow-500" />
                   <span>{journal.total_citation_count.toLocaleString()} Atıf</span>
                </div>
              )}
              
              {journal.h_index != null && (
                <div className={`flex items-center gap-1.5 ${journal.total_citation_count ? 'border-l border-indigo-200 pl-3' : ''}`} title="Dergi H-Index Değeri">
                  <Presentation className="h-3.5 w-3.5 text-indigo-500" />
                  <span>H-Index: {journal.h_index}</span>
                </div>
              )}

              {journal.i10_index != null && (
                <div className={`flex items-center gap-1.5 ${(journal.h_index != null || journal.total_citation_count) ? 'border-l border-indigo-200 pl-3' : ''}`} title="i10-Index: En az 10 atıf almış makale sayısı">
                  <Activity className="h-3.5 w-3.5 text-indigo-500" />
                  <span>i10: {journal.i10_index}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Aims & Scope */}
        {journal.aims_and_scope && (
          <div className="mt-3 pt-3 border-t border-slate-100">
            <button
              onClick={() => setAimsExpanded(!aimsExpanded)}
              className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-700 transition-colors"
            >
              {aimsExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
              Amaç &amp; Kapsam
            </button>
            {aimsExpanded && (
              <div
                className="mt-2 text-xs text-slate-600 leading-relaxed max-h-64 overflow-y-auto pr-1
                  [&_p]:my-1 [&_ul]:my-1 [&_ul]:list-disc [&_ul]:pl-4 [&_li]:my-0
                  [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold
                  [&_a]:text-blue-600 [&_a]:underline"
                dangerouslySetInnerHTML={{ __html: journal.aims_and_scope }}
              />
            )}
          </div>
        )}

        {/* Issues Accordion */}
        {expanded && (
          <div className="mt-6 pt-4 border-t border-slate-200">
            <h4 className="font-medium text-slate-800 mb-3 flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-purple-600" />
              Dergi Sayıları
            </h4>
            
            {loadingIssues ? (
              <div className="animate-pulse flex flex-col gap-2">
                <div className="h-8 bg-slate-100 rounded"></div>
                <div className="h-8 bg-slate-100 rounded"></div>
                <div className="h-8 bg-slate-100 rounded"></div>
              </div>
            ) : issues.length === 0 ? (
              <p className="text-sm text-slate-500 italic">Bu dergiye ait sayı bulunamadı.</p>
            ) : (
              <div className="space-y-2">
                {issues.map(issue => {
                  const issueName = issue.volume ? `Cilt ${issue.volume}${issue.issue_number ? `, Sayı ${issue.issue_number}` : ''}` : `Sayı ${issue.issue_number || issue.year || 'Bilinmiyor'}`;
                  const isIssueExpanded = expandedIssueId === issue.id;
                  
                  return (
                    <div key={issue.id} className="border border-slate-200 rounded-lg overflow-hidden bg-slate-50">
                      <button 
                        onClick={() => handleExpandIssue(issue.id)}
                        className="w-full flex items-center justify-between p-3 bg-white hover:bg-slate-50 transition-colors text-left"
                      >
                        <div className="flex flex-col md:flex-row md:items-center gap-1 md:gap-4 flex-1">
                          <span className="font-semibold text-slate-700 text-sm">{issueName}</span>
                          {(issue.year || issue.month) && (
                            <span className="text-xs text-slate-500">
                              {issue.month ? `${issue.month}/` : ''}{issue.year}
                            </span>
                          )}
                          {issue.article_count > 0 && (
                            <Badge variant="default" className="w-fit text-xs bg-slate-100 text-slate-600 border-none">
                              {issue.article_count} Makale
                           </Badge>
                          )}
                        </div>
                        {isIssueExpanded ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
                      </button>
                      
                      {isIssueExpanded && (
                        <div className="p-3 bg-slate-50 border-t border-slate-200">
                          {loadingArticles[issue.id] ? (
                            <p className="text-sm text-slate-400">Makaleler yükleniyor...</p>
                          ) : articles[issue.id]?.length > 0 ? (
                            <ul className="space-y-2">
                              {articles[issue.id].map(article => (
                                <li 
                                  key={article.id} 
                                  id={`article-${article.id}`} 
                                  className={`bg-white p-3 rounded border ${article.id === highlightArticleId ? 'border-indigo-400 shadow-md ring-1 ring-indigo-400' : 'border-slate-100 shadow-sm hover:border-purple-200'} flex items-start gap-3 transition-colors`}
                                >
                                  <FileText className="h-4 w-4 text-purple-400 mt-1 flex-shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <Link 
                                      href={`/articles?article_id=${article.id}`}
                                      className="text-sm font-semibold text-slate-800 hover:text-purple-600 line-clamp-2"
                                    >
                                      {article.title}
                                    </Link>
                                    <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                                      {article.authors?.length > 0 && (
                                        <p className="text-xs text-slate-500 truncate max-w-[200px]" title={article.authors.join(', ')}>
                                          {article.authors[0]}{article.authors.length > 1 ? ' et al.' : ''}
                                        </p>
                                      )}
                                      {article.citation_count > 0 && (
                                        <span className="text-[10px] font-medium text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded flex items-center gap-1">
                                          <Star className="h-3 w-3" /> {article.citation_count}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-sm text-slate-500 italic">Bu sayıda makale bulunamadı.</p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}