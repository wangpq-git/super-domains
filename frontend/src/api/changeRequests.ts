import request from '@/api/request'

export interface ChangeRequest {
  id: number
  request_no: string
  source: string
  requester_user_id: number
  requester_name: string | null
  operation_type: string
  target_type: string
  target_id: number | null
  domain_id: number | null
  payload: Record<string, any>
  before_snapshot: Record<string, any>
  after_snapshot: Record<string, any>
  risk_level: string
  status: string
  approval_channel: string
  approver_user_id: number | null
  approver_name: string | null
  approved_at: string | null
  rejected_at: string | null
  rejection_reason: string | null
  executed_at: string | null
  execution_result: Record<string, any>
  error_message: string | null
  expires_at: string | null
  created_at: string
  updated_at: string
}

export interface ChangeRequestListResponse {
  items: ChangeRequest[]
  total: number
  page: number
  page_size: number
}

export interface ChangeRequestListParams {
  page?: number
  page_size?: number
  status?: string
  operation_type?: string
  keyword?: string
}

export function getChangeRequests(params: ChangeRequestListParams = {}) {
  return request.get<ChangeRequestListResponse>('/change-requests', { params })
}

export function approveChangeRequest(requestId: number) {
  return request.post<ChangeRequest>(`/change-requests/${requestId}/approve`)
}

export function rejectChangeRequest(requestId: number, reason: string) {
  return request.post<ChangeRequest>(`/change-requests/${requestId}/reject`, { reason })
}

export function cancelChangeRequest(requestId: number) {
  return request.post<ChangeRequest>(`/change-requests/${requestId}/cancel`)
}
