import os
import json
import datetime
import requests
from database import get_connection

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "activity_log.json")

# Cabeçalhos HTTP para simular um navegador real e evitar bloqueios de Cloud/IP na AwesomeAPI
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

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
    """Busca cotações em tempo real na API de Economia com cabeçalhos e tratamento de erros."""
    url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,GBP-BRL,JPY-BRL,CAD-BRL,CHF-BRL,AUD-BRL,BTC-BRL"
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            return res.json()
        else:
            print(f"[ERRO API] Status Code inesperado ao buscar cotações: {res.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[ERRO REQUISICAO] Falha ao conectar na AwesomeAPI (obter_cotacoes): {e}")
    except Exception as e:
        print(f"[ERRO INESPERADO] Erro em obter_cotacoes: {e}")
        
    return None

def converter_moeda(origem, destino, valor):
    """Realiza a conversão entre duas moedas selecionadas pelo usuário."""
    if origem == destino:
        return valor, 1.0

    # Tenta buscar a conversão direta (ex: USD-BRL, EUR-BRL)
    url_direta = f"https://economia.awesomeapi.com.br/last/{origem}-{destino}"
    try:
        res = requests.get(url_direta, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            dados = res.json()
            chave = f"{origem}{destino}"
            if chave in dados:
                taxa = float(dados[chave]["bid"])
                valor_convertido = valor * taxa
                log_event_json("CONVERSAO_MOEDA", {
                    "origem": origem,
                    "destino": destino,
                    "valor_origem": valor,
                    "valor_convertido": valor_convertido,
                    "taxa": taxa
                })
                return valor_convertido, taxa
    except requests.exceptions.RequestException as e:
        print(f"[ERRO REQUISICAO] Falha em converter_moeda direta ({origem}->{destino}): {e}")
    except Exception as e:
        print(f"[ERRO INESPERADO] Erro em conversao direta: {e}")

    # Fallback: Se a conversão direta falhar ou o par não existir (ex: BRL -> USD),
    # calcula inversamente usando a cotação em relação ao BRL
    try:
        if destino == "BRL":
            res = requests.get(f"https://economia.awesomeapi.com.br/last/{origem}-BRL", headers=HEADERS, timeout=10)
            if res.status_code == 200:
                taxa = float(res.json()[f"{origem}BRL"]["bid"])
                valor_convertido = valor * taxa
                return valor_convertido, taxa
        elif origem == "BRL":
            res = requests.get(f"https://economia.awesomeapi.com.br/last/{destino}-BRL", headers=HEADERS, timeout=10)
            if res.status_code == 200:
                taxa_inversa = float(res.json()[f"{destino}BRL"]["bid"])
                taxa = 1 / taxa_inversa
                valor_convertido = valor * taxa
                return valor_convertido, taxa
    except Exception as e:
        print(f"[ERRO FALLBACK] Falha na conversão inversa: {e}")

    return None, None

def listar_metas():
    """Retorna todas as metas salvas no banco de dados SQLite."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, categoria, valor_alvo, valor_atual, data_limite FROM metas_financeiras")
        return [dict(row) for row in cursor.fetchall()]

def salvar_meta(nome, categoria, alvo, atual, limite):
    """Cadastra uma nova meta financeira no banco."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO metas_financeiras (nome, categoria, valor_alvo, valor_atual, data_limite) VALUES (?, ?, ?, ?, ?)",
            (nome, categoria, alvo, atual, limite)
        )
        conn.commit()
    log_event_json("NOVA_META", {"nome": nome, "categoria": categoria, "alvo": alvo, "atual": atual})

def atualizar_saldo_meta(meta_id, novo_saldo):
    """Atualiza o saldo acumulado de uma meta (Aporte/Depósito)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE metas_financeiras SET valor_atual = ? WHERE id = ?", (novo_saldo, meta_id))
        conn.commit()
    log_event_json("APORTE_META", {"meta_id": meta_id, "novo_saldo": novo_saldo})

def excluir_meta(meta_id):
    """Remove uma meta do banco de dados."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM metas_financeiras WHERE id = ?", (meta_id,))
        conn.commit()
    log_event_json("EXCLUSAO_META", {"meta_id": meta_id})