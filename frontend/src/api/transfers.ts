import request from './request'

export function getTransfers(params?: any) { return request.get('/transfers', { params }) }
export function createTransfer(data: any) { return request.post('/transfers', data) }
export function getTransfer(id: number) { return request.get(`/transfers/${id}`) }
export function updateTransfer(id: number, data: any) { return request.put(`/transfers/${id}`, data) }
export function cancelTransfer(id: number) { return request.delete(`/transfers/${id}`) }
