export interface Project {
  id: string
  name: string
  github_repo_url: string
  azure_devops_org_url: string
  azure_devops_project: string
  workspace_path: string
  pr_strategy: string
  is_repo_cloned: boolean
  claude_max_budget_usd: number
  created_at: string
  updated_at: string
}

export interface Task {
  id: string
  external_id: string
  title: string
  description: string
  order: number
  status: string
  retry_count: number
  error_message: string
  completed_at: string | null
}

export interface UserStory {
  id: string
  external_id: string
  title: string
  description: string
  acceptance_criteria: string
  order: number
  status: string
  tasks: Task[]
}

export interface Feature {
  id: string
  external_id: string
  title: string
  description: string
  order: number
  status: string
  user_stories: UserStory[]
}

export interface BacklogTree {
  project_id: string
  features: Feature[]
  total_tasks: number
  completed_tasks: number
  pending_tasks: number
}

export interface ExecutionStatus {
  id: string
  project_id: string
  status: string
  current_task_id: string | null
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  started_at: string
  completed_at: string | null
}

export interface WebSocketMessage {
  type: string
  payload: Record<string, unknown>
}
