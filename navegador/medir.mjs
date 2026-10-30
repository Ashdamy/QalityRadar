// Mide una pagina con Lighthouse y escribe una linea JSON en stdout:
// {lcp_ms, tbt_ms, cls, axe: {violations: [{id, impact, nodes, help}], passes}}
// El backend la interpreta como dato hostil (backend/app/utils/navegador.py).
import lighthouse from "lighthouse";
import * as chromeLauncher from "chrome-launcher";

const url = process.argv[2];

const chrome = await chromeLauncher.launch({
  chromePath: process.env.CHROME_PATH,
  chromeFlags: [
    "--headless=new",
    // El sandbox de Chromium necesita capacidades que el contenedor no da
    // (--cap-drop=ALL): el aislamiento lo pone el contenedor.
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--user-data-dir=/tmp/chrome",
    // Todo sale por el proxy, tambien lo que va a localhost: "<-loopback>"
    // quita la excepcion que Chromium hace por defecto.
    "--proxy-server=http://127.0.0.1:3128",
    "--proxy-bypass-list=<-loopback>",
    // QUIC (UDP) y WebRTC no pasarian por un proxy HTTP: se cortan.
    "--disable-quic",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--no-first-run",
    "--disable-extensions",
    "--disable-sync",
    "--disable-background-networking",
    "--disable-component-update",
  ],
});

try {
  const resultado = await lighthouse(url, {
    port: chrome.port,
    output: "json",
    logLevel: "error",
    onlyCategories: ["performance", "accessibility"],
    maxWaitForLoad: 45000,
  });
  const auditorias = resultado.lhr.audits;
  // Las auditorias de accesibilidad de Lighthouse son reglas de axe-core.
  const reglas = resultado.lhr.categories.accessibility.auditRefs
    .map((ref) => auditorias[ref.id])
    .filter((a) => a && a.scoreDisplayMode === "binary");

  console.log(
    JSON.stringify({
      lcp_ms: auditorias["largest-contentful-paint"]?.numericValue,
      tbt_ms: auditorias["total-blocking-time"]?.numericValue,
      cls: auditorias["cumulative-layout-shift"]?.numericValue,
      axe: {
        violations: reglas
          .filter((a) => a.score === 0)
          .map((a) => ({
            id: a.id,
            impact: a.details?.debugData?.impact ?? "minor",
            nodes: a.details?.items?.length ?? 0,
            help: a.title,
          })),
        passes: reglas.filter((a) => a.score === 1).length,
      },
    }),
  );
} finally {
  await chrome.kill();
}
