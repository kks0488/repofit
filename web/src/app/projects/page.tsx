
'use client'

import { useQuery } from '@tanstack/react-query'
import { supabase } from '@/lib/supabase'
import { Project } from '@/types'
import ProjectCard from '@/components/ProjectCard'
import { Loader2, Plus, FolderGit2 } from 'lucide-react'
import Link from 'next/link'

export default function ProjectsPage() {
  const { data: projects, isLoading } = useQuery({
    queryKey: ['my-projects'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('gt_my_projects')
        .select('*')
        .order('created_at', { ascending: false })
      
      if (error) throw error
      return data as Project[]
    }
  })

  return (
    <div className="space-y-8">
      <header className="flex items-center justify-between">
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <FolderGit2 className="w-6 h-6 text-purple-400" />
          My Projects
        </h1>
        <Link 
          href="/projects/new"
          className="bg-white text-black px-4 py-2 rounded-full text-sm font-semibold hover:bg-zinc-200 transition-colors flex items-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Create Project
        </Link>
      </header>

      {isLoading ? (
        <div className="flex justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-purple-500" />
        </div>
      ) : projects && projects.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      ) : (
        <div className="text-center py-24 bg-white/5 rounded-2xl border border-white/5 border-dashed flex flex-col items-center">
          <div className="w-16 h-16 bg-zinc-800 rounded-full flex items-center justify-center mb-4">
            <Plus className="w-8 h-8 text-zinc-500" />
          </div>
          <h3 className="text-xl font-semibold text-zinc-300 mb-2">No projects yet</h3>
          <p className="text-zinc-500 max-w-sm mb-8">
            Register your project to get personalized AI recommendations for tools and libraries.
          </p>
          <Link
            href="/projects/new"
            className="bg-purple-600 hover:bg-purple-700 text-white font-medium px-8 py-3 rounded-full transition-all hover:scale-105"
          >
            Start a New Project
          </Link>
        </div>
      )}
    </div>
  )
}
