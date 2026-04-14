import { ElMessage as ElementMessage } from 'element-plus'
import 'element-plus/es/components/message/style/css'

const baseOptions = {
  grouping: true,
  showClose: true,
  duration: 2600,
  offset: 24,
} as const

export const ElMessage = {
  success(message: string) {
    return ElementMessage({ ...baseOptions, type: 'success', message })
  },
  warning(message: string) {
    return ElementMessage({ ...baseOptions, type: 'warning', message })
  },
  error(message: string) {
    return ElementMessage({ ...baseOptions, type: 'error', message, duration: 3200 })
  },
  info(message: string) {
    return ElementMessage({ ...baseOptions, type: 'info', message })
  },
  closeAll() {
    ElementMessage.closeAll()
  },
}
