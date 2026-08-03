"""
Vista "Conciliación" para el app de Control de Gastos (Streamlit).

Se integra al app.py existente reusando `mov`, `cuentas` y la conexión.
Solo depende de: streamlit, pandas, pdfplumber, gspread (via conectar_sheets).

Contiene 3 partes:
  1) parse_diners(): lee el PDF de Diners Club y lo normaliza.
  2) conciliar(): cruza el EECC contra los movimientos del app.
  3) render(): dibuja la vista y el flujo completo.

Por ahora el parser es específico de Diners Club. Está aislado para poder
sumar otros bancos después sin tocar el resto.
"""
import re
from datetime import datetime, timedelta

import pandas as pd
import pdfplumber
import streamlit as st

# ══════════════════════════════════════════
# 1) PARSER — DINERS CLUB
# ══════════════════════════════════════════

MESES = {'ENE': 1, 'FEB': 2, 'MAR': 3, 'ABR': 4, 'MAY': 5, 'JUN': 6,
         'JUL': 7, 'AGO': 8, 'SET': 9, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DIC': 12}
X_SPLIT = 525.0  # separa columna SOLES (izq) de DOLARES (der) por coordenada x
FECHA_RE = re.compile(r'^(\d{2})\s+([A-Z]{3})\s+(\d{2})\s+([A-Z]{3})\s+(.*)$')
MONTO_RE = re.compile(r'^-?[\d,]+\.\d{2}$')
CUOTA_RE = re.compile(r'\((\d{2})/(\d{2})\)')
SECCIONES = {
    'PAGOS/ABONOS': 'pago',
    'CONSUMOS REVOLVENTES': 'consumo_revolvente',
    'CONSUMOS EN CUOTAS': 'consumo_cuota',
    'COMISIONES Y OTROS CARGOS': 'comision',
}


def _fecha(dd, mmm, anio):
    return f"{int(dd):02d}/{MESES.get(mmm, 0):02d}/{anio}"


def _lineas(page, tol=3):
    grupos = {}
    for w in page.extract_words():
        grupos.setdefault(round(w['top'] / tol), []).append(w)
    return [sorted(grupos[k], key=lambda x: x['x0']) for k in sorted(grupos)]


def parse_diners(pdf_source, anio=None):
    filas, seccion = [], None
    with pdfplumber.open(pdf_source) as pdf:
        if anio is None:
            txt0 = pdf.pages[0].extract_text() or ""
            m = re.search(r'\b\d{2}/\d{2}/(20\d{2})\b', txt0)
            anio = int(m.group(1)) if m else datetime.now().year
        for page in pdf.pages:
            for ws in _lineas(page):
                texto = ' '.join(w['text'] for w in ws).strip()
                cambio = next((t for et, t in SECCIONES.items()
                               if texto.startswith(et)), None)
                if cambio:
                    seccion = cambio
                    continue
                if seccion is None:
                    continue
                if texto.startswith(('SUB TOTAL', 'Cuotas TEA', 'PERIODO', 'PINTO')):
                    continue
                m = FECHA_RE.match(texto)
                if not m:
                    continue
                dd_c, mmm_c, dd_p, mmm_p, resto = m.groups()
                montos = [(w['text'], w['x1']) for w in ws
                          if MONTO_RE.match(w['text'].replace('US$', ''))]
                if not montos:
                    continue
                if seccion == 'consumo_cuota':
                    cm = CUOTA_RE.search(resto)
                    cuota = f"{cm.group(1)}/{cm.group(2)}" if cm else ''
                    importe_total = float(montos[0][0].replace(',', ''))
                    facturado = float(montos[-1][0].replace(',', ''))
                    moneda = 'Soles' if montos[-1][1] < X_SPLIT else 'Dolares'
                    desc = (resto[:cm.start()] if cm else resto).strip()
                    filas.append(dict(
                        fecha_consumo=_fecha(dd_c, mmm_c, anio),
                        fecha_proceso=_fecha(dd_p, mmm_p, anio),
                        descripcion=desc, tipo=seccion, cuota=cuota,
                        importe_total=importe_total, monto=facturado, moneda=moneda))
                else:
                    valor, x1 = montos[-1]
                    monto = float(valor.replace(',', ''))
                    moneda = 'Soles' if x1 < X_SPLIT else 'Dolares'
                    desc = resto
                    for txt, _ in montos:
                        desc = desc.replace(txt, '')
                    desc = re.sub(r'\s+', ' ', desc).strip()
                    filas.append(dict(
                        fecha_consumo=_fecha(dd_c, mmm_c, anio),
                        fecha_proceso=_fecha(dd_p, mmm_p, anio),
                        descripcion=desc, tipo=seccion, cuota='',
                        importe_total=monto, monto=monto, moneda=moneda))
    return pd.DataFrame(filas)


# ══════════════════════════════════════════
# 2) MOTOR DE CONCILIACIÓN
# ══════════════════════════════════════════

def _cuota_n(c):
    try:
        return int(str(c).split('/')[0])
    except Exception:
        return None


def conciliar(df_eecc, df_app, dias_tolerancia=5):
    e = df_eecc.copy()
    a = df_app.copy()
    e['f'] = pd.to_datetime(e['fecha_consumo'], dayfirst=True, errors='coerce')
    a['f'] = pd.to_datetime(a['fecha'], dayfirst=True, errors='coerce')

    e = e[e['tipo'] != 'pago'].copy()  # pagos = transferencias, fuera
    e['cuota_n'] = e['cuota'].map(_cuota_n)
    financiamiento = e[(e.tipo == 'consumo_cuota') & (e.cuota_n > 1)].copy()
    e = e[~((e.tipo == 'consumo_cuota') & (e.cuota_n > 1))].copy()
    e['monto_match'] = e.apply(
        lambda r: r['importe_total'] if r['tipo'] == 'consumo_cuota' else r['monto'],
        axis=1)

    usados, conciliados, falta = set(), [], []
    for _, r in e.iterrows():
        cand = a[(~a.index.isin(usados)) &
                 (a['cuenta_app'] == r['cuenta_app']) &
                 ((a['monto'] - r['monto_match']).abs() < 0.01)]
        if not cand.empty:
            cand = cand.assign(dd=(cand['f'] - r['f']).abs())
            cand = cand[cand['dd'].dt.days <= dias_tolerancia].sort_values('dd')
        if cand is not None and not cand.empty:
            m = cand.iloc[0]
            usados.add(m.name)
            conciliados.append(dict(
                fecha=r['fecha_consumo'], comercio=r['descripcion'],
                monto=r['monto_match'], cuenta_app=r['cuenta_app'],
                registro_app=m['beneficiario'], fecha_app=m['fecha']))
        else:
            falta.append(dict(
                fecha=r['fecha_consumo'], descripcion=r['descripcion'],
                monto=r['monto_match'], cuenta_app=r['cuenta_app'], tipo=r['tipo']))

    en_app = a[~a.index.isin(usados)][
        ['fecha', 'beneficiario', 'monto', 'cuenta_app']].copy()

    return {
        'conciliados': pd.DataFrame(conciliados),
        'falta_en_app': pd.DataFrame(falta),
        'en_app_no_eecc': en_app,
        'financiamiento': financiamiento[
            ['fecha_consumo', 'descripcion', 'cuota', 'monto', 'moneda']],
    }


# ══════════════════════════════════════════
# 3) ESCRITURA A HOJA PENDIENTES (no toca Movimientos)
# ══════════════════════════════════════════

HOJA_PENDIENTES = "🔄 Pendientes Conciliación"


def _enviar_pendientes(faltantes, conectar_sheets, sheet_id):
    gc = conectar_sheets()
    sh = gc.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(HOJA_PENDIENTES)
    except Exception:
        ws = sh.add_worksheet(title=HOJA_PENDIENTES, rows=200, cols=8)
        ws.append_row(["Fecha", "Descripción", "Monto", "Cuenta",
                       "Tipo EECC", "Origen", "Estado", "Cargado a Movimientos"])
    filas = [[r.fecha, r.descripcion, float(r.monto), r.cuenta_app,
              r.tipo, "Diners", "Por registrar", ""]
             for r in faltantes.itertuples()]
    if filas:
        ws.append_rows(filas, value_input_option="USER_ENTERED")
    return len(filas)


# ══════════════════════════════════════════
# 4) VISTA
# ══════════════════════════════════════════

def _kpi(label, valor, clase=""):
    return (f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-val {clase}">{valor}</div></div>')


def render(mov, cuentas, conectar_sheets, sheet_id):
    st.markdown('<div class="titulo">Conciliación</div>', unsafe_allow_html=True)
    st.caption("Sube el estado de cuenta de tu tarjeta Diners y crúzalo con lo registrado.")

    archivo = st.file_uploader("Estado de cuenta (PDF)", type="pdf")
    if not archivo:
        st.info("Sube un PDF de Diners para empezar.")
        return

    col_a, col_b = st.columns([1, 1])
    with col_a:
        anio = st.number_input("Año del periodo", min_value=2020, max_value=2100,
                               value=datetime.now().year, step=1)
    with col_b:
        dias = st.slider("Tolerancia de fechas (días)", 0, 15, 5)

    try:
        eecc = parse_diners(archivo, anio=int(anio))
    except Exception as e:
        st.error(f"No se pudo leer el PDF: {e}")
        return
    if eecc.empty:
        st.warning("No se detectaron movimientos en el PDF.")
        return

    # Resumen del EECC
    n_cons = (eecc.tipo.isin(['consumo_revolvente', 'consumo_cuota'])).sum()
    n_com = (eecc.tipo == 'comision').sum()
    n_pago = (eecc.tipo == 'pago').sum()
    c1, c2, c3 = st.columns(3)
    c1.markdown(_kpi("Consumos", n_cons), unsafe_allow_html=True)
    c2.markdown(_kpi("Comisiones", n_com), unsafe_allow_html=True)
    c3.markdown(_kpi("Pagos (excluidos)", n_pago, "gris"), unsafe_allow_html=True)

    # Mapeo columna del EECC -> cuenta del app
    nombres_cta = [str(n).strip() for n in cuentas["Nombre Cuenta"]
                   if str(n).strip()]

    def _guess(keys):
        for n in nombres_cta:
            low = n.lower()
            if all(k in low for k in keys):
                return n
        return nombres_cta[0] if nombres_cta else ""

    st.markdown('<div class="sub">¿A qué cuenta va cada columna?</div>',
                unsafe_allow_html=True)
    m1, m2 = st.columns(2)
    with m1:
        cta_soles = st.selectbox(
            "Consumos en SOLES", nombres_cta,
            index=nombres_cta.index(_guess(['diners', 'sol'])) if _guess(['diners', 'sol']) in nombres_cta else 0)
    with m2:
        cta_dolar = st.selectbox(
            "Consumos en DÓLARES", nombres_cta,
            index=nombres_cta.index(_guess(['diners', 'ól'])) if _guess(['diners', 'ól']) in nombres_cta else 0)

    if st.button("Conciliar", type="primary"):
        # EECC -> asignar cuenta segun moneda
        eecc = eecc.copy()
        eecc['cuenta_app'] = eecc['moneda'].map(
            {'Soles': cta_soles, 'Dolares': cta_dolar})

        # Movimientos del app: Egresos de esas 2 cuentas dentro del periodo
        fechas = pd.to_datetime(eecc['fecha_consumo'], dayfirst=True, errors='coerce')
        fmin, fmax = fechas.min().date(), fechas.max().date()
        td = timedelta(days=int(dias))

        a = mov[(mov["Cuenta Nombre"].isin([cta_soles, cta_dolar])) &
                (mov["Tipo"] == "Egreso") &
                (mov["Fecha"].dt.date >= fmin - td) &
                (mov["Fecha"].dt.date <= fmax + td)].copy()
        df_app = pd.DataFrame({
            'fecha': a["Fecha"].dt.strftime("%d/%m/%Y"),
            'monto': pd.to_numeric(a["Monto"], errors='coerce').fillna(0),
            'cuenta_app': a["Cuenta Nombre"],
            'beneficiario': a["Desc"] if "Desc" in a.columns else a["Cuenta Nombre"],
        }).reset_index(drop=True)

        st.session_state['conc_res'] = conciliar(eecc, df_app, dias_tolerancia=int(dias))

    if 'conc_res' not in st.session_state:
        st.stop()

    r = st.session_state['conc_res']
    conc, falta = r['conciliados'], r['falta_en_app']
    en_app, fin = r['en_app_no_eecc'], r['financiamiento']

    st.markdown('<div class="sub">Resultado</div>', unsafe_allow_html=True)
    k1, k2, k3 = st.columns(3)
    k1.markdown(_kpi("Cuadran", len(conc), "pos"), unsafe_allow_html=True)
    k2.markdown(_kpi("Faltan en tu app", len(falta), "neg" if len(falta) else "pos"),
                unsafe_allow_html=True)
    k3.markdown(_kpi("Solo en tu app", len(en_app), "gris"), unsafe_allow_html=True)

    # Falta en app -> lo importante
    st.markdown('<div class="sub">🔴 En el estado de cuenta, falta en tu app</div>',
                unsafe_allow_html=True)
    if falta.empty:
        st.success("Todo lo del estado de cuenta ya está registrado. 🎉")
    else:
        vista_falta = falta.rename(columns={
            'fecha': 'Fecha', 'descripcion': 'Comercio', 'monto': 'Monto',
            'cuenta_app': 'Cuenta', 'tipo': 'Tipo'})
        st.dataframe(vista_falta, use_container_width=True, hide_index=True)
        total_falta = falta['monto'].sum()
        st.caption(f"{len(falta)} movimientos · S/ {total_falta:,.2f} sin registrar")

        b1, b2 = st.columns(2)
        with b1:
            st.download_button(
                "⬇️ Descargar faltantes (CSV)",
                vista_falta.to_csv(index=False).encode('utf-8'),
                file_name="faltantes_conciliacion.csv", mime="text/csv")
        with b2:
            if st.button(f"📤 Enviar a «{HOJA_PENDIENTES}»"):
                try:
                    n = _enviar_pendientes(falta, conectar_sheets, sheet_id)
                    st.success(f"{n} movimientos enviados. Cárgalos desde AppSheet "
                               "para que se generen sus IDs y el Deducible.")
                except Exception as e:
                    st.error(f"No se pudo escribir en la hoja: {e}")

    # En app, no en EECC
    if not en_app.empty:
        with st.expander(f"🟡 En tu app pero no en el estado de cuenta ({len(en_app)})"):
            st.caption("Revisar: pagado con otro medio, duplicado, o cuenta equivocada.")
            st.dataframe(en_app.rename(columns={
                'fecha': 'Fecha', 'beneficiario': 'Descripción',
                'monto': 'Monto', 'cuenta_app': 'Cuenta'}),
                use_container_width=True, hide_index=True)

    # Financiamiento de cuotas
    if not fin.empty:
        with st.expander(f"ℹ️ Cuotas de compras ya registradas ({len(fin)})"):
            st.caption("Son cuotas siguientes de compras que ya registraste completas. "
                       "No hay que hacer nada.")
            st.dataframe(fin.rename(columns={
                'fecha_consumo': 'Fecha', 'descripcion': 'Comercio',
                'cuota': 'Cuota', 'monto': 'Monto', 'moneda': 'Moneda'}),
                use_container_width=True, hide_index=True)

    # Conciliados
    if not conc.empty:
        with st.expander(f"✅ Conciliados ({len(conc)})"):
            st.dataframe(conc.rename(columns={
                'fecha': 'Fecha EECC', 'comercio': 'Comercio', 'monto': 'Monto',
                'cuenta_app': 'Cuenta', 'registro_app': 'Registro en app',
                'fecha_app': 'Fecha app'}),
                use_container_width=True, hide_index=True)
