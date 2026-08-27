Quiero construir QalitiRadar: un escáner automático de calidad de software basado en ISO/IEC 25010.

## VISIÓN DEL PRODUCTO

QalitiRadar analiza automáticamente un repositorio de código (GitHub/GitLab) Y/O una URL de aplicación desplegada (Vercel, Netlify, etc.) y genera una puntuación de calidad del software basada en el estándar ISO/IEC 25010, detectando riesgos, deudas técnicas y oportunidades de mejora con evidencia concreta.

El sistema permite comparar análisis a lo largo del tiempo para mostrar evolución, mejoras y regresiones entre commits.

## DOS MODOS DE ANÁLISIS

### MODO 1: Análisis de Repositorio
- Usuario conecta GitHub/GitLab
- Se clona el repo en entorno seguro
- Se analiza: código, dependencias, tests, secrets, CI/CD, documentación
- Puntuación basada en: mantenibilidad, fiabilidad (tests), seguridad (código), portabilidad

### MODO 2: Análisis de URL (Producción)
- Usuario pega una URL pública (ej: https://mi-app.vercel.app)
- Se analiza: rendimiento real, seguridad runtime, accesibilidad, UX
- Puntuación basada en: rendimiento, seguridad (headers), usabilidad, compatibilidad

### MODO 3: Análisis Combinado (Recomendado)
- Usuario proporciona repo + URL
- Se obtiene visión completa: código vs producción
- Se detectan discrepancias (ej: buen código pero mal deploy, o viceversa)
- Puntuación consolidada con insights adicionales

## USUARIOS OBJETIVO

1. Desarrolladores individuales que quieren mejorar su código
2. Equipos de desarrollo que buscan métricas de calidad objetivas
3. Líderes técnicos que necesitan reportes para stakeholders
4. Consultores que auditan código de clientes
5. Dueños de productos que quieren evaluar apps sin acceso al código

## EJEMPLOS DE CASOS DE USO

### Caso 1: Desarrollador individual
- Usuario: Juan, desarrollador freelance
- Escenario: Acaba de terminar un proyecto y quiere saber su calidad
- Acción: Conecta su repo de GitHub
- Resultado: Recibe puntuación y recomendaciones para mejorar

### Caso 2: Dueño de producto
- Usuario: María, PM de una startup
- Escenario: Quiere evaluar la app de un proveedor sin acceso al código
- Acción: Pega el link de Vercel: https://cliente.vercel.app
- Resultado: Recibe análisis de rendimiento, seguridad y UX

### Caso 3: Equipo de desarrollo
- Usuario: Equipo de 5 desarrolladores
- Escenario: Quieren ver si su código se refleja bien en producción
- Acción: Conectan repo + URL de Vercel
- Resultado: Ven discrepancias y saben qué priorizar

### Caso 4: Consultor de QA
- Usuario: Carlos, consultor independiente
- Escenario: Auditoría rápida para un cliente
- Acción: Analiza repo + URL de múltiples proyectos
- Resultado: Genera reportes PDF profesionales para cada uno

## MVP - FUNCIONALIDADES REQUERIDAS

### 1. Autenticación y gestión de usuarios
- Registro e inicio de sesión (email/password o GitHub OAuth)
- Perfil de usuario básico
- Historial de análisis realizados

### 2. Conexión a repositorios (Modo 1)
- Integración con GitHub OAuth (lectura de repositorios)
- Lista de repositorios del usuario
- Selección de repositorio a analizar
- Soporte para repositorios públicos y privados

### 3. Análisis de URL (Modo 2)
- Input de URL pública (validar formato)
- Soporte para cualquier plataforma (Vercel, Netlify, Heroku, AWS, etc.)
- Análisis sin necesidad de autenticación
- Rate limiting para prevenir abuso

### 4. Motor de análisis de repositorio (backend)

**Análisis de estructura:**
- Detectar lenguaje(s) de programación
- Contar archivos por tipo (.js, .py, .ts, etc.)
- Identificar estructura del proyecto (frontend, backend, fullstack)

**Análisis de documentación:**
- Existencia y calidad de README.md
- Presencia de LICENSE, CONTRIBUTING.md, CHANGELOG.md
- Documentación de arquitectura (ARCHITECTURE.md, docs/)

**Análisis de dependencias:**
- Detectar package.json, requirements.txt, Gemfile, etc.
- Ejecutar npm audit / pip-audit para vulnerabilidades
- Identificar dependencias obsoletas

**Análisis de tests:**
- Detectar carpetas de tests (__tests__, spec, test)
- Calcular cobertura si existen reports de coverage
- Identificar tipos de tests (unitarios, integración, E2E)

**Análisis de CI/CD:**
- Detectar .github/workflows, .gitlab-ci.yml, Jenkinsfile
- Verificar existencia de pipelines de testing
- Identificar estrategias de deploy

**Análisis de seguridad:**
- Ejecutar Gitleaks para detectar secrets expuestos
- Identificar patrones riesgosos con Semgrep
- Verificar .gitignore apropiado

**Análisis de actividad:**
- Frecuencia de commits (últimos 30/90 días)
- Issues abiertos/cerrados
- Pull requests y code review

### 5. Motor de análisis de URL (backend)

**Rendimiento (Lighthouse CI):**
- Performance score (0-100)
- First Contentful Paint (FCP)
- Largest Contentful Paint (LCP)
- Time to Interactive (TTI)
- Total Blocking Time (TBT)
- Cumulative Layout Shift (CLS)

**Seguridad:**
- Verificar HTTPS configurado correctamente
- Headers de seguridad (HSTS, CSP, X-Frame-Options, etc.)
- Vulnerabilidades conocidas (OWASP Top 10 básico)
- Certificados SSL/TLS válidos

**Accesibilidad:**
- axe-core o similar para tests automáticos
- Contraste de colores
- Labels en formularios
- ARIA attributes

**SEO y mejores prácticas:**
- Meta tags básicos
- Estructura semántica
- Imágenes con alt text

**Compatibilidad:**
- Detección de navegadores soportados
- Responsive design (mobile-friendly)

### 6. Modelo de puntuación ISO 25010

**Para análisis de repositorio:**

| Dimensión | Peso | Métricas |
|---|---|---|
| Adecuación funcional | 15% | README claro, ejemplos, documentación de API |
| Fiabilidad | 20% | Cobertura de tests, CI/CD, manejo de errores |
| Seguridad | 20% | Secrets, dependencias vulnerables, patrones riesgosos |
| Mantenibilidad | 20% | Complejidad, duplicación, estructura, deuda técnica |
| Portabilidad | 10% | Docker, infraestructura como código, configuración |
| Actividad del proyecto | 15% | Commits recientes, issues, comunidad |

**Para análisis de URL:**

| Dimensión | Peso | Métricas |
|---|---|---|
| Rendimiento | 25% | Lighthouse performance score |
| Seguridad | 25% | HTTPS, headers, vulnerabilidades |
| Usabilidad | 20% | UX, errores claros, navegación |
| Accesibilidad | 15% | axe-core score, WCAG básico |
| Compatibilidad | 15% | Responsive, multi-navegador |

**Análisis combinado:**
- Promedio ponderado de ambas puntuaciones
- Detección de discrepancias significativas (>15 puntos de diferencia)
- Insights adicionales cuando hay discrepancia

Fórmula:
- Puntuación = Σ(peso_i × métrica_i) / Σ(pesos)
- Nivel de confianza basado en cantidad de evidencia encontrada
- Detección de riesgos críticos que bloquean puntuaciones altas

### 7. Dashboard y visualización (frontend)

**Página de selección de modo:**
- Tarjeta: "Analizar repositorio" (con icono de GitHub)
- Tarjeta: "Analizar URL" (con icono de mundo)
- Tarjeta: "Analizar ambos" (recomendado)

**Página de resultados (modo repositorio):**
- Puntuación general (0-100) con semáforo
- Nivel de confianza
- Gráfico radar con dimensiones ISO 25010
- Lista de riesgos críticos
- Lista de fortalezas
- Plan de mejora priorizado

**Página de resultados (modo URL):**
- Puntuación general (0-100)
- Métricas de rendimiento (Lighthouse)
- Headers de seguridad detectados
- Problemas de accesibilidad
- Capturas de pantalla (opcional)

**Página de resultados (modo combinado):**
- Puntuación repositorio vs puntuación URL
- Gráfico comparativo lado a lado
- Sección: "Discrepancias detectadas"
  - Ej: "Tu código tiene 72 puntos pero en producción se ve como 85"
  - Explicación de posibles causas
  - Recomendaciones específicas
- Puntuación consolidada

**Histórico:**
- Gráfico de evolución de puntuación en el tiempo
- Comparación entre análisis del mismo repo/URL

**Exportación:**
- Generar reporte en PDF descargable
- Opción de compartir reporte (link público temporal)

### 8. Histórico y comparación de análisis

#### Línea de tiempo de análisis

Cada repositorio o URL puede tener múltiples análisis a lo largo del tiempo:

- Análisis #1: 2026-08-20 (commit: abc123)
- Análisis #2: 2026-08-23 (commit: def456)
- Análisis #3: 2026-08-26 (commit: ghi789) ← actual

#### Comparación entre dos análisis

Cuando el usuario selecciona dos análisis para comparar, el sistema muestra:

**Resumen ejecutivo:**
- Puntuación anterior vs puntuación actual
- Cambio neto (+5, -3, 0)
- Tendencia (mejorando, estable, empeorando)

**Mejoras detectadas:**
- ✅ Tests: cobertura aumentó de 65% a 82% (+17%)
- ✅ Seguridad: 3 vulnerabilidades críticas fueron corregidas
- ✅ Documentación: se agregó ARCHITECTURE.md
- ✅ CI/CD: se implementaron pipelines de testing automático
- ✅ Deuda técnica: complejidad promedio reducida de 8.5 a 5.2

**Problemas nuevos o persistentes:**
- ❌ Secrets: nuevo archivo .env expuesto en la última versión
- ❌ Dependencias: 2 nuevas vulnerabilidades introducidas
- ⚠️ Tests: 3 tests fallando en la suite de integración
- ⚠️ Rendimiento: LCP aumentó de 1.8s a 2.4s

**Recomendaciones priorizadas:**
1. [CRÍTICO] Eliminar secrets del repositorio inmediatamente
2. [ALTO] Actualizar dependencias vulnerables
3. [MEDIO] Fixear tests fallando antes del próximo deploy
4. [BAJO] Optimizar imágenes para mejorar LCP

**Métricas detalladas por dimensión:**

| Dimensión | Análisis #1 | Análisis #2 | Cambio | Estado |
|---|---|---|---|---|
| Adecuación funcional | 75/100 | 80/100 | +5 | ✅ Mejoró |
| Fiabilidad | 68/100 | 82/100 | +14 | ✅ Mejoró |
| Seguridad | 60/100 | 55/100 | -5 | ❌ Empeoró |
| Mantenibilidad | 70/100 | 78/100 | +8 | ✅ Mejoró |
| Portabilidad | 80/100 | 80/100 | 0 | ➡️ Sin cambios |

#### Gráfico de evolución

Mostrar gráfico de línea con:
- Eje X: fechas de análisis (o números de commit)
- Eje Y: puntuación (0-100)
- Línea de tendencia
- Puntos clave (mejoras significativas, caídas importantes)

#### Métricas de progreso

- Días desde el primer análisis: 45 días
- Total de análisis realizados: 12
- Mejora promedio por semana: +2.3 puntos
- Mejor puntuación histórica: 85/100 (2026-08-15)
- Puntuación actual: 78/100
- Distancia al mejor histórico: -7 puntos

#### Notificaciones de cambio significativo

Alertar al usuario cuando:
- La puntuación baja más de 10 puntos
- Se detectan nuevos riesgos críticos
- Se introducen vulnerabilidades de seguridad
- La cobertura de tests cae significativamente

#### Entidades de base de datos adicionales
Analysis (id, repository_id OR app_id, analysis_type, overall_score, confidence_level, commit_hash, commit_message, created_at, raw_data)

AnalysisComparison (id, analysis_1_id, analysis_2_id, score_delta, improvements_count, regressions_count, summary_text, created_at)

Improvement (id, comparison_id, dimension, previous_score, current_score, delta, description, evidence)

Regression (id, comparison_id, dimension, previous_score, current_score, delta, description, evidence, severity)


#### Prompt para generar resumen automático

Cuando se comparan dos análisis, usar IA para generar:

```text
Basado en los siguientes datos de dos análisis del mismo proyecto:

ANÁLISIS ANTERIOR (commit abc123, 2026-08-20):
- Puntuación: 72/100
- Tests: 65% cobertura
- Seguridad: 3 vulnerabilidades críticas
- Documentación: README básico
- CI/CD: No configurado

ANÁLISIS ACTUAL (commit ghi789, 2026-08-26):
- Puntuación: 78/100
- Tests: 82% cobertura
- Seguridad: 0 vulnerabilidades críticas
- Documentación: README + ARCHITECTURE.md
- CI/CD: GitHub Actions configurado

Genera un resumen ejecutivo que incluya:
1. Párrafo de apertura (2-3 oraciones)
2. Lista de 3-5 mejoras más importantes
3. Lista de 2-3 problemas pendientes o nuevos
4. Recomendación principal para el próximo sprint

Tono: profesional pero accesible, enfocado en acción.
```

#### Funcionalidades adicionales de comparación

**Comparación rápida (quick compare):**
- Hover sobre un análisis anterior muestra mini-resumen
- Flechas verdes/rojas junto a cada dimensión

**Comparación detallada (full compare):**
- Vista lado a lado de todos los hallazgos
- Filtros por tipo (mejoras, regresiones, nuevos, persistentes)
- Exportar comparación a PDF

**Comparación automática:**
- Cada nuevo análisis se compara automáticamente con el anterior
- Notificación por email con resumen de cambios
- Highlight de cambios críticos en el dashboard

**Benchmarking:**
- Comparar tu evolución con el promedio de proyectos similares
- "Estás mejorando 2x más rápido que el promedio"
- "Tu puntuación de seguridad está 15 puntos arriba del promedio"

#### API endpoints adicionales
GET /api/analysis/:id/comparison/:other_id
POST /api/analysis/compare
Body: { analysis_1_id, analysis_2_id }

GET /api/repository/:id/timeline
Response: lista de análisis con scores y fechas

GET /api/repository/:id/progress
Response: métricas de progreso y tendencias


#### Reglas de negocio

1. **Comparación automática:**
   - Cada nuevo análisis se compara automáticamente con el anterior
   - Si es el primer análisis, no hay comparación

2. **Notificaciones:**
   - Si la puntuación baja >10 puntos: notificación inmediata
   - Si se detectan nuevos riesgos críticos: notificación inmediata
   - Resumen semanal: evolución de la última semana

3. **Límites:**
   - Máximo 50 análisis por repositorio (limpiar los más antiguos)
   - Mantener al menos los últimos 10 análisis siempre

4. **Commits:**
   - Guardar commit_hash y commit_message de cada análisis
   - Mostrar link al commit en GitHub/GitLab
   - Agrupar análisis por rama (main, develop, feature/*)

### 9. Base de datos

Entidades principales:
User (id, email, password_hash, github_id, created_at)
Repository (id, user_id, github_id, name, full_name, last_analyzed)
DeployedApp (id, user_id, name, url, last_analyzed)
Analysis (id, repository_id OR app_id, analysis_type, overall_score, confidence_level, commit_hash, commit_message, created_at, raw_data)
Dimension (id, analysis_id, name, score, weight)
Finding (id, analysis_id, type, severity, title, description, file_path OR url, recommendation)
Discrepancy (id, analysis_id, repo_score, url_score, explanation, recommendations)
AnalysisComparison (id, analysis_1_id, analysis_2_id, score_delta, improvements_count, regressions_count, summary_text, created_at)
Improvement (id, comparison_id, dimension, previous_score, current_score, delta, description, evidence)
Regression (id, comparison_id, dimension, previous_score, current_score, delta, description, evidence, severity)


## STACK TÉCNICO RECOMENDADO

### Backend
- Lenguaje: Python 3.11+
- Framework: FastAPI
- Base de datos: PostgreSQL
- ORM: SQLAlchemy + Alembic (migraciones)
- Cola de tareas: Celery + Redis (análisis en background)
- Autenticación: JWT + GitHub OAuth
- Almacenamiento temporal: S3-compatible o sistema de archivos

### Frontend
- Framework: Next.js 14+ (App Router)
- Lenguaje: TypeScript
- UI: Tailwind CSS + shadcn/ui
- Gráficos: Recharts
- Autenticación: NextAuth.js o integración con backend

### Herramientas de análisis
- Gitleaks: secrets en repositorios
- Semgrep: patrones de código
- Lighthouse CI: rendimiento web
- axe-core: accesibilidad
- OWASP ZAP: seguridad web (opcional para MVP)
- npm audit / pip-audit: dependencias

### Infraestructura
- Contenedores: Docker + Docker Compose para desarrollo
- Deploy: Vercel (frontend) + Railway/Render (backend) o un solo VPS
- CI/CD: GitHub Actions

## REQUISITOS NO FUNCIONALES

1. **Seguridad:**
   - No almacenar código permanentemente
   - Ejecutar análisis en entorno aislado (sandbox)
   - Validar y sanitizar todas las entradas
   - Rate limiting para prevenir abuso
   - No permitir análisis de URLs maliciosas (lista negra)

2. **Rendimiento:**
   - Análisis asíncrono (no bloquear al usuario)
   - Webhooks o polling para notificar cuando termina
   - Cache de resultados (no re-analizar si no hay cambios)
   - Timeout máximo por análisis (ej: 10 minutos)

3. **Privacidad:**
   - No usar el código analizado para entrenar modelos
   - Permitir borrar análisis y repositorios
   - Cumplir con GDPR básico
   - No almacenar URLs de aplicaciones sensibles (bancos, salud)

4. **Escalabilidad:**
   - Diseñar para múltiples análisis en paralelo
   - Separar frontend y backend
   - Usar cola de tareas para escalar workers
   - Rate limiting por usuario (ej: 5 análisis/hora gratis)

5. **Legal:**
   - Términos de uso claros
   - Aclarar que NO es certificación oficial
   - Limitar responsabilidad por falsos positivos/negativos
   - Respetar robots.txt en análisis de URLs

## ESTRUCTURA DE ARCHIVOS SUGERIDA
qaliti-radar/
├── backend/
│ ├── app/
│ │ ├── api/ (endpoints FastAPI)
│ │ ├── core/ (config, security)
│ │ ├── models/ (SQLAlchemy models)
│ │ ├── schemas/ (Pydantic schemas)
│ │ ├── services/ (lógica de negocio)
│ │ ├── analyzers/
│ │ │ ├── repository/ (analizadores de repo)
│ │ │ │ ├── structure.py
│ │ │ │ ├── documentation.py
│ │ │ │ ├── dependencies.py
│ │ │ │ ├── tests.py
│ │ │ │ ├── cicd.py
│ │ │ │ ├── security.py
│ │ │ │ └── activity.py
│ │ │ └── url/ (analizadores de URL)
│ │ │ ├── performance.py (Lighthouse)
│ │ │ ├── security.py (headers, OWASP)
│ │ │ ├── accessibility.py (axe-core)
│ │ │ └── seo.py
│ │ └── utils/ (helpers)
│ ├── tests/
│ ├── alembic/ (migraciones DB)
│ ├── requirements.txt
│ └── Dockerfile
├── frontend/
│ ├── app/ (Next.js App Router)
│ │ ├── dashboard/
│ │ ├── analyze/
│ │ │ ├── repository/
│ │ │ ├── url/
│ │ │ └── combined/
│ │ └── results/
│ ├── components/
│ ├── lib/ (utils, API client)
│ ├── public/
│ ├── package.json
│ └── Dockerfile
├── docker-compose.yml
├── README.md
└── CLAUDE.md (instrucciones para el proyecto)


## PLAN DE IMPLEMENTACIÓN POR FASES

### Fase 1: Setup (Día 1-2)
- [ ] Crear estructura de archivos
- [ ] Configurar Docker Compose (PostgreSQL, Redis, backend, frontend)
- [ ] Setup de base de datos con migraciones iniciales
- [ ] Autenticación básica (registro/login)

### Fase 2: Integración GitHub (Día 3-4)
- [ ] GitHub OAuth
- [ ] Listar repositorios del usuario
- [ ] Clonar repositorio temporalmente

### Fase 3: Analizadores de repositorio (Día 5-8)
- [ ] Analizador de estructura
- [ ] Analizador de documentación
- [ ] Analizador de dependencias
- [ ] Analizador de tests
- [ ] Analizador de CI/CD
- [ ] Analizador de seguridad (Gitleaks, Semgrep)
- [ ] Analizador de actividad

### Fase 4: Analizadores de URL (Día 9-11)
- [ ] Integrar Lighthouse CI
- [ ] Analizador de headers de seguridad
- [ ] Integrar axe-core para accesibilidad
- [ ] Analizador SEO básico

### Fase 5: Modelo de puntuación (Día 12-13)
- [ ] Implementar cálculo ISO 25010 para repositorio
- [ ] Implementar cálculo ISO 25010 para URL
- [ ] Implementar lógica de análisis combinado
- [ ] Detectar discrepancias
- [ ] Generar recomendaciones

### Fase 6: Dashboard (Día 14-17)
- [ ] Página de selección de modo
- [ ] Página de resultados (repo)
- [ ] Página de resultados (URL)
- [ ] Página de resultados (combinado)
- [ ] Gráfico radar
- [ ] Lista de hallazgos
- [ ] Plan de mejora
- [ ] Histórico de análisis
- [ ] Vista de comparación entre análisis
- [ ] Gráfico de evolución temporal
- [ ] Resumen automático de mejoras/regresiones

### Fase 7: Features adicionales (Día 18-21)
- [ ] Exportación a PDF
- [ ] Compartir reporte
- [ ] Webhooks de notificación
- [ ] Tests end-to-end
- [ ] Rate limiting
- [ ] Notificaciones de cambios significativos
- [ ] Benchmarking vs promedio

### Fase 8: Producción (Día 22-25)
- [ ] Deploy a Vercel + Railway
- [ ] Configurar dominio
- [ ] Monitoreo y logs
- [ ] Documentación de usuario
- [ ] Landing page

## REGLAS IMPORTANTES

1. **Antes de escribir código:**
   - Analiza la arquitectura propuesta
   - Diseña el modelo de datos en detalle
   - Identifica riesgos de seguridad
   - Crea un plan detallado
   - Espera mi aprobación

2. **Calidad del código:**
   - Escribe tests unitarios para cada analizador
   - Usa type hints en Python
   - Documenta funciones complejas
   - Sigue principios SOLID

3. **Seguridad:**
   - Nunca ejecutar código arbitrario del usuario
   - Aislar procesos de análisis
   - Validar todas las entradas
   - Sanitizar outputs
   - No permitir análisis de URLs internas (localhost, 192.168.x.x, etc.)

4. **Experiencia de usuario:**
   - Mostrar progreso del análisis en tiempo real
   - Manejar errores gracefulmente
   - Explicar claramente qué significa cada métrica
   - No presentar resultados como certificación oficial
   - Mostrar claramente la diferencia entre análisis de repo vs URL

5. **ISO 25010:**
   - Basar el modelo en el estándar oficial
   - Documentar cómo cada métrica se mapea a la norma
   - Aclarar que es una aproximación, no certificación

6. **Análisis de URLs:**
   - Respetar robots.txt
   - No hacer scraping agresivo
   - Rate limiting para no saturar servidores ajenos
   - Timeout razonable (30 segundos por página)

7. **Comparaciones:**
   - Cada nuevo análisis se compara automáticamente con el anterior
   - Generar resúmenes ejecutivos con IA
   - Mostrar claramente mejoras y regresiones
   - Permitir comparar cualquier par de análisis históricos

## ENTREGABLES ESPERADOS

1. Documento de arquitectura detallado
2. Diagrama de entidad-relación de la base de datos
3. Plan de implementación con milestones
4. Código funcional del MVP
5. Tests unitarios y de integración
6. Documentación de despliegue
7. README para usuarios finales

## PRÓXIMOS PASOS INMEDIATOS

1. Analiza esta especificación y hazme preguntas si algo no está claro
2. Propón la arquitectura técnica detallada
3. Diseña el modelo de datos (tablas, relaciones, índices)
4. Identifica los principales riesgos técnicos y de seguridad
5. Crea un plan de implementación semana por semana
6. Espera mi aprobación antes de escribir código


## REPOSITORIO
Todos los avnces seran subidos a este repositorio https://github.com/Ashdamy/QalitiRadar

¿Comprendes la visión y estás listo para comenzar?