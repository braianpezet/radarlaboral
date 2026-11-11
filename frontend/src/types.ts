export type JobStatus = 'nuevo' | 'visto' | 'guardado' | 'descartado' | 'postulado'

export interface ScoreDetail {
  profile_id: string
  profile_name: string
  priority: number
  score: number
  excluded: boolean
  skills: {
    score: number
    matched: string[]
    missing: string[]
  }
  role: {
    score: number
    matched: string | null
  }
  seniority: {
    value: string | null
    score: number
    adjustment: number
  }
  zone: {
    score: number
    label: string
  }
  language: {
    value: string | null
    score: number
  }
  recency: {
    score: number
    label: string
  }
  reasons: string[]
  todos?: Record<string, number>
}

export interface Job {
  id: number
  title: string
  company_name: string | null
  location: string | null
  modality: string | null
  seniority: string | null
  language: string | null
  salary_text: string | null
  published_at: string | null
  fetched_at: string
  source_id: string
  source_name: string
  url: string
  status: JobStatus
  note: string | null
  has_description: number
  fingerprint: string | null
  score: number | null
  profile_id: string | null
  profile_name: string | null
  score_detail: string | null
  excluded: number
  duplicate_of: number | null
  feedback_vote: number | null
  feedback_motivos: string[]
}

export interface JobDetail extends Job {
  description: string | null
  contract_type: string | null
  detail_error?: string
}

export interface Run {
  id: number
  started_at: string
  finished_at: string | null
  status: 'running' | 'ok' | 'error'
  found: number
  new: number
  updated: number
  errors: number
  message: string | null
}

export interface RunLog {
  id: number
  run_id: number
  source_id: string | null
  source_name: string | null
  level: 'info' | 'warn' | 'error'
  message: string
  created_at: string
}

export interface Profile {
  id: string
  name: string
  priority: number
  job_count: number
  visible_count: number
  hoy_count: number
}

export interface Stats {
  total: number
  nuevos: number
  guardados: number
  postulados: number
  descartados: number
  hoy: number
  duplicados: number
  excluidos: number
  valorados: number
  fuentes_activas: number
  ultima: Run | null
}

export interface Source {
  id: string
  name: string
  type: string
  reliability: string
  enabled: number
  requires_key: number
  last_run_at: string | null
  last_error: string | null
  job_count: number
  visible_count: number
}

export interface SesionAsistida {
  sitio: string
  source_id: string
  name: string
  portal: string
  valid: boolean | null
  detalle: string | null
  checked_at: string | null
  ventana_abierta: boolean
}

export interface SesionesResumen {
  sesiones: SesionAsistida[]
  requerida: boolean
  abierta: string | null
}

export interface FeedbackVoto {
  job_id: number
  profile_id: string | null
  vote: number
  motivos: string[]
  score_base: number | null
  created_at: string
}

export interface FeedbackResumen {
  votos: {
    total: number
    positivos: number
    negativos: number
  }
  por_motivo: Record<string, number>
  etiquetas: {
    total: number
    positivas: number
    negativas: number
    desde_votos: number
    desde_estados: number
    meta: number
    listo: boolean
    faltan_positivas: number
    faltan_negativas: number
  }
}

export interface LimpiezaPreview {
  dias: number
  corte: string
  total: number
  viejos: number
  eliminables: number
  protegidos: number
  con_nota: number
  con_feedback: number
}

export interface LimpiezaResultado {
  eliminados: number
  duplicados: number
  dias: number
  corte: string
  restantes: number
}
