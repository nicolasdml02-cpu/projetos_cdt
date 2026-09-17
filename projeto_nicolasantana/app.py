import os
import csv
import json
import sqlite3
import datetime
import requests
from io import BytesIO, StringIO
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for

# Dependência opcional para geração de PDF
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as pdf_canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

app = Flask(__name__)

DB_FILE = "monitor_data.db"
LOG_FILE = "activity_log.json"

# ==========================================
# BANCO DE DADOS E LOGS
# ==========================================
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metas_financeiras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            valor_alvo REAL NOT NULL,
            valor_atual REAL DEFAULT 0.0,
            data_limite TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            moeda_origem TEXT,
            moeda_destino TEXT,
            valor_origem REAL,
            valor_convertido REAL,
            taxa REAL,
            data_conversao TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT,
            alvo TEXT,
            preco_alvo REAL,
            ativo INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def log_event_json(tipo_evento, detalhe):
    evento = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tipo": tipo_evento,
        "detalhes": detalhe
    }
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    logs.append(evento)
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Erro ao salvar JSON log: {e}")

# ==========================================
# SERVIÇOS E APIS EXTERNAS
# ==========================================
def obter_cotacoes():
    url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,GBP-BRL,JPY-BRL,CAD-BRL,BTC-BRL"
    try:
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

# ==========================================
# ROTAS FLASK (ENDPOINTS)
# ==========================================

@app.route("/")
def index():
    """Página principal da aplicação Web."""
    cotacoes = obter_cotacoes()
    
    conn = get_db_connection()
    metas = conn.execute("SELECT * FROM metas_financeiras").fetchall()
    alertas = conn.execute("SELECT * FROM alertas WHERE ativo = 1").fetchall()
    conn.close()

    # Prepara lista com porcentagens de progresso
    metas_processadas = []
    for m in metas:
        m_dict = dict(m)
        alvo = m_dict["valor_alvo"]
        atual = m_dict["valor_atual"]
        m_dict["progresso"] = round((atual / alvo * 100), 1) if alvo > 0 else 0
        metas_processadas.append(m_dict)

    return render_template("index.html", cotacoes=cotacoes, metas=metas_processadas, alertas=alertas)

@app.route("/api/converter", methods=["POST"])
def converter_moeda():
    """Endpoint API REST para realizar conversão de moedas."""
    data = request.get_json() or {}
    try:
        val = float(data.get("valor", 0))
        de = data.get("de", "USD")
        para = data.get("para", "BRL")

        cotacoes = obter_cotacoes()
        if de == para:
            res = val
            taxa = 1.0
        else:
            def get_rate(m):
                if m == "BRL": return 1.0
                key = f"{m}BRL"
                if cotacoes and key in cotacoes:
                    return float(cotacoes[key]['bid'])
                return None

            taxa_de = get_rate(de)
            taxa_para = get_rate(para)

            if taxa_de is None or taxa_para is None:
                return jsonify({"error": "Erro ao obter cotações para a conversão."}), 400

            valor_brl = val * taxa_de
            res = valor_brl / taxa_para
            taxa = taxa_de / taxa_para

        # Registra no SQLite
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO conversoes (moeda_origem, moeda_destino, valor_origem, valor_convertido, taxa, data_conversao) VALUES (?, ?, ?, ?, ?, ?)",
            (de, para, val, res, taxa, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        conn.close()

        log_event_json("CONVERSAO", {"de": de, "para": para, "valor": val, "resultado": res})
        return jsonify({"valor_convertido": round(res, 2), "taxa": round(taxa, 4)})

    except (ValueError, TypeError):
        return jsonify({"error": "Valor inválido informado."}), 400

@app.route("/meta/salvar", methods=["POST"])
def salvar_meta():
    """Adiciona uma nova meta financeira."""
    nome = request.form.get("nome", "").strip()
    cat = request.form.get("categoria")
    data_limite = request.form.get("data_limite")
    try:
        val_alvo = float(request.form.get("valor_alvo", 0))
        val_atual = float(request.form.get("valor_atual", 0))

        if nome and val_alvo > 0:
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO metas_financeiras (nome, categoria, valor_alvo, valor_atual, data_limite) VALUES (?, ?, ?, ?, ?)",
                (nome, cat, val_alvo, val_atual, data_limite)
            )
            conn.commit()
            conn.close()
            log_event_json("NOVA_META", {"nome": nome, "alvo": val_alvo, "atual": val_atual})
    except ValueError:
        pass
    return redirect(url_for("index"))

@app.route("/meta/atualizar-saldo", methods=["POST"])
def atualizar_saldo_meta():
    """Atualiza o valor acumulado de uma meta existente."""
    meta_id = request.form.get("id")
    try:
        novo_saldo = float(request.form.get("novo_saldo", 0))
        conn = get_db_connection()
        conn.execute("UPDATE metas_financeiras SET valor_atual = ? WHERE id = ?", (novo_saldo, meta_id))
        conn.commit()
        conn.close()
        log_event_json("ATUALIZACAO_META", {"id": meta_id, "novo_saldo": novo_saldo})
    except ValueError:
        pass
    return redirect(url_for("index"))

@app.route("/meta/excluir/<int:meta_id>", methods=["POST"])
def excluir_meta(meta_id):
    """Remove uma meta financeira."""
    conn = get_db_connection()
    conn.execute("DELETE FROM metas_financeiras WHERE id = ?", (meta_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/alerta/salvar", methods=["POST"])
def salvar_alerta():
    """Cadastra um novo alerta de preço."""
    tipo = request.form.get("tipo")
    alvo = request.form.get("alvo", "").strip()
    try:
        preco_alvo = float(request.form.get("preco_alvo", 0))
        if alvo and preco_alvo > 0:
            conn = get_db_connection()
            conn.execute("INSERT INTO alertas (tipo, alvo, preco_alvo) VALUES (?, ?, ?)", (tipo, alvo, preco_alvo))
            conn.commit()
            conn.close()
    except ValueError:
        pass
    return redirect(url_for("index"))

# ==========================================
# EXPORTAÇÃO DE RELATÓRIOS
# ==========================================

@app.route("/exportar/csv")
def exportar_csv():
    """Gera e faz o download das metas em formato CSV."""
    conn = get_db_connection()
    rows = conn.execute("SELECT id, nome, categoria, valor_alvo, valor_atual, data_limite FROM metas_financeiras").fetchall()
    conn.close()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["ID", "Nome Meta", "Categoria", "Valor Alvo", "Valor Atual", "Data Limite"])
    for r in rows:
        writer.writerow(list(r))

    output = BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    
    return send_file(
        output,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"relatorio_metas_{datetime.datetime.now().strftime('%Y%m%d')}.csv"
    )

@app.route("/exportar/pdf")
def exportar_pdf():
    """Gera e faz o download das metas em PDF com ReportLab."""
    if not REPORTLAB_AVAILABLE:
        return "Biblioteca ReportLab não instalada no servidor.", 400

    conn = get_db_connection()
    rows = conn.execute("SELECT nome, categoria, valor_alvo, valor_atual, data_limite FROM metas_financeiras").fetchall()
    conn.close()

    buffer = BytesIO()
    c_pdf = pdf_canvas.Canvas(buffer, pagesize=letter)
    c_pdf.setFont("Helvetica-Bold", 16)
    c_pdf.drawString(50, 750, "Relatório Executivo de Metas Financeiras")
    c_pdf.setFont("Helvetica", 10)
    c_pdf.drawString(50, 730, f"Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    y = 690
    c_pdf.drawString(50, y, "Objetivo")
    c_pdf.drawString(200, y, "Categoria")
    c_pdf.drawString(320, y, "Alvo (R$)")
    c_pdf.drawString(420, y, "Atual (R$)")
    c_pdf.drawString(500, y, "%")
    c_pdf.line(50, y - 5, 550, y - 5)

    y -= 25
    for row in rows:
        if y < 50:
            c_pdf.showPage()
            y = 750
        nome, cat, alvo, atual, lim = row
        pct = (atual / alvo * 100) if alvo > 0 else 0
        c_pdf.drawString(50, y, str(nome)[:20])
        c_pdf.drawString(200, y, str(cat)[:15])
        c_pdf.drawString(320, y, f"R$ {alvo:,.2f}")
        c_pdf.drawString(420, y, f"R$ {atual:,.2f}")
        c_pdf.drawString(500, y, f"{pct:.0f}%")
        y -= 20

    c_pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"relatorio_metas_{datetime.datetime.now().strftime('%Y%m%d')}.pdf"
    )

# ==========================================
# INICIALIZAÇÃO DO SERVIDOR
# ==========================================
if __name__ == "__main__":
    init_db()
    # Executa a aplicação na porta 5000
    app.run(debug=True, port=5000)