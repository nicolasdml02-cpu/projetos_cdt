import os
import json
import datetime
import requests
import yfinance as yf
from database import get_connection

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "activity_log.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
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
    """Busca cotações em tempo real. Tenta AwesomeAPI; se falhar na nuvem, usa yfinance."""
    url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,GBP-BRL,BTC-BRL"
    
    # 1. Tentativa via AwesomeAPI
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"[Aviso] AwesomeAPI indisponível na nuvem ({e}). Usando yfinance como fallback...")

    # 2. Fallback via yfinance (Livre de bloqueios de IP de nuvem)
    try:
        tickers = {
            "USDBRL": "USDBRL=X",
            "EURBRL": "EURBRL=X",
            "GBPBRL": "GBPBRL=X",
            "BTCBRL": "BTC-BRL"
        }
        dados_yf = {}
        for chave, symbol in tickers.items():
            ticker = yf.Ticker(symbol)
            # Tenta pegar o preço de fechamento/atual
            fast_info = ticker.fast_info
            preco = fast_info.last_price or fast_info.previous_close
            dados_yf[chave] = {"bid": str(round(preco, 4))}
            
        return dados_yf
    except Exception as e:
        print(f"[Erro] Falha no fallback yfinance: {e}")

    return None

def converter_moeda(origem, destino, valor):
    """Realiza a conversão de moedas com suporte a múltiplos provedores."""
    if origem == destino:
        return valor, 1.0

    # 1. Tenta conversão direta pela AwesomeAPI
    url_direta = f"https://economia.awesomeapi.com.br/last/{origem}-{destino}"
    try:
        res = requests.get(url_direta, headers=HEADERS, timeout=5)
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

    # 2. Fallback robusto via yfinance para conversões
    try:
        symbol = f"{origem}{destino}=X"
        if origem == "BRL":
            symbol = f"{destino}BRL=X"
            ticker = yf.Ticker(symbol)
            taxa_inv = ticker.fast_info.last_price or ticker.fast_info.previous_close
            taxa = 1 / taxa_inv
        elif destino == "BRL":
            symbol = f"{origem}BRL=X"
            ticker = yf.Ticker(symbol)
            taxa = ticker.fast_info.last_price or ticker.fast_info.previous_close
        else:
            ticker = yf.Ticker(f"{origem}{destino}=X")
            taxa = ticker.fast_info.last_price or ticker.fast_info.previous_close

        valor_convertido = valor * taxa
        log_event_json("CONVERSAO_MOEDA", {
            "origem": origem, "destino": destino,
            "valor_origem": valor, "valor_convertido": valor_convertido, "taxa": taxa
        })
        return valor_convertido, taxa
    except Exception as e:
        print(f"[Erro] Falha ao converter via yfinance: {e}")

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