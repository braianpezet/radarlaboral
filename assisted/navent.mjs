#!/usr/bin/env node
/**
 * Sesión asistida para ZonaJobs y Bumeran (Navent).
 *
 * Este script NO resuelve captchas ni desafíos anti-bot. Abre un Edge real
 * con un perfil persistente para que la persona resuelva la verificación
 * manualmente. Una vez validada, consulta la API pública de avisos desde
 * la misma pestaña (mismo origen, mismas cookies) y devuelve JSON.
 *
 * Uso:
 *   node navent.mjs open  --site zonajobs [--data-dir DIR]
 *   node navent.mjs fetch --site zonajobs --query programador --query "machine learning"
 *                         [--pages 1] [--espera-sesion 90] [--data-dir DIR]
 *   node navent.mjs status --site zonajobs [--data-dir DIR]
 *
 * Salida: una única línea JSON por stdout. Los mensajes van a stderr.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const AQUI = path.dirname(fileURLToPath(import.meta.url))
const RAIZ = path.resolve(AQUI, '..')

const SITIOS = {
  zonajobs: {
    base: 'https://www.zonajobs.com.ar',
    siteId: 'ZJAR',
    nombre: 'ZonaJobs AR',
  },
  bumeran: {
    base: 'https://www.bumeran.com.ar',
    siteId: 'BMAR',
    nombre: 'Bumeran AR',
  },
}

const PAGINA_INICIO = '/empleos.html'
const API = '/api/avisos/searchV2'

function argumento(nombre, defecto = null) {
  const i = process.argv.indexOf(`--${nombre}`)
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : defecto
}

function argumentos(nombre) {
  const salida = []
  for (let i = 0; i < process.argv.length; i += 1) {
    if (process.argv[i] === `--${nombre}` && i + 1 < process.argv.length) {
      salida.push(process.argv[i + 1])
    }
  }
  return salida
}

const comando = process.argv[2] || ''
const siteId = argumento('site', '')
const sitio = SITIOS[siteId]
const dataDir = path.resolve(argumento('data-dir', path.join(RAIZ, 'data')))
const perfilDir = path.join(dataDir, 'sesion_navent')
const logRuta = path.join(dataDir, 'sesion_navent.log')
const maxPaginas = Math.max(1, Number(argumento('pages', '1')) || 1)
const esperaSesion = Math.max(0, Number(argumento('espera-sesion', '90')) || 0)
const consultas = argumentos('query')

function log(...partes) {
  const linea = `[${new Date().toISOString()}] ${partes.join(' ')}`
  process.stderr.write(linea + '\n')
  try {
    fs.mkdirSync(dataDir, { recursive: true })
    fs.appendFileSync(logRuta, linea + '\n', 'utf8')
  } catch {
    /* el log es best-effort */
  }
}

function salir(datos, codigo = 0) {
  process.stdout.write(JSON.stringify(datos) + '\n')
  process.exit(codigo)
}

function marcar(valid, detalle = null) {
  try {
    fs.mkdirSync(dataDir, { recursive: true })
    const ruta = path.join(dataDir, `sesion_navent_${siteId}.json`)
    fs.writeFileSync(
      ruta,
      JSON.stringify(
        {
          site: siteId,
          name: sitio?.nombre || siteId,
          valid: Boolean(valid),
          detalle,
          checked_at: new Date().toISOString(),
        },
        null,
        2,
      ),
      'utf8',
    )
  } catch (exc) {
    log('no se pudo guardar el estado de sesión:', String(exc))
  }
}

async function esperar(ms) {
  await new Promise((resolver) => setTimeout(resolver, ms))
}

async function lanzarContexto(headless) {
  fs.mkdirSync(perfilDir, { recursive: true })
  const opciones = {
    headless,
    locale: 'es-AR',
    timezoneId: 'America/Argentina/Buenos_Aires',
    viewport: headless ? { width: 1366, height: 900 } : null,
    args: headless ? [] : ['--start-maximized'],
  }
  const fallos = []
  for (const channel of ['msedge', 'chrome']) {
    try {
      return await chromium.launchPersistentContext(perfilDir, {
        ...opciones,
        channel,
      })
    } catch (exc) {
      fallos.push(`${channel}: ${String(exc.message || exc).split('\n')[0]}`)
    }
  }
  try {
    return await chromium.launchPersistentContext(perfilDir, opciones)
  } catch (exc) {
    fallos.push(`chromium: ${String(exc.message || exc).split('\n')[0]}`)
  }
  const error = new Error(
    'No se pudo abrir el navegador. Si ya hay una ventana de sesión abierta, ' +
      'cerrala antes de actualizar. ' +
      fallos.join(' | '),
  )
  error.codigo = 'navegador'
  throw error
}

async function conNavegador(tarea) {
  const context = await lanzarContexto(false)
  try {
    return await tarea(context)
  } finally {
    await context.close().catch(() => undefined)
  }
}

async function abrirPortal(context) {
  const page = context.pages()[0] || (await context.newPage())
  try {
    await page.goto(`${sitio.base}${PAGINA_INICIO}`, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    })
  } catch (exc) {
    log('la navegación inicial no terminó:', String(exc.message || exc))
  }
  return page
}

function paginaAbierta(page) {
  try {
    return !page.isClosed()
  } catch {
    return false
  }
}

/**
 * Consulta la API desde el propio origen del portal. Devuelve un objeto
 * normalizado: { estado: 'ok'|'desafio'|'error', ... }.
 */
async function consultarApi(page, consulta, pagina, pageSize = 100) {
  const url = `${sitio.base}${API}?pageSize=${pageSize}&page=${pagina}&sort=RELEVANTES`
  try {
    const r = await page.evaluate(
      async ({ urlApi, siteHeader, query }) => {
        try {
          const respuesta = await fetch(urlApi, {
            method: 'POST',
            credentials: 'include',
            headers: {
              'Content-Type': 'application/json',
              Accept: 'application/json, text/plain, */*',
              'x-site-id': siteHeader,
            },
            body: JSON.stringify({
              filtros: [],
              query,
              internacional: false,
            }),
          })
          const texto = await respuesta.text()
          let datos = null
          try {
            datos = JSON.parse(texto)
          } catch {
            /* puede ser un desafío HTML */
          }
          return {
            status: respuesta.status,
            tipo: respuesta.headers.get('content-type') || '',
            datos,
            muestra: datos ? null : texto.slice(0, 300),
          }
        } catch (exc) {
          return { status: 0, error: String(exc) }
        }
      },
      { urlApi: url, siteHeader: sitio.siteId, query: consulta },
    )

    if (r.status === 200 && r.datos && Array.isArray(r.datos.content)) {
      return { estado: 'ok', datos: r.datos }
    }
    if (
      r.status === 403 ||
      r.status === 503 ||
      (r.status === 200 && !r.datos)
    ) {
      return {
        estado: 'desafio',
        detalle: `HTTP ${r.status} ${r.tipo}`.trim(),
      }
    }
    return {
      estado: 'error',
      detalle: `HTTP ${r.status || 'sin respuesta'} ${r.muestra || r.error || ''}`.trim(),
    }
  } catch (exc) {
    return { estado: 'error', detalle: String(exc.message || exc) }
  }
}

/**
 * Espera a que la sesión esté validada. Si el portal pide verificación,
 * la ventana ya está abierta: la persona debe resolverla manualmente.
 */
async function esperarSesion(page, segundos) {
  marcar(false, 'esperando verificación manual en la ventana del portal')
  const limite = Date.now() + segundos * 1000
  while (true) {
    if (!paginaAbierta(page)) {
      return { estado: 'desafio', detalle: 'ventana cerrada' }
    }
    const r = await consultarApi(page, '', 0, 1)
    if (r.estado === 'ok') {
      marcar(true)
      return r
    }
    if (r.estado === 'error') {
      return r
    }
    if (Date.now() >= limite) {
      marcar(false, r.detalle)
      return r
    }
    log('esperando verificación manual en la ventana del portal…')
    await esperar(4000)
  }
}

async function comandoFetch() {
  if (!sitio) salir({ ok: false, error: 'sitio_desconocido' }, 2)
  if (consultas.length === 0) salir({ ok: false, error: 'sin_consultas' }, 2)

  log(`abriendo sesión para ${sitio.nombre}`)
  const resultado = await conNavegador(async (context) => {
    const page = await abrirPortal(context)
    await esperar(2000)

    let chequeo = await consultarApi(page, '', 0, 1)
    if (chequeo.estado === 'error') {
      return {
        codigo: 1,
        datos: {
          ok: false,
          error: 'consulta_fallida',
          detalle: chequeo.detalle,
        },
      }
    }
    if (chequeo.estado !== 'ok') {
      log('el portal pidió verificación; esperando resolución manual')
      chequeo = await esperarSesion(page, esperaSesion)
      if (chequeo.estado !== 'ok') {
        if (chequeo.estado === 'error') {
          return {
            codigo: 1,
            datos: {
              ok: false,
              error: 'consulta_fallida',
              detalle: chequeo.detalle,
            },
          }
        }
        return {
          codigo: 3,
          datos: {
            ok: false,
            error: 'sesion_requerida',
            detalle:
              chequeo.detalle ||
              'Cloudflare pidió verificación y no se resolvió a tiempo.',
          },
        }
      }
    }

    const resultados = {}
    let total = 0
    for (const consulta of consultas) {
      const items = []
      for (let pagina = 0; pagina < maxPaginas; pagina += 1) {
        const r = await consultarApi(page, consulta, pagina)
        if (r.estado !== 'ok') {
          if (r.estado === 'desafio') {
            marcar(false, r.detalle)
            return {
              codigo: 3,
              datos: {
                ok: false,
                error: 'sesion_requerida',
                detalle:
                  r.detalle || 'La sesión se venció durante la consulta.',
              },
            }
          }
          return {
            codigo: 1,
            datos: {
              ok: false,
              error: 'consulta_fallida',
              detalle: `${consulta}: ${r.detalle}`,
            },
          }
        }
        const contenido = r.datos.content || []
        items.push(...contenido)
        if (contenido.length < 100) break
        await esperar(1200)
      }
      resultados[consulta] = items
      total += items.length
      log(`${consulta}: ${items.length} avisos`)
      await esperar(700)
    }

    marcar(true)
    return { codigo: 0, datos: { ok: true, site: siteId, total, resultados } }
  })

  salir(resultado.datos, resultado.codigo)
}

async function comandoOpen() {
  if (!sitio) salir({ ok: false, error: 'sitio_desconocido' }, 2)
  log(`abriendo ventana de sesión para ${sitio.nombre}`)

  const resultado = await conNavegador(async (context) => {
    const page = await abrirPortal(context)
    marcar(false, 'ventana abierta; esperando verificación manual')

    let valido = false
    while (paginaAbierta(page)) {
      const r = await consultarApi(page, '', 0, 1)
      if (r.estado === 'ok') {
        if (!valido) log('sesión validada')
        valido = true
        marcar(true)
      } else if (r.estado === 'desafio') {
        if (valido) log('la sesión dejó de ser válida')
        valido = false
        marcar(false, r.detalle)
      }
      await esperar(4000)
    }
    marcar(valido)
    return { codigo: 0, datos: { ok: true, site: siteId, valid: valido } }
  })

  salir(resultado.datos, resultado.codigo)
}

async function comandoStatus() {
  if (!sitio) salir({ ok: false, error: 'sitio_desconocido' }, 2)

  const resultado = await conNavegador(async (context) => {
    const page = await abrirPortal(context)
    await esperar(1500)
    const r = await consultarApi(page, '', 0, 1)
    const valido = r.estado === 'ok'
    marcar(valido, r.detalle || null)
    return {
      codigo: 0,
      datos: { ok: true, site: siteId, valid: valido, detalle: r.detalle || null },
    }
  })

  salir(resultado.datos, resultado.codigo)
}

process.on('unhandledRejection', (exc) => {
  log('error no controlado:', String(exc))
  salir({ ok: false, error: 'interno', detalle: String(exc) }, 1)
})

try {
  if (comando === 'open') await comandoOpen()
  else if (comando === 'fetch') await comandoFetch()
  else if (comando === 'status') await comandoStatus()
  else
    salir(
      {
        ok: false,
        error: 'comando_desconocido',
        uso: 'node navent.mjs open|fetch|status --site zonajobs|bumeran',
      },
      2,
    )
} catch (exc) {
  log('error:', String(exc.message || exc))
  salir(
    {
      ok: false,
      error: exc.codigo || 'interno',
      detalle: String(exc.message || exc),
    },
    1,
  )
}
