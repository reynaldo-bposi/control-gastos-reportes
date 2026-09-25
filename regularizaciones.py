
"""
Módulo de Regularizaciones — Streamlit
Automatiza el proceso de marcar gastos como "Regularizado" cuando la empresa devuelve dinero adelantado.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

def render(mov, conectar_sheets, SHEET_ID):
    """
    Renderiza la vista de Regularizaciones.
    
    Parámetros:
        mov (pd.DataFrame): DataFrame de Movimientos cargado desde la Sheet.
        conectar_sheets (func): Función para conectar a Google Sheets.
        SHEET_ID (str): ID de la Sheet.
    """
    
    # Helpers locales (mismos que app.py)
    def fmt(v):
        return f"{v:,.2f}"
    
    def fmt0(v):
        return f"{v:,.0f}"
    
    SIMBOLOS = {"PEN": "S/", "USD": "US$", "ARS": "$ARS"}
    NOMBRE_MONEDA = {"PEN": "soles", "USD": "dólares", "ARS": "pesos arg."}
    
    def moneda_code(m):
        s = str(m).strip().upper()
        if not s or s == "NAN":
            return "PEN"
        if any(k in s for k in ("PEN", "SOL", "S/")):
            return "PEN"
        if any(k in s for k in ("USD", "US$", "DOLAR", "DÓLAR", "DOL")):
            return "USD"
        if any(k in s for k in ("ARS", "PESO ARG", "ARGENTIN")):
            return "ARS"
        if s == "$":
            return "USD"
        if s.isalpha() and len(s) <= 4:
            return s
        return s[:3]
    
    # ══════════════════════════════════════════
    # TAB 1: REPORTE DE PENDIENTES
    # ══════════════════════════════════════════
    
    tab1, tab2 = st.tabs(["📋 Pendientes por Pagar", "✅ Registrar Regularizaciones"])
    
    with tab1:
        st.markdown('<div class="titulo">Gastos Pendientes de Regularizar</div>', 
                    unsafe_allow_html=True)
        
        # Filtros
        col1, col2 = st.columns(2)
        with col1:
            fecha_inicio = st.date_input("Desde", value=datetime(2026, 9, 1), key="reg_fecha_inicio")
        with col2:
            fecha_fin = st.date_input("Hasta", value=datetime(2026, 9, 30), key="reg_fecha_fin")
        
        # Filtrar
        if "Moneda" not in mov.columns:
            mov["Moneda"] = mov.get("_moneda_code", "PEN")
        
        mask = (
            (mov["Perfil"].astype(str).str.strip() == "Empresa") &
            (mov["Estado"].astype(str).str.strip() == "Pendiente regularizar") &
            (mov["Fecha"].dt.date >= fecha_inicio) &
            (mov["Fecha"].dt.date <= fecha_fin)
        )
        df_pend = mov[mask].copy()
        
        if not df_pend.empty:
            # Calcular moneda de cada movimiento
            df_pend["_moneda_mov"] = df_pend.get("Moneda", "PEN").apply(moneda_code)
            
            # Resumen por moneda
            st.markdown('<div class="sub">📊 Resumen por Moneda</div>', unsafe_allow_html=True)
            
            resumen = df_pend.groupby("_moneda_mov")["Monto Neto"].sum().abs()
            resumen_sorted = resumen.reindex(sorted(resumen.index, 
                                                     key=lambda c: ({"PEN": 0, "USD": 1, "ARS": 2}.get(c, 3), c)))
            
            col_res = st.columns(len(resumen_sorted))
            for i, (moneda, monto) in enumerate(resumen_sorted.items()):
                with col_res[i]:
                    sr = SIMBOLOS.get(moneda, moneda)
                    st.markdown(
                        f'<div class="kpi"><div class="kpi-label">{NOMBRE_MONEDA.get(moneda, moneda)}</div>'
                        f'<div class="kpi-val">{sr} {fmt0(monto)}</div></div>',
                        unsafe_allow_html=True)
            
            # Tabla detallada
            st.markdown('<div class="sub">📋 Detalle</div>', unsafe_allow_html=True)
            
            df_show = df_pend[[
                "Fecha", "Beneficiario Nombre", "_moneda_mov", "Monto Neto", "Cuenta Nombre", "Estado"
            ]].copy()
            
            df_show.columns = ["Fecha", "Concepto", "Moneda", "Monto", "Cuenta", "Estado"]
            df_show["Monto"] = df_show["Monto"].apply(lambda x: f"{fmt0(abs(x))}")
            df_show["Fecha"] = df_show["Fecha"].dt.strftime("%d/%m/%Y")
            
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            
            st.caption(f"{len(df_pend)} gastos pendientes en el rango seleccionado")
        else:
            st.info("✅ No hay gastos pendientes en ese rango de fechas")
    
