"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ApiError,
  changePassword,
  deleteAccount,
  disconnectGithub,
  getGithubAuthorizationUrl,
  getMe,
  logoutAll,
  type Me,
} from "@/lib/api";
import { clearToken, endSession, haySesion } from "@/lib/auth";
import { RadarMark } from "@/components/RadarMark";
import { TextField } from "@/components/TextField";
import { PrimaryButton } from "@/components/PrimaryButton";
import { GithubButton } from "@/components/GithubButton";
import { Cargando } from "@/components/RadarCargando";

function mensajeDeError(err: unknown, porDefecto: string): string {
  if (err instanceof ApiError) {
    if (err.status === 422) return "La contraseña nueva debe tener entre 8 y 72 caracteres.";
    return err.message;
  }
  return porDefecto;
}

function Seccion({ titulo, children, peligro }: { titulo: string; children: ReactNode; peligro?: boolean }) {
  return (
    <section
      aria-labelledby={`sec-${titulo}`}
      className={`rounded-[10px] border bg-surface p-6 ${peligro ? "border-bad/50" : "border-border"}`}
    >
      <h2 id={`sec-${titulo}`} className={`mb-4 text-[15px] font-semibold ${peligro ? "text-bad" : ""}`}>
        {titulo}
      </h2>
      {children}
    </section>
  );
}

function Fila({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border py-3 last:border-b-0">
      <span className="text-[13px] text-muted">{etiqueta}</span>
      <span className="text-[13.5px]">{children}</span>
    </div>
  );
}

export default function CuentaPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [errorCarga, setErrorCarga] = useState<string | null>(null);

  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [confirmar, setConfirmar] = useState("");
  const [claveEstado, setClaveEstado] = useState<{ ok: boolean; texto: string } | null>(null);
  const [guardandoClave, setGuardandoClave] = useState(false);

  const [githubOcupado, setGithubOcupado] = useState(false);
  const [errorGithub, setErrorGithub] = useState<string | null>(null);

  const [borrando, setBorrando] = useState(false);
  const [claveBorrar, setClaveBorrar] = useState("");
  const [errorBorrar, setErrorBorrar] = useState<string | null>(null);

  useEffect(() => {
    if (!haySesion()) {
      router.replace("/entrar");
      return;
    }
    getMe()
      .then(setMe)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          clearToken();
          router.replace("/entrar");
          return;
        }
        setErrorCarga("No se pudieron cargar los datos de tu cuenta.");
      });
  }, [router]);

  async function handleCambiarClave(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setClaveEstado(null);
    if (nueva !== confirmar) {
      setClaveEstado({ ok: false, texto: "Las contraseñas nuevas no coinciden." });
      return;
    }
    setGuardandoClave(true);
    try {
      await changePassword(actual, nueva);
      setActual("");
      setNueva("");
      setConfirmar("");
      setClaveEstado({ ok: true, texto: "Contraseña cambiada. Cerramos tus sesiones en otros dispositivos." });
    } catch (err) {
      setClaveEstado({ ok: false, texto: mensajeDeError(err, "No se pudo cambiar la contraseña.") });
    } finally {
      setGuardandoClave(false);
    }
  }

  async function handleDesconectarGithub() {
    setErrorGithub(null);
    setGithubOcupado(true);
    try {
      await disconnectGithub();
      setMe((m) => (m ? { ...m, github_connected: false } : m));
    } catch (err) {
      setErrorGithub(mensajeDeError(err, "No se pudo desconectar GitHub."));
    } finally {
      setGithubOcupado(false);
    }
  }

  async function handleConectarGithub() {
    setErrorGithub(null);
    setGithubOcupado(true);
    try {
      const { authorization_url } = await getGithubAuthorizationUrl();
      window.location.href = authorization_url;
    } catch (err) {
      setErrorGithub(mensajeDeError(err, "No se pudo iniciar la conexión con GitHub."));
      setGithubOcupado(false);
    }
  }

  async function handleCerrarEnTodas() {
    await logoutAll().catch(() => {});
    clearToken();
    router.replace("/entrar");
  }

  async function handleBorrar() {
    setErrorBorrar(null);
    try {
      await deleteAccount(claveBorrar || undefined);
      clearToken();
      router.replace("/");
    } catch (err) {
      setErrorBorrar(mensajeDeError(err, "No se pudo borrar la cuenta."));
    }
  }

  return (
    <main className="flex min-h-screen w-full flex-col bg-bg text-text">
      <div className="flex items-center justify-between border-b border-border px-8 py-4">
        <button
          type="button"
          onClick={() => router.push("/analyze")}
          className="flex items-center gap-[10px] focus:outline-none focus:ring-[3px] focus:ring-accentDim"
        >
          <RadarMark size={20} />
          <span className="text-[14.5px] font-semibold">QalitiRadar</span>
        </button>
        <button
          type="button"
          onClick={async () => {
            await endSession();
            router.push("/");
          }}
          className="text-[13px] text-muted hover:text-text focus:outline-none focus:ring-[3px] focus:ring-accentDim"
        >
          Cerrar sesión
        </button>
      </div>

      <div className="mx-auto flex w-full max-w-[640px] flex-col gap-5 px-6 py-10">
        <div>
          <h1 className="mb-1 text-[22px] font-semibold tracking-[-0.01em]">Mi cuenta</h1>
          <p className="text-[13.5px] text-muted">Tus datos, tu contraseña y tus conexiones.</p>
        </div>

        {errorCarga && (
          <p role="alert" className="text-[13px] text-bad">
            {errorCarga}
          </p>
        )}

        {!me && !errorCarga && <Cargando className="text-[13px] text-muted">Cargando…</Cargando>}

        {me && (
          <>
            <Seccion titulo="Perfil">
              <Fila etiqueta="Correo">{me.email}</Fila>
              <Fila etiqueta="Correo verificado">{me.email_verified ? "Sí" : "Pendiente"}</Fila>
              <Fila etiqueta="Miembro desde">
                {new Date(me.created_at).toLocaleDateString("es", { year: "numeric", month: "long", day: "numeric" })}
              </Fila>
            </Seccion>

            <Seccion titulo="GitHub">
              {me.github_connected ? (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-[13.5px]">
                    Conectado{me.github_username ? <> como <strong>@{me.github_username}</strong></> : null}. Podemos
                    leer tus repositorios.
                  </p>
                  <button
                    type="button"
                    disabled={githubOcupado}
                    onClick={handleDesconectarGithub}
                    className="min-h-[40px] rounded-[6px] border border-border px-3 text-[13px] text-muted hover:text-text disabled:opacity-60 focus:outline-none focus:ring-[3px] focus:ring-accentDim"
                  >
                    Desconectar
                  </button>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  <p className="text-[13.5px] text-muted">
                    Sin conectar. Conéctalo para analizar tus repositorios.
                    {me.github_username ? " Podrás seguir entrando con GitHub igualmente." : ""}
                  </p>
                  <GithubButton label="Conectar con GitHub" onClick={handleConectarGithub} disabled={githubOcupado} />
                </div>
              )}
              {errorGithub && (
                <p role="alert" className="mt-2 text-[12.5px] text-bad">
                  {errorGithub}
                </p>
              )}
            </Seccion>

            <Seccion titulo="Contraseña">
              {me.has_password ? (
                <form onSubmit={handleCambiarClave} className="flex flex-col gap-[14px]">
                  <TextField
                    id="actual"
                    label="Contraseña actual"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={actual}
                    onChange={(e) => setActual(e.target.value)}
                  />
                  <TextField
                    id="nueva"
                    label="Contraseña nueva"
                    type="password"
                    autoComplete="new-password"
                    placeholder="Mínimo 8 caracteres"
                    required
                    minLength={8}
                    maxLength={72}
                    value={nueva}
                    onChange={(e) => setNueva(e.target.value)}
                  />
                  <TextField
                    id="confirmar"
                    label="Confirmar contraseña nueva"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={confirmar}
                    onChange={(e) => setConfirmar(e.target.value)}
                  />
                  {claveEstado && (
                    <p
                      role={claveEstado.ok ? "status" : "alert"}
                      className={`text-[12.5px] ${claveEstado.ok ? "text-good" : "text-bad"}`}
                    >
                      {claveEstado.texto}
                    </p>
                  )}
                  <PrimaryButton type="submit" disabled={guardandoClave} className="self-start">
                    {guardandoClave ? "Guardando…" : "Cambiar contraseña"}
                  </PrimaryButton>
                </form>
              ) : (
                <p className="text-[13.5px] text-muted">
                  Entras con GitHub y no tienes contraseña. Si quieres poder entrar también con tu correo,{" "}
                  <Link href="/recuperar-contrasena" className="text-accent hover:underline">
                    crea una con un enlace por correo
                  </Link>
                  .
                </p>
              )}
            </Seccion>

            <Seccion titulo="Sesiones">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="max-w-[380px] text-[13.5px] text-muted">
                  ¿Dejaste la sesión abierta en un ordenador ajeno? Ciérrala en todos tus dispositivos, este incluido.
                </p>
                <button
                  type="button"
                  onClick={handleCerrarEnTodas}
                  className="min-h-[40px] rounded-[6px] border border-border px-3 text-[13px] hover:border-muted focus:outline-none focus:ring-[3px] focus:ring-accentDim"
                >
                  Cerrar en todas partes
                </button>
              </div>
            </Seccion>

            <Seccion titulo="Borrar la cuenta" peligro>
              {!borrando ? (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="max-w-[380px] text-[13.5px] text-muted">
                    Se borra todo: repositorios, análisis, informes compartidos y el token de GitHub.
                  </p>
                  <button
                    type="button"
                    onClick={() => setBorrando(true)}
                    className="min-h-[40px] rounded-[6px] border border-bad px-3 text-[13px] text-bad focus:outline-none focus:ring-[3px] focus:ring-accentDim"
                  >
                    Borrar mi cuenta
                  </button>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  <p className="text-[13.5px] text-muted">
                    <strong className="text-text">No se puede deshacer.</strong>
                    {me.has_password ? " Escribe tu contraseña para confirmar." : " Pulsa de nuevo para confirmar."}
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    {me.has_password && (
                      <input
                        type="password"
                        value={claveBorrar}
                        onChange={(e) => setClaveBorrar(e.target.value)}
                        placeholder="Tu contraseña"
                        aria-label="Contraseña para confirmar el borrado"
                        autoComplete="current-password"
                        className="min-h-[40px] min-w-0 flex-1 rounded-[6px] border border-border bg-bg px-[10px] text-[13px] text-text placeholder:text-faint focus:border-accent focus:outline-none focus:ring-[3px] focus:ring-accentDim"
                      />
                    )}
                    <button
                      type="button"
                      onClick={handleBorrar}
                      className="min-h-[40px] shrink-0 rounded-[6px] bg-bad px-3 text-[13px] font-semibold text-bg focus:outline-none focus:ring-[3px] focus:ring-accentDim"
                    >
                      Borrar definitivamente
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setBorrando(false);
                        setClaveBorrar("");
                        setErrorBorrar(null);
                      }}
                      className="min-h-[40px] shrink-0 px-2 text-[13px] text-muted hover:text-text focus:outline-none focus:ring-[3px] focus:ring-accentDim"
                    >
                      Cancelar
                    </button>
                  </div>
                  {errorBorrar && (
                    <p role="alert" className="text-[12.5px] text-bad">
                      {errorBorrar}
                    </p>
                  )}
                </div>
              )}
            </Seccion>
          </>
        )}
      </div>
    </main>
  );
}
