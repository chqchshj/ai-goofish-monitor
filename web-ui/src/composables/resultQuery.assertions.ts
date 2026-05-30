import {
  DEFAULT_RESULT_FILTERS,
  buildResultQuery,
  getResultQueryValue,
  parseResultFiltersFromQuery,
  parseResultSortQuery,
  type ResultFilters,
} from './resultQuery.ts'

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message)
}

function assertJsonEqual(actual: unknown, expected: unknown, message: string): void {
  const actualJson = JSON.stringify(actual)
  const expectedJson = JSON.stringify(expected)
  if (actualJson !== expectedJson) {
    throw new Error(`${message}: expected ${expectedJson}, got ${actualJson}`)
  }
}

assert(getResultQueryValue(['current.jsonl', 'ignored.jsonl']) === 'current.jsonl', 'first array query value is used')
assert(getResultQueryValue(null) === undefined, 'empty query value is ignored')

assertJsonEqual(
  parseResultFiltersFromQuery({
    ai_recommended_only: 'true',
    keyword_recommended_only: '1',
    include_hidden: 'false',
    yhb_only: ['1'],
    free_shipping_only: 'true',
    personal_seller_only: '0',
    sort: 'price_asc',
    file: 'demo_full_data.jsonl',
  }),
  {
    ai_recommended_only: true,
    keyword_recommended_only: true,
    include_hidden: false,
    yhb_only: true,
    free_shipping_only: true,
    personal_seller_only: false,
    sort: 'price_asc',
  },
  'query values restore filters without treating file as a filter',
)

assert(parseResultSortQuery('publish_desc') === 'publish_desc', 'valid sort query is restored')
assert(parseResultSortQuery('bad_sort') === DEFAULT_RESULT_FILTERS.sort, 'invalid sort query falls back to default')

assertJsonEqual(
  buildResultQuery(DEFAULT_RESULT_FILTERS, 'demo_full_data.jsonl'),
  { file: 'demo_full_data.jsonl' },
  'default filter values are omitted while file is preserved',
)

const selectedFilters: ResultFilters = {
  ...DEFAULT_RESULT_FILTERS,
  include_hidden: true,
  yhb_only: true,
  personal_seller_only: true,
  sort: 'keyword_hit_desc',
}

assertJsonEqual(
  buildResultQuery(selectedFilters, 'demo_full_data.jsonl'),
  {
    file: 'demo_full_data.jsonl',
    include_hidden: 'true',
    yhb_only: 'true',
    personal_seller_only: 'true',
    sort: 'keyword_hit_desc',
  },
  'non-default booleans and sort are represented in query with file preserved',
)

assertJsonEqual(
  buildResultQuery(selectedFilters, null),
  {
    include_hidden: 'true',
    yhb_only: 'true',
    personal_seller_only: 'true',
    sort: 'keyword_hit_desc',
  },
  'query can be built before a file is selected',
)
