import type { Metadata } from "next";
import Link from "next/link";
import { RadarMark } from "@/components/RadarMark";
import { ModosDeAnalisis } from "@/components/ModosDeAnalisis";
import { SITE_DESCRIPTION, SITE_URL } from "@/lib/sitio";

// Pagina de servidor a proposito: llega a Google ya renderizada. Lo unico
// interactivo, el selector de modos, es un componente de cliente aparte.
export const metadata: Metadata = {
  title: { absolute: "QalitiRadar — Mide la calidad de tu software con ISO/IEC 25010" },
  description: SITE_DESCRIPTION,
  alternates: { canonical: "/" },
};

const DATOS_ESTRUCTURADOS = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "QalitiRadar",
  url: SITE_URL,
  applicationCategory: "DeveloperApplication",
  operatingSystem: "Web",
  inLanguage: "es",
  description: SITE_DESCRIPTION,
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
};

const PASOS = [
  {
    titulo: "Conecta",
    texto:
      "Entra con GitHub y elige un repositorio, o pega la URL de tu aplicación. Solo pedimos permiso de lectura.",
  },
  {
    titulo: "Analizamos en una caja cerrada",
    texto:
      "El código se lee en un contenedor aislado, sin red y sin permisos. Nunca se instala ni se ejecuta nada tuyo. Al terminar, se borra.",
  },
  {
    titulo: "Recibe la nota y el plan",
    texto:
      "Una nota por dimensión, los hallazgos ordenados por gravedad y un plan de mejora con lo que más sube la nota primero.",
  },
];

const DIMENSIONES = [
  {
    nombre: "Seguridad",
    texto:
      "Secretos filtrados, patrones inseguros, dependencias con vulnerabilidades conocidas y cabeceras de seguridad.",
  },
  {
    nombre: "Fiabilidad",
    texto: "Pruebas, integración continua y manejo de errores: lo que evita que un cambio rompa lo que ya funcionaba.",
  },
  {
    nombre: "Mantenibilidad",
    texto: "Estructura, tamaño de archivos, deuda marcada en el código y facilidad para que otra persona lo entienda.",
  },
  {
    nombre: "Eficiencia de desempeño",
    texto: "Lo que tarda tu aplicación en cargar y responder, medido sobre la versión que ven tus usuarios.",
  },
  {
    nombre: "Accesibilidad",
    texto: "Contraste, etiquetas y navegación con teclado: si todas las personas pueden usar lo que construiste.",
  },
  {
    nombre: "Y cuatro más",
    texto:
      "Adecuación funcional, flexibilidad, capacidad de interacción y compatibilidad. La novena, protección, aún no se mide y se marca como tal.",
  },
];

const CALIBRACION = [
  { proyecto: "axios/axios", nota: 68 },
  { proyecto: "pallets/flask", nota: 64 },
  { proyecto: "octocat/Hello-World", nota: 7 },
];

const FUNCIONES = [
  {
    titulo: "Histórico y comparación",
    texto: "Mira cómo evoluciona la nota y qué mejoró o empeoró entre dos análisis.",
    icono: <path d="M3 21L10 13L15 17L25 6" />,
  },
  {
    titulo: "Vigilancia continua",
    texto: "Analiza solo cuando hay commits nuevos y te avisa si la calidad cae.",
    icono: <path d="M14 4a7 7 0 0 0-7 7v5l-2 3h18l-2-3v-5a7 7 0 0 0-7-7zM11 22a3 3 0 0 0 6 0" />,
  },
  {
    titulo: "Informe en PDF y enlace",
    texto: "Descárgalo o compártelo con un enlace temporal. Ideal para clientes y auditorías.",
    icono: <path d="M8 3h9l5 5v17H8zM17 3v5h5M11 15h8M11 19h8" />,
  },
  {
    titulo: "Insignia para tu README",
    texto: "Muestra la nota en tu repositorio. Se actualiza sola con cada análisis.",
    icono: (
      <>
        <rect x="3" y="9" width="22" height="10" rx="3" />
        <path d="M14 9v10" />
      </>
    ),
  },
];

const GARANTIAS = [
  ["Nunca ejecutamos tu código.", "Solo se lee, dentro de un contenedor sin red, sin permisos y con tiempo limitado."],
  ["Permiso mínimo en GitHub.", "Solo lectura. Puedes desconectarlo cuando quieras."],
  ["Nada se queda donde no debe.", "El clon se borra al terminar y el token de GitHub se guarda cifrado."],
  ["Tu cuenta, bajo tu control.", "Bórrala y se va todo: análisis, informes y enlaces."],
];

const PREGUNTAS = [
  {
    pregunta: "¿Cuánto cuesta?",
    respuesta:
      "Es gratis. Para que el servicio siga siendo rápido para todos, cada cuenta puede lanzar 5 análisis por hora y 20 al día, y tener hasta 3 proyectos en seguimiento.",
  },
  {
    pregunta: "¿Funciona con repositorios privados?",
    respuesta:
      "Por ahora, solo con repositorios públicos de GitHub; los privados están en camino. Mientras tanto, puedes analizar la versión desplegada de cualquier aplicación con el modo URL.",
  },
  {
    pregunta: "¿En qué se diferencia de un linter?",
    respuesta:
      "Un linter revisa líneas de código. QalitiRadar mira el proyecto entero —pruebas, dependencias, documentación, actividad— y también la aplicación en producción, y lo resume en una nota comparable en el tiempo.",
  },
  {
    pregunta: "¿Es una certificación ISO?",
    respuesta:
      "No. Es una aproximación al modelo ISO/IEC 25010 hecha con análisis automático. Sirve para saber dónde estás y qué mejorar; no sustituye una auditoría oficial.",
  },
  {
    pregunta: "¿Qué pasa con mi código?",
    respuesta:
      "Se clona en un contenedor aislado, se lee y se borra al terminar. Nunca se instalan dependencias ni se ejecuta nada del repositorio.",
  },
];

function Check() {
  return (
    <svg width="16" height="16" viewBox="0 0 14 14" aria-hidden="true" className="mt-1 flex-none">
      <path
        d="M2 7.5L5.5 11L12 3"
        className="stroke-good"
        fill="none"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Etiqueta({ children }: { children: React.ReactNode }) {
  return <p className="mb-3.5 font-mono text-[13px] tracking-[0.08em] text-accent">{children}</p>;
}

const H2 = "text-[32px] font-bold leading-[1.12] tracking-[-0.02em] md:text-[42px]";
const BOTON =
  "inline-flex min-h-[48px] items-center gap-2.5 rounded-[10px] px-[22px] text-base focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
const BOTON_PRIMARIO = `${BOTON} bg-accent font-semibold text-onAccent hover:bg-accentStrong`;
const BOTON_SECUNDARIO = `${BOTON} border border-border font-medium text-text hover:border-muted`;
const CUADRICULA =
  "pointer-events-none absolute inset-0 [background-image:linear-gradient(var(--color-border)_1px,transparent_1px),linear-gradient(90deg,var(--color-border)_1px,transparent_1px)] [background-size:40px_40px]";

export default function Landing() {
  return (
    <div className="w-full bg-bg text-text">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(DATOS_ESTRUCTURADOS) }}
      />

      <header className="sticky top-0 z-10 border-b border-border bg-bg/90 backdrop-blur">
        <nav aria-label="Principal" className="mx-auto flex max-w-[1200px] items-center justify-between gap-6 px-6 py-3.5">
          <Link href="/" className="flex items-center gap-2.5 text-text">
            <RadarMark size={22} />
            <span className="text-base font-semibold tracking-[0.01em]">QalitiRadar</span>
          </Link>
          <div className="hidden items-center gap-7 text-sm md:flex">
            <a href="#modos" className="text-muted hover:text-text">Cómo funciona</a>
            <a href="#dimensiones" className="text-muted hover:text-text">Qué mide</a>
            <a href="#escala" className="text-muted hover:text-text">La escala</a>
            <a href="#preguntas" className="text-muted hover:text-text">Preguntas</a>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Link href="/entrar" className="hidden px-3.5 py-2.5 text-text hover:text-accent sm:inline">
              Iniciar sesión
            </Link>
            <Link
              href="/entrar"
              className="inline-flex min-h-[44px] items-center rounded-lg bg-accent px-4 font-semibold text-onAccent hover:bg-accentStrong"
            >
              Analizar gratis
            </Link>
          </div>
        </nav>
      </header>

      <main>
        <section className="relative overflow-hidden border-b border-border px-6 py-[72px] md:py-28">
          <div className={`${CUADRICULA} opacity-20`} aria-hidden="true" />
          <div className="relative mx-auto flex max-w-[1200px] flex-col items-center gap-14 lg:flex-row">
            <div className="min-w-0 flex-1">
              <Etiqueta>ISO/IEC 25010 · CÓDIGO Y PRODUCCIÓN</Etiqueta>
              <h1 className="mb-[22px] text-[40px] font-bold leading-[1.05] tracking-[-0.025em] md:text-[60px]">
                Mide la calidad de tu software antes de que la midan tus usuarios.
              </h1>
              <p className="mb-[34px] max-w-[560px] text-[19px] leading-[1.6] text-muted">
                Conecta un repositorio de GitHub o pega la URL de tu aplicación. En minutos tienes una nota de
                0 a 100, los problemas que la bajan y qué arreglar primero. Sin instalar nada.
              </p>
              <div className="mb-[26px] flex flex-wrap gap-3">
                <Link href="/entrar" className={BOTON_PRIMARIO}>
                  Analizar mi proyecto gratis <span aria-hidden="true">→</span>
                </Link>
                <a href="#modos" className={BOTON_SECUNDARIO}>
                  Ver qué analiza
                </a>
              </div>
              <ul className="flex flex-wrap gap-x-5 gap-y-2 text-[13.5px] text-muted">
                <li className="flex items-center gap-2"><Check />Gratis</li>
                <li className="flex items-center gap-2"><Check />Tu código nunca se ejecuta</li>
                <li className="flex items-center gap-2"><Check />Solo lectura</li>
              </ul>
            </div>

            <div className="flex min-w-0 flex-1 justify-center">
              <svg
                viewBox="-70 -24 460 368"
                className="h-auto w-full max-w-[520px]"
                role="img"
                aria-label="Radar de calidad barriendo seis dimensiones"
              >
                <g fill="none" className="stroke-border" strokeWidth="1">
                  <polygon points="160,20 281.2,90 281.2,230 160,300 38.8,230 38.8,90" />
                  <polygon points="160,55 250.9,107.5 250.9,212.5 160,265 69.1,212.5 69.1,107.5" />
                  <polygon points="160,90 220.6,125 220.6,195 160,230 99.4,195 99.4,125" />
                  <polygon points="160,125 190.3,142.5 190.3,177.5 160,195 129.7,177.5 129.7,142.5" />
                  <line x1="160" y1="20" x2="160" y2="300" />
                  <line x1="38.8" y1="90" x2="281.2" y2="230" />
                  <line x1="38.8" y1="230" x2="281.2" y2="90" />
                </g>
                <g className="animate-radar-sweep">
                  <path d="M160 160 L160 20 A140 140 0 0 1 281.2 90 Z" className="fill-accent" opacity="0.1" />
                  <line x1="160" y1="160" x2="281.2" y2="90" className="stroke-accent" strokeWidth="1.2" opacity="0.85" />
                </g>
                <polygon
                  points="160,65.8 238.9,114.2 243.4,208.4 160,244 90,200.1 84.3,115.5"
                  className="fill-accent stroke-accent"
                  fillOpacity="0.16"
                  strokeWidth="1.4"
                />
                <g className="fill-muted font-mono" fontSize="9">
                  <text x="160" y="8" textAnchor="middle">ADECUACIÓN</text>
                  <text x="290" y="86">FIABILIDAD</text>
                  <text x="290" y="240">SEGURIDAD</text>
                  <text x="160" y="320" textAnchor="middle">MANTENIBILIDAD</text>
                  <text x="30" y="240" textAnchor="end">FLEXIBILIDAD</text>
                  <text x="30" y="86" textAnchor="end">COMPATIBILIDAD</text>
                </g>
              </svg>
            </div>
          </div>
        </section>

        <section aria-label="Herramientas en las que se apoya" className="border-b border-border bg-panel px-6 py-7">
          <p className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-center gap-x-10 gap-y-3.5 font-mono text-sm text-muted">
            <span className="text-text">Analiza con herramientas abiertas y probadas:</span>
            <span>Gitleaks</span>
            <span>Semgrep</span>
            <span>OSV</span>
            <span>GitHub API</span>
          </p>
        </section>

        <section id="modos" className="scroll-mt-20 px-6 py-[72px] md:py-28">
          <div className="mx-auto max-w-[1200px]">
            <Etiqueta>TRES FORMAS DE MIRAR</Etiqueta>
            <h2 className={`${H2} mb-4 max-w-[760px]`}>El código cuenta una historia. Producción, otra.</h2>
            <p className="mb-10 max-w-[700px] text-lg text-muted">
              Analiza el repositorio, la aplicación desplegada o las dos a la vez. Cuando no coinciden, QalitiRadar te
              explica por qué.
            </p>
            <ModosDeAnalisis />
          </div>
        </section>

        <section className="border-y border-border bg-panel px-6 py-[72px] md:py-28">
          <div className="mx-auto max-w-[1200px]">
            <Etiqueta>EN TRES PASOS</Etiqueta>
            <h2 className={`${H2} mb-12`}>De un enlace a un plan de mejora.</h2>
            <ol className="grid grid-cols-1 gap-6 md:grid-cols-3">
              {PASOS.map((paso, i) => (
                <li key={paso.titulo} className={`border-t-2 pt-6 ${i === 0 ? "border-accent" : "border-border"}`}>
                  <p className={`mb-3 font-mono text-sm ${i === 0 ? "text-accent" : "text-muted"}`}>0{i + 1}</p>
                  <h3 className="mb-2.5 text-[21px] font-semibold">{paso.titulo}</h3>
                  <p className="text-muted">{paso.texto}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="dimensiones" className="scroll-mt-20 px-6 py-[72px] md:py-28">
          <div className="mx-auto max-w-[1200px]">
            <Etiqueta>QUÉ MIDE</Etiqueta>
            <h2 className={`${H2} mb-4 max-w-[760px]`}>Ocho de las nueve características ISO, un solo informe.</h2>
            <p className="mb-12 max-w-[700px] text-lg text-muted">
              Basado en ISO/IEC 25010, el estándar internacional de calidad del producto software.
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {DIMENSIONES.map((d) => (
                <div key={d.nombre} className="rounded-xl border border-border bg-surface p-6">
                  <h3 className="mb-2 text-lg font-semibold">{d.nombre}</h3>
                  <p className="text-[15px] text-muted">{d.texto}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="escala" className="scroll-mt-20 border-y border-border bg-panel px-6 py-[72px] md:py-28">
          <div className="mx-auto grid max-w-[1200px] grid-cols-1 items-center gap-16 lg:grid-cols-2">
            <div>
              <Etiqueta>UNA ESCALA EXIGENTE</Etiqueta>
              <h2 className={`${H2} mb-5`}>Los puntos se ganan, no se regalan.</h2>
              <p className="mb-4 text-[17px] text-muted">
                Cada dimensión parte de cero y solo sube con evidencia real. Un repositorio vacío no saca buena nota por
                no tener problemas: saca mala nota porque no demuestra nada.
              </p>
              <p className="text-[17px] text-muted">
                Y un problema grave pone techo: un hallazgo crítico limita la nota a 40, por bien que esté todo lo
                demás. Un secreto filtrado no se compensa con buena documentación.
              </p>
            </div>
            <figure className="rounded-2xl border border-border bg-surface p-8">
              <figcaption className="mb-5 text-sm text-muted">Contrastada con proyectos de calidad conocida</figcaption>
              <div className="flex flex-col gap-5">
                {CALIBRACION.map((c) => (
                  <div key={c.proyecto}>
                    <div className="mb-2 flex justify-between font-mono text-sm">
                      <span>{c.proyecto}</span>
                      <span className="font-medium">{c.nota}</span>
                    </div>
                    <div className="h-2 rounded bg-surface2">
                      <div
                        className={`h-full rounded ${c.nota < 20 ? "bg-muted" : "bg-accent"}`}
                        style={{ width: `${c.nota}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-6 text-[13px] text-muted">
                Aproximación al modelo ISO/IEC 25010. No es una certificación oficial.
              </p>
            </figure>
          </div>
        </section>

        <section className="px-6 py-[72px] md:py-28">
          <div className="mx-auto max-w-[1200px]">
            <Etiqueta>MÁS ALLÁ DE UNA FOTO</Etiqueta>
            <h2 className={`${H2} mb-12 max-w-[760px]`}>La calidad cambia con cada commit. QalitiRadar te lo cuenta.</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {FUNCIONES.map((f) => (
                <div key={f.titulo} className="rounded-xl border border-border p-6">
                  <svg
                    width="28"
                    height="28"
                    viewBox="0 0 28 28"
                    aria-hidden="true"
                    fill="none"
                    className="stroke-accent"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    {f.icono}
                  </svg>
                  <h3 className="mb-2 mt-4 text-[17px] font-semibold">{f.titulo}</h3>
                  <p className="text-[14.5px] text-muted">{f.texto}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-y border-border bg-panel px-6 py-[72px] md:py-24">
          <div className="mx-auto grid max-w-[1200px] grid-cols-1 gap-12 lg:grid-cols-2 lg:gap-16">
            <div>
              <Etiqueta>TU CÓDIGO, A SALVO</Etiqueta>
              <h2 className="text-[30px] font-bold leading-[1.15] tracking-[-0.02em] md:text-[38px]">
                Le pedimos a tu código lo mismo que nos exigimos a nosotros.
              </h2>
            </div>
            <ul className="flex flex-col gap-[18px] text-base text-muted">
              {GARANTIAS.map(([titulo, texto]) => (
                <li key={titulo} className="flex gap-3">
                  <Check />
                  <span>
                    <strong className="font-semibold text-text">{titulo}</strong> {texto}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="preguntas" className="scroll-mt-20 px-6 py-[72px] md:py-28">
          <div className="mx-auto max-w-[820px]">
            <h2 className={`${H2} mb-8 text-center`}>Preguntas frecuentes</h2>
            <div className="border-t border-border">
              {PREGUNTAS.map((p) => (
                <details key={p.pregunta} className="group border-b border-border px-1 py-5">
                  <summary className="flex min-h-[44px] cursor-pointer list-none items-center justify-between gap-4 text-[17.5px] font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden">
                    {p.pregunta}
                    <span aria-hidden="true" className="text-2xl text-muted transition-transform duration-150 group-open:rotate-45">
                      +
                    </span>
                  </summary>
                  <p className="mt-3 text-muted">{p.respuesta}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className="relative overflow-hidden border-t border-border px-6 py-[72px] md:py-28">
          <div className={`${CUADRICULA} opacity-[0.18]`} aria-hidden="true" />
          <div className="relative mx-auto max-w-[760px] text-center">
            <h2 className="mb-[18px] text-[36px] font-bold leading-[1.08] tracking-[-0.025em] md:text-5xl">
              ¿Cuánto saca tu proyecto?
            </h2>
            <p className="mb-[34px] text-[19px] text-muted">Averígualo en unos minutos. Gratis y sin instalar nada.</p>
            <div className="flex flex-wrap justify-center gap-3">
              <Link href="/entrar" className={BOTON_PRIMARIO}>
                Empezar con GitHub
              </Link>
              <Link href="/entrar" className={BOTON_SECUNDARIO}>
                Crear cuenta con correo
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border bg-panel px-6 py-10">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-5 text-sm text-muted">
          <span>© 2026 QalitiRadar</span>
          <nav aria-label="Pie de página" className="flex flex-wrap gap-6">
            <Link href="/privacidad" className="hover:text-text">Privacidad</Link>
            <Link href="/terminos" className="hover:text-text">Términos</Link>
            <a href="https://github.com/Ashdamy/QalitiRadar" className="hover:text-text">GitHub</a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
