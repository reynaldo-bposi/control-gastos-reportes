"""
Módulo de Regularizaciones — Streamlit
Automatiza el proceso de marcar gastos como "Regularizado" cuando la empresa devuelve dinero adelantado.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

def render(mov, conectar_sheets, SHEET_ID):
    """Renderiza la vista de Regularizaciones."""
    
    def fmt0(v):
        return f"{v:,.0f}"
    
    SIMBOLOS = {"PEN": "S/", "USD": "US$", "ARS": "$ARS"}
    NOMBRE_MONEDA = {"PEN": "soles", "USD": "dólares", "ARS": "pesos arg."}
    
    st.markdown('<div class="titulo">Regularizaciones</div>', unsafe_allow_html=True)
    
    # ══════════════════════════════════════════
    # FILTROS Y PREVIEW DE GASTOS
    # ══════════════════════════════════════════
    
    col1, col2 = st.columns(2)
    with col1:
        fecha_inicio = st.date_input("Desde", value=datetime(2026, 9, 1), key="reg_fecha_inicio")
    with col2:
        fecha_fin = st.date_input("Hasta", value=datetime(2026, 9, 30), key="reg_fecha_fin")
    
    # Filtrar gastos pendientes
    mask_gastos = (
        (mov["Perfil"].astype(str).str.strip() == "Empresa") &
        (mov["Estado"].astype(str).str.strip() == "Pendiente regularizar") &
        (mov["Fecha"].dt.date >= fecha_inicio) &
        (mov["Fecha"].dt.date <= fecha_fin)
    )
    df_gastos = mov[mask_gastos].copy()
    
    if df_gastos.empty:
        st.warning("⚠️ No hay gastos pendientes en ese rango")
    else:
        # Mostrar resumen por moneda
        st.markdown('<div class="sub">📊 Resumen Gastos Pendientes</div>', unsafe_allow_html=True)
        
        resumen = df_gastos.groupby("Moneda")["Monto Neto"].sum().abs()
        col_res = st.columns(len(resumen))
        for i, (moneda, monto) in enumerate(resumen.items()):
            with col_res[i]:
                sr = SIMBOLOS.get(moneda, moneda)
                st.metric(NOMBRE_MONEDA.get(moneda, moneda), f"{sr} {fmt0(monto)}")
        
        # Tabla de gastos pendientes
        st.markdown('<div class="sub">📋 Gastos a Regularizar</div>', unsafe_allow_html=True)
        
        df_show = df_gastos[[
            "Fecha", "Beneficiario Nombre", "CatSub", "Moneda", "Monto Neto", "Cuenta Nombre"
        ]].copy()
        df_show.columns = ["Fecha", "Beneficiario", "Categoría", "Moneda", "Monto", "Cuenta"]
        df_show["Monto"] = df_show["Monto"].apply(lambda x: f"{fmt0(abs(x))}")
        df_show["Fecha"] = df_show["Fecha"].dt.strftime("%d/%m/%Y")
        
        st.dataframe(df_show, use_container_width=True, hide_index=True)
        
        # ══════════════════════════════════════════
        # DIVIDER
        # ══════════════════════════════════════════
        
        st.divider()
        
        # ══════════════════════════════════════════
        # SELECCIONAR TRANSFERENCIA DE DEVOLUCIÓN
        # ══════════════════════════════════════════
        
        st.markdown('<div class="sub">💰 Selecciona la Transferencia de Devolución</div>', unsafe_allow_html=True)
        
        # Obtener IDs de transferencias ya usadas (presentes en ID Trf Regularizada)
        ids_usadas = set(mov["ID Trf Regularizada"].astype(str).str.strip().unique())
        ids_usadas.discard("")
        ids_usadas.discard("nan")
        ids_usadas.discard("NaN")
        ids_usadas.discard("None")
        
        # Filtrar transferencias de CC LABPOSI IBK Soles que no se hayan usado
        mask_transferencias = (
            (mov["Cuenta Nombre"].astype(str).str.strip() == "CC LABPOSI IBK Soles") &
            (mov["Tipo Mov."].astype(str).str.strip() == "Transferencia") &
            (mov["Monto Neto"] < 0) &
            ~(mov["ID Transferencia"].astype(str).str.strip().isin(ids_usadas))
        )
        df_transf = mov[mask_transferencias].copy()
        
        if df_transf.empty:
            st.warning("⚠️ No hay transferencias disponibles desde CC LABPOSI IBK Soles")
        else:
            # Crear opciones de dropdown
            opciones = []
            for idx, row in df_transf.iterrows():
                fecha_str = row["Fecha"].strftime("%d/%m/%Y")
                cuenta_dest = row.get("Cuenta Destino Nombre", "Desconocida")
                monto = abs(row["Monto Neto"])
                moneda = row.get("Moneda", "PEN")
                sr = SIMBOLOS.get(moneda, moneda)
                id_transf = row.get("ID Transferencia", "")
                
                label = f"{fecha_str} → {cuenta_dest} ({sr} {fmt0(monto)})"
                opciones.append((label, id_transf, idx, monto, moneda))
            
            # Selectbox
            st.markdown("**De:** CC LABPOSI IBK Soles")
            selected_label = st.selectbox(
                "**Hacia:**",
                options=[opt[0] for opt in opciones],
                key="select_transferencia",
                label_visibility="collapsed"
            )
            
            # Obtener datos de la transferencia seleccionada
            selected_idx = [opt[0] for opt in opciones].index(selected_label)
            selected_opt = opciones[selected_idx]
            id_transf_selected = selected_opt[1]
            monto_selected = selected_opt[3]
            moneda_selected = selected_opt[4]
            
            # Mostrar detalles
            st.markdown('<div class="sub">📌 Transferencia Seleccionada</div>', unsafe_allow_html=True)
            
            col_det1, col_det2 = st.columns(2)
            with col_det1:
                sr = SIMBOLOS.get(moneda_selected, moneda_selected)
                st.metric("Monto", f"{sr} {fmt0(monto_selected)}")
            with col_det2:
                st.metric("ID Transferencia", id_transf_selected)
            
            # ══════════════════════════════════════════
            # CONFIRMACIÓN Y EJECUCIÓN
            # ══════════════════════════════════════════
            
            st.divider()
            
            st.markdown('<div class="sub">✅ Aplicar Regularización</div>', unsafe_allow_html=True)
            
            # Checkbox de confirmación
            confirmar = st.checkbox(
                f"Confirmo que deseo regularizar {len(df_gastos)} registro{'s' if len(df_gastos) > 1 else ''}",
                key="confirmar_reg"
            )
            
            # Botón (desactivado hasta confirmar)
            if st.button(
                f"🔄 Regularizar {len(df_gastos)} Registro{'s' if len(df_gastos) > 1 else ''}",
                use_container_width=True,
                disabled=not confirmar
            ):
                if not confirmar:
                    st.error("⚠️ Debes confirmar antes de continuar")
                else:
                    try:
                        # Conectar a la Sheet
                        gc = conectar_sheets()
                        sh = gc.open_by_key(SHEET_ID)
                        ws = sh.worksheet("Movimientos")
                        
                        # Obtener índices de columnas
                        header_row = list(mov.columns)
                        
                        try:
                            idx_id_reg = header_row.index("ID Trf Regularizada") + 1
                        except:
                            st.error("❌ No encontré 'ID Trf Regularizada'")
                            idx_id_reg = None
                        
                        try:
                            idx_estado = header_row.index("Estado") + 1
                        except:
                            st.error("❌ No encontré 'Estado'")
                            idx_estado = None
                        
                        if not (idx_id_reg and idx_estado):
                            st.error("❌ Faltan columnas en el DataFrame")
                        else:
                            # Actualizar registros
                            count = 0
                            for _, row in df_gastos.iterrows():
                                row_num = int(row["_RowNumber"])
                                
                                # Copiar ID de la transferencia seleccionada
                                ws.update_cell(row_num, idx_id_reg, id_transf_selected)
                                ws.update_cell(row_num, idx_estado, "Regularizado")
                                count += 1
                            
                            if count > 0:
                                st.success(f"✅ {count} gasto{'s' if count > 1 else ''} regularizado{'s' if count > 1 else ''} con ID: {id_transf_selected}")
                                st.cache_data.clear()
                                st.balloons()
                            else:
                                st.warning("⚠️ No se pudieron regularizar")
                    
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
