import request from './request'

export function getUsers() {
  return request.get('/users')
}

export function updateUser(id: number, data: any) {
  return request.put(`/users/${id}`, data)
}
