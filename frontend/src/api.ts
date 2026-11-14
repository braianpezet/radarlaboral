import type {
  CvAdaptacion,
  CvDocumento,
  CvEstado,
  CvImportado,
  FeedbackResumen,
  FeedbackVoto,
  Job,
  JobDetail,
  JobStatus,
  LimpiezaPreview,
  LimpiezaResultado,
  Profile,
  Run,
  RunLog,
  SesionAsistida,
  SesionesResumen,
  Source,
  Stats,
} from './types'

async function pedir<T>(url: string, init?: RequestInit): Promise<T> {
  const respuesta = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!respuesta.ok) {
    let detalle = `HTTP ${respuesta.status}`
    try {
      const cuerpo = await respuesta.json()
      detalle = cuerpo.detail ?? detalle
    } catch {
      /* sin cuerpo */
    }
    throw new Error(detalle)
  }
  return respuesta.json() as Promise<T>
}

export interface FiltrosJobs {
  q?: string
  source?: string
  status?: string
  view?: string
  profile?: string
  modality?: string
  seniority?: string
  language?: string
  minScore?: number
  sort?: 'score' | 'date'
  order?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

export function listarJobs(filtros: FiltrosJobs) {
  const qs = new URLSearchParams()
  if (filtros.q) qs.set('q', filtros.q)
  if (filtros.source) qs.set('source', filtros.source)
  if (filtros.status) qs.set('status', filtros.status)
  if (filtros.view) qs.set('view', filtros.view)
  if (filtros.profile) qs.set('profile', filtros.profile)
  if (filtros.modality) qs.set('modality', filtros.modality)
  if (filtros.seniority) qs.set('seniority', filtros.seniority)
  if (filtros.language) qs.set('language', filtros.language)
  if (filtros.minScore != null) qs.set('min_score', String(filtros.minScore))
  qs.set('sort', filtros.sort ?? 'score')
  qs.set('order', filtros.order ?? 'desc')
  qs.set('limit', String(filtros.limit ?? 1000))
  qs.set('offset', String(filtros.offset ?? 0))
  return pedir<{ total: number; items: Job[] }>(`/api/jobs?${qs.toString()}`)
}

export function obtenerJob(id: number) {
  return pedir<JobDetail>(`/api/jobs/${id}`)
}

export function actualizarJob(id: number, cambios: { status?: JobStatus; note?: string }) {
  return pedir<{ id: number; status: JobStatus; note: string | null }>(`/api/jobs/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(cambios),
  })
}

export function obtenerStats() {
  return pedir<Stats>('/api/stats')
}

export function obtenerFuentes() {
  return pedir<Source[]>('/api/sources')
}

export function obtenerPerfiles() {
  return pedir<Profile[]>('/api/profiles')
}

export function ultimaCorrida() {
  return pedir<Run | null>('/api/runs/latest')
}

export function actualizarAhora() {
  return pedir<{ run_id: number }>('/api/refresh', { method: 'POST' })
}

export function obtenerRun(id: number) {
  return pedir<Run>(`/api/runs/${id}`)
}

export function obtenerLogs(limit = 150) {
  return pedir<RunLog[]>(`/api/logs?limit=${limit}`)
}

export function obtenerSesiones() {
  return pedir<SesionesResumen>('/api/session')
}

export function abrirSesion(sourceId: string) {
  return pedir<SesionAsistida>(`/api/session/${sourceId}`, { method: 'POST' })
}

export function registrarFeedback(jobId: number, vote: 1 | -1, motivos: string[] = []) {
  return pedir<FeedbackVoto>('/api/feedback', {
    method: 'POST',
    body: JSON.stringify({ job_id: jobId, vote, motivos }),
  })
}

export function borrarFeedback(jobId: number) {
  return pedir<{ eliminados: number }>(`/api/feedback/${jobId}`, { method: 'DELETE' })
}

export function obtenerFeedbackResumen() {
  return pedir<FeedbackResumen>('/api/feedback/summary')
}

export function actualizarFuente(sourceId: string, enabled: boolean) {
  return pedir<Source>(`/api/sources/${sourceId}`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  })
}

export function obtenerLimpiezaPreview() {
  return pedir<LimpiezaPreview>('/api/cleanup/preview')
}

export function limpiarAvisos() {
  return pedir<LimpiezaResultado>('/api/cleanup', { method: 'POST' })
}

export function obtenerCv() {
  return pedir<CvEstado>('/api/cv')
}

export function guardarCv(contenido: string, profileId = '') {
  return pedir<CvDocumento>('/api/cv', {
    method: 'PUT',
    body: JSON.stringify({ contenido, profile_id: profileId }),
  })
}

async function detalleError(respuesta: Response): Promise<string> {
  let detalle = `HTTP ${respuesta.status}`
  try {
    const cuerpo = await respuesta.json()
    detalle = cuerpo.detail ?? detalle
  } catch {
    /* sin cuerpo */
  }
  return detalle
}

export async function importarCvWord(archivo: File) {
  const respuesta = await fetch(
    `/api/cv/plantilla?nombre=${encodeURIComponent(archivo.name)}`,
    {
      method: 'POST',
      headers: {
        'Content-Type':
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      },
      body: archivo,
    },
  )
  if (!respuesta.ok) throw new Error(await detalleError(respuesta))
  return respuesta.json() as Promise<CvImportado>
}

export async function descargarCvWord(adaptacionId: number, nombre = '') {
  const limpio = nombre.trim()
  const consulta = limpio ? `?nombre=${encodeURIComponent(limpio)}` : ''
  const respuesta = await fetch(`/api/cv/adaptaciones/${adaptacionId}/docx${consulta}`)
  if (!respuesta.ok) throw new Error(await detalleError(respuesta))
  const blob = await respuesta.blob()
  const disposicion = respuesta.headers.get('Content-Disposition') ?? ''
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposicion)
  const ascii = /filename="?([^";]+)"?/i.exec(disposicion)
  let nombreArchivo = `cv-adaptado-${adaptacionId}.docx`
  if (utf8) {
    try {
      nombreArchivo = decodeURIComponent(utf8[1])
    } catch {
      /* deja el nombre alternativo */
    }
  } else if (ascii) {
    nombreArchivo = ascii[1]
  }
  return { blob, nombre: nombreArchivo }
}

export function adaptarCv(jobId: number, profileId = '', instrucciones = '') {
  return pedir<CvAdaptacion>('/api/cv/adaptar', {
    method: 'POST',
    body: JSON.stringify({
      job_id: jobId,
      profile_id: profileId,
      instrucciones,
    }),
  })
}

export function obtenerAdaptacionesCv(jobId: number) {
  return pedir<CvAdaptacion[]>(`/api/jobs/${jobId}/cv`)
}

export function borrarAdaptacionCv(adaptacionId: number) {
  return pedir<{ eliminados: number }>(`/api/cv/adaptaciones/${adaptacionId}`, {
    method: 'DELETE',
  })
}

export type { JobStatus } from './types'
