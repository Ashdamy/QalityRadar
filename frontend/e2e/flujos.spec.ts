import { expect, test, type Page } from "@playwright/test";

/**
 * Recorridos completos contra la aplicación real: navegador → frontend →
 * backend → worker → Postgres/Redis. Nada simulado.
 *
 * Alcance declarado: el flujo de URL se prueba entero porque solo necesita una
 * cuenta con contraseña. Los flujos de repositorio y combinado **no** se
 * automatizan aquí: ambos parten de repositorios traídos de GitHub, y eso
 * exige un token OAuth real que no se puede obtener sin intervención humana.
 * Fingir ese paso probaría el simulacro, no el sistema. De esos dos flujos se
 * comprueba lo que sí es honesto comprobar: que la pantalla existe, exige
 * sesión y pide lo que debe.
 */

// Una cuenta nueva por prueba. Compartirla haria que el segundo registro
// devolviera 409 y la pantalla se quedara en el formulario; ademas cada cuenta
// arranca con su limite de uso intacto.
//
// example.com y no example.test: los dominios reservados (.test, .local,
// .invalid) los rechaza el validador de email del backend.
const CONTRASENA = "contrasena-de-prueba-123";
let secuencia = 0;

function emailNuevo(): string {
  secuencia += 1;
  return `e2e-${Date.now()}-${secuencia}@example.com`;
}

// Página pública, estable y ligera. Se analiza una sola vez por ejecución.
const URL_OBJETIVO = "https://example.com";

async function crearCuentaYEntrar(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Crear cuenta" }).first().click();
  await page.locator("#email").fill(emailNuevo());
  await page.locator("#password").fill(CONTRASENA);
  await page.locator("#confirmPassword").fill(CONTRASENA);
  await page.getByRole("button", { name: "Crear cuenta" }).last().click();
  // Margen amplio: en desarrollo, Next compila cada ruta la primera vez que
  // se visita, y esa compilacion puede tardar mas que el registro entero.
  await expect(page).toHaveURL(/\/analyze/, { timeout: 60_000 });
}

// Se visitan todas las rutas una vez antes de empezar. En desarrollo, la
// primera visita a cada una dispara su compilacion, y ese coste no tiene nada
// que ver con lo que se quiere medir.
test.beforeAll(async ({ browser }) => {
  const contexto = await browser.newContext();
  const pagina = await contexto.newPage();
  for (const ruta of ["/", "/analyze", "/analyze/url", "/analyze/combined", "/repositories"]) {
    await pagina.goto(ruta).catch(() => {});
  }
  await contexto.close();
});

test.describe("Flujo de URL, de principio a fin", () => {
  test("registro, análisis, resultado, compartir y enlace público", async ({ page }) => {
    await crearCuentaYEntrar(page);

    // -- Elegir modo -------------------------------------------------------
    await expect(page.getByRole("heading", { name: "¿Qué quieres analizar?" })).toBeVisible();
    await page.getByRole("button", { name: /Analizar URL/ }).click();
    await expect(page).toHaveURL(/\/analyze\/url/);

    // -- Lanzar el análisis ------------------------------------------------
    await page.locator("#url").fill(URL_OBJETIVO);
    await page.getByRole("button", { name: "Analizar", exact: true }).click();

    // El análisis es real: se descarga la página y se puntúan cinco
    // dimensiones, así que puede tardar.
    await expect(page.getByRole("heading", { name: "Análisis completado" })).toBeVisible({
      timeout: 150_000,
    });

    // -- El resultado tiene contenido real ---------------------------------
    await expect(page.getByText("Puntuación", { exact: true })).toBeVisible();
    await expect(page.getByText("Confianza", { exact: true })).toBeVisible();
    // Cinco dimensiones en el modo URL.
    await expect(page.getByText(/Puntuación sobre 5 dimensiones/)).toBeVisible();

    // -- Compartir ---------------------------------------------------------
    await page.getByRole("button", { name: "Compartir" }).click();
    const campoEnlace = page.getByLabel("Enlace público al informe");
    await expect(campoEnlace).toBeVisible({ timeout: 20_000 });

    const enlace = await campoEnlace.inputValue();
    expect(enlace).toContain("/r/");
    await expect(page.getByText(/Cualquiera con el enlace/)).toBeVisible();

    // -- El enlace funciona SIN sesión -------------------------------------
    // Contexto nuevo y limpio: sin él, el localStorage de la sesión actual
    // haría pasar la prueba aunque el endpoint exigiera autenticación.
    const anonimo = await page.context().browser()!.newContext();
    const paginaAnonima = await anonimo.newPage();
    await paginaAnonima.goto(enlace);
    await expect(paginaAnonima.getByText("Informe compartido")).toBeVisible({
      timeout: 30_000,
    });
    await expect(paginaAnonima.getByText("Puntuación", { exact: true })).toBeVisible();
    await anonimo.close();
  });

  test("un enlace inventado no revela nada", async ({ page }) => {
    await page.goto("/r/este-token-no-existe");
    await expect(page.getByText(/no existe o ha caducado/)).toBeVisible({ timeout: 30_000 });
  });
});

test.describe("Puertas de acceso", () => {
  test("las pantallas con sesión redirigen si no la hay", async ({ page }) => {
    for (const ruta of ["/analyze", "/analyze/url", "/analyze/combined", "/repositories"]) {
      await page.goto(ruta);
      await expect(page).toHaveURL("http://localhost:3000/", { timeout: 15_000 });
    }
  });

  test("el modo combinado pide repositorio y dirección", async ({ page }) => {
    await crearCuentaYEntrar(page);
    await page.goto("/analyze/combined");

    await expect(
      page.getByRole("heading", { name: /Compara tu repositorio con su despliegue/ }),
    ).toBeVisible();
    await expect(page.locator("#repositorio")).toBeVisible();
    await expect(page.locator("#url")).toBeVisible();

    // Sin los dos campos rellenos no se puede lanzar nada.
    await expect(page.getByRole("button", { name: /Analizar ambos/ })).toBeDisabled();
  });

  test("los tres modos se ofrecen desde la pantalla de inicio", async ({ page }) => {
    await crearCuentaYEntrar(page);
    for (const modo of ["Analizar repositorio", "Analizar URL", "Analizar ambos"]) {
      await expect(page.getByRole("heading", { name: modo })).toBeVisible();
    }
  });
});
