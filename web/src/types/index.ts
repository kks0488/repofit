
export interface TrendingRepo {
  id: string
  full_name: string
  description: string | null
  language: string | null
  stars: number
  stars_today: number
  forks: number
  overall_score: number | null
  topics: string[] | null
  rank: number
  summary: string | null
  use_cases: string[] | null
}

export interface Project {
  id: string
  name: string
  description: string
  tech_stack: string[]
  tags: string[]
  goals: string | null
  created_at: string
}

export interface Recommendation {
  recommendation_id: string
  repo_id: string
  project_name: string
  full_name: string // Repo name
  description: string | null
  language: string | null
  stars: number
  score: number
  reasons: Array<string | { text?: string }>
  overall_score: number | null
  summary: string | null
}
