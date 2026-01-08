
'use client'

import { Recommendation } from '@/types'
import { CheckCircle2, Star, ArrowUpRight } from 'lucide-react'
import BookmarkButton from './BookmarkButton'

export default function RecommendationCard({ rec }: { rec: Recommendation }) {
  const scorePct = Number.isFinite(rec.score)
    ? Math.round(rec.score > 1 ? rec.score : rec.score * 100)
    : 0

  const reasons = (rec.reasons || [])
    .map((reason) => (typeof reason === 'string' ? reason : reason?.text))
    .filter(Boolean)

  return (
    <div className="glass-card rounded-2xl p-6 border-l-4 border-l-emerald-500 relative overflow-hidden group">
      <div className="absolute top-4 right-4 z-20">
        <BookmarkButton repoId={rec.repo_id} />
      </div>

      <div className="flex flex-col md:flex-row gap-6">
        
        {/* Left: Score & Repo Info */}
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
             <div className="bg-emerald-500/10 text-emerald-400 font-bold px-3 py-1 rounded-full text-sm flex items-center gap-1">
               {scorePct}% Match
             </div>
             <div className="text-sm text-zinc-500">
               for <span className="text-zinc-300 font-medium">{rec.project_name}</span>
             </div>
          </div>

          <h3 className="text-2xl font-bold text-white mb-2 flex items-center gap-2">
            {rec.full_name}
             <a href={`https://github.com/${rec.full_name}`} target="_blank" rel="noopener noreferrer" className="opacity-0 group-hover:opacity-100 transition-opacity">
                <ArrowUpRight className="w-5 h-5 text-zinc-400 hover:text-white" />
             </a>
          </h3>
          <p className="text-zinc-400 mb-4">{rec.description || 'No description provided.'}</p>

          <div className="flex items-center gap-4 text-sm text-zinc-500">
            <span className="flex items-center gap-1">
              <Star className="w-4 h-4 text-amber-400" /> {rec.stars.toLocaleString()}
            </span>
            <span className="bg-zinc-800 px-2 py-0.5 rounded text-zinc-300">
              {rec.language || 'Unknown'}
            </span>
          </div>
        </div>

        {/* Right: Reasons */}
        <div className="flex-1 bg-white/5 rounded-xl p-4 border border-white/5">
          <h4 className="text-sm font-semibold text-zinc-300 mb-3 uppercase tracking-wider">Why it's a match</h4>
          <ul className="space-y-2">
            {reasons.map((reason, idx) => (
              <li key={idx} className="flex items-start gap-2 text-sm text-zinc-400">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      
      {/* Background decoration */}
      <div className="absolute top-0 right-0 w-64 h-full bg-emerald-500/5 -skew-x-12 -z-10 pointer-events-none" />
    </div>
  )
}
