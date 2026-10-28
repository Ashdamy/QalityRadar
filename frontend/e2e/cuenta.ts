import { expect, type Page } from "@playwright/test";

/**
 * Crear una cuenta ya no basta para entrar: hay que abrir el enlace que llega
 * por correo. Las pruebas lo leen de Mailpit, la bandeja falsa del
 * docker-compose, así que el backend tiene que estar enviando ahí
 * (SMTP_HOST=localhost, SMTP_PORT=1025, SMTP_STARTTLS=false). Con un SMTP real
 * los correos irían de verdad a direcciones @example.com.
 */
const MAILPIT = process.env.MAILPIT_URL ?? "http://localhost:8025";

async function enlaceDeVerificacion(email: string): Promise<string> {
  const limite = Date.now() + 30_000;
  while (Date.now() < limite) {
    const busqueda = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`);
    const { messages } = (await busqueda.json()) as { messages: { ID: string }[] };
    if (messages.length > 0) {
      const mensaje = await fetch(`${MAILPIT}/api/v1/message/${messages[0].ID}`);
      const { Text } = (await mensaje.json()) as { Text: string };
      const enlace = Text.match(/https?:\/\/\S+\/verificar-email#token=\S+/);
      if (enlace) return enlace[0];
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`No llegó a Mailpit el correo de verificación de ${email}`);
}

export async function crearCuentaYEntrar(page: Page, email: string, contrasena: string) {
  await page.goto("/entrar");
  await page.getByRole("button", { name: "Crear cuenta" }).first().click();
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(contrasena);
  await page.locator("#confirmPassword").fill(contrasena);
  await page.getByRole("button", { name: "Crear cuenta" }).last().click();
  await expect(page.getByText(`Te enviamos un enlace a ${email}`)).toBeVisible({ timeout: 60_000 });

  await page.goto(await enlaceDeVerificacion(email));
  await expect(page.getByRole("heading", { name: "Correo confirmado" })).toBeVisible({ timeout: 60_000 });

  await page.goto("/entrar");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(contrasena);
  await page.getByRole("button", { name: "Iniciar sesión" }).last().click();
  // Margen amplio: en desarrollo, Next compila cada ruta la primera vez que
  // se visita, y esa compilacion puede tardar mas que el registro entero.
  await expect(page).toHaveURL(/\/analyze/, { timeout: 60_000 });
}
