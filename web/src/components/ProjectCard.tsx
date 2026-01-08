
'use client'

import { Project } from '@/types'
import { Code2, Rocket } from 'lucide-react'

export default function ProjectCard({ project }: { project: Project }) {
  return (
    <div className="glass-card rounded-xl p-6 hover:bg-white/5 transition-all duration-300 group">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-xl font-bold text-white group-hover:text-purple-300 transition-colors">
            {project.name}
          </h3>
          <p className="text-sm text-zinc-500 font-mono mt-1">
            {new Date(project.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="bg-white/5 p-2 rounded-lg">
          <Rocket className="w-5 h-5 text-purple-400" />
        </div>
      </div>

      <p className="text-zinc-400 text-sm mb-6 line-clamp-2">
        {project.description}
      </p>

      <div className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {project.tech_stack.slice(0, 3).map((tech) => (
            <span key={tech} className="text-xs bg-purple-500/10 text-purple-300 px-2 py-1 rounded">
              {tech}
            </span>
          ))}
          {project.tech_stack.length > 3 && (
            <span className="text-xs bg-white/5 text-zinc-400 px-2 py-1 rounded">
              +{project.tech_stack.length - 3}
            </span>
          )}
        </div>
        
        {project.goals && (
          <div className="pt-3 border-t border-white/5 flex items-start gap-2">
            <Code2 className="w-4 h-4 text-zinc-500 mt-0.5" />
            <p className="text-xs text-zinc-400 line-clamp-1 italic">
              Goal: {project.goals}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
