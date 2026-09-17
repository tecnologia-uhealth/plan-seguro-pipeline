# -*- coding: utf-8 -*-
"""
Llena el PDF "Orden de Trabajo" de Plan Seguro (AcroForm rellenable) con
los datos del/los asegurado(s).

⚠️ ESTADO ACTUAL: SOLO LA FILA 1 ESTÁ VALIDADA. Carlos confirmó visualmente
que estos campos caen en el lugar correcto (prueba PRUEBA_orden_trabajo_fila1.pdf):
    Text10 = Nombre(s)
    aP1    = Apellido paterno
    APM1   = Apellido materno
    f1_af_date = Fecha de nacimiento
    Text12 = Parentesco

Grupos de MÁS DE 1 asegurado por trámite (confirmado por Carlos, siguiendo
la nota impresa en el propio formulario: "En caso de solicitar más de 4
Altas de asegurados, debe anexar archivo magnético..."):
    - El Excel "Lista de Asegurados" lleva a TODOS los asegurados del grupo
      (sin límite — generar_excel_plan_seguro.py ya lo soporta).
    - El PDF "Orden de Trabajo" solo necesita UNA fila de ejemplo (la
      primera persona de la lista) — no hace falta ni es requerido listar
      a todos físicamente en el PDF, sin importar cuántos sean (2, 4, o 50).
      Se agrega una nota en el campo de descripción indicando que el
      listado completo está en el Excel adjunto.
"""

from datetime import datetime, date
from pypdf import PdfReader, PdfWriter

TEMPLATE_PATH = "orden_trabajo_template.pdf"  # copiar aquí el PDF en blanco real

# Confirmados contra el PDF real, no cambian por trámite
CONTRATANTE_NOMBRE = "U HEALTH"
CONTRATANTE_APELLIDO1 = "INSURTECH"
CONTRATANTE_APELLIDO2 = "SA DE CV"
AGENTE_NOMBRE = "GRUPO CYSE, AGENTE"
AGENTE_APELLIDO1 = "DE SEGUROS Y DE"
AGENTE_APELLIDO2 = "FIANZAS SA DE CV"
CLAVE_AGENTE = "AG014206"
PRODUCTO = "GOLDEN COLECTIVO"  # confirmado: siempre el mismo para las 4 pólizas Vanquish


def _fecha_ddmmyyyy(fecha) -> str:
    if isinstance(fecha, str):
        fecha = datetime.strptime(fecha, "%Y-%m-%d")
    return fecha.strftime("%d-%m-%Y")


def generar_orden_trabajo(
    asegurados: list[dict],
    no_poliza: str,
    fecha_solicitud=None,
    template_path: str = TEMPLATE_PATH,
    salida: str = "/tmp/orden_trabajo.pdf",
) -> str:
    """
    asegurados: lista de dicts con nombre, apellido_paterno, apellido_materno,
        fecha_nacimiento, sexo ("M"/"F"), parentesco
    no_poliza: ej. "LD000854"

    Si asegurados tiene más de 1 elemento, solo el PRIMERO se usa para
    llenar la fila 1 del PDF (como ejemplo/representante del grupo) — el
    Excel "Lista de Asegurados" (generado por separado, con TODOS) es el
    que hace el trabajo real de listar a cada persona. Confirmado por
    Carlos, siguiendo la nota impresa en el propio formulario oficial.
    """
    fecha_solicitud = fecha_solicitud or date.today()

    reader = PdfReader(template_path)
    writer = PdfWriter()
    writer.append(reader)

    a = asegurados[0]

    nota_grupo = (
        "VER ARCHIVO EXCEL ADJUNTO PARA EL LISTADO COMPLETO DE ASEGURADOS. "
        if len(asegurados) > 1
        else ""
    )

    datos = {
        "Fecha4_af_date": fecha_solicitud.strftime("%d/%m/%Y") if isinstance(fecha_solicitud, date) else fecha_solicitud,
        "Text4": no_poliza,
        "Text5": PRODUCTO,
        "Text7": CONTRATANTE_NOMBRE,
        "appelido 1": CONTRATANTE_APELLIDO1,
        "materno1": CONTRATANTE_APELLIDO2,
        "agent nom": AGENTE_NOMBRE,
        "appelido 2": AGENTE_APELLIDO1,
        "materno2": AGENTE_APELLIDO2,
        "Text8": CLAVE_AGENTE,
        "Text9": CLAVE_AGENTE,
        # --- Fila 1 (validada) — representa a todo el grupo si son varios ---
        "Text10": a["nombre"],
        "aP1": a["apellido_paterno"],
        "APM1": a.get("apellido_materno", ""),
        "f1_af_date": _fecha_ddmmyyyy(a["fecha_nacimiento"]),
        "Text12": a.get("parentesco", ""),
        "Text34": nota_grupo + "FAVOR DE DAR DE ALTA, GRACIAS",
        # Sexo (checkbox) — CONFIRMADO: el campo "Check Box2" (fila 1)
        # tiene 2 posiciones con nombres internos inconsistentes por una
        # rareza de codificación del PDF original: "Sí" = Masculino,
        # "F" = Femenino.
        "Check Box2": "Sí" if a["sexo"] == "M" else "F",
    }

    # ⚠️ CRÍTICO: la plantilla puede traer datos reales de un trámite
    # anterior (confirmado — apareció "DIEGO ELIAN CUEVAS ESPINOSA" en la
    # fila 2 sin que nosotros lo hubiéramos puesto ahí). Antes de escribir
    # nada, se borran TODOS los campos del PDF sin excepción, para
    # garantizar que nunca se filtre información de otra persona/trámite,
    # sin importar qué traiga la plantilla.
    campos_existentes = reader.get_fields() or {}
    limpieza = {}
    for nombre_campo, campo in campos_existentes.items():
        tipo_campo = campo.get('/FT')
        if tipo_campo == '/Tx':
            limpieza[nombre_campo] = ""
        # Los checkboxes/radio (/Btn) se dejan tal cual el valor por
        # defecto del PDF (normalmente "Off") — no forzamos ahí porque
        # update_page_form_field_values con "" no aplica bien a botones,
        # y de cualquier forma no representan datos personales por sí solos.

    for pagina in writer.pages:
        if limpieza:
            writer.update_page_form_field_values(pagina, limpieza)

    for pagina in writer.pages:
        writer.update_page_form_field_values(pagina, datos)

    with open(salida, "wb") as f:
        writer.write(f)

    return salida


if __name__ == "__main__":
    # Prueba de 1 sola persona
    ejemplo_individual = [{
        "nombre": "JUAN CARLOS",
        "apellido_paterno": "PEREZ",
        "apellido_materno": "TORRES",
        "fecha_nacimiento": "1995-03-21",
        "sexo": "M",
        "parentesco": "Titular",
    }]
    ruta1 = generar_orden_trabajo(ejemplo_individual, no_poliza="LD000854", salida="/tmp/orden_trabajo_TEST.pdf")
    print("Generado (individual):", ruta1)

    # Prueba de grupo (varias personas — solo la 1ra se usa como ejemplo en el PDF)
    ejemplo_grupo = [
        {"nombre": "JUAN CARLOS", "apellido_paterno": "PEREZ", "apellido_materno": "TORRES",
         "fecha_nacimiento": "1995-03-21", "sexo": "M", "parentesco": "Titular"},
        {"nombre": "MARIA", "apellido_paterno": "LOPEZ", "apellido_materno": "GOMEZ",
         "fecha_nacimiento": "1998-07-10", "sexo": "F", "parentesco": "Cónyuge"},
    ]
    ruta2 = generar_orden_trabajo(ejemplo_grupo, no_poliza="LD000854", salida="/tmp/orden_trabajo_GRUPO_TEST.pdf")
    print("Generado (grupo, solo fila 1 como ejemplo):", ruta2)
