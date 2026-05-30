import { ref, reactive, watch, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { ResultInsights, ResultItem } from '@/types/result.d.ts'
import * as resultsApi from '@/api/results'
import type { GetResultContentParams, ResultSort } from '@/api/results'
import { useWebSocket } from '@/composables/useWebSocket'
import * as tasksApi from '@/api/tasks'

type ResultFilters = Required<Pick<
  GetResultContentParams,
  | 'ai_recommended_only'
  | 'keyword_recommended_only'
  | 'include_hidden'
  | 'yhb_only'
  | 'free_shipping_only'
  | 'personal_seller_only'
  | 'sort'
>>

const DEFAULT_FILTERS: ResultFilters = {
  ai_recommended_only: false,
  keyword_recommended_only: false,
  include_hidden: false,
  yhb_only: false,
  free_shipping_only: false,
  personal_seller_only: false,
  sort: 'discovered_desc',
}

const BOOLEAN_QUERY_KEYS = [
  'ai_recommended_only',
  'keyword_recommended_only',
  'include_hidden',
  'yhb_only',
  'free_shipping_only',
  'personal_seller_only',
] as const

const VALID_SORTS: ResultSort[] = [
  'discovered_desc',
  'discovered_asc',
  'publish_desc',
  'publish_asc',
  'price_desc',
  'price_asc',
  'keyword_hit_desc',
  'keyword_hit_asc',
]

export function useResults() {
  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  // State
  const files = ref<string[]>([])
  const selectedFile = ref<string | null>(null)
  const results = ref<ResultItem[]>([])
  const insights = ref<ResultInsights | null>(null)
  const totalItems = ref(0)
  const page = ref(1)
  const limit = ref(100)
  const blacklistKeywords = ref<string[]>([])
  const taskNameByKeyword = ref<Record<string, string>>({})
  const isFileOptionsReady = ref(false)
  const hasFetchedFiles = ref(false)
  const hasFetchedTasks = ref(false)
  const isSavingBlacklist = ref(false)
  const readyDelayMs = 200
  let readyTimer: ReturnType<typeof setTimeout> | null = null
  let isApplyingRouteQuery = false

  function getQueryValue(value: unknown): string | undefined {
    if (Array.isArray(value)) return typeof value[0] === 'string' ? value[0] : undefined
    return typeof value === 'string' ? value : undefined
  }

  function parseBooleanQuery(value: unknown): boolean {
    const queryValue = getQueryValue(value)
    return queryValue === 'true' || queryValue === '1'
  }

  function parseSortQuery(value: unknown): ResultSort {
    const queryValue = getQueryValue(value)
    return VALID_SORTS.includes(queryValue as ResultSort)
      ? queryValue as ResultSort
      : DEFAULT_FILTERS.sort
  }

  function parseFiltersFromQuery(): ResultFilters {
    return {
      ...DEFAULT_FILTERS,
      ai_recommended_only: parseBooleanQuery(route.query.ai_recommended_only),
      keyword_recommended_only: parseBooleanQuery(route.query.keyword_recommended_only),
      include_hidden: parseBooleanQuery(route.query.include_hidden),
      yhb_only: parseBooleanQuery(route.query.yhb_only),
      free_shipping_only: parseBooleanQuery(route.query.free_shipping_only),
      personal_seller_only: parseBooleanQuery(route.query.personal_seller_only),
      sort: parseSortQuery(route.query.sort),
    }
  }

  function applyQueryFilters() {
    const nextFilters = parseFiltersFromQuery()
    BOOLEAN_QUERY_KEYS.forEach((key) => {
      filters[key] = nextFilters[key]
    })
    filters.sort = nextFilters.sort
  }

  const filters = reactive<ResultFilters>(parseFiltersFromQuery())

  const isLoading = ref(false)
  const error = ref<Error | null>(null)
  const { on } = useWebSocket()

  function normalizeKeyword(value: string) {
    return value.trim().toLowerCase().replace(/\s+/g, '_')
  }

  function getKeywordFromFilename(filename: string) {
    return filename.replace(/_full_data\.jsonl$/i, '').toLowerCase()
  }

  // Methods
  async function fetchFiles() {
    try {
      const fileList = await resultsApi.getResultFiles()
      files.value = fileList
      // If a file is selected that no longer exists, reset it.
      // Otherwise, if nothing is selected, select the first file by default.
      if (selectedFile.value && fileList.includes(selectedFile.value)) {
        return
      }

      const routeFile = getQueryValue(route.query.file)
      if (routeFile && fileList.includes(routeFile)) {
        selectedFile.value = routeFile
        return
      }

      if (!routeFile) {
        const lastSelected = localStorage.getItem('lastSelectedResultFile')
        if (lastSelected && fileList.includes(lastSelected)) {
          selectedFile.value = lastSelected
          return
        }
      }

      selectedFile.value = fileList[0] || null
    } catch (e) {
      if (e instanceof Error) error.value = e
    } finally {
      hasFetchedFiles.value = true
      scheduleFileOptionsReady()
    }
  }

  async function fetchResults() {
    if (!selectedFile.value) {
      results.value = []
      totalItems.value = 0
      return
    }

    isLoading.value = true
    error.value = null
    try {
      const data = await resultsApi.getResultContent(selectedFile.value, {
        ...filters,
        page: page.value,
        limit: limit.value,
      })
      results.value = data.items
      totalItems.value = data.total_items
    } catch (e) {
      if (e instanceof Error) error.value = e
      results.value = []
      totalItems.value = 0
    } finally {
      isLoading.value = false
    }
  }

  async function fetchInsights() {
    if (!selectedFile.value) {
      insights.value = null
      return
    }

    try {
      insights.value = await resultsApi.getResultInsights(selectedFile.value)
    } catch (e) {
      if (e instanceof Error) error.value = e
      insights.value = null
    }
  }

  async function fetchBlacklistRules() {
    if (!selectedFile.value) {
      blacklistKeywords.value = []
      return
    }

    try {
      const data = await resultsApi.getResultBlacklistRules(selectedFile.value)
      blacklistKeywords.value = data.keywords || []
    } catch (e) {
      if (e instanceof Error) error.value = e
      blacklistKeywords.value = []
    }
  }

  async function fetchTaskNameMap() {
    try {
      const tasks = await tasksApi.getAllTasks()
      const mapping: Record<string, string> = {}
      tasks.forEach((task) => {
        if (task.keyword) {
          mapping[normalizeKeyword(task.keyword)] = task.task_name
        }
      })
      taskNameByKeyword.value = mapping
    } catch (e) {
      if (e instanceof Error) error.value = e
    } finally {
      hasFetchedTasks.value = true
      scheduleFileOptionsReady()
    }
  }

  function scheduleFileOptionsReady() {
    if (isFileOptionsReady.value || !hasFetchedFiles.value || !hasFetchedTasks.value) return
    if (readyTimer) return
    readyTimer = setTimeout(() => {
      isFileOptionsReady.value = true
      readyTimer = null
    }, readyDelayMs)
  }

  // Real-time updates
  on('results_updated', async () => {
    const oldFile = selectedFile.value
    await fetchFiles()
    // If the selected file remains the same, refresh its content (in case of append)
    // If it changed (e.g. from null to new file), the watcher will handle it.
    if (selectedFile.value && selectedFile.value === oldFile) {
      fetchResults()
      fetchInsights()
    }
  })

  on('tasks_updated', () => {
    fetchTaskNameMap()
  })

  async function refreshResults() {
    const current = selectedFile.value
    await fetchFiles()
    if (selectedFile.value && selectedFile.value === current) {
      await fetchResults()
      await fetchInsights()
      await fetchBlacklistRules()
    }
  }

  function exportSelectedResults() {
    if (!selectedFile.value) return
    resultsApi.downloadResultExport(selectedFile.value, { ...filters })
  }

  async function deleteSelectedFile(filename?: string) {
    const target = filename || selectedFile.value
    if (!target) return
    isLoading.value = true
    error.value = null
    try {
      await resultsApi.deleteResultFile(target)
      if (selectedFile.value === target) {
        const lastSelected = localStorage.getItem('lastSelectedResultFile')
        if (lastSelected === target) {
          localStorage.removeItem('lastSelectedResultFile')
        }
      }
      await fetchFiles()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function toggleItemBlock(item: ResultItem) {
    if (!selectedFile.value) return
    const itemId = item.商品信息?.商品ID
    if (!itemId) return
    const newStatus = item._status === 'hidden' ? 'active' : 'hidden'
    try {
      await resultsApi.updateItemStatus(selectedFile.value, itemId, newStatus)
      await fetchResults()
    } catch (e) {
      if (e instanceof Error) error.value = e
    }
  }

  async function saveBlacklistRules(keywords: string[]) {
    if (!selectedFile.value) return
    isSavingBlacklist.value = true
    error.value = null
    try {
      const data = await resultsApi.updateResultBlacklistRules(selectedFile.value, keywords)
      blacklistKeywords.value = data.keywords || []
      await fetchResults()
      await fetchInsights()
    } catch (e) {
      if (e instanceof Error) error.value = e
      throw e
    } finally {
      isSavingBlacklist.value = false
    }
  }

  // Watchers
  watch([selectedFile, filters], fetchResults, { deep: true })
  watch(selectedFile, () => {
    fetchInsights()
    fetchBlacklistRules()
  })
  watch(selectedFile, (value) => {
    if (value) localStorage.setItem('lastSelectedResultFile', value)
  })

  watch([selectedFile, filters], () => {
    if (isApplyingRouteQuery) return
    const query: Record<string, string> = {}
    if (selectedFile.value) {
      query.file = selectedFile.value
    }
    BOOLEAN_QUERY_KEYS.forEach((key) => {
      if (filters[key]) {
        query[key] = 'true'
      }
    })
    if (filters.sort !== DEFAULT_FILTERS.sort) {
      query.sort = filters.sort
    }
    router.replace({ query })
  }, { deep: true })

  watch(
    () => route.query,
    () => {
      isApplyingRouteQuery = true
      try {
        applyQueryFilters()
        const routeFile = getQueryValue(route.query.file)
        if (routeFile && files.value.includes(routeFile)) {
          selectedFile.value = routeFile
        } else if (!routeFile && !selectedFile.value && files.value.length > 0) {
          const lastSelected = localStorage.getItem('lastSelectedResultFile')
          selectedFile.value =
            lastSelected && files.value.includes(lastSelected)
              ? lastSelected
              : files.value[0] || null
        }
      } finally {
        isApplyingRouteQuery = false
      }
    },
    { immediate: true }
  )

  watch(
    files,
    (currentFiles) => {
      const routeFile = getQueryValue(route.query.file)
      if (routeFile && currentFiles.includes(routeFile)) {
        selectedFile.value = routeFile
      }
    },
    { immediate: true }
  )

  const fileOptions = computed(() =>
    files.value.map((file) => {
      const keyword = getKeywordFromFilename(file)
      const taskName = taskNameByKeyword.value[keyword]
      return {
        value: file,
        taskName: taskName || t('common.unnamed'),
        label: t('results.filters.taskNameLabel', {
          task: taskName || t('common.unnamed'),
        }),
      }
    })
  )

  // Lifecycle
  onMounted(() => {
    fetchFiles()
    fetchTaskNameMap()
  })

  return {
    files,
    selectedFile,
    results,
    insights,
    totalItems,
    filters,
    isLoading,
    error,
    fetchFiles, // Expose to allow manual refresh
    refreshResults,
    exportSelectedResults,
    deleteSelectedFile,
    toggleItemBlock,
    blacklistKeywords,
    isSavingBlacklist,
    saveBlacklistRules,
    fileOptions,
    isFileOptionsReady,
  }
}
