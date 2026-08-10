import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../views/DashboardView.vue'),
    },
    {
      path: '/projects/new',
      name: 'project-setup',
      component: () => import('../views/ProjectSetupView.vue'),
    },
    {
      path: '/projects/:id/backlog',
      name: 'backlog',
      component: () => import('../views/BacklogView.vue'),
    },
    {
      path: '/projects/:id/requirements/:storyId',
      name: 'requirement-analysis',
      component: () => import('../views/RequirementAnalysisView.vue'),
    },
    {
      path: '/projects/:id/implementation/:storyId',
      name: 'implementation-plan',
      component: () => import('../views/ImplementationPlanView.vue'),
    },
    {
      path: '/projects/:id/execute',
      name: 'execution',
      component: () => import('../views/ExecutionView.vue'),
    },
    {
      path: '/projects/:id/quality/:storyId',
      name: 'quality',
      component: () => import('../views/QualityView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
    },
  ],
})

export default router
