import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { ProjectRead, RunSummary } from '../api'
import { StatusBadge } from '../components/StatusBadge'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function SkeletonRow() {
  return (
    <tr className="border-b border-gray-100">
      {Array.from({ length: 4 }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div
            className="h-4 bg-gray-200 rounded animate-pulse"
            style={{ width: i === 3 ? '60px' : i === 2 ? '100px' : '70%' }}
          />
        </td>
      ))}
    </tr>
  )
}

export default function Projects() {
  const navigate = useNavigate()

  const [projects, setProjects] = useState<ProjectRead[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [projectRuns, setProjectRuns] = useState<Record<string, RunSummary[]>>({})
  const [runsLoading, setRunsLoading] = useState<Set<string>>(new Set())

  const [showModal, setShowModal] = useState(false)
  const [formName, setFormName] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formSubmitting, setFormSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const loadProjects = () => {
    setLoading(true)
    setError(null)
    api
      .listProjects()
      .then(({ items }) => {
        setProjects(items)
        setLoading(false)
      })
      .catch((err: Error) => {
        setError(err.message)
        setLoading(false)
      })
  }

  useEffect(() => {
    loadProjects()
  }, [])

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
        if (!(id in projectRuns) && !runsLoading.has(id)) {
          setRunsLoading((rl) => new Set(rl).add(id))
          void api
            .listProjectRuns(id)
            .then(({ items }) => {
              setProjectRuns((pr) => ({ ...pr, [id]: items }))
              setRunsLoading((rl) => {
                const s = new Set(rl)
                s.delete(id)
                return s
              })
            })
            .catch(() => {
              setProjectRuns((pr) => ({ ...pr, [id]: [] }))
              setRunsLoading((rl) => {
                const s = new Set(rl)
                s.delete(id)
                return s
              })
            })
        }
      }
      return next
    })
  }

  const openModal = () => {
    setFormName('')
    setFormDescription('')
    setFormError(null)
    setShowModal(true)
  }

  const closeModal = () => {
    setShowModal(false)
    setFormError(null)
  }

  const handleCreate = () => {
    if (!formName.trim()) {
      setFormError('Name is required.')
      return
    }
    setFormSubmitting(true)
    setFormError(null)
    void api
      .createProject({ name: formName.trim(), description: formDescription.trim() })
      .then((project) => {
        setProjects((prev) => [project, ...prev])
        setFormSubmitting(false)
        closeModal()
      })
      .catch((err: Error) => {
        setFormError(err.message)
        setFormSubmitting(false)
      })
  }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Projects</h1>
        <button
          onClick={openModal}
          className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 text-sm font-medium transition-colors"
        >
          New project
        </button>
      </div>

      {error && (
        <div className="mb-4 flex items-center justify-between bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <span className="text-sm text-red-700">{error}</span>
          <button
            onClick={loadProjects}
            className="text-sm font-medium text-red-700 hover:text-red-900 underline ml-4"
          >
            Retry
          </button>
        </div>
      )}

      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="w-10 px-4 py-3" />
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Name
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Description
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Created
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)
            ) : projects.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-sm text-gray-500">
                  No projects yet. Create your first project.
                </td>
              </tr>
            ) : (
              projects.map((project) => {
                const isExpanded = expandedIds.has(project.id)
                const runs = projectRuns[project.id]
                const isRunsLoading = runsLoading.has(project.id)

                return (
                  <>
                    <tr key={project.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => toggleExpand(project.id)}
                          className="text-gray-400 hover:text-gray-700 text-xs leading-none select-none"
                          aria-label={isExpanded ? 'Collapse' : 'Expand'}
                        >
                          {isExpanded ? '▼' : '▶'}
                        </button>
                      </td>
                      <td className="px-4 py-3 font-medium text-gray-900">{project.name}</td>
                      <td className="px-4 py-3 text-gray-600 max-w-sm truncate">
                        {project.description || <span className="text-gray-400 italic">—</span>}
                      </td>
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                        {formatDate(project.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          disabled
                          title="Coming soon"
                          className="text-xs text-gray-400 font-medium cursor-not-allowed"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr key={`${project.id}-runs`} className="bg-gray-50">
                        <td colSpan={5} className="px-6 py-3">
                          {isRunsLoading ? (
                            <div className="py-4 flex items-center gap-2 text-sm text-gray-500">
                              <div className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
                              Loading runs…
                            </div>
                          ) : !runs || runs.length === 0 ? (
                            <p className="py-3 text-sm text-gray-500 italic">
                              No runs in this project
                            </p>
                          ) : (
                            <div className="border border-gray-200 rounded-lg overflow-hidden">
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className="bg-white border-b border-gray-200">
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                      Engine
                                    </th>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                      Model
                                    </th>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                      Status
                                    </th>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                      Requests
                                    </th>
                                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                      Started
                                    </th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100 bg-white">
                                  {runs.map((run) => (
                                    <tr
                                      key={run.id}
                                      onClick={() => navigate(`/runs/${run.id}`)}
                                      className="hover:bg-indigo-50 cursor-pointer transition-colors"
                                    >
                                      <td className="px-4 py-2 font-medium text-gray-900">
                                        {run.engine}
                                      </td>
                                      <td
                                        className="px-4 py-2 text-gray-700 max-w-xs truncate"
                                        title={run.model}
                                      >
                                        {run.model}
                                      </td>
                                      <td className="px-4 py-2">
                                        <StatusBadge status={run.status} />
                                      </td>
                                      <td className="px-4 py-2 text-gray-600">
                                        {run.total_requests}
                                      </td>
                                      <td className="px-4 py-2 text-gray-600 whitespace-nowrap">
                                        {run.started_at ? formatDate(run.started_at) : '—'}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeModal()
          }}
        >
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">New project</h2>

            {formError && (
              <div className="mb-4 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
                {formError}
              </div>
            )}

            <div className="flex flex-col gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleCreate()
                    if (e.key === 'Escape') closeModal()
                  }}
                  placeholder="My benchmark project"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Description <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <textarea
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  placeholder="What are you benchmarking?"
                  rows={3}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={closeModal}
                disabled={formSubmitting}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={formSubmitting || !formName.trim()}
                className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {formSubmitting ? 'Creating…' : 'Create project'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
