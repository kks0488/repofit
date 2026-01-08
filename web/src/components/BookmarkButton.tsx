
'use client'

import { useEffect, useState } from 'react'
import { Heart } from 'lucide-react'
import { supabase } from '@/lib/supabase'

export default function BookmarkButton({ repoId, initialBookmarked = false }: { repoId: string, initialBookmarked?: boolean }) {
  const [isBookmarked, setIsBookmarked] = useState(initialBookmarked)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let active = true

    const loadBookmark = async () => {
      const { data, error } = await supabase
        .from('gt_bookmarks')
        .select('id')
        .eq('repository_id', repoId)
        .is('project_id', null)
        .limit(1)

      if (!error && active) {
        setIsBookmarked(!!data?.length)
      }
    }

    if (repoId) {
      loadBookmark()
    }

    return () => {
      active = false
    }
  }, [repoId])
  
  const toggleBookmark = async (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (loading) return

    setLoading(true)
    const newState = !isBookmarked
    setIsBookmarked(newState) // Optimistic update

    try {
      if (newState) {
        const { error } = await supabase
          .from('gt_bookmarks')
          .insert({ repository_id: repoId })
        if (error && error.code !== '23505') throw error
      } else {
        const { error } = await supabase
          .from('gt_bookmarks')
          .delete()
          .eq('repository_id', repoId)
          .is('project_id', null)
        if (error) throw error
      }
    } catch (err) {
      console.error('Error toggling bookmark:', err)
      setIsBookmarked(!newState) // Revert on error
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={toggleBookmark}
      className={`p-2 rounded-full transition-all duration-300 ${
        isBookmarked 
          ? 'bg-rose-500/10 text-rose-500' 
          : 'bg-white/5 text-zinc-400 hover:bg-white/10 hover:text-white'
      }`}
    >
      <Heart 
        className={`w-5 h-5 ${isBookmarked ? 'fill-rose-500' : ''} ${loading ? 'animate-pulse' : ''}`} 
      />
    </button>
  )
}
