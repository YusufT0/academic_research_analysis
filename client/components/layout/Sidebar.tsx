'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  FileText,
  BookOpen,
  TrendingUp,
  Database,
  Search,
  Network,
  Users,
  HelpCircle,
} from 'lucide-react';
import SidebarStars from './SidebarStars';

const navigation = [
  { name: 'Genel Bakış', href: '/', icon: LayoutDashboard },
  { name: 'Makaleler', href: '/articles', icon: FileText },
  { name: 'Dergiler', href: '/journals', icon: BookOpen },
  { name: 'Yazarlar', href: '/authors', icon: Users },
  { name: 'Makale Arama', href: '/search', icon: Search },
  { name: 'Atıf Haritası', href: '/citation-map', icon: Network },
  { name: 'Scraper Kontrol', href: '/scrapers', icon: Database },
];

/*
 * Layout math (minimize):
 *   wrapper:  left/top/right/bottom = 2px (tolerance zone)
 *   aside:    inset-0.5 inside wrapper = 4px from screen edge
 *   aside W:  64px → screen X 4..68 (sidebar center @ 36)
 *   For each section, inner padding = (64 - icon_w) / 2 so the icon's
 *   screen X coordinate stays at 36 in BOTH minimize and hover states.
 *     - Logo (icon 28): px-[18px]  → icon center = 4 + 18 + 14 = 36
 *     - Nav (icon 20):  nav px-2, link px-3.5 → 4 + 8 + 14 + 10 = 36
 *     - Footer (icon 32): px-4 → 4 + 16 + 16 = 36
 */

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="fixed left-0.5 top-0.5 bottom-0.5 z-40 group w-[68px] hover:w-[calc(16rem+4px)] transition-[width] duration-150 ease-in-out">
      <aside className="absolute inset-0.5 bg-[#0c1220] text-white rounded-2xl shadow-xl overflow-hidden">
        <SidebarStars />

        {/* Logo */}
        <div className="relative z-10 flex h-16 items-center border-b border-slate-700 px-[18px]">
          <span className="shrink-0">
            <TrendingUp className="h-7 w-7 text-indigo-400" />
          </span>
          <div className="ml-3 overflow-hidden whitespace-nowrap max-w-0 opacity-0 group-hover:max-w-xs group-hover:opacity-100 transition-all duration-150 ease-in-out">
            <h1 className="text-sm font-bold leading-tight">Akademik Trend</h1>
            <p className="text-xs font-semibold text-slate-300">Analiz Sistemi</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="relative z-10 mt-4 px-2">
          <ul className="space-y-1">
            {navigation.map((item) => {
              const isActive = pathname === item.href;
              return (
                <li key={item.name}>
                  <Link
                    href={item.href}
                    className={`flex items-center rounded-xl px-3.5 py-2.5 text-sm font-medium transition-colors ${
                      isActive
                        ? 'bg-indigo-600 text-white'
                        : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                    }`}
                  >
                    <span className="shrink-0">
                      <item.icon className="h-5 w-5" />
                    </span>
                    <span className="ml-3 overflow-hidden whitespace-nowrap max-w-0 opacity-0 group-hover:max-w-xs group-hover:opacity-100 transition-all duration-150 ease-in-out">
                      {item.name}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Footer */}
        <div className="absolute bottom-0 left-0 right-0 z-10 border-t border-slate-700 px-4 py-3">
          <div className="flex items-center">
            <div className="h-8 w-8 shrink-0 rounded-full bg-indigo-600 flex items-center justify-center">
              <HelpCircle className="h-4 w-4" />
            </div>
            <div className="ml-3 overflow-hidden whitespace-nowrap max-w-0 opacity-0 group-hover:max-w-xs group-hover:opacity-100 transition-all duration-150 ease-in-out">
              <p className="text-sm font-medium">BM495 - BM496</p>
              <p className="text-xs text-slate-400">2025 - 2026</p>
            </div>
          </div>
        </div>

      </aside>
    </div>
  );
}
