
'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Plus, LayoutGrid, Sparkles, FolderGit2 } from 'lucide-react'

export default function Navbar() {
  const pathname = usePathname()

  const navItems = [
    { name: 'Trending', href: '/', icon: LayoutGrid },
    { name: 'For You', href: '/recommendations', icon: Sparkles },
    { name: 'My Projects', href: '/projects', icon: FolderGit2 },
  ]

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass-card border-b border-white/10">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link href="/" className="text-xl font-bold tracking-tight flex items-center gap-2">
          <span className="text-gradient">Trending.AI</span>
        </Link>

        <div className="hidden md:flex items-center gap-1">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = pathname === item.href
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all duration-300 ${
                  isActive
                    ? 'bg-white/10 text-white shadow-lg shadow-purple-500/10'
                    : 'text-zinc-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <Icon className="w-4 h-4" />
                {item.name}
              </Link>
            )
          })}
        </div>

        <Link
          href="/projects/new"
          className="flex items-center gap-2 bg-white text-black px-4 py-2 rounded-full text-sm font-semibold hover:bg-zinc-200 transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>Add Project</span>
        </Link>
      </div>
    </nav>
  )
}
