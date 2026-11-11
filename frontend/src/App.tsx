import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import * as api from './api'
import './styles.css'
import type { FeedbackResumen, Job, JobDetail, JobStatus, LimpiezaPreview, LimpiezaResultado, Profile, Run, RunLog, ScoreDetail, SesionAsistida, Source, Stats } from './types'

const TABS = [
  { valor: '', etiqueta: 'Todas' },
  { valor: 'nuevo', etiqueta: 'Nuevos' },
  { valor: 'guardado', etiqueta: 'Guardados' },
  { valor: 'postulado', etiqueta: 'Postulados' },
  { valor: 'descartado', etiqueta: 'Descartados' },
]

const ETIQUETA_ESTADO: Record<string, string> = {
  nuevo: 'Nuevo',
  visto: 'Visto',
  guardado: 'Guardado',
  descartado: 'Descartado',
  postulado: 'Postulado',
}

const ETIQUETA_MODALIDAD: Record<string, string> = {
  remoto: 'Remoto',
  hibrido: 'Híbrido',
  presencial: 'Presencial',
}

const ETIQUETA_SENIORITY: Record<string, string> = {
  trainee: 'Trainee',
  junior: 'Junior',
  'semi-senior': 'Semi-Senior',
  senior: 'Senior',
}

const MOTIVOS_FEEDBACK = [
  { id: 'seniority', etiqueta: 'Seniority' },
  { id: 'stack', etiqueta: 'Stack' },
  { id: 'zona', etiqueta: 'Zona' },
  { id: 'modalidad', etiqueta: 'Modalidad' },
  { id: 'empresa', etiqueta: 'Empresa' },
  { id: 'idioma', etiqueta: 'Idioma' },
  { id: 'tareas', etiqueta: 'Tareas' },
  { id: 'salario', etiqueta: 'Salario' },
]

const ORDENES = [
  { valor: 'score-desc', etiqueta: 'Mayor puntaje' },
  { valor: 'score-asc', etiqueta: 'Menor puntaje' },
  { valor: 'date-desc', etiqueta: 'Más recientes' },
  { valor: 'date-asc', etiqueta: 'Más antiguos' },
]

const PUNTAJES_MINIMOS = [
  { valor: '', etiqueta: 'Cualquiera' },
  { valor: '50', etiqueta: '50 o más' },
  { valor: '70', etiqueta: '70 o más' },
  { valor: '85', etiqueta: '85 o más' },
]

function fechaRelativa(iso: string | null): string {
  if (!iso) return 'sin fecha'
  const objetivo = new Date(iso).getTime()
  if (Number.isNaN(objetivo)) return 'sin fecha'
  const segundos = (objetivo - Date.now()) / 1000
  const abs = Math.abs(segundos)
  const rtf = new Intl.RelativeTimeFormat('es', { numeric: 'auto' })
  if (abs < 60) return 'recién'
  if (abs < 3600) return rtf.format(Math.round(segundos / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(segundos / 3600), 'hour')
  if (abs < 2592000) return rtf.format(Math.round(segundos / 86400), 'day')
  return new Date(iso).toLocaleDateString('es-AR', { day: 'numeric', month: 'short' })
}

function Chip({ children, tono = 'neutro' }: { children: ReactNode; tono?: string }) {
  return <span className={`chip chip-${tono}`}>{children}</span>
}

function tonoScore(score: number | null): string {
  if (score == null) return 'bajo'
  if (score >= 85) return 'alto'
  if (score >= 70) return 'medio'
  return 'bajo'
}

function parseScoreDetail(job: Job | JobDetail): ScoreDetail | null {
  if (!job.score_detail) return null
  try {
    return JSON.parse(job.score_detail) as ScoreDetail
  } catch {
    return null
  }
}

function StatCard({ label, value, tono = 'neutro' }: { label: string; value: number; tono?: string }) {
  return (
    <div className={`stat stat-${tono}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}

const TONO_CONFIABILIDAD: Record<string, string> = {
  alta: 'verde',
  media: 'ambar',
  baja: 'rojo',
}

function Configuracion({
  fuentes,
  refrescando,
  onCerrar,
  onCambiar,
  onLimpiar,
}: {
  fuentes: Source[]
  refrescando: boolean
  onCerrar: () => void
  onCambiar: (sourceId: string, habilitada: boolean) => void
  onLimpiar: () => Promise<LimpiezaResultado>
}) {
  const [preview, setPreview] = useState<LimpiezaPreview | null>(null)
  const [resultado, setResultado] = useState<LimpiezaResultado | null>(null)
  const [limpiando, setLimpiando] = useState(false)
  const [errorLimpieza, setErrorLimpieza] = useState<string | null>(null)

  useEffect(() => {
    const alTeclear = (evento: KeyboardEvent) => {
      if (evento.key === 'Escape') onCerrar()
    }
    window.addEventListener('keydown', alTeclear)
    return () => window.removeEventListener('keydown', alTeclear)
  }, [onCerrar])

  useEffect(() => {
    let activo = true
    api
      .obtenerLimpiezaPreview()
      .then((datos) => {
        if (activo) setPreview(datos)
      })
      .catch(() => undefined)
    return () => {
      activo = false
    }
  }, [])

  const activas = fuentes.filter((f) => f.enabled).length

  async function limpiar() {
    if (!preview || preview.eliminables === 0 || limpiando) return
    const aceptar = window.confirm(
      `Se van a eliminar ${preview.eliminables} avisos con más de ${preview.dias} días. ` +
        'Se conservan los guardados, postulados, valorados y con nota. ¿Continuar?',
    )
    if (!aceptar) return
    setLimpiando(true)
    setErrorLimpieza(null)
    try {
      const r = await onLimpiar()
      setResultado(r)
      setPreview(await api.obtenerLimpiezaPreview())
    } catch (e) {
      setErrorLimpieza((e as Error).message)
    } finally {
      setLimpiando(false)
    }
  }

  return (
    <div className="modal-fondo" role="presentation" onClick={onCerrar}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="config-titulo"
        onClick={(evento) => evento.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2 id="config-titulo">Configuración</h2>
            <p>
              {activas} de {fuentes.length} fuentes activas
            </p>
          </div>
          <button className="modal-cerrar" onClick={onCerrar} aria-label="Cerrar configuración">
            ×
          </button>
        </div>

        <p className="config-nota">
          Una fuente desactivada no se vuelve a consultar en las próximas
          actualizaciones. Los avisos ya guardados siguen visibles y se pueden
          seguir filtrando.
        </p>

        <ul className="config-fuentes">
          {fuentes.map((f) => (
            <li key={f.id} className={f.enabled ? 'config-fuente' : 'config-fuente inactiva'}>
              <div className="config-fuente-info">
                <div className="config-fuente-titulo">
                  <strong>{f.name}</strong>
                  <Chip tono={f.enabled ? 'verde' : 'neutro'}>
                    {f.enabled ? 'Activa' : 'Inactiva'}
                  </Chip>
                  <Chip tono="azul">{f.type}</Chip>
                  {f.reliability && (
                    <Chip tono={TONO_CONFIABILIDAD[f.reliability] ?? 'neutro'}>
                      {f.reliability}
                    </Chip>
                  )}
                  {Boolean(f.requires_key) && <Chip tono="ambar">Requiere clave</Chip>}
                </div>
                <span className="config-fuente-meta">
                  {f.visible_count} visibles · {f.job_count} en base ·{' '}
                  {f.last_run_at
                    ? `última corrida ${fechaRelativa(f.last_run_at)}`
                    : 'sin corridas'}
                </span>
                {f.id === 'linkedin' && (
                  <span className="config-fuente-aviso">
                    Apagada por defecto: sus términos de uso prohíben la recolección
                    automatizada y el sitio puede limitar la IP (HTTP 429). Se consulta
                    sin login y con bajo volumen.
                  </span>
                )}
                {f.last_error && <span className="config-fuente-error">{f.last_error}</span>}
              </div>
              <button
                role="switch"
                aria-checked={Boolean(f.enabled)}
                aria-label={`${f.enabled ? 'Desactivar' : 'Activar'} ${f.name}`}
                className={f.enabled ? 'switch activo' : 'switch'}
                disabled={refrescando}
                title={
                  refrescando
                    ? 'Esperá a que termine la actualización en curso'
                    : f.enabled
                      ? 'Desactivar para las próximas actualizaciones'
                      : 'Volver a consultar esta fuente'
                }
                onClick={() => onCambiar(f.id, !f.enabled)}
              >
                <span />
              </button>
            </li>
          ))}
        </ul>

        <div className="config-mantenimiento">
          <div className="config-mantenimiento-texto">
            <strong>Mantenimiento</strong>
            <span>
              {preview
                ? `${preview.eliminables} de ${preview.viejos} avisos con más de ${preview.dias} días se pueden eliminar. Se conservan guardados, postulados, valorados y con nota.`
                : 'Calculando avisos antiguos…'}
            </span>
            {resultado && (
              <span className="config-mantenimiento-ok">
                Se eliminaron {resultado.eliminados} avisos; quedan {resultado.restantes} en base.
              </span>
            )}
            {errorLimpieza && <span className="config-fuente-error">{errorLimpieza}</span>}
          </div>
          <button
            className="btn"
            onClick={limpiar}
            disabled={!preview || preview.eliminables === 0 || limpiando}
            title={
              preview && preview.eliminables === 0
                ? 'No hay avisos antiguos para limpiar'
                : undefined
            }
          >
            {limpiando ? 'Limpiando…' : 'Limpiar ahora'}
          </button>
        </div>

        <div className="modal-pie">
          <span>Los cambios se aplican en la próxima actualización.</span>
          <button className="btn" onClick={onCerrar}>
            Cerrar
          </button>
        </div>
      </div>
    </div>
  )
}

function horaLog(iso: string): string {
  const fecha = new Date(iso)
  if (Number.isNaN(fecha.getTime())) return '--:--:--'
  return fecha.toLocaleTimeString('es-AR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function Registro({ run, onCerrar }: { run: Run | null; onCerrar: () => void }) {
  const [logs, setLogs] = useState<RunLog[]>([])
  const [soloErrores, setSoloErrores] = useState(false)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const listaRef = useRef<HTMLDivElement | null>(null)
  const finRef = useRef<HTMLDivElement | null>(null)
  const pegadoAlFondo = useRef(true)

  const cargar = useCallback(async () => {
    try {
      setLogs(await api.obtenerLogs(200))
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    cargar()
  }, [cargar])

  useEffect(() => {
    if (run?.status !== 'running') {
      cargar()
      return
    }
    const intervalo = window.setInterval(cargar, 1500)
    return () => window.clearInterval(intervalo)
  }, [run?.status, cargar])

  useEffect(() => {
    const alTeclear = (evento: KeyboardEvent) => {
      if (evento.key === 'Escape') onCerrar()
    }
    window.addEventListener('keydown', alTeclear)
    return () => window.removeEventListener('keydown', alTeclear)
  }, [onCerrar])

  const visibles = soloErrores ? logs.filter((l) => l.level === 'error') : logs
  const errores = logs.filter((l) => l.level === 'error').length
  const advertencias = logs.filter((l) => l.level === 'warn').length

  useEffect(() => {
    if (pegadoAlFondo.current) {
      finRef.current?.scrollIntoView({ block: 'end' })
    }
  }, [visibles.length, soloErrores])

  return (
    <div className="modal-fondo" role="presentation" onClick={onCerrar}>
      <div
        className="modal modal-log"
        role="dialog"
        aria-modal="true"
        aria-labelledby="log-titulo"
        onClick={(evento) => evento.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2 id="log-titulo">Registro de escaneos</h2>
            <p>
              {run?.status === 'running'
                ? 'Escaneo en curso; el registro se actualiza solo.'
                : 'Eventos de las últimas actualizaciones.'}
            </p>
          </div>
          <button className="modal-cerrar" onClick={onCerrar} aria-label="Cerrar registro">
            ×
          </button>
        </div>

        <div className="log-barra">
          <label className="log-filtro">
            <input
              type="checkbox"
              checked={soloErrores}
              onChange={(evento) => setSoloErrores(evento.target.checked)}
            />
            Solo errores
          </label>
          <span className="log-resumen">
            {logs.length} {logs.length === 1 ? 'evento' : 'eventos'} · {errores}{' '}
            {errores === 1 ? 'error' : 'errores'} · {advertencias}{' '}
            {advertencias === 1 ? 'advertencia' : 'advertencias'}
          </span>
        </div>

        <div
          className="log-lista"
          ref={listaRef}
          onScroll={() => {
            const el = listaRef.current
            if (!el) return
            pegadoAlFondo.current =
              el.scrollHeight - el.scrollTop - el.clientHeight < 28
          }}
        >
          {cargando && <p className="log-vacio">Cargando registro…</p>}
          {!cargando && visibles.length === 0 && (
            <p className="log-vacio">
              {soloErrores
                ? 'No hay errores registrados.'
                : 'Todavía no hay eventos. Ejecutá una actualización para ver el detalle.'}
            </p>
          )}
          {visibles.map((linea) => (
            <div key={linea.id} className={`log-linea log-${linea.level}`}>
              <span className="log-hora">{horaLog(linea.created_at)}</span>
              <span className={`log-nivel log-nivel-${linea.level}`}>{linea.level}</span>
              {linea.source_name && <span className="log-fuente">{linea.source_name}</span>}
              <span className="log-mensaje">{linea.message}</span>
            </div>
          ))}
          <div ref={finRef} />
        </div>

        {error && <div className="log-error">{error}</div>}

        <div className="modal-pie">
          <span>{logs.length > 0 ? `Últimos ${logs.length} eventos` : 'Sin eventos'}</span>
          <button className="btn" onClick={onCerrar}>
            Cerrar
          </button>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<Stats | null>(null)
  const [fuentes, setFuentes] = useState<Source[]>([])
  const [perfiles, setPerfiles] = useState<Profile[]>([])
  const [sesiones, setSesiones] = useState<SesionAsistida[]>([])
  const [resumenFeedback, setResumenFeedback] = useState<FeedbackResumen | null>(null)
  const [q, setQ] = useState('')
  const [fuente, setFuente] = useState('')
  const [estado, setEstado] = useState('')
  const [vista, setVista] = useState<'hoy' | 'todos'>('hoy')
  const [perfil, setPerfil] = useState('')
  const [modalidad, setModalidad] = useState('')
  const [seniority, setSeniority] = useState('')
  const [idioma, setIdioma] = useState('')
  const [puntajeMin, setPuntajeMin] = useState('')
  const [orden, setOrden] = useState('score-desc')
  const [seleccionado, setSeleccionado] = useState<Job | null>(null)
  const [detalle, setDetalle] = useState<JobDetail | null>(null)
  const [cargandoDetalle, setCargandoDetalle] = useState(false)
  const [run, setRun] = useState<Run | null>(null)
  const [refrescando, setRefrescando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cargandoLista, setCargandoLista] = useState(true)
  const [configAbierta, setConfigAbierta] = useState(false)
  const [logAbierto, setLogAbierto] = useState(false)

  const cargarResumen = useCallback(async () => {
    try {
      const [s, f, p] = await Promise.all([
        api.obtenerStats(),
        api.obtenerFuentes(),
        api.obtenerPerfiles(),
      ])
      setStats(s)
      setFuentes(f)
      setPerfiles(p)
      setRun((prev) => (prev && prev.status === 'running' ? prev : s.ultima))
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  const cargarSesiones = useCallback(async () => {
    try {
      const resumen = await api.obtenerSesiones()
      setSesiones(resumen.sesiones)
    } catch {
      /* el estado de sesión es informativo */
    }
  }, [])

  const cargarFeedback = useCallback(async () => {
    try {
      setResumenFeedback(await api.obtenerFeedbackResumen())
    } catch {
      /* el resumen de aprendizaje es informativo */
    }
  }, [])

  const cargarJobs = useCallback(async () => {
    setCargandoLista(true)
    const [sort, order] = orden.split('-') as ['score' | 'date', 'asc' | 'desc']
    try {
      const r = await api.listarJobs({
        q,
        source: fuente,
        status: estado,
        view: vista,
        profile: perfil,
        modality: modalidad,
        seniority,
        language: idioma,
        minScore: puntajeMin ? Number(puntajeMin) : undefined,
        sort,
        order,
      })
      setJobs(r.items)
      setTotal(r.total)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCargandoLista(false)
    }
  }, [q, fuente, estado, vista, perfil, modalidad, seniority, idioma, puntajeMin, orden])

  useEffect(() => {
    cargarResumen()
    cargarSesiones()
    cargarFeedback()
    api.ultimaCorrida().then(setRun).catch(() => undefined)
  }, [cargarResumen, cargarSesiones, cargarFeedback])

  useEffect(() => {
    const alEnfocar = () => cargarSesiones()
    window.addEventListener('focus', alEnfocar)
    return () => window.removeEventListener('focus', alEnfocar)
  }, [cargarSesiones])

  const ventanaSesion = sesiones.some((s) => s.ventana_abierta)

  useEffect(() => {
    if (!ventanaSesion && !refrescando) return
    const intervalo = window.setInterval(cargarSesiones, 3000)
    return () => window.clearInterval(intervalo)
  }, [ventanaSesion, refrescando, cargarSesiones])

  useEffect(() => {
    const t = window.setTimeout(cargarJobs, 250)
    return () => window.clearTimeout(t)
  }, [cargarJobs])

  useEffect(() => {
    if (!error) return
    const t = window.setTimeout(() => setError(null), 7000)
    return () => window.clearTimeout(t)
  }, [error])

  const runId = run?.id
  const runActivo = run?.status === 'running'

  useEffect(() => {
    if (!runId || !runActivo) return
    const intervalo = window.setInterval(async () => {
      try {
        const r = await api.obtenerRun(runId)
        setRun(r)
        if (r.status !== 'running') {
          setRefrescando(false)
          cargarResumen()
          cargarJobs()
          cargarSesiones()
        }
      } catch {
        /* se reintenta en el próximo tick */
      }
    }, 700)
    return () => window.clearInterval(intervalo)
  }, [runId, runActivo, cargarResumen, cargarJobs, cargarSesiones])

  async function actualizarAhora() {
    setError(null)
    try {
      const { run_id } = await api.actualizarAhora()
      setRefrescando(true)
      setRun({
        id: run_id,
        started_at: new Date().toISOString(),
        finished_at: null,
        status: 'running',
        found: 0,
        new: 0,
        updated: 0,
        errors: 0,
        message: null,
      })
    } catch (e) {
      setError((e as Error).message)
      setRefrescando(false)
    }
  }

  async function abrirSesionPortal(sourceId: string) {
    setError(null)
    try {
      const estado = await api.abrirSesion(sourceId)
      setSesiones((prev) => prev.map((s) => (s.source_id === sourceId ? estado : s)))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function cambiarFuente(sourceId: string, habilitada: boolean) {
    if (sourceId === 'linkedin' && habilitada) {
      const aceptar = window.confirm(
        'LinkedIn prohíbe la recolección automatizada en sus términos de uso. ' +
          'El sitio además limita rápido las consultas (HTTP 429) y puede bloquear ' +
          'temporalmente tu IP. ¿Activar la fuente igual?',
      )
      if (!aceptar) return
    }
    if (sourceId === 'jooble' && habilitada) {
      const aceptar = window.confirm(
        'Jooble usa una clave distinta por país: la de jooble.org solo trae avisos ' +
          'de EE. UU. Para Argentina hay que pedirla en ar.jooble.org/api/about y ' +
          'guardarla en el archivo .env. El plan gratuito tiene 500 consultas en ' +
          'total, así que se pide una sola página por búsqueda. ¿Activar la fuente?',
      )
      if (!aceptar) return
    }
    try {
      const actualizada = await api.actualizarFuente(sourceId, habilitada)
      setFuentes((prev) => prev.map((f) => (f.id === sourceId ? actualizada : f)))
      setStats((prev) =>
        prev
          ? {
              ...prev,
              fuentes_activas: Math.max(0, prev.fuentes_activas + (habilitada ? 1 : -1)),
            }
          : prev,
      )
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function limpiarAvisos() {
    try {
      const resultado = await api.limpiarAvisos()
      setSeleccionado(null)
      setDetalle(null)
      await Promise.all([cargarResumen(), cargarJobs(), cargarFeedback()])
      return resultado
    } catch (e) {
      setError((e as Error).message)
      throw e
    }
  }

  async function abrir(job: Job) {
    setSeleccionado(job)
    setDetalle(null)
    setCargandoDetalle(true)
    try {
      const d = await api.obtenerJob(job.id)
      setDetalle(d)
      if (job.status === 'nuevo') {
        await api.actualizarJob(job.id, { status: 'visto' })
        setJobs((prev) => prev.map((j) => (j.id === job.id ? { ...j, status: 'visto' } : j)))
        setSeleccionado((prev) => (prev ? { ...prev, status: 'visto' } : prev))
        setStats((prev) => (prev ? { ...prev, nuevos: Math.max(0, prev.nuevos - 1) } : prev))
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setCargandoDetalle(false)
    }
  }

  async function cambiarEstado(job: Job, nuevo: JobStatus) {
    try {
      await api.actualizarJob(job.id, { status: nuevo })
      setJobs((prev) => prev.map((j) => (j.id === job.id ? { ...j, status: nuevo } : j)))
      setDetalle((prev) => (prev && prev.id === job.id ? { ...prev, status: nuevo } : prev))
      setSeleccionado((prev) => (prev && prev.id === job.id ? { ...prev, status: nuevo } : prev))
      cargarResumen()
      cargarFeedback()
      if (estado) cargarJobs()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function aplicarFeedback(jobId: number, vote: number | null, motivos: string[]) {
    setJobs((prev) =>
      prev.map((j) => (j.id === jobId ? { ...j, feedback_vote: vote, feedback_motivos: motivos } : j)),
    )
    setSeleccionado((prev) =>
      prev && prev.id === jobId
        ? { ...prev, feedback_vote: vote, feedback_motivos: motivos }
        : prev,
    )
    setDetalle((prev) =>
      prev && prev.id === jobId
        ? { ...prev, feedback_vote: vote, feedback_motivos: motivos }
        : prev,
    )
  }

  async function votar(job: Job, voto: 1 | -1) {
    try {
      if (job.feedback_vote === voto) {
        await api.borrarFeedback(job.id)
        aplicarFeedback(job.id, null, [])
      } else {
        const r = await api.registrarFeedback(job.id, voto, voto === 1 ? [] : job.feedback_motivos ?? [])
        aplicarFeedback(job.id, r.vote, r.motivos)
      }
      cargarFeedback()
      cargarResumen()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function cambiarMotivos(job: Job, motivos: string[]) {
    if (job.feedback_vote !== -1) return
    try {
      const r = await api.registrarFeedback(job.id, -1, motivos)
      aplicarFeedback(job.id, r.vote, r.motivos)
      cargarFeedback()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function guardarNota(job: Job, nota: string) {
    try {
      await api.actualizarJob(job.id, { note: nota })
      setDetalle((prev) => (prev && prev.id === job.id ? { ...prev, note: nota || null } : prev))
      setJobs((prev) => prev.map((j) => (j.id === job.id ? { ...j, note: nota || null } : j)))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const mensajeCorrida =
    run?.status === 'running'
      ? `Actualizando… ${run.found} avisos encontrados`
      : run?.finished_at
        ? `Última actualización: ${fechaRelativa(run.finished_at)}`
        : 'Sin actualizaciones todavía'

  const hayFiltros = Boolean(
    q || fuente || estado || perfil || modalidad || seniority || idioma || puntajeMin || vista === 'hoy',
  )
  const hayFiltrosManuales = Boolean(
    q || fuente || estado || perfil || modalidad || seniority || idioma || puntajeMin,
  )

  function limpiarFiltros() {
    setQ('')
    setFuente('')
    setEstado('')
    setPerfil('')
    setModalidad('')
    setSeniority('')
    setIdioma('')
    setPuntajeMin('')
  }

  const fuentesBloqueadas = fuentes.filter(
    (f) =>
      Boolean(f.enabled) &&
      Boolean(f.last_error) &&
      /bloque|waf|captcha|human verification/i.test(f.last_error ?? ''),
  )

  const errorSesion = fuentes.some(
    (f) => Boolean(f.enabled) && /sesi[oó]n asistida/i.test(f.last_error ?? ''),
  )
  const ventanaSesionActiva = sesiones.find((s) => s.ventana_abierta) ?? null
  const sesionesPendientes = sesiones.filter((s) => s.valid !== true)
  const mostrarSesion =
    errorSesion || sesiones.some((s) => s.valid === false) || Boolean(ventanaSesionActiva)
  const nombresSesion = (sesionesPendientes.length > 0 ? sesionesPendientes : sesiones)
    .map((s) => s.name)
    .join(' y ')

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <span />
          </div>
          <div>
            <h1>Radar Laboral</h1>
            <p>Avisos que encajan con tu perfil</p>
          </div>
        </div>
        <div className="topbar-right">
          <span className="last-run">{mensajeCorrida}</span>
          <button
            className={`btn btn-log${(run?.errors ?? 0) > 0 ? ' btn-log-alerta' : ''}`}
            onClick={() => setLogAbierto(true)}
            aria-haspopup="dialog"
            title="Ver eventos y errores de los escaneos"
          >
            Registro
            {(run?.errors ?? 0) > 0 && (
              <span className="btn-badge">{Math.min(run?.errors ?? 0, 99)}</span>
            )}
          </button>
          <button
            className="btn"
            onClick={() => setConfigAbierta(true)}
            aria-haspopup="dialog"
            title="Activar o desactivar fuentes"
          >
            Configuración
          </button>
          <button
            className="btn btn-primary"
            onClick={actualizarAhora}
            disabled={refrescando || ventanaSesion}
            title={
              ventanaSesion
                ? 'Cerrá la ventana de sesión antes de actualizar'
                : undefined
            }
          >
            {refrescando ? 'Actualizando…' : 'Actualizar ahora'}
          </button>
        </div>
      </header>

      {configAbierta && (
        <Configuracion
          fuentes={fuentes}
          refrescando={refrescando}
          onCerrar={() => setConfigAbierta(false)}
          onCambiar={cambiarFuente}
          onLimpiar={limpiarAvisos}
        />
      )}

      {logAbierto && <Registro run={run} onCerrar={() => setLogAbierto(false)} />}

      {error && (
        <div className="toast" role="alert">
          {error}
          <button onClick={() => setError(null)} aria-label="Cerrar aviso">
            ×
          </button>
        </div>
      )}

      {fuentesBloqueadas.length > 0 && (
        <div className="aviso-fuente" role="status">
          <span>
            <strong>{fuentesBloqueadas.map((f) => f.name).join(', ')}</strong> pidió
            verificación humana (WAF). La fuente se detuvo sin reintentar; esperá unos
            minutos antes de volver a actualizar.
          </span>
        </div>
      )}

      {mostrarSesion && (
        <div className="aviso-sesion" role="status">
          <div className="aviso-sesion-texto">
            <strong>Sesión asistida · {nombresSesion}</strong>
            <span>
              {ventanaSesionActiva
                ? `Se abrió la ventana de ${ventanaSesionActiva.name}. Resolvé la verificación de Cloudflare ahí: la sesión se detecta sola. Cuando figure validada, cerrá la ventana y actualizá.`
                : sesionesPendientes.length === 0
                  ? 'La sesión quedó validada. Actualizá para traer los avisos nuevos.'
                  : 'Cloudflare pide una verificación manual. Abrí la ventana, resolvela vos y volvé a actualizar. La app no resuelve captchas ni automatiza la postulación.'}
            </span>
            {sesiones.length > 0 && (
              <span className="aviso-sesion-estado">
                {sesiones
                  .map((s) => {
                    const estado =
                      s.valid === true
                        ? 'validada'
                        : s.valid === false
                          ? 'sin validar'
                          : 'sin verificar'
                    return `${s.name}: ${estado}`
                  })
                  .join(' · ')}
              </span>
            )}
          </div>
          <div className="aviso-sesion-acciones">
            {sesionesPendientes.map((s) => (
              <button
                key={s.source_id}
                className="btn"
                onClick={() => abrirSesionPortal(s.source_id)}
                disabled={Boolean(ventanaSesionActiva)}
                title={
                  ventanaSesionActiva && !s.ventana_abierta
                    ? 'Cerrá la ventana de sesión abierta antes de abrir la otra'
                    : undefined
                }
              >
                {s.ventana_abierta
                  ? 'Esperando verificación…'
                  : `${s.valid === false ? 'Renovar' : 'Abrir'} ${s.name.replace(' AR', '')}`}
              </button>
            ))}
            {sesionesPendientes.length === 0 && (
              <button
                className="btn btn-primary"
                onClick={actualizarAhora}
                disabled={refrescando || ventanaSesion}
                title={
                  ventanaSesion
                    ? 'Cerrá la ventana de sesión antes de actualizar'
                    : undefined
                }
              >
                {refrescando ? 'Actualizando…' : 'Actualizar ahora'}
              </button>
            )}
          </div>
        </div>
      )}

      <section className="stats">
        <StatCard label="Avisos" value={stats?.total ?? 0} />
        <StatCard label="Para hoy" value={stats?.hoy ?? 0} tono="verde" />
        <StatCard label="Nuevos" value={stats?.nuevos ?? 0} tono="azul" />
        <StatCard label="Guardados" value={stats?.guardados ?? 0} tono="violeta" />
        <StatCard label="Valorados" value={stats?.valorados ?? 0} tono="ambar" />
        <StatCard label="Fuentes activas" value={stats?.fuentes_activas ?? 0} />
      </section>

      <section className="toolbar">
        <div className="search">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3.5-3.5" />
          </svg>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar por puesto, empresa o palabra clave…"
            aria-label="Buscar avisos"
          />
          {q && (
            <button className="limpiar" onClick={() => setQ('')} aria-label="Limpiar búsqueda">
              ×
            </button>
          )}
        </div>
        <select value={perfil} onChange={(e) => setPerfil(e.target.value)} aria-label="Filtrar por perfil">
          <option value="">Todos los perfiles</option>
          {perfiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.id} · {p.name} ({vista === 'hoy' ? p.hoy_count : p.visible_count})
            </option>
          ))}
        </select>
        <select value={fuente} onChange={(e) => setFuente(e.target.value)} aria-label="Filtrar por fuente">
          <option value="">Todas las fuentes</option>
          {fuentes.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name} ({f.visible_count}){f.enabled ? '' : ' · inactiva'}
            </option>
          ))}
        </select>
      </section>

      <section className="filtros" aria-label="Filtros y orden">
        <label className="filtro">
          <span>Modalidad</span>
          <select value={modalidad} onChange={(e) => setModalidad(e.target.value)}>
            <option value="">Todas</option>
            <option value="remoto">Remoto</option>
            <option value="hibrido">Híbrido</option>
            <option value="presencial">Presencial</option>
          </select>
        </label>
        <label className="filtro">
          <span>Seniority</span>
          <select value={seniority} onChange={(e) => setSeniority(e.target.value)}>
            <option value="">Todos</option>
            <option value="trainee">Trainee</option>
            <option value="junior">Junior</option>
            <option value="semi-senior">Semi-Senior</option>
            <option value="senior">Senior</option>
          </select>
        </label>
        <label className="filtro">
          <span>Idioma</span>
          <select value={idioma} onChange={(e) => setIdioma(e.target.value)}>
            <option value="">Todos</option>
            <option value="es">Español</option>
            <option value="en">Inglés</option>
          </select>
        </label>
        <label className="filtro">
          <span>Puntaje</span>
          <select value={puntajeMin} onChange={(e) => setPuntajeMin(e.target.value)}>
            {PUNTAJES_MINIMOS.map((p) => (
              <option key={p.valor} value={p.valor}>
                {p.etiqueta}
              </option>
            ))}
          </select>
        </label>
        <label className="filtro filtro-orden">
          <span>Ordenar por</span>
          <select value={orden} onChange={(e) => setOrden(e.target.value)}>
            {ORDENES.map((o) => (
              <option key={o.valor} value={o.valor}>
                {o.etiqueta}
              </option>
            ))}
          </select>
        </label>
        {hayFiltrosManuales && (
          <button className="btn-limpiar" onClick={limpiarFiltros}>
            Limpiar filtros
          </button>
        )}
      </section>

      <nav className="tabs" aria-label="Filtros de la lista">
        <div className="vistas">
          <button
            className={vista === 'hoy' ? 'vista activo' : 'vista'}
            onClick={() => setVista('hoy')}
            title="Avisos con puntaje 70 o más"
          >
            Hoy <span className="tab-count">{stats?.hoy ?? 0}</span>
          </button>
          <button
            className={vista === 'todos' ? 'vista activo' : 'vista'}
            onClick={() => setVista('todos')}
          >
            Todos
          </button>
        </div>
        <span className="tabs-sep" aria-hidden="true" />
        {TABS.map((t) => (
          <button
            key={t.valor}
            className={estado === t.valor ? 'tab activo' : 'tab'}
            onClick={() => setEstado(t.valor)}
          >
            {t.etiqueta}
            {t.valor === '' && <span className="tab-count">{total}</span>}
          </button>
        ))}
      </nav>

      <main className="workspace">
        <section className="lista">
          {cargandoLista && jobs.length === 0 ? (
            <div className="estado-vacio">
              <p>Cargando avisos…</p>
            </div>
          ) : jobs.length === 0 ? (
            <div className="estado-vacio">
              <h2>{hayFiltros ? 'No hay avisos con esos filtros' : 'Todavía no hay avisos'}</h2>
              <p>
                {hayFiltros
                  ? 'Probá con otra búsqueda, cambiá de perfil o mirá todos los avisos.'
                  : 'Actualizá para traer ofertas de los portales.'}
              </p>
              {hayFiltros && vista === 'hoy' ? (
                <button className="btn" onClick={() => setVista('todos')}>
                  Ver todos los avisos
                </button>
              ) : !hayFiltros ? (
                <button className="btn btn-primary" onClick={actualizarAhora} disabled={refrescando || ventanaSesion}>
                  Actualizar ahora
                </button>
              ) : null}
            </div>
          ) : (
            jobs.map((job) => (
              <article
                key={job.id}
                className={`job ${seleccionado?.id === job.id ? 'activo' : ''}`}
                onClick={() => abrir(job)}
              >
                <div className="job-body">
                  <div className="job-top">
                    <h3>{job.title}</h3>
                    {job.status !== 'nuevo' && (
                      <span className={`pill pill-${job.status}`}>{ETIQUETA_ESTADO[job.status]}</span>
                    )}
                  </div>
                  <p className="job-company">
                    {job.company_name || 'Empresa no informada'}
                    {job.location ? <span> · {job.location}</span> : null}
                  </p>
                  <div className="chips">
                    {job.modality && (
                      <Chip tono="azul">{ETIQUETA_MODALIDAD[job.modality] ?? job.modality}</Chip>
                    )}
                    {job.seniority && (
                      <Chip tono="violeta">{ETIQUETA_SENIORITY[job.seniority] ?? job.seniority}</Chip>
                    )}
                    {job.salary_text && <Chip tono="verde">{job.salary_text}</Chip>}
                    {job.language === 'en' && <Chip tono="ambar">Inglés</Chip>}
                    {job.feedback_vote === 1 && <Chip tono="verde">Me interesa</Chip>}
                    {job.feedback_vote === -1 && <Chip tono="rojo">No me interesa</Chip>}
                  </div>
                </div>
                <div className="job-side">
                  {job.score != null && (
                    <span
                      className={`score score-${tonoScore(job.score)}`}
                      title={`${job.profile_id ?? 'Sin perfil'} · ${job.profile_name ?? ''} · ${job.score}/100`}
                    >
                      {job.score}
                      {job.profile_id && <small>{job.profile_id}</small>}
                    </span>
                  )}
                  <span className="job-date">{fechaRelativa(job.published_at)}</span>
                  <span className="job-source">{job.source_name}</span>
                  <button
                    className="btn-mini"
                    onClick={(e) => {
                      e.stopPropagation()
                      cambiarEstado(job, job.status === 'guardado' ? 'visto' : 'guardado')
                    }}
                  >
                    {job.status === 'guardado' ? 'Quitar' : 'Guardar'}
                  </button>
                  <div className="job-votos">
                    <button
                      className={`btn-mini btn-voto ${job.feedback_vote === 1 ? 'activo-si' : ''}`}
                      aria-label="Me interesa"
                      aria-pressed={job.feedback_vote === 1}
                      title="Me interesa: se guarda para el aprendizaje"
                      onClick={(e) => {
                        e.stopPropagation()
                        votar(job, 1)
                      }}
                    >
                      Sí
                    </button>
                    <button
                      className={`btn-mini btn-voto ${job.feedback_vote === -1 ? 'activo-no' : ''}`}
                      aria-label="No me interesa"
                      aria-pressed={job.feedback_vote === -1}
                      title="No me interesa: se guarda para el aprendizaje"
                      onClick={(e) => {
                        e.stopPropagation()
                        votar(job, -1)
                      }}
                    >
                      No
                    </button>
                  </div>
                </div>
              </article>
            ))
          )}
        </section>

        <aside className={`detalle ${seleccionado ? 'visible' : ''}`}>
          {!seleccionado ? (
            <div className="estado-vacio detalle-vacio">
              <div className="detalle-icono">◎</div>
              <h2>Elegí un aviso</h2>
              <p>Hacé clic en una oferta para ver la descripción completa y guardar una nota.</p>
            </div>
          ) : (
            <Detalle
              job={detalle ?? seleccionado}
              cargando={cargandoDetalle}
              onCerrar={() => {
                setSeleccionado(null)
                setDetalle(null)
              }}
              onEstado={cambiarEstado}
              onNota={guardarNota}
              onVoto={votar}
              onMotivos={cambiarMotivos}
              resumenFeedback={resumenFeedback}
            />
          )}
        </aside>
      </main>
    </div>
  )
}

function Detalle({
  job,
  cargando,
  onCerrar,
  onEstado,
  onNota,
  onVoto,
  onMotivos,
  resumenFeedback,
}: {
  job: Job | JobDetail
  cargando: boolean
  onCerrar: () => void
  onEstado: (job: Job, estado: JobStatus) => void
  onNota: (job: Job, nota: string) => void
  onVoto: (job: Job, voto: 1 | -1) => void
  onMotivos: (job: Job, motivos: string[]) => void
  resumenFeedback: FeedbackResumen | null
}) {
  const detallado = 'description' in job ? job : null
  const descripcion = detallado?.description ?? null
  const errorDetalle = detallado?.detail_error

  return (
    <div className="detalle-panel">
      <div className="detalle-head">
        <button className="cerrar" onClick={onCerrar} aria-label="Cerrar detalle">
          ×
        </button>
        <span className="detalle-fuente">
          {job.source_name} · {fechaRelativa(job.published_at)}
        </span>
        <h2>{job.title}</h2>
        <p className="detalle-empresa">
          {job.company_name || 'Empresa no informada'}
          {job.location ? ` · ${job.location}` : ''}
        </p>
        <div className="chips">
          {job.modality && <Chip tono="azul">{ETIQUETA_MODALIDAD[job.modality] ?? job.modality}</Chip>}
          {job.seniority && (
            <Chip tono="violeta">{ETIQUETA_SENIORITY[job.seniority] ?? job.seniority}</Chip>
          )}
          {job.salary_text && <Chip tono="verde">{job.salary_text}</Chip>}
          {job.language === 'en' && <Chip tono="ambar">Inglés</Chip>}
        </div>
        <div className="detalle-acciones">
          <a className="btn btn-primary" href={job.url} target="_blank" rel="noreferrer">
            Abrir original ↗
          </a>
          <button
            className={`btn ${job.status === 'guardado' ? 'btn-activo' : ''}`}
            onClick={() => onEstado(job, 'guardado')}
          >
            Guardar
          </button>
          <button
            className={`btn ${job.status === 'postulado' ? 'btn-activo' : ''}`}
            onClick={() => onEstado(job, 'postulado')}
          >
            Postulado
          </button>
          <button
            className={`btn ${job.status === 'descartado' ? 'btn-peligro' : ''}`}
            onClick={() => onEstado(job, 'descartado')}
          >
            Descartar
          </button>
        </div>
      </div>

      <div className="detalle-cuerpo">
        {cargando ? (
          <div className="cargando">Cargando descripción…</div>
        ) : descripcion ? (
          <div className="descripcion">{descripcion}</div>
        ) : (
          <div className="sin-descripcion">
            <p>{errorDetalle ?? 'Esta oferta no tiene descripción disponible en el portal.'}</p>
            <a href={job.url} target="_blank" rel="noreferrer">
              Verla en el portal ↗
            </a>
          </div>
        )}
        <Explicacion job={job} />
        <Valoracion
          job={job}
          resumen={resumenFeedback}
          onVoto={onVoto}
          onMotivos={onMotivos}
        />
      </div>

      <div className="detalle-nota">
        <EditorNota job={job} onGuardar={(nota) => onNota(job, nota)} />
      </div>
    </div>
  )
}

function Valoracion({
  job,
  resumen,
  onVoto,
  onMotivos,
}: {
  job: Job | JobDetail
  resumen: FeedbackResumen | null
  onVoto: (job: Job, voto: 1 | -1) => void
  onMotivos: (job: Job, motivos: string[]) => void
}) {
  const voto = job.feedback_vote
  const etiquetas = resumen?.etiquetas
  const [motivosLocales, setMotivosLocales] = useState<string[]>(job.feedback_motivos ?? [])
  const motivosRef = useRef<string[]>(job.feedback_motivos ?? [])
  const temporizador = useRef<number | null>(null)

  useEffect(() => {
    const iniciales = job.feedback_motivos ?? []
    motivosRef.current = iniciales
    setMotivosLocales(iniciales)
    // Solo al cambiar de aviso: los cambios de motivos ya se reflejan localmente.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id])

  useEffect(() => {
    if (job.feedback_vote !== -1) {
      motivosRef.current = []
      setMotivosLocales([])
    }
  }, [job.feedback_vote])

  function alternarMotivo(id: string) {
    const actuales = motivosRef.current
    const siguiente = actuales.includes(id)
      ? actuales.filter((motivo) => motivo !== id)
      : [...actuales, id]
    motivosRef.current = siguiente
    setMotivosLocales(siguiente)
    if (temporizador.current) window.clearTimeout(temporizador.current)
    // Se agrupan los clics seguidos en un solo guardado.
    temporizador.current = window.setTimeout(() => {
      temporizador.current = null
      onMotivos(job, siguiente)
    }, 250)
  }

  function votarLocal(votoElegido: 1 | -1) {
    if (temporizador.current) {
      window.clearTimeout(temporizador.current)
      temporizador.current = null
    }
    onVoto(job, votoElegido)
  }

  return (
    <section className="feedback" aria-label="Tu valoración">
      <div className="feedback-head">
        <strong>Tu valoración</strong>
        {etiquetas && (
          <span className="feedback-progreso">
            Aprendizaje: {etiquetas.positivas} positivos · {etiquetas.negativas} negativos
            {etiquetas.listo
              ? ' · listo para entrenar'
              : ` · faltan ${etiquetas.faltan_positivas} y ${etiquetas.faltan_negativas}`}
          </span>
        )}
      </div>
      <div className="feedback-acciones">
        <button
          className={`btn ${voto === 1 ? 'btn-activo' : ''}`}
          aria-pressed={voto === 1}
          onClick={() => votarLocal(1)}
        >
          Me interesa
        </button>
        <button
          className={`btn ${voto === -1 ? 'btn-peligro' : ''}`}
          aria-pressed={voto === -1}
          onClick={() => votarLocal(-1)}
        >
          No me interesa
        </button>
      </div>
      {voto === -1 && (
        <div className="feedback-motivos">
          <span className="feedback-motivos-label">¿Por qué?</span>
          {MOTIVOS_FEEDBACK.map((motivo) => (
            <button
              key={motivo.id}
              className={`chip-opcion ${motivosLocales.includes(motivo.id) ? 'activo' : ''}`}
              aria-pressed={motivosLocales.includes(motivo.id)}
              onClick={() => alternarMotivo(motivo.id)}
            >
              {motivo.etiqueta}
            </button>
          ))}
        </div>
      )}
      <p className="feedback-ayuda">
        Se guarda junto con el puntaje y el perfil del aviso. Tus estados (guardado,
        postulado, descartado) también cuentan como señal para el futuro ranking.
      </p>
    </section>
  )
}

function Explicacion({ job }: { job: Job | JobDetail }) {
  const detalle = parseScoreDetail(job)
  if (!detalle) return null

  const { skills } = detalle
  const otros = Object.entries(detalle.todos ?? {})
    .filter(([id]) => id !== detalle.profile_id)
    .sort((a, b) => b[1] - a[1])

  return (
    <section className="explicacion">
      <div className="explicacion-head">
        <span className={`score score-${tonoScore(detalle.score)}`}>{detalle.score}</span>
        <div className="explicacion-titulo">
          <strong>
            {detalle.profile_id} · {detalle.profile_name}
          </strong>
          <span className="explicacion-sub">
            {detalle.score >= 70 ? 'Encaja con tu perfil' : 'Coincidencia parcial'} · {detalle.zone.label}
          </span>
        </div>
      </div>

      {detalle.reasons.length > 0 && (
        <ul className="razones">
          {detalle.reasons.map((razon) => (
            <li key={razon}>{razon}</li>
          ))}
        </ul>
      )}

      {(skills.matched.length > 0 || skills.missing.length > 0) && (
        <div className="skills">
          {skills.matched.length > 0 && (
            <div className="skills-linea">
              <span className="skills-label">Coincide</span>
              {skills.matched.map((skill) => (
                <Chip key={skill} tono="verde">
                  {skill}
                </Chip>
              ))}
            </div>
          )}
          {skills.missing.length > 0 && (
            <div className="skills-linea">
              <span className="skills-label">Falta</span>
              {skills.missing.map((skill) => (
                <span key={skill} className="chip chip-hueco">
                  {skill}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <details className="desglose">
        <summary>Ver desglose del puntaje</summary>
        <div className="desglose-grid">
          <span>
            Skills <b>{skills.score}/40</b>
          </span>
          <span>
            Rol <b>{detalle.role.score}/20</b>
          </span>
          <span>
            Seniority <b>{detalle.seniority.score}/10</b>
            {detalle.seniority.adjustment
              ? ` (${detalle.seniority.adjustment > 0 ? '+' : ''}${detalle.seniority.adjustment})`
              : ''}
          </span>
          <span>
            Zona <b>{detalle.zone.score}/10</b>
          </span>
          <span>
            Idioma <b>{detalle.language.score}/10</b>
          </span>
          <span>
            Recencia <b>{detalle.recency.score}/10</b>
          </span>
        </div>
        {otros.length > 0 && (
          <p className="otros-perfiles">
            También puntúa en:{' '}
            {otros.map(([id, valor]) => `${id} ${valor}`).join(' · ')}
          </p>
        )}
      </details>
    </section>
  )
}

function EditorNota({ job, onGuardar }: { job: Job | JobDetail; onGuardar: (nota: string) => void }) {
  const [texto, setTexto] = useState(job.note ?? '')
  const [abierto, setAbierto] = useState(Boolean(job.note?.trim()))

  useEffect(() => {
    setTexto(job.note ?? '')
    setAbierto(Boolean(job.note?.trim()))
    // Solo se reinicia al cambiar de aviso.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id])

  const cambiado = texto !== (job.note ?? '')

  if (!abierto) {
    return (
      <button className="btn btn-nota" onClick={() => setAbierto(true)}>
        ＋ Agregar nota personal
      </button>
    )
  }

  return (
    <div className="nota">
      <div className="nota-head">
        <label htmlFor="nota">Nota personal</label>
        <button
          className="nota-ocultar"
          onClick={() => setAbierto(false)}
          title="Ocultar la nota"
        >
          Ocultar
        </button>
      </div>
      <textarea
        id="nota"
        rows={3}
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder="Por qué te interesa, contacto, fecha de postulación…"
      />
      <button className="btn" disabled={!cambiado} onClick={() => onGuardar(texto)}>
        Guardar nota
      </button>
    </div>
  )
}
