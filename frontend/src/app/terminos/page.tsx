import type { Metadata } from "next";
import Link from "next/link";
import { PaginaLegal } from "@/components/PaginaLegal";

export const metadata: Metadata = {
  title: "Términos de uso",
  description: "Las condiciones para usar QalitiRadar: qué ofrece el servicio, qué puedes hacer con él y sus límites.",
  alternates: { canonical: "/terminos" },
};

export default function TerminosPage() {
  return (
    <PaginaLegal titulo="Términos de uso" actualizada="28 de octubre de 2026">
      <p>
        Estos términos regulan el uso de QalitiRadar, un servicio de QalitiRadar [TIPO DE SOCIEDAD], NIT [NIT], con
        domicilio en [DIRECCIÓN], [CIUDAD], Colombia. Al crear una cuenta o entrar con GitHub los aceptas. Si no estás
        de acuerdo, no uses el servicio.
      </p>

      <h2>1. Qué es QalitiRadar</h2>
      <p>
        Una herramienta que analiza repositorios de código y aplicaciones web desplegadas, y resume su calidad con una
        nota basada en el modelo ISO/IEC 25010. Hoy es gratuita y tiene límites de uso por cuenta. Podemos cambiar sus
        funciones o sus límites; si alguna vez introducimos planes de pago, te avisaremos antes y nunca cobraremos nada
        que no hayas contratado expresamente.
      </p>

      <h2>2. Tu cuenta</h2>
      <ul>
        <li>Debes ser mayor de edad y usar un correo que sea tuyo.</li>
        <li>Eres responsable de guardar tu contraseña y de lo que se haga desde tu cuenta.</li>
        <li>Una persona, una cuenta: crear varias para saltarse los límites de uso no está permitido.</li>
        <li>
          Puedes borrar tu cuenta cuando quieras desde <Link href="/cuenta">Mi cuenta</Link>.
        </li>
      </ul>

      <h2>3. Uso aceptable</h2>
      <p>Te comprometes a:</p>
      <ul>
        <li>
          Analizar solo repositorios públicos o sobre los que tengas derecho, y aplicaciones web que sean tuyas, que
          estés autorizado a evaluar o que sean de acceso público.
        </li>
        <li>No usar el servicio para atacar, saturar o buscar vulnerabilidades en sistemas de terceros sin permiso.</li>
        <li>No intentar saltarte los límites de uso, el aislamiento de los análisis ni la seguridad del servicio.</li>
        <li>No usar el servicio para nada contrario a la ley colombiana.</li>
      </ul>
      <p>
        Si encuentras un fallo de seguridad en QalitiRadar, escríbenos a [CORREO DE CONTACTO] antes de publicarlo. Lo
        agradecemos y lo corregiremos.
      </p>

      <h2>4. Tu contenido</h2>
      <p>
        Tu código y tus aplicaciones siguen siendo tuyos. Nos das permiso solo para leerlos y analizarlos con el fin de
        prestarte el servicio. El código no se guarda: se borra al terminar cada análisis. Los resultados quedan en tu
        cuenta, y si compartes un informe con un enlace, quien lo tenga podrá verlo hasta que caduque.
      </p>

      <h2>5. Qué significan los resultados</h2>
      <p>
        La nota es una <strong>aproximación automática</strong> al modelo ISO/IEC 25010.{" "}
        <strong>No es una certificación oficial</strong>, no garantiza que tu software sea seguro ni que esté libre de
        errores, y no sustituye una auditoría profesional. Los resúmenes los redacta un modelo de inteligencia
        artificial y pueden contener imprecisiones. Las decisiones que tomes con ellos son tuyas.
      </p>

      <h2>6. Disponibilidad</h2>
      <p>
        Hacemos lo posible para que el servicio funcione siempre, pero puede haber interrupciones, errores o análisis
        que fallen. El servicio se ofrece tal como está, sin garantías distintas de las que exige la ley.
      </p>

      <h2>7. Responsabilidad</h2>
      <p>
        En la medida en que la ley colombiana lo permita, QalitiRadar no responde por daños indirectos, pérdida de
        datos, de ingresos o de oportunidades derivados del uso del servicio o de decisiones tomadas a partir de sus
        resultados. Nada en estos términos limita los derechos que te reconoce la ley como consumidor.
      </p>

      <h2>8. Suspensión</h2>
      <p>
        Podemos suspender o cerrar una cuenta que incumpla estos términos, especialmente si pone en riesgo el servicio o
        a terceros. Cuando sea posible, te avisaremos antes y te explicaremos el motivo.
      </p>

      <h2>9. Datos personales</h2>
      <p>
        Cómo tratamos tus datos está en la <Link href="/privacidad">Política de tratamiento de datos personales</Link>,
        que forma parte de estos términos.
      </p>

      <h2>10. Cambios</h2>
      <p>
        Si cambiamos estos términos de forma importante, te avisaremos antes de que se apliquen. Seguir usando el
        servicio después del aviso supone aceptarlos.
      </p>

      <h2>11. Ley aplicable</h2>
      <p>
        Estos términos se rigen por las leyes de la República de Colombia. Cualquier controversia se resolverá ante los
        jueces de [CIUDAD], salvo que la ley de protección al consumidor te permita acudir a otros.
      </p>

      <h2>12. Contacto</h2>
      <p>Para cualquier duda sobre estos términos, escríbenos a [CORREO DE CONTACTO].</p>
    </PaginaLegal>
  );
}
