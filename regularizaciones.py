"""
Módulo de Regularizaciones — Streamlit
Automatiza el proceso de marcar gastos como "Regularizado" cuando la empresa devuelve dinero adelantado.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

def render(mov, conectar_sheets, SHEET_ID):
    """Renderiza la vista de Regularizaciones."""
    
    def fmt(v):
        return f"{v:,.2f}"
    
    def fmt0(v):
        return f"{v:,.0f}"
    
    SIMBOLOS = {"PEN": "S/", "USD": "US$", "ARS": "$ARS"}
    NOMBRE_MONEDA = {"PEN": "soles", "USD": "dólares", "ARS": "pesos arg."}
    
    # ══════════════════════════════════════════
    # TABS
    # ══════════════════════════════════════════
    
    tab1, tab2 = st.tabs(["📋 Pendientes por Pagar", "✅ Registrar Regularizaciones"])
    
    # ══════════════════════════════════════════
    # TAB 1: PENDIENTES POR PAGAR
    # ══════════════════════════════════════════
    
    with tab1:
        st.markdown('<div class="titulo">Gastos Pendientes de Regularizar</div>', 
                    unsafe_allow_html=True)
        
        # DEBUG: Mostrar qué columnas tiene mov
        with st.expander("🔍 Debug — Columnas disponibles"):
            st.write("Columnas en mov:", list(mov.columns))
        
        col1, col2 = st.columns(2)
        with col1:
            fecha_inicio = st.date_input("Desde", value=datetime(2026, 9, 1), key="reg_fecha_inicio")
        with col2:
            fecha_fin = st.date_input("Hasta", value=datetime(2026, 9, 30), key="reg_fecha_fin")
        
        # Filtrar
        mask = (
            (mov["Perfil"].astype(str).str.strip() == "Empresa") &
            (mov["Estado"].astype(str).str.strip() == "Pendiente regularizar") &
            (mov["Fecha"].dt.date >= fecha_inicio) &
            (mov["Fecha"].dt.date <= fecha_fin)
        )
        df_pend = mov[mask].copy()
        
        if not df_pend.empty:
            # DEBUG: Mostrar valores en Cat Nombre y Sub Nombre
            with st.expander("🔍 Debug — Valores en Cat/Sub para registros"):
                st.write("Primeros registros filtrados:")
                st.dataframe(df_pend[["Beneficiario Nombre", "Cat Nombre", "Sub Nombre", "Estado"]].head(10))
            
            # Resumen por moneda
            st.markdown('<div class="sub">📊 Resumen por Moneda</div>', unsafe_allow_html=True)
            
            resumen = df_pend.groupby("Moneda")["Monto Neto"].sum().abs()
            col_res = st.columns(len(resumen))
            for i, (moneda, monto) in enumerate(resumen.items()):
                with col_res[i]:
                    sr = SIMBOLOS.get(moneda, moneda)
                    st.metric(NOMBRE_MONEDA.get(moneda, moneda), f"{sr} {fmt0(monto)}")
            
            # Tabla
            st.markdown('<div class="sub">📋 Detalle</div>', unsafe_allow_html=True)
            
            df_show = df_pend[[
                "Fecha", "Beneficiario Nombre", "Cat Nombre", "Sub Nombre", "Moneda", "Monto Neto", "Cuenta Nombre"
            ]].copy()
            df_show.columns = ["Fecha", "Beneficiario", "Categoría", "Subcategoría", "Moneda", "Monto", "Cuenta"]
            df_show["Monto"] = df_show["Monto"].apply(lambda x: f"{fmt0(abs(x))}")
            df_show["Fecha"] = df_show["Fecha"].dt.strftime("%d/%m/%Y")
            
            st.dataframe(df_show, use_container_width=True, hide_index=True)
            st.caption(f"{len(df_pend)} gastos pendientes")
        else:
            st.info("✅ No hay gastos pendientes en ese rango")
    
    # ══════════════════════════════════════════
    # TAB 2: REGISTRAR REGULARIZACIONES
    # ══════════════════════════════════════════
    
    with tab2:
        st.markdown('<div class="titulo">Registrar Regularizaciones</div>', 
                    unsafe_allow_html=True)
        
        st.markdown("Selecciona el rango de fechas y haz clic en 'Ejecutar'")
        
        col1, col2 = st.columns(2)
        with col1:
            fecha_inicio_reg = st.date_input("Desde", value=datetime(2026, 9, 1), key="reg_ejecutar_inicio")
        with col2:
            fecha_fin_reg = st.date_input("Hasta", value=datetime(2026, 9, 30), key="reg_ejecutar_fin")
        
        if st.button("✅ Ejecutar Regularización", use_container_width=True):
            try:
                # Filtrar
                mask = (
                    (mov["Perfil"].astype(str).str.strip() == "Empresa") &
                    (mov["Estado"].astype(str).str.strip() == "Pendiente regularizar") &
                    (mov["Fecha"].dt.date >= fecha_inicio_reg) &
                    (mov["Fecha"].dt.date <= fecha_fin_reg)
                )
                df_to_update = mov[mask].copy()
                
                if df_to_update.empty:
                    st.warning("⚠️ No hay gastos para regularizar")
                else:
                    st.info(f"Se actualizarán {len(df_to_update)} registros")
                    
                    # Conectar
                    gc = conectar_sheets()
                    sh = gc.open_by_key(SHEET_ID)
                    ws = sh.worksheet("Movimientos")
                    
                    # Columnas
                    header_row = list(mov.columns)
                    
                    idx_id_transf = None
                    idx_id_reg = None
                    idx_estado = None
                    
                    try:
                        idx_id_transf = header_row.index("ID Transferencia") + 1
                    except:
                        pass
                    
                    try:
                        idx_id_reg = header_row.index("ID Trf Regularizada") + 1
                    except:
                        pass
                    
                    try:
                        idx_estado = header_row.index("Estado") + 1
                    except:
                        pass
                    
                    if not (idx_id_transf and idx_id_reg and idx_estado):
                        st.error("❌ Faltan columnas")
                    else:
                        count = 0
                        for _, row in df_to_update.iterrows():
                            row_num = int(row["_RowNumber"])
                            id_orig = row.get("ID Transferencia", "")
                            
                            if id_orig and str(id_orig).strip():
                                ws.update_cell(row_num, idx_id_reg, id_orig)
                                ws.update_cell(row_num, idx_estado, "Regularizado")
                                count += 1
                        
                        if count > 0:
                            st.success(f"✅ {count} gastos actualizados")
                            st.cache_data.clear()
                            st.balloons()
                        else:
                            st.warning("⚠️ Sin cambios")
            
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
