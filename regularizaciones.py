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
    
    # ══════════════════════════════════════════
    # TAB 2: REGISTRAR REGULARIZACIONES
    # ══════════════════════════════════════════
    
    with tab2:
        st.markdown('<div class="titulo">Registrar Regularizaciones</div>', 
                    unsafe_allow_html=True)
        
        st.markdown("**Paso 1:** Selecciona el rango de fechas de los gastos que vas a regularizar.")
        st.markdown("**Paso 2:** Haz clic en 'Ejecutar' para copiar el ID Transferencia original a ID Trf Regularizada.")
        
        st.markdown("")  # Espaciador
        
        # Fechas
        st.markdown('<div class="sub">Rango de Transacciones a Regularizar</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            fecha_inicio_reg = st.date_input("Desde", value=datetime(2026, 9, 1), key="reg_ejecutar_inicio")
        with col2:
            fecha_fin_reg = st.date_input("Hasta", value=datetime(2026, 9, 30), key="reg_ejecutar_fin")
        
        st.markdown("")  # Espaciador
        
        # Filtrar movimientos para mostrar preview
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
            st.markdown('<div class="sub">📋 Vista Previa</div>', unsafe_allow_html=True)
            st.warning(f"⚠️ Se actualizarán **{len(df_to_update)} registros**")
            
            # Mostrar tabla de preview
            df_preview = df_to_update[[
                "Fecha", "Beneficiario Nombre", "ID Transferencia", "Monto Neto"
            ]].copy()
            df_preview.columns = ["Fecha", "Concepto", "ID a Copiar", "Monto"]
            df_preview["Monto"] = df_preview["Monto"].apply(lambda x: f"{fmt0(abs(x))}")
            df_preview["Fecha"] = df_preview["Fecha"].dt.strftime("%d/%m/%Y")
            
            st.dataframe(df_preview, use_container_width=True, hide_index=True)
            
            st.markdown("")
            
            # Checkbox de confirmación
            confirmar = st.checkbox("✅ Confirmo que deseo actualizar estos registros", key="confirmar_regularizacion")
            
            if st.button("✅ Ejecutar Regularización", use_container_width=True, disabled=not confirmar):
                if not confirmar:
                    st.error("⚠️ Debes confirmar antes de continuar")
                else:
                    try:
                        # Conectar a la Sheet
                        gc = conectar_sheets()
                        sh = gc.open_by_key(SHEET_ID)
                        ws = sh.worksheet("Movimientos")
                        
                        # Obtener TODOS los datos
                        datos = ws.get_all_values()
                        
                        # Buscar fila de encabezados (como hace app.py)
                        fila_enc = 0
                        for i, fila in enumerate(datos[:4]):
                            if sum(1 for c in fila if str(c).strip()) >= 2:
                                fila_enc = i
                                break
                        
                        header_row = [c.strip() for c in datos[fila_enc]]
                        
                        # Buscar índices de columnas
                        idx_id_transf_orig = None
                        idx_id_trf_regularizada = None
                        idx_estado = None
                        
                        try:
                            idx_id_transf_orig = header_row.index("ID Transferencia") + 1
                        except ValueError:
                            st.error("❌ No encontré 'ID Transferencia'")
                        
                        try:
                            idx_id_trf_regularizada = header_row.index("ID Trf Regularizada") + 1
                        except ValueError:
                            st.error("❌ No encontré 'ID Trf Regularizada'")
                        
                        try:
                            idx_estado = header_row.index("Estado") + 1
                        except ValueError:
                            st.error("❌ No encontré 'Estado'")
                        
                        if not idx_id_transf_orig or not idx_id_trf_regularizada or not idx_estado:
                            st.error("❌ Faltan columnas en la Sheet")
                        else:
                            # Aplicar cambios
                            count = 0
                            for _, row in df_to_update.iterrows():
                                row_num = int(row["_RowNumber"])
                                id_transferencia_original = row.get("ID Transferencia", "")
                                
                                if id_transferencia_original and str(id_transferencia_original).strip():
                                    ws.update_cell(row_num, idx_id_trf_regularizada, id_transferencia_original)
                                    ws.update_cell(row_num, idx_estado, "Regularizado")
                                    count += 1
                            
                            if count > 0:
                                st.success(f"✅ {count} gastos marcados como Regularizado")
                                st.cache_data.clear()
                                st.balloons()
                            else:
                                st.warning("⚠️ No hay gastos con ID Transferencia")
                    
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
