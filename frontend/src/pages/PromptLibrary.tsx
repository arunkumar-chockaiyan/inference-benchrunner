import { useState, useEffect } from 'react'
import { api } from '../api'
import type { PromptRead, SuiteRead, PromptCreate, PromptUpdate, SuiteCreate } from '../api'

type ActiveTab = 'prompts' | 'suites'
type CategoryFilter = 'All' | 'short' | 'long' | 'code' | 'chat'
const CATEGORIES: CategoryFilter[] = ['All', 'short', 'long', 'code', 'chat']
const CATEGORY_OPTIONS = ['short', 'long', 'code', 'chat'] as const

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function SkeletonCard() {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-3 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-4 bg-gray-200 rounded w-1/3" />
        <div className="h-5 bg-gray-200 rounded-full w-14" />
      </div>
      <div className="h-3 bg-gray-200 rounded w-full" />
      <div className="h-3 bg-gray-200 rounded w-4/5" />
      <div className="h-3 bg-gray-100 rounded w-1/4 mt-2" />
    </div>
  )
}

interface PromptFormState {
  name: string
  category: typeof CATEGORY_OPTIONS[number]
  content: string
  variablesRaw: string
  variablesError: string | null
}

function emptyPromptForm(): PromptFormState {
  return { name: '', category: 'short', content: '', variablesRaw: '', variablesError: null }
}

function promptFormFromRead(p: PromptRead): PromptFormState {
  const raw = Object.keys(p.variables).length > 0 ? JSON.stringify(p.variables, null, 2) : ''
  return { name: p.name, category: p.category as typeof CATEGORY_OPTIONS[number], content: p.content, variablesRaw: raw, variablesError: null }
}

interface PromptModalProps {
  editing: PromptRead | null
  onClose: () => void
  onSaved: (p: PromptRead) => void
}

function PromptModal({ editing, onClose, onSaved }: PromptModalProps) {
  const [form, setForm] = useState<PromptFormState>(editing ? promptFormFromRead(editing) : emptyPromptForm())
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  function setField<K extends keyof PromptFormState>(key: K, value: PromptFormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function parseVariables(): Record<string, string> | null {
    const raw = form.variablesRaw.trim()
    if (!raw) return {}
    try {
      const parsed = JSON.parse(raw)
      if (typeof parsed !== 'object' || Array.isArray(parsed) || parsed === null) return null
      return parsed as Record<string, string>
    } catch {
      return null
    }
  }

  async function handleSave() {
    const variables = parseVariables()
    if (variables === null) {
      setField('variablesError', 'Invalid JSON — must be an object e.g. {"key": "default"}')
      return
    }
    setField('variablesError', null)
    setSaving(true)
    setSaveError(null)
    try {
      let result: PromptRead
      if (editing) {
        const body: PromptUpdate = { name: form.name, category: form.category, content: form.content, variables }
        result = await api.updatePrompt(editing.id, body)
      } else {
        const body: PromptCreate = { name: form.name, category: form.category, content: form.content, variables }
        result = await api.createPrompt(body)
      }
      onSaved(result)
    } catch (err) {
      setSaveError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">{editing ? 'Edit prompt' : 'New prompt'}</h2>

        {saveError && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
            {saveError}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setField('name', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="My prompt"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
            <select
              value={form.category}
              onChange={(e) => setField('category', e.target.value as typeof CATEGORY_OPTIONS[number])}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
            >
              {CATEGORY_OPTIONS.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Content</label>
            <textarea
              value={form.content}
              onChange={(e) => setField('content', e.target.value)}
              rows={6}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none font-mono"
              placeholder="Enter prompt content…"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Variables <span className="text-gray-400 font-normal">(optional JSON)</span>
            </label>
            <textarea
              value={form.variablesRaw}
              onChange={(e) => { setField('variablesRaw', e.target.value); setField('variablesError', null) }}
              rows={3}
              className={`w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none font-mono ${form.variablesError ? 'border-red-400' : 'border-gray-300'}`}
              placeholder='{"key": "default"}'
            />
            {form.variablesError && (
              <p className="mt-1 text-xs text-red-600">{form.variablesError}</p>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => void handleSave()}
            disabled={saving || !form.name.trim() || !form.content.trim()}
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

interface SuiteFormState {
  name: string
  description: string
  selectedIds: string[]
}

interface SuiteModalProps {
  prompts: PromptRead[]
  onClose: () => void
  onSaved: (s: SuiteRead) => void
}

function SuiteModal({ prompts, onClose, onSaved }: SuiteModalProps) {
  const [form, setForm] = useState<SuiteFormState>({ name: '', description: '', selectedIds: [] })
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  function togglePrompt(id: string) {
    setForm((prev) => {
      if (prev.selectedIds.includes(id)) {
        return { ...prev, selectedIds: prev.selectedIds.filter((x) => x !== id) }
      }
      return { ...prev, selectedIds: [...prev.selectedIds, id] }
    })
  }

  function moveUp(index: number) {
    if (index === 0) return
    setForm((prev) => {
      const ids = [...prev.selectedIds]
      ;[ids[index - 1], ids[index]] = [ids[index], ids[index - 1]]
      return { ...prev, selectedIds: ids }
    })
  }

  function moveDown(index: number) {
    setForm((prev) => {
      if (index >= prev.selectedIds.length - 1) return prev
      const ids = [...prev.selectedIds]
      ;[ids[index], ids[index + 1]] = [ids[index + 1], ids[index]]
      return { ...prev, selectedIds: ids }
    })
  }

  async function handleSave() {
    setSaving(true)
    setSaveError(null)
    try {
      const body: SuiteCreate = { name: form.name, description: form.description, prompt_ids: form.selectedIds }
      const result = await api.createSuite(body)
      onSaved(result)
    } catch (err) {
      setSaveError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const promptMap = Object.fromEntries(prompts.map((p) => [p.id, p]))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl mx-4 p-6 space-y-4 max-h-[90vh] flex flex-col">
        <h2 className="text-lg font-semibold text-gray-900">New suite</h2>

        {saveError && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
            {saveError}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="My suite"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="Optional description"
            />
          </div>
        </div>

        <div className="flex gap-4 flex-1 min-h-0 overflow-hidden">
          <div className="flex-1 flex flex-col min-h-0">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">All prompts</p>
            <div className="flex-1 overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-100">
              {prompts.length === 0 && (
                <p className="px-3 py-4 text-sm text-gray-400 text-center">No prompts available</p>
              )}
              {prompts.map((p) => (
                <label key={p.id} className="flex items-center gap-3 px-3 py-2.5 hover:bg-gray-50 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.selectedIds.includes(p.id)}
                    onChange={() => togglePrompt(p.id)}
                    className="w-4 h-4 text-indigo-600 border-gray-300 rounded cursor-pointer"
                  />
                  <span className="text-sm text-gray-800 truncate">{p.name}</span>
                  <span className="ml-auto text-xs text-gray-400 shrink-0">{p.category}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex-1 flex flex-col min-h-0">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
              Selected order{form.selectedIds.length > 0 && ` (${form.selectedIds.length})`}
            </p>
            <div className="flex-1 overflow-y-auto border border-gray-200 rounded-lg divide-y divide-gray-100">
              {form.selectedIds.length === 0 && (
                <p className="px-3 py-4 text-sm text-gray-400 text-center">No prompts selected</p>
              )}
              {form.selectedIds.map((id, idx) => {
                const p = promptMap[id]
                return (
                  <div key={id} className="flex items-center gap-2 px-3 py-2.5">
                    <span className="text-xs text-gray-400 w-4 shrink-0">{idx + 1}</span>
                    <span className="text-sm text-gray-800 truncate flex-1">{p?.name ?? id}</span>
                    <div className="flex flex-col shrink-0">
                      <button
                        onClick={() => moveUp(idx)}
                        disabled={idx === 0}
                        className="text-gray-400 hover:text-gray-700 disabled:opacity-30 leading-none text-xs px-0.5"
                        aria-label="Move up"
                      >
                        ▲
                      </button>
                      <button
                        onClick={() => moveDown(idx)}
                        disabled={idx === form.selectedIds.length - 1}
                        className="text-gray-400 hover:text-gray-700 disabled:opacity-30 leading-none text-xs px-0.5"
                        aria-label="Move down"
                      >
                        ▼
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => void handleSave()}
            disabled={saving || !form.name.trim() || form.selectedIds.length === 0}
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save suite'}
          </button>
        </div>
      </div>
    </div>
  )
}

const CATEGORY_COLORS: Record<string, string> = {
  short: 'bg-green-100 text-green-700',
  long: 'bg-blue-100 text-blue-700',
  code: 'bg-purple-100 text-purple-700',
  chat: 'bg-yellow-100 text-yellow-700',
}

function CategoryBadge({ category }: { category: string }) {
  const cls = CATEGORY_COLORS[category] ?? 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {category}
    </span>
  )
}

export default function PromptLibrary() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('prompts')

  const [prompts, setPrompts] = useState<PromptRead[]>([])
  const [promptsLoading, setPromptsLoading] = useState(true)
  const [promptsError, setPromptsError] = useState<string | null>(null)
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>('All')

  const [suites, setSuites] = useState<SuiteRead[]>([])
  const [suitesLoading, setSuitesLoading] = useState(true)
  const [suitesError, setSuitesError] = useState<string | null>(null)

  const [promptModal, setPromptModal] = useState<{ open: boolean; editing: PromptRead | null }>({ open: false, editing: null })
  const [suiteModalOpen, setSuiteModalOpen] = useState(false)
  const [deletingPromptId, setDeletingPromptId] = useState<string | null>(null)
  const [deletingSuiteId, setDeletingSuiteId] = useState<string | null>(null)

  function loadPrompts() {
    setPromptsLoading(true)
    setPromptsError(null)
    api
      .listPrompts()
      .then(({ items }) => {
        setPrompts(items)
        setPromptsLoading(false)
      })
      .catch((err: Error) => {
        setPromptsError(err.message)
        setPromptsLoading(false)
      })
  }

  function loadSuites() {
    setSuitesLoading(true)
    setSuitesError(null)
    api
      .listSuites()
      .then(({ items }) => {
        setSuites(items)
        setSuitesLoading(false)
      })
      .catch((err: Error) => {
        setSuitesError(err.message)
        setSuitesLoading(false)
      })
  }

  useEffect(() => {
    loadPrompts()
    loadSuites()
  }, [])

  async function handleDeletePrompt(id: string) {
    if (!window.confirm('Delete this prompt? This cannot be undone.')) return
    setDeletingPromptId(id)
    try {
      await api.deletePrompt(id)
      setPrompts((prev) => prev.filter((p) => p.id !== id))
    } catch (err) {
      alert((err as Error).message)
    } finally {
      setDeletingPromptId(null)
    }
  }

  async function handleDeleteSuite(id: string) {
    if (!window.confirm('Delete this suite? This cannot be undone.')) return
    setDeletingSuiteId(id)
    try {
      await api.deleteSuite(id)
      setSuites((prev) => prev.filter((s) => s.id !== id))
    } catch (err) {
      alert((err as Error).message)
    } finally {
      setDeletingSuiteId(null)
    }
  }

  function handlePromptSaved(p: PromptRead) {
    setPrompts((prev) => {
      const idx = prev.findIndex((x) => x.id === p.id)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = p
        return next
      }
      return [p, ...prev]
    })
    setPromptModal({ open: false, editing: null })
  }

  function handleSuiteSaved(s: SuiteRead) {
    setSuites((prev) => [s, ...prev])
    setSuiteModalOpen(false)
  }

  const filteredPrompts = categoryFilter === 'All' ? prompts : prompts.filter((p) => p.category === categoryFilter)

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Prompt Library</h1>
        {activeTab === 'prompts' ? (
          <button
            onClick={() => setPromptModal({ open: true, editing: null })}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 text-sm font-medium transition-colors"
          >
            New prompt
          </button>
        ) : (
          <button
            onClick={() => setSuiteModalOpen(true)}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 text-sm font-medium transition-colors"
          >
            New suite
          </button>
        )}
      </div>

      <div className="flex gap-1 mb-6 border-b border-gray-200">
        {(['prompts', 'suites'] as ActiveTab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors capitalize ${
              activeTab === tab
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === 'prompts' && (
        <div>
          <div className="flex items-center gap-2 mb-4 flex-wrap">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setCategoryFilter(cat)}
                className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                  categoryFilter === cat
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {promptsError && (
            <div className="mb-4 flex items-center justify-between bg-red-50 border border-red-200 rounded-lg px-4 py-3">
              <span className="text-sm text-red-700">{promptsError}</span>
              <button
                onClick={loadPrompts}
                className="text-sm font-medium text-red-700 hover:text-red-900 underline ml-4"
              >
                Retry
              </button>
            </div>
          )}

          {promptsLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          ) : filteredPrompts.length === 0 ? (
            <div className="text-center py-16 text-sm text-gray-500">
              {prompts.length === 0
                ? 'No prompts yet. Create your first prompt to get started.'
                : 'No prompts match the selected category.'}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredPrompts.map((p) => (
                <div key={p.id} className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-2 hover:border-indigo-200 transition-colors">
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-medium text-gray-900 text-sm leading-snug">{p.name}</span>
                    <CategoryBadge category={p.category} />
                  </div>
                  <p className="text-sm text-gray-500 leading-relaxed line-clamp-3 flex-1">
                    {p.content.length > 120 ? p.content.slice(0, 120) + '…' : p.content}
                  </p>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-xs text-gray-400">{formatDate(p.created_at)}</span>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => setPromptModal({ open: true, editing: p })}
                        className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => void handleDeletePrompt(p.id)}
                        disabled={deletingPromptId === p.id}
                        className="text-xs text-red-500 hover:text-red-700 font-medium disabled:opacity-50"
                      >
                        {deletingPromptId === p.id ? 'Deleting…' : 'Delete'}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!promptsLoading && !promptsError && filteredPrompts.length > 0 && (
            <p className="mt-3 text-xs text-gray-500">
              Showing {filteredPrompts.length} of {prompts.length} prompt{prompts.length !== 1 ? 's' : ''}
            </p>
          )}
        </div>
      )}

      {activeTab === 'suites' && (
        <div>
          {suitesError && (
            <div className="mb-4 flex items-center justify-between bg-red-50 border border-red-200 rounded-lg px-4 py-3">
              <span className="text-sm text-red-700">{suitesError}</span>
              <button
                onClick={loadSuites}
                className="text-sm font-medium text-red-700 hover:text-red-900 underline ml-4"
              >
                Retry
              </button>
            </div>
          )}

          {suitesLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="bg-white rounded-lg border border-gray-200 p-4 animate-pulse">
                  <div className="flex items-center justify-between mb-2">
                    <div className="h-4 bg-gray-200 rounded w-1/4" />
                    <div className="h-5 bg-gray-200 rounded-full w-16" />
                  </div>
                  <div className="h-3 bg-gray-200 rounded w-2/3" />
                </div>
              ))}
            </div>
          ) : suites.length === 0 ? (
            <div className="text-center py-16 text-sm text-gray-500">
              No suites yet. Create a suite to group prompts for a benchmark run.
            </div>
          ) : (
            <div className="space-y-3">
              {suites.map((s) => (
                <div key={s.id} className="bg-white rounded-lg border border-gray-200 p-4 flex items-center gap-4 hover:border-indigo-200 transition-colors">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-gray-900 text-sm">{s.name}</span>
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                        v{s.version}
                      </span>
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-600">
                        {s.prompt_ids.length} prompt{s.prompt_ids.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                    {s.description && (
                      <p className="text-sm text-gray-500 truncate">{s.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-xs text-gray-400">{formatDate(s.created_at)}</span>
                    <button
                      onClick={() => void handleDeleteSuite(s.id)}
                      disabled={deletingSuiteId === s.id}
                      className="text-xs text-red-500 hover:text-red-700 font-medium disabled:opacity-50"
                    >
                      {deletingSuiteId === s.id ? 'Deleting…' : 'Delete'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!suitesLoading && !suitesError && suites.length > 0 && (
            <p className="mt-3 text-xs text-gray-500">
              {suites.length} suite{suites.length !== 1 ? 's' : ''}
            </p>
          )}
        </div>
      )}

      {promptModal.open && (
        <PromptModal
          editing={promptModal.editing}
          onClose={() => setPromptModal({ open: false, editing: null })}
          onSaved={handlePromptSaved}
        />
      )}

      {suiteModalOpen && (
        <SuiteModal
          prompts={prompts}
          onClose={() => setSuiteModalOpen(false)}
          onSaved={handleSuiteSaved}
        />
      )}
    </div>
  )
}
