
'use client'

import { TrendingRepo } from '@/types'
import { Star, GitFork, Trophy, ArrowUpRight } from 'lucide-react'
import BookmarkButton from './BookmarkButton'

export default function TrendingCard({ repo, index }: { repo: TrendingRepo; index: number }) {
  const scoreLabel = repo.overall_score ?? '—'

  return (
    <div 
      className="glass-card rounded-2xl p-6 hover:translate-y-[-4px] transition-all duration-300 group relative overflow-hidden animate-enter"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Background Gradient Blob */}
      <div className="absolute -right-10 -top-10 w-40 h-40 bg-purple-500/10 blur-[50px] rounded-full group-hover:bg-purple-500/20 transition-all duration-500" />

      {/* Top Actions */}
      <div className="absolute top-4 right-4 flex items-center gap-2 z-20">
        <BookmarkButton repoId={repo.id} />
        <div className="flex items-center gap-1 text-xs font-mono text-zinc-500 border border-white/5 rounded px-2 py-1 bg-black/20 backdrop-blur-sm">
          <span>#</span>
          {repo.rank}
        </div>
      </div>

      <div className="mb-4 relative z-10">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-medium text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-full">
            {repo.language || 'Unknown'}
          </span>
          <span className="text-xs font-medium text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full flex items-center gap-1">
            <Trophy className="w-3 h-3" />
            {scoreLabel} AI Score
          </span>
        </div>
        <h3 className="text-xl font-bold text-white group-hover:text-purple-300 transition-colors flex items-center gap-2">
          {repo.full_name}
          <a href={`https://github.com/${repo.full_name}`} target="_blank" rel="noopener noreferrer" className="opacity-0 group-hover:opacity-100 transition-opacity">
            <ArrowUpRight className="w-4 h-4" />
          </a>
        </h3>
      </div>

      <p className="text-zinc-400 text-sm line-clamp-2 mb-6 h-10 relative z-10">
        {repo.description || 'No description provided.'}
      </p>

      {/* AI Summary if available */}
      {repo.summary && (
        <div className="mb-4 bg-white/5 p-3 rounded-lg border border-white/5">
          <p className="text-xs text-zinc-300 italic">&ldquo;{repo.summary}&rdquo;</p>
        </div>
      )}

      <div className="flex items-center justify-between text-zinc-400 text-sm relative z-10 border-t border-white/5 pt-4">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1">
            <Star className="w-4 h-4 text-amber-400 fill-amber-400/20" />
            <span>{repo.stars.toLocaleString()}</span>
          </div>
          <div className="flex items-center gap-1">
            <GitFork className="w-4 h-4" />
            <span>{repo.forks.toLocaleString()}</span>
          </div>
        </div>
        <div className="text-emerald-400 text-xs font-bold flex items-center gap-1">
           +{repo.stars_today} today
        </div>
      </div>
    </div>
  )
}
