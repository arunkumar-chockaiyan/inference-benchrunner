import { lazy, Suspense } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'

const RunList = lazy(() => import('./pages/RunList'))
const NewRunWizard = lazy(() => import('./pages/NewRunWizard'))
const RunDetail = lazy(() => import('./pages/RunDetail'))
const Compare = lazy(() => import('./pages/Compare'))
const PromptLibrary = lazy(() => import('./pages/PromptLibrary'))
const Projects = lazy(() => import('./pages/Projects'))
const ModelRegistry = lazy(() => import('./pages/ModelRegistry'))

function NavBar() {
  return (
    <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
      <span className="text-lg font-semibold text-indigo-600 tracking-tight">
        Inference Bench Runner
      </span>
      <div className="flex items-center gap-6">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            `text-sm font-medium transition-colors ${isActive ? 'text-indigo-600' : 'text-gray-600 hover:text-gray-900'
            }`
          }
        >
          Runs
        </NavLink>
        <NavLink
          to="/compare"
          className={({ isActive }) =>
            `text-sm font-medium transition-colors ${isActive ? 'text-indigo-600' : 'text-gray-600 hover:text-gray-900'
            }`
          }
        >
          Compare
        </NavLink>
        <NavLink
          to="/prompts"
          className={({ isActive }) =>
            `text-sm font-medium transition-colors ${isActive ? 'text-indigo-600' : 'text-gray-600 hover:text-gray-900'
            }`
          }
        >
          Prompts
        </NavLink>
        <NavLink
          to="/projects"
          className={({ isActive }) =>
            `text-sm font-medium transition-colors ${isActive ? 'text-indigo-600' : 'text-gray-600 hover:text-gray-900'
            }`
          }
        >
          Projects
        </NavLink>
        <NavLink
          to="/models"
          className={({ isActive }) =>
            `text-sm font-medium transition-colors ${isActive ? 'text-indigo-600' : 'text-gray-600 hover:text-gray-900'
            }`
          }
        >
          Models
        </NavLink>
      </div>
    </nav>
  )
}

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <NavBar />
      <main className="flex-1 p-6">
        <Suspense fallback={<div className="text-gray-500 text-sm">Loading…</div>}>
          <Routes>
            <Route path="/" element={<RunList />} />
            <Route path="/runs/new" element={<NewRunWizard />} />
            <Route path="/runs/:id" element={<RunDetail />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/prompts" element={<PromptLibrary />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/models" element={<ModelRegistry />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  )
}
