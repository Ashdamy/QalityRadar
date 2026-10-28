import type { Metadata } from "next";
import Link from "next/link";
import { PaginaLegal } from "@/components/PaginaLegal";

export const metadata: Metadata = {
  title: "Política de privacidad",
  description:
    "Qué datos personales trata QalitiRadar, para qué, cuánto tiempo los conserva y cómo ejercer tus derechos según la Ley 1581 de 2012.",
  alternates: { canonical: "/privacidad" },
};

// Los valores entre corchetes los rellena el responsable antes de abrir el
// servicio al publico: son datos de la empresa que el codigo no conoce.
export default function PrivacidadPage() {
  return (
    <PaginaLegal titulo="Política de tratamiento de datos personales" actualizada="28 de octubre de 2026">
      <p>
        Esta política explica qué datos personales trata QalitiRadar, para qué los usa, cuánto tiempo los guarda y
        cómo puedes ejercer tus derechos. Se rige por la <strong>Ley 1581 de 2012</strong>, el Decreto 1377 de 2013
        (compilado en el Decreto 1074 de 2015) y las demás normas colombianas de protección de datos personales.
      </p>

      <h2>1. Quién es el responsable</h2>
      <ul>
        <li>
          <strong>Responsable del tratamiento:</strong> QalitiRadar [TIPO DE SOCIEDAD, p. ej. S.A.S.]
        </li>
        <li>
          <strong>NIT:</strong> [NIT]
        </li>
        <li>
          <strong>Domicilio:</strong> [DIRECCIÓN], [CIUDAD], Colombia
        </li>
        <li>
          <strong>Correo para temas de privacidad:</strong> [CORREO DE PRIVACIDAD]
        </li>
        <li>
          <strong>Teléfono:</strong> [TELÉFONO]
        </li>
      </ul>

      <h2>2. Qué datos tratamos</h2>
      <ul>
        <li>
          <strong>Datos de tu cuenta:</strong> tu correo electrónico y tu contraseña, que guardamos cifrada con bcrypt
          (nunca en claro). Si entras con GitHub, también tu identificador, tu nombre de usuario y tu foto de perfil
          de GitHub, y el token de acceso que GitHub nos da, guardado cifrado.
        </li>
        <li>
          <strong>Lo que analizas:</strong> los repositorios y las direcciones web que nos pides analizar, y los
          resultados: notas, hallazgos, comparaciones, informes y enlaces compartidos.
        </li>
        <li>
          <strong>Registro de seguridad de la cuenta:</strong> entradas, salidas, intentos fallidos, cambios de
          contraseña y vinculaciones con GitHub, con la fecha y la dirección IP desde la que se hicieron.
        </li>
        <li>
          <strong>Prueba de tu autorización:</strong> la fecha en que aceptaste esta política y su versión.
        </li>
      </ul>
      <p>
        No tratamos datos sensibles ni datos de menores de edad. El código de tus repositorios se lee para analizarlo,
        pero no se guarda: se borra al terminar cada análisis.
      </p>

      <h2>3. Para qué los usamos</h2>
      <ul>
        <li>Crear y mantener tu cuenta, y verificar que el correo es tuyo.</li>
        <li>Hacer los análisis que pides, guardar su histórico y avisarte de cambios en los proyectos que vigilas.</li>
        <li>Enviarte los correos necesarios para el servicio: verificar tu correo y recuperar tu contraseña.</li>
        <li>
          Proteger el servicio y tu cuenta: detectar intentos de acceso indebidos, aplicar límites de uso y poder
          investigar un incidente.
        </li>
      </ul>
      <p>
        <strong>No vendemos tus datos, no los usamos para publicidad y no los compartimos con nadie para otros
        fines.</strong>
      </p>

      <h2>4. Con quién se comparten y transferencia internacional</h2>
      <p>Para prestar el servicio usamos estos proveedores, que tratan datos por nuestra cuenta:</p>
      <ul>
        <li>
          <strong>GitHub</strong> (Estados Unidos): para iniciar sesión con GitHub y leer tus repositorios, solo con
          permiso de lectura.
        </li>
        <li>
          <strong>Hugging Face</strong> (Estados Unidos y Unión Europea): redacta el resumen de cada análisis. Solo
          recibe el nombre del repositorio o la dirección analizada, las notas y los títulos de los hallazgos. Nunca tu
          correo ni tu código.
        </li>
        <li>
          <strong>[PROVEEDOR DE CORREO]</strong> ([PAÍS]): envía los correos del servicio.
        </li>
        <li>
          <strong>[PROVEEDORES DE ALOJAMIENTO]</strong> ([PAÍS O PAÍSES]): alojan la aplicación y la base de datos.
        </li>
      </ul>
      <p>
        Algunos de estos proveedores están fuera de Colombia, así que tus datos pueden transferirse a otros países. Al
        aceptar esta política autorizas esa transferencia, que se hace solo con proveedores que ofrecen medidas de
        protección adecuadas. Solo entregaremos datos a una autoridad cuando una ley o una orden judicial lo exija.
      </p>

      <h2>5. Cookies</h2>
      <p>Usamos solo tres cookies, todas necesarias para que la sesión funcione. Ninguna es de publicidad ni de analítica.</p>
      <ul>
        <li>
          <strong>qr_access</strong> y <strong>qr_refresh</strong>: mantienen tu sesión abierta. No son accesibles
          desde JavaScript.
        </li>
        <li>
          <strong>qr_sesion</strong>: solo indica a la interfaz que hay una sesión abierta. No contiene ningún dato
          tuyo.
        </li>
      </ul>

      <h2>6. Cuánto tiempo los guardamos</h2>
      <ul>
        <li>Los datos de tu cuenta, mientras la cuenta exista. Si la borras, se borra todo lo que cuelga de ella.</li>
        <li>
          Los análisis, como máximo 90 días o los 50 más recientes de cada proyecto. Siempre conservamos los 10 últimos
          para que no pierdas el histórico.
        </li>
        <li>El registro de seguridad de la cuenta, 90 días.</li>
        <li>Las cuentas que no verifican su correo, 7 días.</li>
        <li>Las sesiones, como máximo 30 días; las cerradas se borran a diario.</li>
        <li>Los enlaces compartidos, hasta que caducan: entre 1 y 30 días, según elijas.</li>
      </ul>

      <h2>7. Cómo los protegemos</h2>
      <p>
        Contraseñas cifradas con bcrypt, token de GitHub cifrado, sesión en cookies que JavaScript no puede leer,
        conexiones cifradas, límites contra intentos repetidos y análisis dentro de contenedores aislados sin acceso a
        la red. Ningún sistema es infalible: si ocurriera un incidente que afecte a tus datos, te avisaremos y lo
        comunicaremos a la Superintendencia de Industria y Comercio como exige la ley.
      </p>

      <h2>8. Tus derechos</h2>
      <p>Como titular de tus datos tienes derecho a:</p>
      <ul>
        <li>Conocer, actualizar y rectificar tus datos personales.</li>
        <li>Pedir prueba de la autorización que nos diste.</li>
        <li>Ser informado sobre el uso que hacemos de tus datos.</li>
        <li>
          Presentar quejas ante la <strong>Superintendencia de Industria y Comercio</strong> por infracciones a la
          ley, una vez hayas agotado el trámite de reclamo ante nosotros.
        </li>
        <li>Revocar la autorización y pedir que borremos tus datos, cuando no exista un deber legal de conservarlos.</li>
        <li>Acceder gratuitamente a tus datos.</li>
      </ul>
      <p>
        Puedes ver tus datos y borrar tu cuenta tú mismo, en cualquier momento, desde{" "}
        <Link href="/cuenta">Mi cuenta</Link>.
      </p>

      <h2>9. Cómo ejercerlos</h2>
      <p>
        Escribe a <strong>[CORREO DE PRIVACIDAD]</strong> desde el correo de tu cuenta, indicando qué pides. Este
        canal lo atiende [ÁREA O PERSONA RESPONSABLE].
      </p>
      <ul>
        <li>
          <strong>Consultas</strong> (qué datos tenemos y cómo los usamos): respondemos en un máximo de 10 días
          hábiles. Si no fuera posible, te diremos por qué y responderemos en los 5 días hábiles siguientes.
        </li>
        <li>
          <strong>Reclamos</strong> (corregir, actualizar o borrar datos, o revocar la autorización): incluye tu
          identificación, la descripción de los hechos y los documentos que quieras aportar. Respondemos en un máximo de
          15 días hábiles, ampliables 8 días hábiles más si es necesario, avisándote del motivo.
        </li>
      </ul>

      <h2>10. Cambios en esta política</h2>
      <p>
        Si la cambiamos de forma sustancial, te avisaremos por correo o al entrar, antes de que el cambio se aplique, y
        te pediremos que la aceptes de nuevo cuando la ley lo exija. Esta versión rige desde el 28 de octubre de 2026.
      </p>
    </PaginaLegal>
  );
}
