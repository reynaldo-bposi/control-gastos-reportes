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
                "Fecha", "Desc", "_moneda_mov", "Monto Neto", "Cuenta Nombre", "Estado"
            ]].copy()
            df_show.columns = ["Fecha", "Concepto", "Moneda", "Monto", "Cuenta", "Estado"]
            df_show["Monto"] = df_show["Monto"].apply(lambda x: f"{fmt0(abs(x))}")
            df_show["Fecha"] = df_show["Fecha"].dt.strftime("%d/%m/%Y")
            
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            
            st.caption(f"{len(df_pend)} gastos pendientes en el rango seleccionado")
        else:
            st.info("✅ No hay gastos pendientes en ese rango de fechas")
    
    # ══════════════════════════════════════════
    # TAB 2: REGISTRAR REGULARIZACIONES
    # ══════════════════════════════════════════
    
    with tab2:
        st.markdown('<div class="titulo">Registrar Regularizaciones</div>', 
                    unsafe_allow_html=True)
        
        st.markdown("**Paso 1:** Ya realizaste las transferencias en tu app y tienes los IDs.")
        st.markdown("**Paso 2:** Ingresa aquí los IDs de cada moneda.")
        st.markdown("**Paso 3:** Haz clic en 'Ejecutar' para marcar los gastos como regularizados.")
        
        st.markdown("")  # Espaciador
        
        # Inputs para IDs
        st.markdown('<div class="sub">IDs de Transferencia</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            id_sol = st.text_input("Soles (SOL)", placeholder="REG-2026-09-SOL", key="id_sol_reg")
        with col2:
            id_usd = st.text_input("Dólares (USD)", placeholder="REG-2026-09-USD", key="id_usd_reg")
        
        # Fechas
        st.markdown('<div class="sub">Rango de Transacciones</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            fecha_inicio_reg = st.date_input("Desde", value=datetime(2026, 9, 1), key="reg_ejecular_inicio")
        with col2:
            fecha_fin_reg = st.date_input("Hasta", value=datetime(2026, 9, 30), key="reg_ejecutar_fin")
        
        st.markdown("")  # Espaciador
        
        if st.button("✅ Ejecutar Regularización", use_container_width=True):
            if not id_sol and not id_usd:
                st.error("⚠️ Ingresa al menos un ID de transferencia (soles o dólares)")
            else:
                # Filtrar movimientos
                mask = (
                    (mov["Perfil"].astype(str).str.strip() == "Empresa") &
                    (mov["Estado"].astype(str).str.strip() == "Pendiente regularizar") &
                    (mov["Fecha"].dt.date >= fecha_inicio_reg) &
                    (mov["Fecha"].dt.date <= fecha_fin_reg)
                )
                df_to_update = mov[mask].copy()
                
                if df_to_update.empty:
                    st.warning("⚠️ No hay gastos para regularizar en ese rango")
                else:
                    try:
                        # Conectar a la Sheet
                        gc = conectar_sheets()
                        sh = gc.open_by_key(SHEET_ID)
                        ws = sh.worksheet("Movimientos")
                        
                        # Obtener nombres de columnas (de la fila de encabezado)
                        header_row = ws.row_values(1)
                        
                        # Buscar índice de las columnas
                        try:
                            idx_id_transf = header_row.index("ID Transferencia") + 1
                        except ValueError:
                            st.error("❌ No encontré columna 'ID Transferencia' en la Sheet")
                            idx_id_transf = None
                        
                        try:
                            idx_estado = header_row.index("Estado") + 1
                        except ValueError:
                            st.error("❌ No encontré columna 'Estado' en la Sheet")
                            idx_estado = None
                        
                        if not idx_id_transf or not idx_estado:
                            st.error("❌ Error de configuración: columnas no encontradas")
                        else:
                            # Aplicar cambios
                            if "Moneda" not in df_to_update.columns:
                                df_to_update["Moneda"] = df_to_update.get("_moneda_code", "PEN")
                            
                            df_to_update["_moneda_mov"] = df_to_update["Moneda"].apply(moneda_code)
                            
                            count = 0
                            for _, row in df_to_update.iterrows():
                                row_num = int(row["_RowNumber"])
                                moneda = row["_moneda_mov"]
                                
                                # Asignar ID según moneda
                                id_a_usar = None
                                if moneda == "SOL" and id_sol:
                                    id_a_usar = id_sol
                                elif moneda == "USD" and id_usd:
                                    id_a_usar = id_usd
                                
                                if id_a_usar:
                                    ws.update_cell(row_num, idx_id_transf, id_a_usar)
                                    ws.update_cell(row_num, idx_estado, "Regularizado")
                                    count += 1
                            
                            if count > 0:
                                st.success(f"✅ {count} gastos marcados como Regularizado")
                                st.info(f"• Soles: {len(df_to_update[df_to_update['_moneda_mov'] == 'SOL']) if id_sol else 0}")
                                st.info(f"• Dólares: {len(df_to_update[df_to_update['_moneda_mov'] == 'USD']) if id_usd else 0}")
                                
                                # Limpiar cache para recargar datos
                                st.cache_data.clear()
                                st.balloons()
                            else:
                                st.warning("⚠️ No se asignó ningún ID (verifica que los IDs coincidan con las monedas)")
                    
                    except Exception as e:
                        st.error(f"❌ Error al actualizar la Sheet: {str(e)}")
                        st.write("Verifica que:")
                        st.write("- La Sheet está accesible")
                        st.write("- Las credenciales tienen permiso de escritura")
                        st.write("- Los nombres de columnas son exactos")
