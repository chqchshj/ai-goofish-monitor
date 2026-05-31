import type { ResultInsights, ResultItem, ResultItemStatus } from '@/types/result.d.ts'
import { http } from '@/lib/http'

export type ResultSort =
  | 'discovered_desc'
  | 'discovered_asc'
  | 'publish_desc'
  | 'publish_asc'
  | 'price_desc'
  | 'price_asc'
  | 'keyword_hit_desc'
  | 'keyword_hit_asc'


export interface BatchUpdateItemsPayload {
  item_ids: string[];
  status?: ResultItemStatus;
  is_processed?: boolean;
  is_contacted?: boolean;
}

export interface BatchUpdateItemsResponse {
  message: string;
  requested_count: number;
  updated_count: number;
  status: ResultItemStatus | null;
  is_processed: boolean | null;
  is_contacted: boolean | null;
}

export interface UpdateItemFlagsResponse {
  message: string;
  is_processed: boolean | null;
  is_contacted: boolean | null;
}

export interface GetResultContentParams {
  recommended_only?: boolean;
  ai_recommended_only?: boolean;
  keyword_recommended_only?: boolean;
  include_hidden?: boolean;
  yhb_only?: boolean;
  free_shipping_only?: boolean;
  seller?: string;
  personal_seller_only?: boolean;
  processed_only?: boolean;
  contacted_only?: boolean;
  hide_processed?: boolean;
  sort?: ResultSort;
  sort_by?: 'crawl_time' | 'publish_time' | 'price' | 'keyword_hit_count';
  sort_order?: 'asc' | 'desc';
  page?: number;
  limit?: number;
}

export interface SellerSummary {
  seller_nickname: string;
  item_count: number;
  min_price: number | null;
  max_price: number | null;
  latest_crawl_time: string;
  recommended_count: number;
  personal_seller_summary: string | null;
}

export interface GetSellerAggregationResponse {
  total_sellers: number;
  total_items: number;
  sellers: SellerSummary[];
}

export async function getResultFiles(): Promise<string[]> {
  const data = await http('/api/results/files')
  return data.files || []
}

export async function deleteResultFile(filename: string): Promise<{ message: string }> {
  return await http(`/api/results/files/${filename}`, { method: 'DELETE' })
}

export async function getResultContent(
  filename: string,
  params: GetResultContentParams = {}
): Promise<{ total_items: number; items: ResultItem[] }> {
  return await http(`/api/results/${filename}`, { params: params as Record<string, any> })
}

export async function getResultInsights(filename: string): Promise<ResultInsights> {
  return await http(`/api/results/${filename}/insights`)
}

export async function getResultBlacklistRules(filename: string): Promise<{ keywords: string[] }> {
  return await http(`/api/results/${filename}/blacklist-rules`)
}

export async function updateResultBlacklistRules(filename: string, keywords: string[]): Promise<{ message: string; keywords: string[] }> {
  return await http(`/api/results/${filename}/blacklist-rules`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keywords }),
  })
}

export function buildResultExportUrl(filename: string, params: GetResultContentParams = {}): string {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      searchParams.set(key, String(value))
    }
  })
  const queryString = searchParams.toString()
  return `/api/results/${encodeURIComponent(filename)}/export${queryString ? `?${queryString}` : ''}`
}

export function downloadResultExport(filename: string, params: GetResultContentParams = {}) {
  const url = buildResultExportUrl(filename, params)
  const link = document.createElement('a')
  link.href = url
  link.download = ''
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

export async function updateItemStatus(filename: string, itemId: string, status: ResultItemStatus): Promise<{ message: string; status: ResultItemStatus }> {
  return await http(`/api/results/${filename}/items/${itemId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}

export async function updateItemFlags(
  filename: string,
  itemId: string,
  flags: { is_processed?: boolean; is_contacted?: boolean }
): Promise<UpdateItemFlagsResponse> {
  return await http(`/api/results/${filename}/items/${itemId}/flags`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(flags),
  })
}


export async function updateItemsBatch(
  filename: string,
  payload: BatchUpdateItemsPayload
): Promise<BatchUpdateItemsResponse> {
  return await http(`/api/results/${filename}/items/batch`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function getSellerAggregation(
  filename: string,
  params: GetResultContentParams = {}
): Promise<GetSellerAggregationResponse> {
  return await http(`/api/results/${filename}/sellers`, { params: params as Record<string, any> })
}
