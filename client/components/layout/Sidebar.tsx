'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  FileText,
  BookOpen,
  TrendingUp,
  Settings,
  Database,
  Search,
  BarChart2,
  Network,
  Users,
} from 'lucide-react';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Makaleler', href: '/articles', icon: FileText },
  { name: 'Dergiler', href: '/journals', icon: BookOpen },
  { name: 'Yazarlar', href: '/authors', icon: Users },
  { name: 'Arama', href: '/search', icon: Search },
  { name: 'Trendler', href: '/trends', icon: TrendingUp },
  { name: 'Atıf Haritası', href: '/citation-map', icon: Network },
  { name: 'Scraper', href: '/scrapers', icon: Database },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-64 bg-slate-900 text-white">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 border-b border-slate-700 px-6">
        <TrendingUp className="h-8 w-8 text-emerald-500" />
        <div>
          <h1 className="text-lg font-bold">Trend Analiz</h1>
          <p className="text-xs text-slate-400">Akademik Araştırma</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="mt-6 px-3">
        <ul className="space-y-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href;
            return (
              <li key={item.name}>
                <Link
                  href={item.href}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-emerald-600 text-white'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                  }`}
                >
                  <item.icon className="h-5 w-5" />
                  {item.name}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Monitoring */}
      <div className="mt-6 px-3 border-t border-slate-700 pt-4">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500 px-3 mb-2">Monitoring</p>
        <a
          href="http://localhost:3001"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
        >
          <BarChart2 className="h-5 w-5" />
          Grafana
        </a>
      </div>

      {/* Footer */}
      <div className="absolute bottom-0 left-0 right-0 border-t border-slate-700 p-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-full bg-emerald-600 flex items-center justify-center">
            <Settings className="h-4 w-4" />
          </div>
          <div>
            <p className="text-sm font-medium">BM495 Projesi</p>
            <p className="text-xs text-slate-400">2025-2026 Güz</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

