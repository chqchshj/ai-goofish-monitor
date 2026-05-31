import { http } from '@/lib/http'

export interface SellerDetail {
  seller_key: string
  seller_nickname: string
  status: string
  notes: string
  tags: string[]
  item_count: number
  recommended_count: number
  min_price: number | null
  max_price: number | null
  latest_crawl_time: string
  personal_seller_summary: string | null
  tracking_created_at: string
  tracking_updated_at: string
}

export interface SellerTrackingUpdate {
  status?: string
  notes?: string
  tags?: string[]
}

export interface SellerTrackingResponse {
  seller_key: string
  status: string
  notes: string
  tags: string[]
  created_at: string
  updated_at: string
}

export interface SellerItemsResponse {
  items: Record<string, any>[]
  total: number
  page: number
  limit: number
}

export async function getSellerDetail(
  sellerKey: string,
  resultFilename: string,
): Promise<SellerDetail> {
  return await http(`/api/sellers/${encodeURIComponent(sellerKey)}`, {
    params: { result_filename: resultFilename },
  })
}

export async function updateSellerTracking(
  sellerKey: string,
  update: SellerTrackingUpdate,
): Promise<SellerTrackingResponse> {
  return await http(`/api/sellers/${encodeURIComponent(sellerKey)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  })
}

export async function deleteSellerTracking(sellerKey: string): Promise<{ message: string }> {
  return await http(`/api/sellers/${encodeURIComponent(sellerKey)}/tracking`, {
    method: 'DELETE',
  })
}

export async function getSellerItems(
  sellerKey: string,
  resultFilename: string,
  page = 1,
  limit = 20,
): Promise<SellerItemsResponse> {
  return await http(`/api/sellers/${encodeURIComponent(sellerKey)}/items`, {
    params: { result_filename: resultFilename, page, limit },
  })
}
