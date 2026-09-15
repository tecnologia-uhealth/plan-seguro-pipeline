# -*- coding: utf-8 -*-
"""
Genera el Excel "Lista de Asegurados" de Plan Seguro, en el formato real
confirmado (LISTADO_854_ALTAS.xlsx que Carlos compartió).

Estructura confirmada:
    Hoja: nombre de la póliza (ej. "LD000854")
    Fila 1 (encabezados): PÓLIZA | NOMBRE | F. NAC. | EDAD | SEXO | PARENTESCO | FECHA DE ALTA | FECHA DE ANTIGÜEDAD
    Fila 2 en adelante: un asegurado por fila

Notas de campos:
    - NOMBRE: nombre completo en una sola celda (no separado en columnas)
    - SEXO: "Masculino" / "Femenino" completo (NO abreviado M/F, a diferencia
      de Thona y AIG)
    - PARENTESCO: usa el valor real capturado en parentesco_asegurado
      (Titular, Cónyuge, Hijo(a), etc.) — NUNCA se deja vacío ni se asume
      "Titular" a la fuerza, ya que el checkout YA captura este dato
      correctamente desde que se agregó el campo al formulario de carga
      masiva.
    - FECHA DE ANTIGÜEDAD: es la misma fecha que FECHA DE ALTA (el día en
      que se emite/da de alta) — confirmado por Carlos, no requiere
      capturar ningún dato externo.
"""

from datetime import datetime, date
from openpyxl import Workbook


def _parse_fecha(fecha):
    if isinstance(fecha, (datetime, date)):
        return fecha
    return datetime.strptime(fecha, "%Y-%m-%d")


def _calcular_edad(fecha_nac: date, referencia: date = None) -> int:
    referencia = referencia or date.today()
    edad = referencia.year - fecha_nac.year
    if (referencia.month, referencia.day) < (fecha_nac.month, fecha_nac.day):
        edad -= 1
    return edad


def generar_excel_plan_seguro(asegurados: list[dict], no_poliza: str, salida: str) -> str:
    """
    asegurados: lista de dicts con las llaves:
        nombre_completo, fecha_nacimiento (YYYY-MM-DD o date),
        sexo ("Masculino"/"Femenino"), parentesco (Titular/Cónyuge/Hijo(a)/etc.)
    no_poliza: ej. "LD000854" — se usa como nombre de la hoja y valor de columna
    salida: ruta de archivo .xlsx a generar
    """
    wb = Workbook()
    ws = wb.active
    ws.title = no_poliza

    headers = ["PÓLIZA", "NOMBRE", "F. NAC.", "EDAD", "SEXO", "PARENTESCO",
               "FECHA DE ALTA", "FECHA DE ANTIGÜEDAD"]
    ws.append(headers)

    hoy = date.today()
    for a in asegurados:
        fecha_nac = _parse_fecha(a["fecha_nacimiento"])
        fila = [
            no_poliza,
            a["nombre_completo"],
            fecha_nac,
            _calcular_edad(fecha_nac.date() if isinstance(fecha_nac, datetime) else fecha_nac),
            a["sexo"],
            a.get("parentesco") or "",  # nunca inventar "Titular" — viene del dato real
            hoy,
            hoy,  # FECHA DE ANTIGÜEDAD = misma fecha que FECHA DE ALTA (confirmado)
        ]
        ws.append(fila)

    # Formato de fecha legible en las columnas de fecha
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        row[2].number_format = "DD/MM/YYYY"  # F. NAC.
        row[6].number_format = "DD/MM/YYYY"  # FECHA DE ALTA
        row[7].number_format = "DD/MM/YYYY"  # FECHA DE ANTIGÜEDAD

    wb.save(salida)
    return salida


if __name__ == "__main__":
    ejemplo = [{
        "nombre_completo": "MARIA FERNANDA GOMEZ LOPEZ",
        "fecha_nacimiento": "1990-05-12",
        "sexo": "Femenino",
        "parentesco": "Titular",
    }]
    ruta = generar_excel_plan_seguro(ejemplo, no_poliza="LD000854", salida="/tmp/LISTADO_TEST.xlsx")
    print("Generado:", ruta)
