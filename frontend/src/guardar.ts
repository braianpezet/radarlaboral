type Escritura = {
  write: (datos: Blob) => Promise<void>
  close: () => Promise<void>
}

type ArchivoHandle = {
  createWritable: () => Promise<Escritura>
}

type SelectorGuardado = (opciones: {
  suggestedName?: string
  types?: Array<{ description?: string; accept: Record<string, string[]> }>
}) => Promise<ArchivoHandle>

type VentanaConGuardado = Window & {
  showSaveFilePicker?: SelectorGuardado
}

/**
 * Abre primero el diálogo nativo de Windows (lo hace el backend) y, si no está
 * disponible, usa el selector del navegador o una descarga directa.
 */
export async function guardarComo(
  nombre: string,
  tipo: string,
  extension: string,
  descripcion: string,
  contenido: () => Promise<Blob>,
): Promise<'guardado' | 'cancelado' | 'descargado'> {
  const blob = await contenido()

  const nativo = await intentarGuardadoNativo(nombre, extension, blob)
  if (nativo) return nativo

  const selector = (window as VentanaConGuardado).showSaveFilePicker?.bind(window)
  if (!selector) {
    descargarBlob(blob, nombre)
    return 'descargado'
  }

  let handle: ArchivoHandle
  try {
    handle = await selector({
      suggestedName: nombre,
      types: [{ description: descripcion, accept: { [tipo]: [`.${extension}`] } }],
    })
  } catch (error) {
    if ((error as DOMException)?.name === 'AbortError') return 'cancelado'
    descargarBlob(blob, nombre)
    return 'descargado'
  }

  const escritura = await handle.createWritable()
  await escritura.write(blob)
  await escritura.close()
  return 'guardado'
}

async function intentarGuardadoNativo(
  nombre: string,
  extension: string,
  blob: Blob,
): Promise<'guardado' | 'cancelado' | null> {
  const consulta = new URLSearchParams({ nombre, extension })
  let respuesta: Response
  try {
    respuesta = await fetch(`/api/guardar-como?${consulta.toString()}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: blob,
    })
  } catch {
    return null
  }

  if (respuesta.status === 404 || respuesta.status === 405) return null
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

  const resultado = (await respuesta.json()) as {
    guardado?: boolean
    cancelado?: boolean
  }
  if (resultado.cancelado) return 'cancelado'
  return resultado.guardado ? 'guardado' : null
}

function descargarBlob(blob: Blob, nombre: string) {
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  enlace.click()
  URL.revokeObjectURL(url)
}

/** Limpia el nombre elegido para que el diálogo del sistema lo acepte. */
export function nombreSeguro(valor: string, alternativo: string): string {
  const limpio = (valor || '')
    .replace(/\.docx$/i, '')
    .replace(/[\\/:*?"<>|\x00-\x1f]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/^[ .]+|[ .]+$/g, '')
    .slice(0, 100)
  return limpio || alternativo
}
