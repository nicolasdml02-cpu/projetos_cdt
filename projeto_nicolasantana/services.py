import os
import json
import datetime
import requests
from database import get_connection

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "activity_log.json")

def log_event_json(tipo_evento, detalhe):
    """Registra eventos no arquivo de log em formato JSON."""
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
    """Busca cotações em tempo real com fallback para HTTPS seguro."""
    url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,GBP-BRL,JPY-BRL,CAD-BRL,CHF-BRL,AUD-BRL,BTC-BRL"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"Erro ao obter cotações: {e}")
    return None

def converter_moeda(origem, destino, valor):
    """Realiza a conversão lidando com BRL como pivô se necessário."""
    if origem == destino:
        return valor, 1.0

    headers = {"User-Agent": "Mozilla/5.0"}

    # Tenta buscar diretamente a conversão solicitada
    url_direta = f"https://economia.awesomeapi.com.br/last/{origem}-{destino}"
    try:
        res = requests.get(url_direta, headers=headers, timeout=8)
        if res.status_code == 200:
            dados = res.json()
            chave = f"{origem}{destino}"
            if chave in dados:
                taxa = float(dados[chave]["bid"])
                valor_convertido = valor * taxa
                log_event_json("CONVERSAO_MOEDA", {
                    "origem": origem, "destino": destino,
                    "valor_origem": valor, "valor_convertido": valor_convertido, "taxa": taxa
                })
                return valor_convertido, taxa
    except Exception:
        pass

    # Se a conversão direta falhar (ex: BRL -> USD), faz o cálculo inverso usando USD-BRL ou destino-BRL
    try:
        if destino == "BRL":
            res = requests.get(f"https://economia.awesomeapi.com.br/last/{origem}-BRL", headers=headers, timeout=8)
            if res.status_code == 200:
                taxa = float(res.json()[f"{origem}BRL"]["bid"])
                return valor * taxa, taxa
        elif origem == "BRL":
            res = requests.get(f"https://economia.awesomeapi.com.br/last/{destino}-BRL", headers=headers, timeout=8)
            if res.status_code == 200:
                taxa = 1 / float(res.json()[f"{destino}BRL"]["bid"])
                return valor * taxa, taxa
    except Exception as e:
        print(f"Erro na conversão secundária: {e}")

    return None, None

def listar_metas():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, categoria, valor_alvo, valor_atual, data_limite FROM metas_financeiras")
        return [dict(row) for row in cursor.fetchall()]

def salvar_meta(nome, categoria, alvo, atual, limite):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO metas_financeiras (nome, categoria, valor_alvo, valor_atual, data_limite) VALUES (?, ?, ?, ?, ?)",
            (nome, categoria, alvo, atual, limite)
        )
        conn.commit()
    log_event_json("NOVA_META", {"nome": nome, "categoria": categoria, "alvo": alvo, "atual": atual})

def atualizar_saldo_meta(meta_id, novo_saldo):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE metas_financeiras SET valor_atual = ? WHERE id = ?", (novo_saldo, meta_id))
        conn.commit()
    log_event_json("APORTE_META", {"meta_id": meta_id, "novo_saldo": novo_saldo})

def excluir_meta(meta_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM metas_financeiras WHERE id = ?", (meta_id,))
        conn.commit()
    log_event_json("EXCLUSAO_META", {"meta_id": meta_id})