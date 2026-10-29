# Mapeo a ISO/IEC 25010:2023

> El spec exige documentar cómo cada métrica se relaciona con la norma y aclarar que esto es una aproximación, no una certificación. Este documento cumple esa obligación.

## Advertencia previa, y va en serio

**ISO/IEC 25010 no define un algoritmo de puntuación.** La norma describe un *modelo de calidad*: un vocabulario de características y sub-características para razonar sobre la calidad de un producto software. No dice cuántos puntos vale un README, ni qué proporción de tests es aceptable.

Por tanto:

- Las rúbricas de este proyecto son **criterio nuestro**, no de la norma. Están todas en un solo archivo ([`backend/app/services/scoring_service.py`](../backend/app/services/scoring_service.py)) precisamente para que se puedan leer, discutir y ajustar.
- Una puntuación alta aquí **no acredita conformidad con ISO/IEC 25010**, ni sustituye una evaluación formal según ISO/IEC 25040.
- Medimos lo que se puede observar leyendo un repositorio. Muchas subcaracterísticas de la norma (eficiencia de desempeño, capacidad de interacción, compatibilidad) requieren ejecutar el software, y para eso está el modo de análisis de URL.

## Las 9 características de ISO/IEC 25010:2023 y qué cubrimos

El modelo es el de la **revisión de 2023**. Frente a la de 2011 tiene nueve características en vez de ocho: renombra dos, añade una y reorganiza algunas subcaracterísticas.

| Característica (2023) | Antes (2011) | ¿La cubrimos? | Dónde | Clave interna |
|---|---|---|---|---|
| Adecuación funcional | igual | ✅ Parcial | Repositorio | `functional_suitability` |
| Eficiencia de desempeño | igual | ✅ Parcial | URL | `performance` |
| Compatibilidad | igual | ✅ Parcial | URL | `compatibility` |
| **Capacidad de interacción** | Usabilidad | ✅ Parcial | URL | `usability` (+ `accessibility`) |
| Fiabilidad | igual | ✅ Parcial | Repositorio | `reliability` |
| Seguridad | igual | ✅ Parcial | Repositorio + URL | `security` |
| Mantenibilidad | igual | ✅ Parcial | Repositorio | `maintainability` |
| **Flexibilidad** | Portabilidad | ✅ Parcial | Repositorio | `portability` |
| **Protección** (*safety*) | — (nueva) | ❌ **Sin medir** | — | `safety` |

### Por qué las claves internas no se renombran

`usability` y `portability` siguen siendo las claves internas aunque la etiqueta sea "Capacidad de interacción" y "Flexibilidad". Se evaluó renombrarlas y **no compensa**:

- El nombre de cada dimensión está guardado como texto en cada análisis ya hecho (`dimensions.name`), en las comparaciones entre análisis y en los `raw_data`. Renombrar exige migrar todo el histórico; si la migración se quedara a medias, un proyecto compararía "portability" con "flexibility" y vería una dimensión desaparecer y otra aparecer de la nada.
- `usability` es además un valor del enum de Postgres `finding_type`, y quitar un valor de un enum en Postgres obliga a recrear el tipo.
- El modo combinado guarda las dimensiones como `codigo:portability`, `produccion:usability`.

Cambiar la etiqueta da al usuario exactamente lo mismo sin tocar un solo dato. Las etiquetas viven en un único sitio por lado: [`backend/app/services/iso25010.py`](../backend/app/services/iso25010.py) y [`frontend/src/lib/dimensiones.ts`](../frontend/src/lib/dimensiones.ts). Antes había tres copias en cada lado y se desfasaban entre sí.

### Accesibilidad en 2023

La norma de 2023 deja de tener una subcaracterística llamada "accesibilidad": lo cubre la **inclusividad** (y en parte la **asistencia al usuario**), dentro de la capacidad de interacción. El modo URL la sigue midiendo como eje propio, con la etiqueta "Accesibilidad (inclusividad)", porque se comprueba con pruebas distintas y tiene su propio peso.

### Protección (safety), sin medir

Es la característica nueva de 2023: que el sistema no ponga en peligro a personas, bienes o el entorno (restricción operativa, identificación de riesgos, comportamiento a prueba de fallos, avisos de peligro, integración segura). No se puede juzgar leyendo un repositorio ni una página web, así que **no se mide**. Aparece en el radar, en el informe y en el PDF como "sin medir" y queda **fuera del denominador**: ni resta (darle 0 castigaría lo que no se comprobó) ni suma (darle 100 lo regalaría).

### La actividad del proyecto: aparte, fuera de la nota

El spec incluía "Actividad del proyecto" como sexta dimensión con un 15% de la nota global. **No es una característica de ISO/IEC 25010**: puntúa la frescura de los commits, que el repositorio tenga descripción y temas, y las **estrellas y forks**. Son señales de que un proyecto está vivo y tiene ojos encima, no de su calidad. Con ella dentro, un repositorio popular sacaba nota por ser popular.

Desde ahora:

- **Se sigue calculando** y se enseña como **"Indicador de salud del proyecto (no forma parte de ISO/IEC 25010)"**, fuera del radar, de la lista de características y de la nota global. En el PDF tiene su propia sección.
- **No pesa.** Se guarda como dimensión con peso 0, y los cinco pesos restantes se **renormalizan** sobre 0,85 para que sumen 1,0 conservando su proporción:

  | Característica | Peso del spec | Peso actual |
  |---|---|---|
  | Adecuación funcional | 15% | 17,6% |
  | Fiabilidad | 20% | 23,5% |
  | Seguridad | 20% | 23,5% |
  | Mantenibilidad | 20% | 23,5% |
  | Flexibilidad | 10% | 11,8% |

- **El modo combinado** pondera cada lado por cuántas características ISO mide. Antes el repositorio contaba seis y pesaba más que la URL; ahora son cinco y cinco, y pesan lo mismo.
- **El resumen de IA tampoco la menciona**: si no, "lo más sólido" de casi cualquier proyecto popular serían sus estrellas.

**Recalibración**, con análisis reales hechos con el motor actual (las métricas están en [`tests/fixtures/calibracion_2026_10.json`](../backend/tests/fixtures/calibracion_2026_10.json) y las notas fijadas en [`tests/test_salud_del_proyecto.py`](../backend/tests/test_salud_del_proyecto.py)):

| Proyecto | Con actividad | Sin actividad | Su actividad |
|---|---|---|---|
| axios/axios | 68,8 | **63,3** | 100 |
| pallets/flask | 64,0 | **57,6** | 100 |
| octocat/Hello-World (vacío) | 7,4 | **2,1** | 37 |

Bajan las tres, y es lo esperado: las tres tenían la actividad por encima de su media, y Hello-World, un repositorio sin código, sacaba 5 de sus 7 puntos por sus estrellas. La escala sigue discriminando: las referencias por encima de 55, el repositorio vacío por debajo de 5.

**Los análisis ya guardados** se recalculan con la fórmula nueva (migración `0023`, reversible), junto con las diferencias guardadas en las comparaciones. Sin eso, el primer análisis después del cambio "bajaría" respecto al anterior sin que el código hubiera cambiado: el aviso de caída de nota saltaría en falso y la gráfica de evolución tendría un escalón sin significado. Los **análisis combinados** ya guardados conservan su nota, porque su explicación de la discrepancia cita las notas en prosa y reescribirla sería inventarla.

---

## Desglose por subcaracterística

Cada dimensión se guarda con su desglose: cuántos puntos sacó en cada subcaracterística y de cuántos posibles. La suma del desglose es exactamente la nota de la dimensión. Se ve en el panel (pulsando cada dimensión), en el informe compartido y en el PDF.

Tres tipos de fila:

- **Subcaracterística medida**: puntos ganados / máximo.
- **Grupo que no es de la norma** (marcado "no es ISO"): suma puntos porque mide algo útil —la gobernanza del proyecto, el CI/CD—, pero ISO/IEC 25010 no lo recoge y no se le hace pasar por lo que no es.
- **Subcaracterística sin medir**: la norma la define y aquí no se comprueba. Se lista para que se vea el hueco, **sin puntos**: un 0 diría "se miró y está mal", y la verdad es "no se miró".

**Dónde se guarda:** en una columna JSONB propia, `dimensions.subcharacteristics` (migración `0022`), y no dentro de `raw_metrics`. `raw_metrics` es lo que midieron los analizadores, la *entrada* de la puntuación, y además se copia a `analyses.raw_data`, que lee la comprobación de correspondencia del modo combinado. El desglose es el *resultado*; mezclarlos haría que una clave calculada pudiera tomarse por una medida. Los análisis anteriores a la migración no tienen desglose y no se recalcula hacia atrás: sus métricas se puntuaron con rúbricas que pudieron cambiar, y un desglose que no cuadrase con la nota guardada sería peor que ninguno.

**El desglose no cambió ninguna nota.** Se comprobó puntuando 11.000 combinaciones aleatorias de métricas antes y después del cambio (cero diferencias) y se fija con los análisis reales de calibración en [`tests/test_subcaracteristicas.py`](../backend/tests/test_subcaracteristicas.py).

---

## Adecuación funcional (peso 17,6%)

*¿El producto hace lo que necesita, y se puede saber qué hace?*

| Subcaracterística (2023) | Qué observamos | Puntos |
|---|---|---|
| **Pertinencia funcional** (60) | Existe README | 8 |
| | Extensión del README (por tramos) | hasta 14 |
| | Incluye instrucciones de instalación | 12 |
| | Incluye sección de uso | 10 |
| | Incluye ejemplos de código | 8 |
| | Hay un directorio de ejemplos | 8 |
| **Completitud funcional** (18) | Sin funciones declaradas y no implementadas | 10 |
| | Pocas marcas TODO/FIXME por archivo | hasta 8 |
| **Gobernanza del proyecto** (22) · *no es ISO* | LICENSE | 10 |
| | CONTRIBUTING | 4 |
| | CHANGELOG | 3 |
| | Documentación de arquitectura | 3 |
| | Documentación de API (OpenAPI/Swagger) | 2 |
| **Corrección funcional** | — | *sin medir* |

La completitud solo puntúa si de verdad se escaneó código. La **corrección funcional** (que el software haga lo correcto) no se puede verificar sin ejecutarlo; los tests son una prueba indirecta y se puntúan en fiabilidad.

## Fiabilidad (peso 23,5%)

*¿Se comporta como debe, durante el tiempo que debe, y se recupera de los fallos?*

| Subcaracterística (2023) | Qué observamos | Puntos |
|---|---|---|
| **Ausencia de fallos** (55) · *la "madurez" de 2011* | Existen tests | 12 |
| | Proporción de tests frente a código (por tramos) | hasta 21 |
| | Hay tests de integración | 12 |
| | Hay tests end-to-end | 10 |
| **Tolerancia a fallos** (30) | Proporción de archivos con manejo de errores | hasta 14 |
| | Ningún bloque descarta errores en silencio | 8 |
| | Ninguna captura de excepción sin tipo | 4 |
| | Se usan timeouts | 2 |
| | Se usan reintentos | 2 |
| **Recuperabilidad** (15) | Proporción de archivos con logging | hasta 10 |
| | Hay migraciones de base de datos (cambios reversibles) | 5 |
| **Disponibilidad** | — | *sin medir* |

La **disponibilidad** solo se puede medir sobre un sistema en ejecución.

## Mantenibilidad (peso 23,5%)

*¿Se puede entender, modificar y probar sin romperlo?*

| Subcaracterística (2023) | Qué observamos | Puntos |
|---|---|---|
| **Modularidad** (38) | Media de líneas por archivo (por tramos) | hasta 12 |
| | Tamaño del archivo más grande | hasta 10 |
| | Media de líneas por función | hasta 8 |
| | Estructura real de carpetas | 5 |
| | Forma del proyecto identificable | 3 |
| **Analizabilidad** (30) | Proporción de comentarios | hasta 11 |
| | Proporción de funciones documentadas | hasta 9 |
| | Profundidad máxima de anidamiento | hasta 10 |
| **Modificabilidad** (32) | Configuración de linter o formateador | 10 |
| | `.gitignore` | 5 |
| | Manifiesto de dependencias | 5 |
| | Proporción de anotaciones de tipo | hasta 8 |
| | Sin archivos duplicados | 4 |
| **Reusabilidad** | — | *sin medir* |
| **Capacidad de prueba** | — | *sin medir* |

Medir la reusabilidad exigiría un grafo de dependencias entre módulos; la capacidad de prueba, analizar el acoplamiento del código con lo que lo rodea.

## Seguridad (peso 23,5%)

*¿Protege la información y resiste el uso indebido?*

| Subcaracterística (2023) | Qué observamos | Puntos |
|---|---|---|
| **Confidencialidad** (50) | Sin archivos de credenciales versionados | 14 |
| | Sin credenciales escritas en el código | 10 |
| | `.gitignore` protege los `.env` | 6 |
| | Gitleaks no encuentra secretos (solo si llegó a ejecutarse) | 20 |
| **Integridad** (50) | Sin ejecución de código dinámico (`eval`, `exec`) | 12 |
| | Sin SQL construido por concatenación | 12 |
| | Dependencias fijadas con lockfile | 8 |
| | Ninguna dependencia con vulnerabilidad conocida en OSV (solo si se consultó) | 18 |
| **No repudio**, **Responsabilidad**, **Autenticidad** | — | *sin medir* |
| **Resistencia** (nueva en 2023) | — | *sin medir* en el repositorio |

Lo que un escáner no llega a ejecutar no acredita nada: si Gitleaks falla o la consulta a OSV no responde, esos puntos no se dan. La **resistencia** sí se mide en el modo URL, sobre la aplicación desplegada.

## Flexibilidad (antes portabilidad, peso 11,8%)

*¿Se puede llevar a otro entorno y crecer?*

| Subcaracterística (2023) | Qué observamos | Puntos |
|---|---|---|
| **Instalabilidad** (50) | Definición de contenedor (Dockerfile) | 25 |
| | Lockfile de dependencias | 25 |
| **Adaptabilidad** (30) | Configuración leída del entorno | 12 |
| | Hay un `.env.example` | 8 |
| | Sin rutas absolutas de una máquina concreta | 6 |
| | Infraestructura como código | 4 |
| **Automatización (CI/CD)** (20) · *no es ISO* | Hay integración continua | 8 |
| | El CI ejecuta las pruebas | 7 |
| | El CI ejecuta el linter | 3 |
| | Hay una etapa de despliegue | 2 |
| **Escalabilidad** (nueva en 2023) | — | *sin medir* |
| **Reemplazabilidad** | — | *sin medir* |

La **escalabilidad** solo se puede observar con el sistema bajo carga; la **reemplazabilidad**, analizando el acoplamiento a proveedores concretos.

---

## Referencia por lenguaje (benchmark), simulada

`GET /api/repositories/{id}/benchmark` compara las notas del último análisis de repositorio completado con una referencia según su lenguaje principal (el que detecta el analizador de estructura). Se ve en la página de evolución del repositorio y bajo el resultado de cada análisis.

**Los valores de referencia son simulados.** La tabla `benchmark_data` tiene nueve valores de ejemplo (mantenibilidad, seguridad y fiabilidad para Python, JavaScript y TypeScript), sembrados en la migración `0009` con `is_simulated = true`. No son medias de proyectos reales: para calcularlas hacen falta muchos más análisis. Por eso:

- La API devuelve `is_simulated` en cada respuesta, y mientras sea verdadero el frontend muestra **"Referencia simulada, no son datos reales"** junto al título, no en letra pequeña.
- Si no hay análisis, no se detectó lenguaje o el lenguaje no tiene referencia, la API responde **204** y el frontend no muestra nada: mejor nada que comparar contra una referencia que no existe.
- Solo se comparan las dimensiones que tienen referencia; el resto no aparece.

Cuando haya datos reales basta con cargarlos con `is_simulated = false`: la etiqueta desaparece sola.

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
nota_global      = Σ(peso_i × nota_i) / Σ(pesos de las características ISO medidas)
nota_global      = min(nota_global, techo por riesgo crítico)
```

La normalización sobre las características **realmente medidas** evita penalizar a un proyecto por lo que este análisis todavía no cubre. Quedan fuera del denominador la **protección** (sin medir) y el **indicador de salud** (no es ISO). Cuando entren los analizadores restantes, el denominador crecerá.

## Principio de diseño: los puntos se ganan

Cada dimensión parte de **cero**. Nunca se acredita calidad que no se haya comprobado:

- Una dimensión que se analizó y no aportó evidencia puntúa 0, no 100: un repositorio sin código no tiene mantenibilidad que acreditar.
- Lo que **no se mide** no puntúa ni 0 ni 100: se **excluye** de la nota y se marca "sin medir". Así se tratan la protección y las subcaracterísticas que la norma define y aquí no se comprueban. La diferencia con el punto anterior es que ahí sí se miró.
- La *ausencia* de un problema solo suma si de verdad se escanearon archivos. "No tiene credenciales expuestas" sin haber leído ningún archivo no es un mérito, es desconocimiento.

Esto corrige el modelo original, que restaba penalizaciones desde 100 y por tanto premiaba la ausencia de evidencia: un repositorio con un solo archivo y sin nada más sacaba 87/100.


---

# Análisis de URL (Modo 2)

Cinco dimensiones con los pesos del spec. **84 señales medidas** sobre el HTML
y las cabeceras HTTP, sin ejecutar un navegador.

## Eficiencia de desempeño — 25%

| Subcaracterística (2023) | Qué observamos | Puntos |
|---|---|---|
| **Comportamiento temporal** | Tiempo de respuesta del servidor, por tramos | 34 |
| **Utilización de recursos** | Compresión, `Cache-Control`, `ETag`, redirecciones | 28 |
| | Scripts y hojas de estilo que bloquean el dibujado, dominios de terceros, peso del HTML | 31 |
| | Imágenes sin carga diferida y sin dimensiones declaradas | 7 |
| **Capacidad** | — | *sin medir* |

*Limitación declarada:* se mide la respuesta del servidor y cómo está construida la página, **no el renderizado**. La **capacidad** (cuánta carga aguanta) exige pruebas de carga.

## Seguridad — 25%

| Subcaracterística (2023) | Qué observamos | Puntos |
|---|---|---|
| **Confidencialidad** | HTTPS, HSTS (duración y subdominios) | 26 |
| | Cookies: `HttpOnly`, `Secure`, `SameSite` (sin cookies, puntuación completa) | 14 |
| **Integridad** | CSP: presencia, modo informe, `unsafe-inline`, `unsafe-eval`, directivas clave | 25 |
| | Contenido mixto, integridad de scripts externos (SRI) | 9 |
| **Resistencia** | `X-Frame-Options`/`frame-ancestors`, `nosniff`, `Referrer-Policy` | 15 |
| | `Permissions-Policy`, COOP/CORP, CORS restrictivo | 8 |
| | Formularios que envían por HTTP, filtración de versión del servidor | 3 |
| **No repudio**, **Responsabilidad**, **Autenticidad** | — | *sin medir* |

Sin HTTPS la nota se queda en 5: todo lo demás depende del canal cifrado.

## Capacidad de interacción (antes usabilidad) — 20%

| Subcaracterística (2023) | Qué observamos | Puntos |
|---|---|---|
| **Reconocibilidad de la adecuación** | Título y su longitud, meta descripción, favicon, Open Graph, canonical | 58 |
| **Autodescriptividad** | Región `main`, HTML semántico, navegación, `theme-color` | 42 |
| **Aprendizaje**, **Operabilidad**, **Protección frente a errores del usuario**, **Compromiso del usuario**, **Asistencia al usuario** | — | *sin medir* |

*Limitación declarada:* la operabilidad real requiere interacción; aquí solo se juzga cómo se presenta e identifica la página. La **inclusividad**, la otra subcaracterística de 2023 que sí se comprueba, tiene su propio eje: accesibilidad.

## Accesibilidad (inclusividad) — 15%

En 2023 la accesibilidad se cubre con la **inclusividad**, dentro de la capacidad de interacción. Se comprueba siguiendo los principios de WCAG, que dan nombre a sus tres partes (ninguna es una subcaracterística ISO por sí sola, por eso van marcadas "no es ISO" en el desglose):

| Parte (WCAG) | Qué observamos | Puntos |
|---|---|---|
| **Perceptible** | Idioma declarado, **zoom no bloqueado**, texto alternativo, tablas con cabeceras, sin reproducción automática | 40 |
| **Operable** | Etiquetas de formulario, sin `tabindex` positivo, títulos de iframe, texto de enlace descriptivo | 28 |
| **Estructura navegable** | `h1` (y solo uno), jerarquía sin saltos, HTML semántico, `main`, ids únicos | 32 |

*Limitación declarada:* son comprobaciones estáticas del HTML. **No sustituyen a axe-core**: el contraste de color efectivo y el árbol de accesibilidad final solo se pueden evaluar con renderizado real.

## Compatibilidad — 15%

| Subcaracterística (2023) | Qué observamos | Puntos |
|---|---|---|
| **Interoperabilidad** | `<!DOCTYPE html>`, codificación declarada, idioma del contenido | 40 |
| **Adaptación a dispositivos** · *no es ISO aquí* | Etiqueta viewport, imágenes responsivas (`srcset`/`picture`) | 46 |
| **Tecnología vigente** · *no es ISO* | Sin etiquetas HTML obsoletas, manifiesto web | 14 |
| **Coexistencia** | — | *sin medir* |

En 2023 la adaptación a entornos distintos es parte de la **flexibilidad**, no de la compatibilidad; se mantiene en este eje por cómo se mide (sobre la página desplegada), pero se marca para no confundirla.
