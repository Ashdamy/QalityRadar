# Mapeo a ISO/IEC 25010

> El spec exige documentar cómo cada métrica se relaciona con la norma y aclarar que esto es una aproximación, no una certificación. Este documento cumple esa obligación.

## Advertencia previa, y va en serio

**ISO/IEC 25010 no define un algoritmo de puntuación.** La norma describe un *modelo de calidad*: un vocabulario de características y sub-características para razonar sobre la calidad de un producto software. No dice cuántos puntos vale un README, ni qué proporción de tests es aceptable.

Por tanto:

- Las rúbricas de este proyecto son **criterio nuestro**, no de la norma. Están todas en un solo archivo ([`backend/app/services/scoring_service.py`](../backend/app/services/scoring_service.py)) precisamente para que se puedan leer, discutir y ajustar.
- Una puntuación alta aquí **no acredita conformidad con ISO/IEC 25010**, ni sustituye una evaluación formal según ISO/IEC 25040.
- Medimos lo que se puede observar leyendo un repositorio. Muchas sub-características de la norma (rendimiento, usabilidad, compatibilidad) requieren ejecutar el software, y para eso está el modo de análisis de URL.

## Las 8 características de la norma y qué cubrimos

| Característica ISO | ¿La cubrimos? | Dónde |
|---|---|---|
| Adecuación funcional | ✅ Parcial | Análisis de repositorio |
| Eficiencia de desempeño | ✅ Parcial | Análisis de URL |
| Compatibilidad | ✅ Parcial | Análisis de URL |
| Usabilidad | ✅ Parcial | Análisis de URL |
| Fiabilidad | ✅ Parcial | Análisis de repositorio |
| Seguridad | ✅ Parcial | Análisis de repositorio + URL |
| Mantenibilidad | ✅ Parcial | Análisis de repositorio |
| Portabilidad | ✅ Parcial | Análisis de repositorio |

**Nota honesta sobre "Actividad del proyecto":** el spec incluye esta dimensión con un peso del 15%, pero **no es una característica de ISO/IEC 25010**. Es un añadido nuestro, útil para juzgar si un proyecto está vivo y mantenido. Lo señalamos para no dar a entender que forma parte de la norma.

---

## Adecuación funcional (peso 15%)

*¿El producto hace lo que necesita, y se puede saber qué hace?*

| Sub-característica ISO | Qué observamos | Puntos |
|---|---|---|
| **Pertinencia funcional** | Existe README | 8 |
| | Extensión del README (por tramos) | hasta 14 |
| | Incluye instrucciones de instalación | 12 |
| | Incluye sección de uso | 10 |
| | Incluye ejemplos de código | 8 |
| | Hay un directorio de ejemplos | 8 |
| **Gobernanza del proyecto** | LICENSE | 10 |
| | CONTRIBUTING | 4 |
| | CHANGELOG | 3 |
| | Documentación de arquitectura | 3 |
| | Documentación de API (OpenAPI/Swagger) | 2 |
| **Completitud funcional** | Sin funciones declaradas y no implementadas | 10 |
| | Pocas marcas TODO/FIXME por archivo | hasta 8 |

*Limitación conocida:* no podemos verificar la **corrección funcional** (que el software haga lo correcto) sin ejecutarlo. Los tests son una prueba indirecta y se puntúan bajo fiabilidad.

## Fiabilidad (peso 20%)

*¿Se comporta como debe, durante el tiempo que debe, y se recupera de los fallos?*

| Sub-característica ISO | Qué observamos | Puntos |
|---|---|---|
| **Madurez** | Existen tests | 12 |
| | Proporción de tests frente a código (por tramos) | hasta 21 |
| | Hay tests de integración | 12 |
| | Hay tests end-to-end | 10 |
| **Tolerancia a fallos** | Proporción de archivos con manejo de errores | hasta 14 |
| | Ningún bloque descarta errores en silencio | 8 |
| | Ninguna captura de excepción sin tipo | 4 |
| | Se usan timeouts | 2 |
| | Se usan reintentos | 2 |
| **Recuperabilidad** | Proporción de archivos con logging | hasta 10 |
| | Hay migraciones de base de datos (cambios reversibles) | 5 |

*Limitación conocida:* la **disponibilidad** solo se puede medir sobre un sistema en ejecución.

## Mantenibilidad (peso 20%)

*¿Se puede entender, modificar y probar sin romperlo?*

| Sub-característica ISO | Qué observamos | Puntos |
|---|---|---|
| **Modularidad** | Media de líneas por archivo (por tramos) | hasta 12 |
| | Tamaño del archivo más grande | hasta 10 |
| | Media de líneas por función | hasta 8 |
| | Estructura real de carpetas | 5 |
| | Forma del proyecto identificable | 3 |
| **Analizabilidad** | Proporción de comentarios | hasta 11 |
| | Proporción de funciones documentadas | hasta 9 |
| | Profundidad máxima de anidamiento | hasta 10 |
| **Modificabilidad** | Configuración de linter o formateador | 10 |
| | `.gitignore` | 5 |
| | Manifiesto de dependencias | 5 |
| | Proporción de anotaciones de tipo | hasta 8 |
| | Sin archivos duplicados | 4 |

*Limitación conocida:* la **reusabilidad** y la **testabilidad** se aproximan indirectamente; medir acoplamiento real requeriría análisis de grafo de dependencias, previsto para más adelante.

## Seguridad (peso 20%)

*¿Protege la información y resiste el uso indebido?*

| Sub-característica ISO | Qué observamos | Puntos |
|---|---|---|
| **Confidencialidad** | Sin archivos de credenciales versionados | 25 |
| | Sin credenciales escritas en el código | 20 |
| | `.gitignore` protege los `.env` | 10 |
| **Integridad** | Sin ejecución de código dinámico (`eval`, `exec`) | 18 |
| | Sin SQL construido por concatenación | 17 |
| | Dependencias fijadas con lockfile | 10 |

*Cobertura parcial declarada:* Gitleaks y Semgrep, que analizan el historial completo y aplican cientos de reglas, llegan en la Semana 2B. Lo actual detecta lo evidente y es deliberadamente conservador para no llenar el informe de falsos positivos. Las sub-características de **no repudio**, **responsabilidad** y **autenticidad** no se cubren todavía.

## Portabilidad (peso 10%)

*¿Se puede llevar a otro entorno?*

| Sub-característica ISO | Qué observamos | Puntos |
|---|---|---|
| **Instalabilidad** | Definición de contenedor (Dockerfile) | 25 |
| | Lockfile de dependencias | 25 |
| **Adaptabilidad** | Configuración leída del entorno | 20 |
| | Hay un `.env.example` | 12 |
| | Sin rutas absolutas de una máquina concreta | 10 |
| | Infraestructura como código | 8 |

*Limitación conocida:* la **reemplazabilidad** requeriría analizar el acoplamiento a proveedores concretos, aún no implementado.

---

## Riesgos críticos que bloquean puntuaciones altas

El spec pide que *"los riesgos críticos bloqueen puntuaciones altas"*. Implementado así:

| Gravedad máxima encontrada | Techo de la nota global |
|---|---|
| Crítica | 40/100 |
| Alta | 70/100 |
| Media o inferior | Sin techo |

Un proyecto con credenciales expuestas no puede sacar buena nota por muy bien documentado que esté.

## Cómo se combina todo

```
nota_dimensión   = suma de puntos ganados en su rúbrica (0-100)
nota_global      = Σ(peso_i × nota_i) / Σ(pesos de las dimensiones medidas)
nota_global      = min(nota_global, techo por riesgo crítico)
```

La normalización sobre las dimensiones **realmente medidas** evita penalizar a un proyecto por características que este análisis todavía no cubre. Cuando entren los analizadores restantes, el denominador crecerá.

## Principio de diseño: los puntos se ganan

Cada dimensión parte de **cero**. Nunca se acredita calidad que no se haya comprobado:

- Una dimensión sin rúbrica todavía puntúa 0, no 100.
- La *ausencia* de un problema solo suma si de verdad se escanearon archivos. "No tiene credenciales expuestas" sin haber leído ningún archivo no es un mérito, es desconocimiento.

Esto corrige el modelo original, que restaba penalizaciones desde 100 y por tanto premiaba la ausencia de evidencia: un repositorio con un solo archivo y sin nada más sacaba 87/100.


---

# Análisis de URL (Modo 2)

Cinco dimensiones con los pesos del spec. **84 señales medidas** sobre el HTML
y las cabeceras HTTP, sin ejecutar un navegador.

## Rendimiento — 25%

| Sub-característica ISO | Qué observamos |
|---|---|
| **Comportamiento temporal** | Tiempo de respuesta del servidor, por tramos |
| **Uso de recursos** | Compresión, `Cache-Control`, `ETag`, redirecciones, peso del HTML |
| | Scripts que bloquean el dibujado (sin `defer`/`async` en la cabecera) |
| | Hojas de estilo bloqueantes, dominios de terceros |
| | Imágenes sin carga diferida y sin dimensiones declaradas |

*Limitación declarada:* se mide la respuesta del servidor y cómo está construida la página, **no el renderizado**. El tiempo hasta que la página es usable requiere Lighthouse.

## Seguridad — 25%

| Sub-característica ISO | Qué observamos |
|---|---|
| **Confidencialidad** | HTTPS, HSTS (duración y subdominios) |
| | Cookies: `HttpOnly`, `Secure`, `SameSite` |
| **Integridad** | CSP: presencia, modo informe, `unsafe-inline`, `unsafe-eval`, directivas clave |
| | Contenido mixto, integridad de scripts externos (SRI) |
| **Resistencia** | `X-Frame-Options`/`frame-ancestors`, `nosniff`, `Referrer-Policy` |
| | `Permissions-Policy`, COOP/CORP, CORS restrictivo |
| | Formularios que envían por HTTP, filtración de versión del servidor |

## Usabilidad — 20%

| Sub-característica ISO | Qué observamos |
|---|---|
| **Reconocibilidad** | Título y su longitud, meta descripción, favicon, Open Graph, canonical |
| **Facilidad de uso** | Región `main`, HTML semántico, navegación, `theme-color` |

*Limitación declarada:* la operabilidad real requiere interacción; aquí solo se juzga cómo se presenta e identifica la página.

## Accesibilidad — 15%

| Sub-característica ISO | Qué observamos |
|---|---|
| **Percepción** | Idioma declarado, **zoom no bloqueado**, texto alternativo |
| | Tablas con cabeceras, ausencia de reproducción automática |
| **Operabilidad** | Etiquetas de formulario, `tabindex` positivo, títulos de iframe |
| | Texto de enlace descriptivo |
| **Estructura** | Un solo `h1`, jerarquía sin saltos, HTML semántico, `main`, ids únicos |

*Limitación declarada:* son comprobaciones estáticas del HTML. **No sustituyen a axe-core**: el contraste de color efectivo y el árbol de accesibilidad final solo se pueden evaluar con renderizado real.

## Compatibilidad — 15%

| Sub-característica ISO | Qué observamos |
|---|---|
| **Adaptabilidad** | Etiqueta viewport, imágenes responsivas (`srcset`/`picture`) |
| **Interoperabilidad** | `<!DOCTYPE html>`, codificación declarada, idioma del contenido |
| | Ausencia de etiquetas HTML obsoletas, manifiesto web |
