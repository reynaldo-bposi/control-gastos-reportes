"""
Vista "Conciliación" para el app de Control de Gastos (Streamlit).

Se integra al app.py existente reusando `mov`, `cuentas` y la conexión.
Solo depende de: streamlit, pandas, pdfplumber, gspread (via conectar_sheets).

Contiene 3 partes:
  1) parse_diners(): lee el PDF de Diners Club y lo normaliza.
  2) conciliar(): cruza el EECC contra los movimientos del app.
  3) render(): dibuja la vista y el flujo completo.

Parsers por banco (Diners y BCP), aislados en el registro BANCOS para
sumar más bancos sin tocar el motor de cruce ni la vista.
"""
import re
import html as _html
from datetime import datetime, timedelta
from itertools import combinations

import pandas as pd
import pdfplumber
import streamlit as st

# ══════════════════════════════════════════
# 1) PARSER — DINERS CLUB
# ══════════════════════════════════════════

MESES = {'ENE': 1, 'JAN': 1, 'FEB': 2, 'MAR': 3, 'ABR': 4, 'APR': 4, 'MAY': 5,
         'JUN': 6, 'JUL': 7, 'AGO': 8, 'AUG': 8, 'SET': 9, 'SEP': 9, 'OCT': 10,
         'NOV': 11, 'DIC': 12, 'DEC': 12}
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


# ══════════════════════════════════════════
# 1b) PARSER — BCP (Tarjeta Visa)
# ══════════════════════════════════════════

X_SPLIT_BCP = 496.0          # separa columna SOLES de DOLARES en BCP
FECHA_TOK = re.compile(r'^(\d{2})([A-Za-z]{3})$')
MONEY_BCP = re.compile(r'^-?[\d,]+\.\d{2}-?$')
TIPOS_BCP = {'CONSUMO', 'PAGOSERVIC', 'PAGO'}
AUTO_BCP = ['SEGURO DE DESGRAVAMEN', 'COMISION ANUAL POR MEMBRESIA',
            'ENVIO FISICO', 'COMISION POR USO DE CANALES', 'INTERESES']


def _bcp_anios(pdf):
    """Lee el ciclo de facturación (Del / Al) para asignar el año a cada mes."""
    txt = pdf.pages[0].extract_text() or ""
    ds = re.findall(r'(\d{2})/(\d{2})/(\d{2})', txt)
    if len(ds) < 2:
        y = datetime.now().year
        return (1, y), (12, y)
    (_, m1, y1), (_, m2, y2) = ds[0], ds[1]
    return (int(m1), 2000 + int(y1)), (int(m2), 2000 + int(y2))


def parse_bcp(pdf_source, anio=None):
    filas = []
    with pdfplumber.open(pdf_source) as pdf:
        (sm, sy), (em, ey) = _bcp_anios(pdf)
        for page in pdf.pages:
            for ws in _lineas(page):
                toks = [w['text'] for w in ws]
                texto = ' '.join(toks)
                es_detalle = (len(toks) >= 2 and FECHA_TOK.match(toks[0])
                              and FECHA_TOK.match(toks[1]))
                if not es_detalle:
                    # Cargos automáticos del banco (bloque resumen, sin fecha)
                    if 'SUB TOTAL' in texto or 'MONTO TOTAL' in texto:
                        continue
                    for lab in AUTO_BCP:
                        if lab in texto:
                            m = [w for w in ws if MONEY_BCP.match(w['text'])]
                            if m:
                                val = float(m[-1]['text'].replace(',', '').replace('-', ''))
                                filas.append(dict(
                                    fecha_consumo='', fecha_proceso='',
                                    descripcion=lab.title(), tipo='comision', cuota='',
                                    importe_total=val, monto=val,
                                    moneda='Soles' if m[-1]['x1'] < X_SPLIT_BCP else 'Dolares'))
                    continue
                # Fila de detalle: el tipo va justo antes del monto (último token)
                monts = [w for w in ws if MONEY_BCP.match(w['text'])]
                if not monts:
                    continue
                mw = monts[-1]
                money_idx = ws.index(mw)
                tipo_op = toks[money_idx - 1] if money_idx >= 3 else ''
                if tipo_op not in TIPOS_BCP:
                    continue
                desc = ' '.join(toks[2:money_idx - 1]).strip()
                desc = re.sub(r'\s+(PE|CA|US)$', '', desc).strip()
                mc = FECHA_TOK.match(toks[1])
                mon = MESES.get(mc.group(2).upper(), 0)
                y = sy if mon == sm else ey
                fecha = f"{int(mc.group(1)):02d}/{mon:02d}/{y}"
                val = float(mw['text'].replace(',', '').replace('-', ''))
                filas.append(dict(
                    fecha_consumo=fecha, fecha_proceso='', descripcion=desc,
                    tipo=('pago' if tipo_op == 'PAGO' else 'consumo_revolvente'),
                    cuota='', importe_total=val, monto=val,
                    moneda='Soles' if mw['x1'] < X_SPLIT_BCP else 'Dolares'))
    return pd.DataFrame(filas)


# Registro de bancos disponibles (parser por banco)
BANCOS = {'Diners': parse_diners, 'BCP': parse_bcp}


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

    # ── Pasada 1: cruce directo 1 a 1 (monto exacto + cuenta + fecha) ──
    usados, conciliados, pendientes = set(), [], []
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
                registro_app=m['beneficiario'], fecha_app=m['fecha'],
                match='directo', partes=None))
        else:
            pendientes.append(r)

    # ── Pasada 2: consumo dividido en el app (misma cuenta + fecha) ──
    # Acepta una combinación de 2-3 registros cuya suma == línea del EECC cuando:
    #   (a) comparten beneficiario  → compra partida en varias categorías, o
    #   (b) incluye una transferencia de salida → consumo cuyo excedente se
    #       transfiere a otra cuenta (ej. "Transferir a Sueldo BCP", reembolso).
    falta = []
    for r in pendientes:
        libres = a[(~a.index.isin(usados)) & (a['cuenta_app'] == r['cuenta_app'])].copy()
        libres = libres[(libres['f'] - r['f']).abs().dt.days <= dias_tolerancia]
        hallado = None
        if not libres.empty:
            for fch, grupo in libres.groupby(libres['f'].dt.date):
                if len(grupo) < 2:
                    continue
                idxs = list(grupo.index)
                if len(idxs) > 15:
                    idxs = idxs[:15]
                for k in (2, 3):
                    for combo in combinations(idxs, k):
                        sub = a.loc[list(combo)]
                        if abs(sub['monto'].sum() - r['monto_match']) >= 0.01:
                            continue
                        mismo_benef = sub['beneficiario'].nunique() == 1
                        tiene_transfer = bool(sub['es_transfer'].any()) \
                            if 'es_transfer' in sub.columns else False
                        if mismo_benef or tiene_transfer:
                            hallado = (list(combo), fch)
                            break
                    if hallado:
                        break
                if hallado:
                    break
        if hallado:
            combo, fch = hallado
            usados.update(combo)
            partes = [dict(
                fecha=a.loc[i, 'fecha'],
                beneficiario=a.loc[i, 'beneficiario'],
                categoria=(a.loc[i, 'categoria'] if 'categoria' in a.columns else ''),
                monto=float(a.loc[i, 'monto']),
                es_transfer=bool(a.loc[i, 'es_transfer']) if 'es_transfer' in a.columns else False)
                for i in combo]
            # nombre representativo: el del consumo real, no el de la transferencia
            no_tr = [p for p in partes if not p['es_transfer']]
            ben = no_tr[0]['beneficiario'] if no_tr else partes[0]['beneficiario']
            conciliados.append(dict(
                fecha=r['fecha_consumo'], comercio=r['descripcion'],
                monto=r['monto_match'], cuenta_app=r['cuenta_app'],
                registro_app=ben, fecha_app=str(fch),
                match='dividido', partes=partes))
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


def _col(df, cands):
    low = {str(c).strip().lower(): c for c in df.columns}
    for c in cands:
        if c in df.columns:
            return c
        if c.lower() in low:
            return low[c.lower()]
    return None


def _es_activa(v):
    return str(v).strip().lower() in (
        "sí", "si", "true", "1", "x", "yes", "verdadero", "activo", "activa", "vigente")


def _cuentas_por_moneda(cuentas, solo_activas):
    """Opciones (soles, dolares) ordenadas por 'Orden', activas primero.
    Una cuenta marcada dólar solo va al filtro de dólares; una de soles solo a soles;
    si la moneda no es clara, aparece en ambos filtros."""
    col_nom = _col(cuentas, ["Nombre Cuenta", "Nombre"])
    col_mon = _col(cuentas, ["Moneda"])
    col_ord = _col(cuentas, ["Orden"])
    col_act = _col(cuentas, ["Activa", "Activo"])

    c = cuentas.copy()
    c["_nom"] = c[col_nom].astype(str).str.strip()
    c = c[c["_nom"] != ""]
    c["_ord"] = pd.to_numeric(c[col_ord], errors="coerce").fillna(9999) if col_ord else 9999
    c["_act"] = c[col_act].map(_es_activa) if col_act else True

    def _cur(row):
        blob = ((str(row[col_mon]) if col_mon else "") + " " + row["_nom"]).lower()
        if any(k in blob for k in ("dolar", "dólar", "usd", "us$")):
            return "D"
        if any(k in blob for k in ("sol", "pen", "s/")):
            return "S"
        return "?"
    c["_cur"] = c.apply(_cur, axis=1)

    if solo_activas:
        c = c[c["_act"]]
    c = c.sort_values(["_act", "_ord", "_nom"], ascending=[False, True, True])

    todas = c["_nom"].tolist()
    soles = c[c["_cur"].isin(["S", "?"])]["_nom"].tolist() or todas
    dolar = c[c["_cur"].isin(["D", "?"])]["_nom"].tolist() or todas
    return soles, dolar


def _fmt(n):
    try:
        return f"{float(n):,.2f}"
    except Exception:
        return str(n)


def _tabla_conciliados(conc):
    """Tabla única de conciliados; las filas divididas (2-3 registros del app)
    se muestran con un desplegable que abre el detalle de sus partes."""
    esc = _html.escape
    cols = "0.85fr 2fr 0.8fr 1.3fr 1.9fr 1.05fr"
    css = f"""<style>
.ctab{{font-size:13px;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;margin-top:4px}}
.ctab .hd,.ctab .rw,.ctab summary{{display:grid;grid-template-columns:{cols};
  gap:8px;padding:8px 12px;align-items:center}}
.ctab .hd{{background:#f3f4f6;font-weight:600;color:#374151}}
.ctab .rw,.ctab details{{border-top:1px solid #eee}}
.ctab summary{{cursor:pointer;list-style:none}}
.ctab summary::-webkit-details-marker{{display:none}}
.ctab summary:hover{{background:#f9fafb}}
.ctab .mono{{text-align:right;font-variant-numeric:tabular-nums}}
.ctab .det{{background:#fafafa;padding:2px 12px 10px 34px}}
.ctab .drow{{display:grid;grid-template-columns:0.9fr 2fr 1.6fr 0.9fr;gap:8px;
  padding:5px 0;border-top:1px dashed #e5e7eb;color:#4b5563;font-size:12px}}
.ctab .dh{{font-weight:600;color:#6b7280}}
.ctab .ct{{display:inline-block;transition:transform .12s;color:#6366f1;font-size:11px}}
.ctab details[open] .ct{{transform:rotate(90deg)}}
.bdg{{border-radius:6px;padding:1px 8px;font-size:11px;font-weight:600;white-space:nowrap}}
.bdg-x{{background:#e8f7f0;color:#0f7a52}}
.bdg-d{{background:#eef2ff;color:#3730a3}}
.tw{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
</style>"""
    h = [css, '<div class="ctab">',
         '<div class="hd"><div>Fecha EECC</div><div>Comercio</div>'
         '<div class="mono">Monto</div><div>Cuenta</div>'
         '<div>Registro en app</div><div>Cruce</div></div>']
    for _, row in conc.iterrows():
        partes = row.get('partes')
        f, com = esc(str(row['fecha'])), esc(str(row['comercio']))
        mo, cta = _fmt(row['monto']), esc(str(row['cuenta_app']))
        reg = esc(str(row['registro_app']))
        if isinstance(partes, list) and len(partes) >= 2:
            bdg = f'<span class="bdg bdg-d">dividido ({len(partes)})</span>'
            det = ['<div class="det">',
                   '<div class="drow dh"><div>Fecha</div><div>Beneficiario</div>'
                   '<div>Categoría</div><div class="mono">Monto</div></div>']
            for p in partes:
                es_tr = bool(p.get("es_transfer"))
                ben_p = ("↩ " if es_tr else "") + str(p["beneficiario"])
                cat_p = str(p.get("categoria", "") or ("Transferencia (reembolso)" if es_tr else ""))
                det.append(
                    f'<div class="drow"><div>{esc(str(p["fecha"]))}</div>'
                    f'<div class="tw">{esc(ben_p)}</div>'
                    f'<div class="tw">{esc(cat_p)}</div>'
                    f'<div class="mono">{_fmt(p["monto"])}</div></div>')
            det.append('</div>')
            h.append(
                f'<details><summary><div>{f}</div><div class="tw">{com}</div>'
                f'<div class="mono">{mo}</div><div class="tw">{cta}</div>'
                f'<div class="tw"><span class="ct">▸</span> {reg}</div>'
                f'<div>{bdg}</div></summary>' + ''.join(det) + '</details>')
        else:
            h.append(
                f'<div class="rw"><div>{f}</div><div class="tw">{com}</div>'
                f'<div class="mono">{mo}</div><div class="tw">{cta}</div>'
                f'<div class="tw">{reg}</div>'
                f'<div><span class="bdg bdg-x">directo</span></div></div>')
    h.append('</div>')
    return ''.join(h)


def render(mov, cuentas, conectar_sheets, sheet_id):
    st.markdown('<div class="titulo">Conciliación</div>', unsafe_allow_html=True)
    st.caption("Sube el estado de cuenta de tu tarjeta y crúzalo con lo registrado.")
    st.markdown("""<style>
.st-key-btn_conciliar button{background:#1baf7a !important;color:#fff !important;
  border:none !important;font-weight:700;width:100%;}
.st-key-btn_conciliar button:hover{background:#148f63 !important;color:#fff !important;}
</style>""", unsafe_allow_html=True)

    banco = st.radio("Banco", list(BANCOS.keys()), horizontal=True)
    archivo = st.file_uploader("Estado de cuenta (PDF)", type=["pdf"])
    if not archivo:
        st.info(f"Sube un PDF de {banco} para empezar.")
        return

    col_a, col_b = st.columns([1, 1])
    with col_a:
        anio = st.number_input(
            "Año del periodo (solo Diners)", min_value=2020, max_value=2100,
            value=datetime.now().year, step=1,
            help="Diners no trae el año en las fechas; BCP lo detecta solo del ciclo.")
    with col_b:
        dias = st.slider("Tolerancia de fechas (días)", 0, 15, 5)

    try:
        eecc = BANCOS[banco](archivo, anio=int(anio))
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
    st.markdown('<div class="sub">¿A qué cuenta va cada columna?</div>',
                unsafe_allow_html=True)
    solo_act = st.toggle("Solo cuentas activas", value=True, key="conc_solo_act")
    op_soles, op_dolar = _cuentas_por_moneda(cuentas, solo_act)
    if not op_soles and not op_dolar:
        st.warning("No hay cuentas disponibles con ese filtro.")
        return

    def _idx(opciones):
        for i, o in enumerate(opciones):
            if banco.lower() in o.lower():
                return i
        return 0

    m1, m2 = st.columns(2)
    with m1:
        cta_soles = st.selectbox("Consumos en SOLES", op_soles, index=_idx(op_soles))
    with m2:
        cta_dolar = st.selectbox("Consumos en DÓLARES", op_dolar, index=_idx(op_dolar))

    if st.button("🔍 Conciliar", type="primary", key="btn_conciliar"):
        # EECC -> asignar cuenta segun moneda
        eecc = eecc.copy()
        eecc['cuenta_app'] = eecc['moneda'].map(
            {'Soles': cta_soles, 'Dolares': cta_dolar})

        # Movimientos del app en esas 2 cuentas dentro del periodo.
        # Incluimos SALIDAS de la tarjeta (Monto Neto < 0): consumos (Egreso) y
        # transferencias de salida como "Transferir a Sueldo BCP" (parte reembolsada
        # de un consumo). Se excluyen los pagos a la tarjeta (Monto Neto > 0).
        fechas = pd.to_datetime(eecc['fecha_consumo'], dayfirst=True, errors='coerce')
        fmin, fmax = fechas.min().date(), fechas.max().date()
        td = timedelta(days=int(dias))

        neto = pd.to_numeric(mov["Monto Neto"], errors='coerce') if "Monto Neto" in mov.columns \
            else -pd.to_numeric(mov["Monto"], errors='coerce')
        a = mov[(mov["Cuenta Nombre"].isin([cta_soles, cta_dolar])) &
                (neto < 0) &
                (mov["Fecha"].dt.date >= fmin - td) &
                (mov["Fecha"].dt.date <= fmax + td)].copy()
        df_app = pd.DataFrame({
            'fecha': a["Fecha"].dt.strftime("%d/%m/%Y"),
            'monto': pd.to_numeric(a["Monto"], errors='coerce').fillna(0),
            'cuenta_app': a["Cuenta Nombre"],
            'beneficiario': a["Desc"] if "Desc" in a.columns else a["Cuenta Nombre"],
            'categoria': (a["Cat Nombre"] if "Cat Nombre" in a.columns
                          else (a["Sub Nombre"] if "Sub Nombre" in a.columns else "")),
            'es_transfer': (a["Tipo"].astype(str).str.strip() == "Transferencia")
                           if "Tipo" in a.columns else False,
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
        n_div = int((conc['match'] == 'dividido').sum()) if 'match' in conc else 0
        etiqueta = f"✅ Conciliados ({len(conc)})"
        if n_div:
            etiqueta += f" · {n_div} de compras divididas"
        with st.expander(etiqueta):
            st.markdown(_tabla_conciliados(conc), unsafe_allow_html=True)
