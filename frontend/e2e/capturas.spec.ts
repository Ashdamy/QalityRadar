import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Genera las capturas del README recorriendo la aplicación de verdad.
 *
 * No son montajes: cada imagen sale de un navegador real contra el backend
 * real, así que si una pantalla se rompe, la captura lo enseña. Se ejecuta a
 * mano cuando la interfaz cambia:
 *
 *     npx playwright test e2e/capturas.spec.ts
 *
 * La cuenta se crea al vuelo y solo se usa aquí, para que en las imágenes no
 * aparezca ningún dato personal.
 */

const DESTINO = resolve(process.cwd(), "..", "docs", "screenshots");
const CONTRASENA = "capturas-de-prueba-123";
const URL_OBJETIVO = "https://example.com";

let secuencia = 0;
function emailNuevo(): string {
  secuencia += 1;
  return `capturas-${Date.now()}-${secuencia}@example.com`;
}

async function guardar(page: Page, nombre: string) {
  mkdirSync(DESTINO, { recursive: true });
  // El indicador de desarrollo de Next se cuela en cada captura y no forma
  // parte del producto.
  await page
    .addStyleTag({
      content:
        "nextjs-portal, [data-nextjs-dev-tools-button], #next-logo { display: none !important; }",
    })
    .catch(() => {});
  await page.screenshot({ path: resolve(DESTINO, `${nombre}.png`), fullPage: false });
}

test.use({ viewport: { width: 1280, height: 860 } });

test("captura el recorrido completo", async ({ page }) => {
  test.setTimeout(240_000);

  // 1. Entrada
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Crear cuenta" }).first()).toBeVisible();
  await guardar(page, "01-inicio-sesion");

  // 2. Elección de modo
  await page.getByRole("button", { name: "Crear cuenta" }).first().click();
  await page.locator("#email").fill(emailNuevo());
  await page.locator("#password").fill(CONTRASENA);
  await page.locator("#confirmPassword").fill(CONTRASENA);
  await page.getByRole("button", { name: "Crear cuenta" }).last().click();
  await expect(page).toHaveURL(/\/analyze/, { timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "¿Qué quieres analizar?" })).toBeVisible();
  await guardar(page, "02-modos-de-analisis");

  // 3. Formulario de análisis de URL
  await page.getByRole("button", { name: /Analizar URL/ }).click();
  await expect(page.locator("#url")).toBeVisible();
  await guardar(page, "03-analizar-url");

  // 4. Resultado real
  await page.locator("#url").fill(URL_OBJETIVO);
  await page.getByRole("button", { name: "Analizar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Análisis completado" })).toBeVisible({
    timeout: 180_000,
  });
  await page.waitForTimeout(600); // deja asentar el radar antes de disparar
  await guardar(page, "04-resultado-del-analisis");

  // Segunda toma con el radar y las dimensiones a la vista: es lo que de
  // verdad enseña que el analisis mide algo.
  // scrollIntoViewIfNeeded no baja si considera que ya se ve un poco, y el
  // radar quedaba fuera de cuadro. Se centra a mano.
  await page
    .getByText("Dimensiones", { exact: true })
    .evaluate((el) => el.scrollIntoView({ block: "center" }));
  await page.waitForTimeout(500);
  await guardar(page, "04b-dimensiones");

  // 5. Enlace público
  await page.getByRole("button", { name: "Compartir" }).click();
  const campo = page.getByLabel("Enlace público al informe");
  await expect(campo).toBeVisible({ timeout: 30_000 });
  await guardar(page, "05-compartir-informe");

  const enlace = await campo.inputValue();
  await page.goto(enlace);
  await expect(page.getByText("Informe compartido")).toBeVisible({ timeout: 30_000 });
  await guardar(page, "06-informe-publico");

  // 6. Seguimiento, vacio: es lo primero que ve alguien que empieza
  await page.goto("/monitors");
  await expect(page.getByText(/Todavía no vigilas/)).toBeVisible({ timeout: 60_000 });
  await guardar(page, "07-seguimiento-vacio");
});

/**
 * El seguimiento solo se entiende con algo dentro, y para eso hacen falta
 * repositorios traidos de GitHub. Se reutiliza la sesion local existente en
 * vez de inventar datos: la captura enseña el producto funcionando de verdad.
 *
 * Requiere los tokens en E2E_ACCESS_TOKEN / E2E_REFRESH_TOKEN; sin ellos la
 * prueba se salta sola.
 */
test("captura el seguimiento con proyectos", async ({ page }) => {
  const acceso = process.env.E2E_ACCESS_TOKEN;
  test.skip(!acceso, "sin sesión con repositorios enganchados");

  await page.goto("/");
  await page.evaluate(
    ([token, refresco]) => {
      window.localStorage.setItem("qalitiradar.token", token!);
      if (refresco) window.localStorage.setItem("qalitiradar.refresh", refresco);
    },
    [acceso, process.env.E2E_REFRESH_TOKEN] as const,
  );

  await page.goto("/monitors");
  await expect(page.getByRole("heading", { name: "Seguimiento" })).toBeVisible({
    timeout: 60_000,
  });
  // Sin esperar a la tarjeta, la captura sale con la pantalla a medio cargar.
  await expect(page.getByText("Proyectos vigilados")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(1200);
  await guardar(page, "07-seguimiento");
});
