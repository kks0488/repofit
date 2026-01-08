
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { supabase } from '@/lib/supabase'
import { Loader2, ArrowLeft, Save } from 'lucide-react'
import Link from 'next/link'

export default function NewProjectPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    tech_stack: '',
    tags: '',
    goals: '',
    readme_content: ''
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    // Parse comma-separated strings into arrays
    const techStackArray = formData.tech_stack.split(',').map(s => s.trim()).filter(Boolean)
    const tagsArray = formData.tags.split(',').map(s => s.trim()).filter(Boolean)

    try {
      const { error } = await supabase
        .from('gt_my_projects')
        .insert({
          name: formData.name,
          description: formData.description,
          tech_stack: techStackArray,
          tags: tagsArray,
          goals: formData.goals,
          readme_content: formData.readme_content
        })

      if (error) throw error

      router.push('/projects')
      router.refresh()
    } catch (error) {
      console.error('Error creating project:', error)
      alert('Failed to create project. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value
    }))
  }

  return (
    <div className="max-w-2xl mx-auto pb-20">
      <Link href="/projects" className="inline-flex items-center gap-2 text-zinc-500 hover:text-white mb-8 transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back to Projects
      </Link>

      <div className="mb-10">
        <h1 className="text-4xl font-bold mb-3">Register Project</h1>
        <p className="text-zinc-400">
          Tell us about what you&apos;re building. Our AI will analyze your stack and goals to recommend relevant trending repositories.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-8 glass-card p-8 rounded-2xl border border-white/5">
        
        {/* Basic Info */}
        <div className="space-y-6">
          <div>
            <label htmlFor="name" className="block text-sm font-medium text-zinc-300 mb-2">Project Name</label>
            <input
              type="text"
              id="name"
              name="name"
              required
              value={formData.name}
              onChange={handleChange}
              className="w-full bg-zinc-900/50 border border-zinc-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all placeholder:text-zinc-700"
              placeholder="e.g. NeoDashboard"
            />
          </div>

          <div>
            <label htmlFor="description" className="block text-sm font-medium text-zinc-300 mb-2">Short Description</label>
            <textarea
              id="description"
              name="description"
              required
              rows={3}
              value={formData.description}
              onChange={handleChange}
              className="w-full bg-zinc-900/50 border border-zinc-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all placeholder:text-zinc-700"
              placeholder="A brief overview of what this project does..."
            />
          </div>
        </div>

        {/* Tech & Context */}
        <div className="space-y-6 pt-6 border-t border-white/5">
          <h3 className="text-lg font-semibold text-white">Technical Context</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label htmlFor="tech_stack" className="block text-sm font-medium text-zinc-300 mb-2">Tech Stack (comma separated)</label>
              <input
                type="text"
                id="tech_stack"
                name="tech_stack"
                value={formData.tech_stack}
                onChange={handleChange}
                className="w-full bg-zinc-900/50 border border-zinc-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all placeholder:text-zinc-700"
                placeholder="React, Next.js, Supabase..."
              />
            </div>

            <div>
              <label htmlFor="tags" className="block text-sm font-medium text-zinc-300 mb-2">Tags / Topics</label>
              <input
                type="text"
                id="tags"
                name="tags"
                value={formData.tags}
                onChange={handleChange}
                className="w-full bg-zinc-900/50 border border-zinc-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all placeholder:text-zinc-700"
                placeholder="dashboard, analytics, ai..."
              />
            </div>
          </div>

          <div>
            <label htmlFor="goals" className="block text-sm font-medium text-zinc-300 mb-2">Primary Goals</label>
            <input
              type="text"
              id="goals"
              name="goals"
              value={formData.goals}
              onChange={handleChange}
              className="w-full bg-zinc-900/50 border border-zinc-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all placeholder:text-zinc-700"
              placeholder="What are you trying to achieve? e.g. &apos;Build a fast dashboard for financial data&apos;"
            />
          </div>

          <div>
            <label htmlFor="readme_content" className="block text-sm font-medium text-zinc-300 mb-2">README Content / Context (Optional)</label>
            <textarea
              id="readme_content"
              name="readme_content"
              rows={5}
              value={formData.readme_content}
              onChange={handleChange}
              className="w-full bg-zinc-900/50 border border-zinc-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all placeholder:text-zinc-700 text-sm font-mono"
              placeholder="Paste your README or detailed specs here for better AI analysis..."
            />
          </div>
        </div>

        <div className="pt-6">
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-white text-black font-bold text-lg py-4 rounded-xl hover:bg-zinc-200 transition-all active:scale-[0.99] flex items-center justify-center gap-2"
          >
            {loading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <>
                <Save className="w-5 h-5" />
                Save Project
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
