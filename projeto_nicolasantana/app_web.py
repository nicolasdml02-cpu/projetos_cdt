import os
import csv
import json
import io
import sqlite3
import datetime
import requests
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_file, flash

# Dependências Opcionais / Externas
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as pdf_canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


app = Flask(__name__)
app.secret_key = "chave_secreta_monitor_financeiro"

DB_FILE = "monitor_data.db"
LOG_FILE = "activity_log.json"

# ==========================================
# GESTÃO DE BANCO DE DADOS E LOGS JSON
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
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

def obter_cotacoes():
    """Busca cotações em tempo real via AwesomeAPI."""
    url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,GBP-BRL,JPY-BRL,CAD-BRL,BTC-BRL"
    try:
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

# ==========================================
# TEMPLATES HTML (INTERFACES E ABAS)
# ==========================================
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sistema Integrado de Monitoramento Financeiro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background-color: #181825; color: #cdd6f4; }
        .card { background-color: #1e1e2e; border: 1px solid #313244; color: #cdd6f4; }
        .nav-tabs .nav-link { color: #cdd6f4; border: none; }
        .nav-tabs .nav-link.active { background-color: #89b4fa; color: #11111b; font-weight: bold; }
        .table { color: #cdd6f4; }
        .table-dark { --bs-table-bg: #1e1e2e; }
        .btn-custom { background-color: #89b4fa; color: #11111b; font-weight: bold; }
        .btn-custom:hover { background-color: #b4befe; color: #11111b; }
    </style>
</head>
<body class="p-4">
    <div class="container-fluid">
        <h2 class="mb-4 text-info">Sistema Integrado de Monitoramento Financeiro & Metas</h2>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <ul class="nav nav-tabs mb-4" id="mainTabs">
            <li class="nav-item"><a class="nav-link {% if active_tab == 'cotacoes' %}active{% endif %}" href="{{ url_for('index') }}">💱 Conversor & Moedas</a></li>
            <li class="nav-item"><a class="nav-link {% if active_tab == 'metas' %}active{% endif %}" href="{{ url_for('metas') }}">🎯 Metas & Orçamento</a></li>
            <li class="nav-item"><a class="nav-link {% if active_tab == 'alertas' %}active{% endif %}" href="{{ url_for('alertas') }}">🔔 Alertas</a></li>
            <li class="nav-item"><a class="nav-link {% if active_tab == 'graficos' %}active{% endif %}" href="{{ url_for('graficos') }}">📊 Gráficos</a></li>
            <li class="nav-item"><a class="nav-link {% if active_tab == 'relatorios' %}active{% endif %}" href="{{ url_for('relatorios') }}">📄 Relatórios</a></li>
            <li class="nav-item"><a class="nav-link {% if active_tab == 'acessibilidade' %}active{% endif %}" href="{{ url_for('acessibilidade') }}">♿ Guia & Acessibilidade</a></li>
        </ul>

        <div>
            {% block content %}{% endblock %}
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ==========================================
# ROTAS DA APLICAÇÃO WEB
# ==========================================
@app.route("/", methods=["GET", "POST"])
def index():
    cotacoes = obter_cotacoes()
    resultado = None

    if request.method == "POST":
        try:
            val = float(request.form.get("valor").replace(",", "."))
            de = request.form.get("de")
            para = request.form.get("para")

            if de == para:
                res = val
                taxa = 1.0
            else:
                def get_rate(m):
                    if m == "BRL": return 1.0
                    key = f"{m}BRL"
                    if cotacoes and key in cotacoes:
                        return float(cotacoes[key]["bid"])
                    return None

                taxa_de = get_rate(de)
                taxa_para = get_rate(para)

                if taxa_de is None or taxa_para is None:
                    flash("Erro ao obter taxas para a conversão.", "danger")
                    return redirect(url_for('index'))

                valor_brl = val * taxa_de
                res = valor_brl / taxa_para
                taxa = taxa_de / taxa_para

            resultado = f"Resultado: {val:.2f} {de} = {res:.2f} {para} (Taxa: {taxa:.4f})"

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO conversoes (moeda_origem, moeda_destino, valor_origem, valor_convertido, taxa, data_conversao) VALUES (?, ?, ?, ?, ?, ?)",
                      (de, para, val, res, taxa, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()
            log_event_json("CONVERSAO", {"de": de, "para": para, "valor": val, "resultado": res})
        except ValueError:
            flash("Insira um valor numérico válido.", "danger")

    template = BASE_TEMPLATE + """
    {% block content %}
    <div class="card p-4 mb-4">
        <h4>Painel de Cotações em Tempo Real</h4>
        {% if cotacoes %}
            <div class="row mt-3 text-success font-monospace">
                <div class="col-md-4">💵 Dólar (USD): R$ {{ "%.2f"|format(cotacoes.USDBRL.bid|float) }}</div>
                <div class="col-md-4">💶 Euro (EUR): R$ {{ "%.2f"|format(cotacoes.EURBRL.bid|float) }}</div>
                <div class="col-md-4">💷 Libra (GBP): R$ {{ "%.2f"|format(cotacoes.GBPBRL.bid|float) }}</div>
                <div class="col-md-4 mt-2">💴 Iene (JPY): R$ {{ "%.4f"|format(cotacoes.JPYBRL.bid|float) }}</div>
                <div class="col-md-4 mt-2">🇨🇦 CAD: R$ {{ "%.2f"|format(cotacoes.CADBRL.bid|float) }}</div>
                <div class="col-md-4 mt-2">₿ Bitcoin (BTC): R$ {{ "%.2f"|format(cotacoes.BTCBRL.bid|float) }}</div>
            </div>
        {% else %}
            <p class="text-warning">Não foi possível conectar com o servidor de cotações.</p>
        {% endif %}
    </div>

    <div class="card p-4">
        <h4>Conversor Integrado</h4>
        <form method="POST" class="row g-3 mt-1">
            <div class="col-md-3">
                <label class="form-label">Valor:</label>
                <input type="text" name="valor" class="form-control" value="100.00" required>
            </div>
            <div class="col-md-3">
                <label class="form-label">De:</label>
                <select name="de" class="form-select">
                    {% for m in ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'BTC', 'BRL'] %}
                        <option value="{{m}}">{{m}}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-md-3">
                <label class="form-label">Para:</label>
                <select name="para" class="form-select">
                    {% for m in ['BRL', 'USD', 'EUR', 'GBP', 'JPY', 'CAD', 'BTC'] %}
                        <option value="{{m}}">{{m}}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-md-3 d-flex align-items-end">
                <button type="submit" class="btn btn-success w-100">Converter</button>
            </div>
        </form>
        {% if resultado %}
            <h5 class="mt-4 text-warning">{{ resultado }}</h5>
        {% endif %}
    </div>
    {% endblock %}
    """
    return render_template_string(template, active_tab="cotacoes", cotacoes=cotacoes, resultado=resultado)

@app.route("/metas", methods=["GET", "POST"])
def metas():
    if request.method == "POST":
        nome = request.form.get("nome").strip()
        cat = request.form.get("categoria")
        data_lim = request.form.get("data_limite").strip()
        try:
            val_alvo = float(request.form.get("valor_alvo").replace(",", "."))
            val_atual = float(request.form.get("valor_atual").replace(",", "."))
            if not nome or val_alvo <= 0:
                raise ValueError()

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO metas_financeiras (nome, categoria, valor_alvo, valor_atual, data_limite) VALUES (?, ?, ?, ?, ?)",
                      (nome, cat, val_alvo, val_atual, data_lim))
            conn.commit()
            conn.close()

            log_event_json("NOVA_META", {"nome": nome, "alvo": val_alvo, "atual": val_atual})
            flash("Meta cadastrada com sucesso!", "success")
        except ValueError:
            flash("Preencha o nome e valores numéricos válidos.", "danger")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, nome, categoria, valor_alvo, valor_atual, data_limite FROM metas_financeiras")
    metas_raw = c.fetchall()
    conn.close()

    metas_lista = []
    for r in metas_raw:
        m_id, nome, cat, alvo, atual, limite = r
        pct = (atual / alvo * 100) if alvo > 0 else 0
        metas_lista.append({
            "id": m_id, "nome": nome, "categoria": cat, "alvo": alvo,
            "atual": atual, "progresso": f"{pct:.1f}", "limite": limite
        })

    template = BASE_TEMPLATE + """
    {% block content %}
    <div class="card p-4 mb-4">
        <h4>Nova Meta / Orçamento</h4>
        <form method="POST" class="row g-3 mt-1">
            <div class="col-md-4">
                <label class="form-label">Nome da Meta:</label>
                <input type="text" name="nome" class="form-control" required>
            </div>
            <div class="col-md-4">
                <label class="form-label">Categoria:</label>
                <select name="categoria" class="form-select">
                    {% for c in ["Reserva de Emergência", "Investimentos", "Viagem", "Tecnologia", "Educação", "Outros"] %}
                        <option value="{{c}}">{{c}}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-md-4">
                <label class="form-label">Data Limite:</label>
                <input type="date" name="data_limite" class="form-control" value="2026-12-31">
            </div>
            <div class="col-md-4">
                <label class="form-label">Valor Alvo (R$):</label>
                <input type="text" name="valor_alvo" class="form-control" required>
            </div>
            <div class="col-md-4">
                <label class="form-label">Valor Atual (R$):</label>
                <input type="text" name="valor_atual" class="form-control" value="0.00">
            </div>
            <div class="col-md-4 d-flex align-items-end">
                <button type="submit" class="btn btn-custom w-100">➕ Adicionar Meta</button>
            </div>
        </form>
    </div>

    <div class="card p-4">
        <h4>Metas Cadastradas</h4>
        <table class="table table-dark table-striped mt-3">
            <thead>
                <tr>
                    <th>ID</th><th>Meta</th><th>Categoria</th><th>Alvo</th><th>Atual</th><th>Progresso</th><th>Limite</th><th>Ações</th>
                </tr>
            </thead>
            <tbody>
                {% for m in metas %}
                <tr>
                    <td>{{m.id}}</td>
                    <td>{{m.nome}}</td>
                    <td>{{m.categoria}}</td>
                    <td>R$ {{ "%.2f"|format(m.alvo) }}</td>
                    <td>R$ {{ "%.2f"|format(m.atual) }}</td>
                    <td>{{m.progresso}}%</td>
                    <td>{{m.limite}}</td>
                    <td>
                        <form method="POST" action="{{ url_for('atualizar_saldo', meta_id=m.id) }}" class="d-inline-flex">
                            <input type="text" name="novo_saldo" placeholder="Novo Saldo" class="form-control form-control-sm me-1" style="width: 100px;">
                            <button type="submit" class="btn btn-sm btn-success me-2">Atualizar</button>
                        </form>
                        <a href="{{ url_for('excluir_meta', meta_id=m.id) }}" class="btn btn-sm btn-danger">Excluir</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endblock %}
    """
    return render_template_string(template, active_tab="metas", metas=metas_lista)

@app.route("/metas/atualizar/<int:meta_id>", methods=["POST"])
def atualizar_saldo(meta_id):
    try:
        novo_val = float(request.form.get("novo_saldo").replace(",", "."))
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE metas_financeiras SET valor_atual = ? WHERE id = ?", (novo_val, meta_id))
        conn.commit()
        conn.close()
        log_event_json("ATUALIZACAO_META", {"id": meta_id, "novo_saldo": novo_val})
        flash("Saldo atualizado com sucesso!", "success")
    except ValueError:
        flash("Insira um valor válido para atualizar.", "danger")
    return redirect(url_for('metas'))

@app.route("/metas/excluir/<int:meta_id>")
def excluir_meta(meta_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM metas_financeiras WHERE id = ?", (meta_id,))
    conn.commit()
    conn.close()
    flash("Meta excluída com sucesso.", "warning")
    return redirect(url_for('metas'))

@app.route("/alertas", methods=["GET", "POST"])
def alertas():
    if request.method == "POST":
        tipo = request.form.get("tipo")
        alvo = request.form.get("alvo").strip()
        try:
            preco = float(request.form.get("preco").replace(",", "."))
            if not alvo: raise ValueError()
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO alertas (tipo, alvo, preco_alvo) VALUES (?, ?, ?)", (tipo, alvo, preco))
            conn.commit()
            conn.close()
            flash("Alerta cadastrado com sucesso!", "success")
        except ValueError:
            flash("Preencha o alvo e o preço limite corretamente.", "danger")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, tipo, alvo, preco_alvo FROM alertas WHERE ativo = 1")
    alertas_raw = c.fetchall()
    conn.close()

    template = BASE_TEMPLATE + """
    {% block content %}
    <div class="card p-4 mb-4">
        <h4>Cadastrar Alerta de Cotação</h4>
        <form method="POST" class="row g-3 mt-1">
            <div class="col-md-3">
                <label class="form-label">Tipo:</label>
                <select name="tipo" class="form-select">
                    <option value="Moeda">Moeda</option>
                    <option value="Meta Progresso">Meta Progresso</option>
                </select>
            </div>
            <div class="col-md-3">
                <label class="form-label">Alvo (ex: USD):</label>
                <input type="text" name="alvo" class="form-control" required>
            </div>
            <div class="col-md-3">
                <label class="form-label">Preço Máximo Teto (R$):</label>
                <input type="text" name="preco" class="form-control" required>
            </div>
            <div class="col-md-3 d-flex align-items-end">
                <button type="submit" class="btn btn-custom w-100">➕ Salvar Alerta</button>
            </div>
        </form>
    </div>

    <div class="card p-4">
        <h4>Alertas Ativos</h4>
        <table class="table table-dark table-striped mt-3">
            <thead>
                <tr><th>ID</th><th>Tipo</th><th>Alvo</th><th>Preço Alvo Teto</th></tr>
            </thead>
            <tbody>
                {% for a in alertas %}
                <tr>
                    <td>{{a[0]}}</td><td>{{a[1]}}</td><td>{{a[2]}}</td><td>R$ {{ "%.2f"|format(a[3]) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endblock %}
    """
    return render_template_string(template, active_tab="alertas", alertas=alertas_raw)

@app.route("/graficos")
def graficos():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT nome, valor_alvo, valor_atual FROM metas_financeiras LIMIT 6")
    rows = c.fetchall()
    conn.close()

    labels = [r[0][:12] for r in rows]
    alvos = [r[1] for r in rows]
    atuais = [r[2] for r in rows]

    template = BASE_TEMPLATE + """
    {% block content %}
    <div class="card p-4">
        <h4>Progresso das Metas Financeiras</h4>
        <div style="width: 80%; margin: 0 auto;">
            <canvas id="metasChart"></canvas>
        </div>
    </div>
    <script>
        const ctx = document.getElementById('metasChart').getContext('2d');
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: {{ labels|tojson }},
                datasets: [
                    { label: 'Alvo (R$)', data: {{ alvos|tojson }}, backgroundColor: '#45475a' },
                    { label: 'Atual (R$)', data: {{ atuais|tojson }}, backgroundColor: '#89b4fa' }
                ]
            },
            options: {
                responsive: true,
                scales: {
                    y: { beginAtZero: true, ticks: { color: '#cdd6f4' } },
                    x: { ticks: { color: '#cdd6f4' } }
                },
                plugins: {
                    legend: { labels: { color: '#cdd6f4' } }
                }
            }
        });
    </script>
    {% endblock %}
    """
    return render_template_string(template, active_tab="graficos", labels=labels, alvos=alvos, atuais=atuais)

@app.route("/relatorios")
def relatorios():
    template = BASE_TEMPLATE + """
    {% block content %}
    <div class="card p-4">
        <h4>Central de Exportação de Relatórios</h4>
        <div class="mt-3">
            <a href="{{ url_for('exportar_csv') }}" class="btn btn-custom me-3">📥 Exportar Metas Financeiras (CSV)</a>
            <a href="{{ url_for('exportar_pdf') }}" class="btn btn-success">📄 Gerar Relatório Executivo de Metas (PDF)</a>
        </div>
    </div>
    {% endblock %}
    """
    return render_template_string(template, active_tab="relatorios")

@app.route("/relatorios/csv")
def exportar_csv():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM metas_financeiras")
    rows = c.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Nome Meta", "Categoria", "Valor Alvo", "Valor Atual", "Data Limite"])
    writer.writerows(rows)

    response = send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype="text/csv",
        as_attachment=True,
        download_name="relatorio_metas.csv"
    )
    return response

@app.route("/relatorios/pdf")
def exportar_pdf():
    if not REPORTLAB_AVAILABLE:
        flash("Biblioteca ReportLab não está instalada no servidor.", "danger")
        return redirect(url_for('relatorios'))

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT nome, categoria, valor_alvo, valor_atual, data_limite FROM metas_financeiras")
    rows = c.fetchall()
    conn.close()

    buffer = io.BytesIO()
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
    c_pdf.line(50, y-5, 550, y-5)
    
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
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name="relatorio_metas.pdf")

@app.route("/acessibilidade")
def acessibilidade():
    template = BASE_TEMPLATE + """
    {% block content %}
    <div class="card p-4">
        <h4>Guia de Uso & Acessibilidade</h4>
        <button onclick="falarGuia()" class="btn btn-warning font-weight-bold mb-3 w-auto">🔊 Ouvir Explicação (Voz Web API)</button>
        <div class="p-3 bg-dark text-light rounded font-monospace" style="white-space: pre-line;" id="textoGuia">
SOBRE O SISTEMA:
Este software é um gerenciador financeiro projetado para auxiliar no acompanhamento de cotações de moedas e na gestão de metas de orçamento pessoal.

COMO ELE TE AJUDA NO DIA A DIA:
1. Cotações e Conversões: Permite visualizar instantaneamente taxas de moedas estrangeiras em tempo real e fazer conversões diretas.
2. Gestão de Metas & Orçamento: Permite cadastrar e acompanhar metas financeiras, monitorando o valor acumulado e a porcentagem concluída.
3. Gráficos & Alertas: Exibe comparativos visuais do progresso das suas metas e permite salvar alertas de preço teto.
4. Exportação de Dados: Gera relatórios completos em formatos CSV e PDF organizados para download.
        </div>
    </div>
    <script>
        function falarGuia() {
            if ('speechSynthesis' in window) {
                const msg = new SpeechSynthesisUtterance("Bem-vindo ao sistema web de cotações e metas financeiras. Utilize o menu superior para navegar entre as seções.");
                msg.lang = 'pt-BR';
                window.speechSynthesis.speak(msg);
            } else {
                alert("Sintetizador de voz não suportado neste navegador.");
            }
        }
    </script>
    {% endblock %}
    """
    return render_template_string(template, active_tab="acessibilidade")

# ==========================================
# EXECUÇÃO DO SERVIDOR WEB
# ==========================================
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)