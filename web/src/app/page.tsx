
'use client'

import { useQuery } from '@tanstack/react-query'
import { supabase } from '@/lib/supabase'
import { TrendingRepo } from '@/types'
import TrendingCard from '@/components/TrendingCard'
import { Loader2, Flame } from 'lucide-react'

export default function Home() {
  const { data: trending, isLoading } = useQuery({
    queryKey: ['trending'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('gt_v_latest_trending')
        .select('*')
        .order('rank', { ascending: true })
      
      if (error) throw error
      return data as TrendingRepo[]
    }
  })

  return (
    <div className="space-y-12">
      {/* Hero Section */}
      <section className="relative py-10">
        <div className="absolute top-0 left-0 w-64 h-64 bg-purple-500/20 blur-[100px] -z-10 rounded-full" />
        
        <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-6">
          Discover what's <br />
          <span className="text-gradient">building the future.</span>
        </h1>
        <p className="text-xl text-zinc-400 max-w-2xl leading-relaxed">
          AI-curated trending repositories. We analyze thousands of projects daily to find the hidden gems before they go mainstream.
        </p>
      </section>

      {/* Stats / Filter Bar (Visual only for now) */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/5 pb-6">
        <div className="flex items-center gap-2 text-zinc-300">
          <Flame className="w-5 h-5 text-orange-500" />
          <span className="font-semibold">Trending Today</span>
        </div>
        <div className="text-sm text-zinc-500 font-mono">
          UPDATED: {new Date().toLocaleDateString()}
        </div>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {trending?.map((repo, idx) => (
            <TrendingCard key={repo.id} repo={repo} index={idx} />
          ))}
        </div>
      )}
    </div>
  )
}
