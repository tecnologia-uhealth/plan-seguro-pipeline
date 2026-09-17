# -*- coding: utf-8 -*-
"""
RPA de Plan Seguro — reconstruido a partir de una grabación REAL con
`playwright codegen` (rpa_plan_seguro_grabado.py, sept 2026). A diferencia
de la versión anterior, estos selectores SÍ están confirmados contra el
portal real, mayormente por ID (#selectProcedure, #inputAttachedDoc0, etc.)
que son mucho más estables que buscar por texto visible.

⚠️ LO QUE SIGUE SIN CONFIRMAR:
    1. El contenido exacto del diálogo final (después de "Enviar el
       trámite al contratante") — la grabación solo hizo clic genérico
       sobre el diálogo sin leer su contenido. Este script SÍ intenta leer
       el texto de ese diálogo antes de cerrarlo, por si trae el folio,
       pero no está confirmado que el folio aparezca ahí (podría aparecer
       solo hasta el correo de confirmación que llega después, que ya es
       parte del paso manual de Carlos).
    2. #selectPolicyValidites — ambas grabaciones (alta y baja) seleccionaron
       la única opción disponible en ese momento ("01/02/2026-01/02/2027").
       Este script selecciona automáticamente la PRIMERA opción disponible
       del desplegable, asumiendo que normalmente solo hay una vigencia
       activa por póliza.

VALORES CONFIRMADOS (de 2 grabaciones reales — alta y baja):
    #selectProcedure = "15"                    → Modificación de Póliza
    #selectProcedureSubtype = "7" (alta) / "8" (baja)
    #selectProcedureTypeDummy = "COLECTIVO"    → SOLO aparece en el flujo
                                                  de ALTA, no en el de BAJA
                                                  (confirmado con 2 grabaciones
                                                  reales — no es un descuido,
                                                  es una diferencia real del
                                                  portal)
    #selectProcedureSubtype2 = "2"             → Persona Moral (ambos flujos)
    #inputAttachedDoc0 = Lista de asegurados (Excel) — el ÚNICO archivo
                          obligatorio para BAJA
    #inputAttachedDoc1 = Cuestionarios médicos (Orden de Trabajo) — SOLO
                          para ALTA, no existe/no aplica en BAJA
    #inputAttachedDoc2 = Identificación oficial (INE) — OPCIONAL, se sube
                          solo si se recibe (confirmado: el portal no la exige)
    Para BAJA existe además un campo opcional "Acta de defunción" (sin
    asterisco, no obligatorio) — no confirmado su selector todavía, se deja
    sin implementar por ahora ya que no es requerido.
"""

import os
import base64
import tempfile
import logging
from playwright.sync_api import sync_playwright

log = logging.getLogger("rpa_plan_seguro")

PLAN_SEGURO_USER = os.environ.get("PLAN_SEGURO_USER")
PLAN_SEGURO_PASS = os.environ.get("PLAN_SEGURO_PASS")

PORTAL_LOGIN_URL = "https://oficina.planseguro.com.mx/"

# Confirmado con 2 grabaciones reales — alta y baja.
VALORES_SUBTIPO_TRAMITE = {
    "alta": "7",
    "baja": "8",
}


class TipoMovimientoNoConfirmadoError(Exception):
    """Se lanza si se pide un tipo_movimiento distinto de 'alta'/'baja'
    (los únicos 2 confirmados con grabaciones reales)."""
    pass


class RPAError(Exception):
    """Envuelve cualquier error real del RPA (selector no encontrado, timeout,
    etc.) junto con una captura de pantalla en base64 del momento exacto del
    fallo, para poder diagnosticar sin tener que correrlo con headless=False."""
    def __init__(self, mensaje, screenshot_base64=None):
        super().__init__(mensaje)
        self.screenshot_base64 = screenshot_base64


def emitir_movimiento_plan_seguro(
    no_poliza: str,
    tipo_movimiento: str,  # "alta" o "baja" — ambos confirmados
    lista_asegurados_path: str,
    correo_contratante_aprobacion: str,
    orden_trabajo_path: str | None = None,     # solo para ALTA
    ine_base64: str | None = None,              # solo para ALTA
    ine_nombre_archivo: str = "identificacion.pdf",
    acta_defuncion_path: str | None = None,     # opcional, solo BAJA
    headless: bool = True,
) -> str:
    if tipo_movimiento not in VALORES_SUBTIPO_TRAMITE:
        raise TipoMovimientoNoConfirmadoError(
            f"El tipo de movimiento '{tipo_movimiento}' no está soportado. "
            f"Solo 'alta' y 'baja' están confirmados con grabaciones reales."
        )

    if not PLAN_SEGURO_USER or not PLAN_SEGURO_PASS:
        raise RuntimeError(
            "Faltan las variables de entorno PLAN_SEGURO_USER / PLAN_SEGURO_PASS"
        )

    ine_path = None
    if tipo_movimiento == "alta":
        if not orden_trabajo_path:
            raise ValueError("orden_trabajo_path es obligatorio para ALTA.")
        # Identificación oficial: OPCIONAL — confirmado que el portal NO la
        # exige (no tiene asterisco de obligatorio), a diferencia de "Lista
        # de asegurados". Se sube solo si llega.
        if ine_base64:
            ine_path = os.path.join(tempfile.gettempdir(), ine_nombre_archivo)
            with open(ine_path, "wb") as f:
                f.write(base64.b64decode(ine_base64))

    mensaje = (
        "hola buen día por favor dar de alta al siguiente asegurado, gracias."
        if tipo_movimiento == "alta"
        else "HOLA BUEN DÍA, FAVOR DE DAR DE BAJA A LA SIGUIENTE PERSONA, GRACIAS."
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        try:
            # --- 1. Login ---
            page.goto(PORTAL_LOGIN_URL)
            page.get_by_role("textbox", name="Usuario").click()
            page.get_by_role("textbox", name="Usuario").fill(PLAN_SEGURO_USER)
            page.get_by_role("textbox", name="Contraseña").click()
            page.get_by_role("textbox", name="Contraseña").fill(PLAN_SEGURO_PASS)
            page.get_by_role("button", name="Continuar").click()

            # Modal "Actualiza tu información" — puede no aparecer siempre
            try:
                page.get_by_role("button", name="En otro momento").click(timeout=8000)
            except Exception:
                log.info("No apareció el modal 'Actualiza tu información' (o ya se había mostrado antes).")

            # --- 2. Trámites -> Ingreso de trámites ---
            page.get_by_role("link", name="Trámites").click()
            page.get_by_role("button", name=" Ingreso de trámites").click()

            # --- 3. Selecciona trámite: Modificación de Póliza -> Alta/Baja -> [Colectivo solo en alta] -> Persona Moral ---
            page.locator("#selectProcedure").select_option("15")  # Modificación de Póliza
            page.locator("#selectProcedureSubtype").select_option(
                VALORES_SUBTIPO_TRAMITE[tipo_movimiento]
            )
            if tipo_movimiento == "alta":
                # Confirmado con 2 grabaciones: este dropdown SOLO aparece
                # en el flujo de alta, no en el de baja.
                page.locator("#selectProcedureTypeDummy").select_option("COLECTIVO")
            page.locator("#selectProcedureSubtype2").select_option("2")  # Persona Moral

            # --- 4. Número de póliza + Validar ---
            campo_poliza = page.get_by_role("textbox", name="Ingresa número de póliza (")
            campo_poliza.click()
            campo_poliza.fill(no_poliza)
            page.get_by_text("Validar").click()

            # --- 5. Vigencia — seleccionar la primera opción disponible ---
            select_vigencia = page.locator("#selectPolicyValidites")
            select_vigencia.wait_for(state="visible", timeout=15000)
            opciones = select_vigencia.locator("option").all()
            valores_opciones = [
                o.get_attribute("value") for o in opciones if o.get_attribute("value")
            ]
            if not valores_opciones:
                raise RuntimeError(
                    f"No se encontró ninguna vigencia disponible para la póliza {no_poliza}. "
                    "Puede que el número de póliza sea incorrecto o esté inactiva."
                )
            select_vigencia.select_option(valores_opciones[0])

            # --- 6. Mensaje ---
            campo_mensaje = page.get_by_role("textbox", name="Captura una descripción")
            campo_mensaje.click()
            campo_mensaje.fill(mensaje)

            # --- 7. Subir archivos — varía según tipo de movimiento ---
            # BAJA: solo Lista de asegurados (obligatorio) + Acta de defunción (opcional)
            # ALTA: Lista de asegurados + Cuestionarios médicos (Orden de Trabajo) + Identificación oficial
            page.locator("#inputAttachedDoc0").set_input_files(lista_asegurados_path)
            if tipo_movimiento == "alta":
                page.locator("#inputAttachedDoc1").set_input_files(orden_trabajo_path)
                if ine_path:
                    page.locator("#inputAttachedDoc2").set_input_files(ine_path)
                    page.locator("#selectIdentifierTypeSelection2").select_option("INE")
                # Checkbox/consentimiento visto en la grabación de ALTA justo antes de registrar
                page.locator("div").filter(has_text="A continuación puedes").nth(1).click()
            elif acta_defuncion_path:
                # TODO: confirmar el selector real del campo "Acta de defunción"
                # cuando se necesite usarlo — no se grabó en la sesión de baja
                # porque no se subió ese archivo opcional.
                log.warning(
                    "Se pidió subir acta de defunción pero el selector real "
                    "todavía no está confirmado — se omite por ahora."
                )

            # --- 8. Registrar trámite ---
            page.get_by_role("button", name="Registrar trámite ").click()

            # --- 9. Modal de aprobación del contratante ---
            campo_correo_contratante = page.get_by_role("textbox", name="...")
            campo_correo_contratante.wait_for(state="visible", timeout=15000)
            campo_correo_contratante.click()
            campo_correo_contratante.fill(correo_contratante_aprobacion)
            page.get_by_role("button", name="Enviar el trámite al").click()

            # --- 10. Diálogo final ---
            # Confirmado por Carlos: el folio NUNCA aparece en este diálogo,
            # solo llega hasta el correo de confirmación que Carlos revisa
            # manualmente. Por eso aquí solo cerramos el diálogo sin intentar
            # extraer nada — el folio se captura a mano después, en Odoo.
            try:
                dialogo_final = page.get_by_role("dialog")
                dialogo_final.wait_for(state="visible", timeout=10000)
                dialogo_final.click()
            except Exception as e:
                log.warning(f"No se pudo cerrar el diálogo final normalmente: {e}")

            # 🛑 AQUÍ TERMINA EL RPA — el código OTP y la captura del folio
            # (una vez que llegue el correo) los termina un humano
            # manualmente en gmm@grupocyse.com, fuera de este script.

        except Exception as e:
            # Captura de pantalla en el momento exacto del error, para poder
            # diagnosticar qué pasaba en el navegador sin necesidad de
            # correrlo localmente — se regresa codificada en base64 dentro
            # del error, para que el webhook la incluya en su respuesta.
            screenshot_b64 = None
            try:
                screenshot_bytes = page.screenshot(full_page=True)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode()
            except Exception as e_screenshot:
                log.warning(f"No se pudo tomar captura de pantalla del error: {e_screenshot}")

            raise RPAError(str(e), screenshot_base64=screenshot_b64) from e

        finally:
            context.close()
            browser.close()
            if ine_path and os.path.exists(ine_path):
                os.remove(ine_path)

    return None  # el folio no se puede capturar automáticamente — se llena a mano en Odoo


if __name__ == "__main__":
    # Prueba manual local — usa headless=False para ver el navegador.
    # ⚠️ Esto SÍ va a crear un trámite real en Plan Seguro si se corre
    # contra credenciales reales. Usar con cuidado.
    logging.basicConfig(level=logging.INFO)

    # --- Ejemplo ALTA ---
    with open("/tmp/ine_test.pdf", "rb") as f:
        ine_b64_test = base64.b64encode(f.read()).decode() if os.path.exists("/tmp/ine_test.pdf") else None

    folio = emitir_movimiento_plan_seguro(
        no_poliza="LD000854",
        tipo_movimiento="alta",
        lista_asegurados_path="/tmp/LISTADO_TEST.xlsx",
        orden_trabajo_path="/tmp/orden_trabajo_TEST.pdf",
        correo_contratante_aprobacion="gmm@grupocyse.com",
        ine_base64=ine_b64_test,
        headless=False,
    )
    print("Folio (alta):", folio)

    # --- Ejemplo BAJA (mucho más simple: solo el Excel) ---
    # folio = emitir_movimiento_plan_seguro(
    #     no_poliza="LD000854",
    #     tipo_movimiento="baja",
    #     lista_asegurados_path="/tmp/LISTADO_TEST.xlsx",
    #     correo_contratante_aprobacion="gmm@grupocyse.com",
    #     headless=False,
    # )
    # print("Folio (baja):", folio)
