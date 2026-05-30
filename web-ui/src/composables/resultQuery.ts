import type { GetResultContentParams, ResultSort } from '@/api/results'

export type ResultFilters = Required<Pick<
  GetResultContentParams,
  | 'ai_recommended_only'
  | 'keyword_recommended_only'
  | 'include_hidden'
  | 'yhb_only'
  | 'free_shipping_only'
  | 'personal_seller_only'
  | 'processed_only'
  | 'contacted_only'
  | 'hide_processed'
  | 'sort'
>>

export type ResultQueryValue = unknown
export type ResultRouteQuery = Record<string, unknown>

export const DEFAULT_RESULT_FILTERS: ResultFilters = {
  ai_recommended_only: false,
  keyword_recommended_only: false,
  include_hidden: false,
  yhb_only: false,
  free_shipping_only: false,
  personal_seller_only: false,
  processed_only: false,
  contacted_only: false,
  hide_processed: false,
  sort: 'discovered_desc',
}

export const BOOLEAN_RESULT_QUERY_KEYS = [
  'ai_recommended_only',
  'keyword_recommended_only',
  'include_hidden',
  'yhb_only',
  'free_shipping_only',
  'personal_seller_only',
  'processed_only',
  'contacted_only',
  'hide_processed',
] as const

export const VALID_RESULT_SORTS: ResultSort[] = [
  'discovered_desc',
  'discovered_asc',
  'publish_desc',
  'publish_asc',
  'price_desc',
  'price_asc',
  'keyword_hit_desc',
  'keyword_hit_asc',
]

export function getResultQueryValue(value: ResultQueryValue): string | undefined {
  if (Array.isArray(value)) return typeof value[0] === 'string' ? value[0] : undefined
  return typeof value === 'string' ? value : undefined
}

export function parseResultBooleanQuery(value: ResultQueryValue): boolean {
  const queryValue = getResultQueryValue(value)
  return queryValue === 'true' || queryValue === '1'
}

export function parseResultSortQuery(value: ResultQueryValue): ResultSort {
  const queryValue = getResultQueryValue(value)
  return VALID_RESULT_SORTS.includes(queryValue as ResultSort)
    ? queryValue as ResultSort
    : DEFAULT_RESULT_FILTERS.sort
}

export function parseResultFiltersFromQuery(query: ResultRouteQuery): ResultFilters {
  return {
    ...DEFAULT_RESULT_FILTERS,
    ai_recommended_only: parseResultBooleanQuery(query.ai_recommended_only),
    keyword_recommended_only: parseResultBooleanQuery(query.keyword_recommended_only),
    include_hidden: parseResultBooleanQuery(query.include_hidden),
    yhb_only: parseResultBooleanQuery(query.yhb_only),
    free_shipping_only: parseResultBooleanQuery(query.free_shipping_only),
    personal_seller_only: parseResultBooleanQuery(query.personal_seller_only),
    processed_only: parseResultBooleanQuery(query.processed_only),
    contacted_only: parseResultBooleanQuery(query.contacted_only),
    hide_processed: parseResultBooleanQuery(query.hide_processed),
    sort: parseResultSortQuery(query.sort),
  }
}

export function buildResultQuery(filters: ResultFilters, selectedFile: string | null): Record<string, string> {
  const query: Record<string, string> = {}
  if (selectedFile) {
    query.file = selectedFile
  }
  BOOLEAN_RESULT_QUERY_KEYS.forEach((key) => {
    if (filters[key]) {
      query[key] = 'true'
    }
  })
  if (filters.sort !== DEFAULT_RESULT_FILTERS.sort) {
    query.sort = filters.sort
  }
  return query
}
