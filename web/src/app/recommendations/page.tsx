
'use client'

import { useQuery } from '@tanstack/react-query'
import { supabase } from '@/lib/supabase'
import { Recommendation } from '@/types'
import RecommendationCard from '@/components/RecommendationCard'
import { Loader2, Sparkles } from 'lucide-react'
import Link from 'next/link'

export default function RecommendationsPage() {
  const { data: recommendations, isLoading } = useQuery({
    queryKey: ['recommendations'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('gt_v_recommendations')
        .select('*')
        .order('score', { ascending: false })
      
      if (error) throw error
      return data as Recommendation[]
    }
  })

  return (
    <div className="space-y-8">
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-emerald-400" />
            AI Recommendations
          </h1>
          <p className="text-zinc-400 mt-1">
            Repositories matching your registered projects&apos; tech stacks and goals.
          </p>
        </div>
        
        <Link 
          href="/projects/new"
          className="text-sm bg-white/5 hover:bg-white/10 border border-white/10 px-4 py-2 rounded-full transition-colors"
        >
          Manage Projects
        </Link>
      </header>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
          <p className="text-zinc-500 animate-pulse">Analyzing your tech stack...</p>
        </div>
      ) : recommendations && recommendations.length > 0 ? (
        <div className="grid gap-6">
          {recommendations.map((rec) => (
            <RecommendationCard key={rec.recommendation_id} rec={rec} />
          ))}
        </div>
      ) : (
        <div className="text-center py-20 bg-white/5 rounded-2xl border border-white/5 border-dashed">
          <h3 className="text-xl font-semibold text-zinc-300 mb-2">No recommendations yet</h3>
          <p className="text-zinc-500 max-w-md mx-auto mb-6">
            Add a project, then run <span className="font-mono text-zinc-300">gt match</span> or{' '}
            <span className="font-mono text-zinc-300">gt quickstart</span> to generate matches.
          </p>
          <Link
            href="/projects/new"
            className="bg-emerald-500 hover:bg-emerald-600 text-white font-medium px-6 py-2 rounded-lg transition-colors"
          >
            Add Your First Project
          </Link>
        </div>
      )}
    </div>
  )
}
