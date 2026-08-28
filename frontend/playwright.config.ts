import { defineConfig, devices } from "@playwright/test";

/**
 * Pruebas end-to-end contra la aplicación real: navegador, frontend, backend,
 * worker, Postgres y Redis. No se simula nada.
 *
 * No arrancan los servicios (`webServer`) a propósito: el backend necesita el
 * worker, Docker y las variables de entorno del host, y levantarlo desde aquí
 * duplicaría esa configuración en un segundo sitio donde se desincronizaría.
 * Se ejecutan contra los servicios ya en marcha.
 */
export default defineConfig({
  testDir: "./e2e",
  // Un análisis real tarda decenas de segundos; el valor por defecto de 30 s
  // haría fallar pruebas que en realidad van bien.
  timeout: 180_000,
  expect: { timeout: 15_000 },
  // En serie: los análisis compiten por el límite de 2 simultáneos por
  // usuario, y en paralelo se estorbarían entre ellos.
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
