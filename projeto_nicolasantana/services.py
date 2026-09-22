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
    """Busca cotações em tempo real com suporte duplo (AwesomeAPI e Fallback do yfinance)."""
    url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,GBP-BRL,BTC-BRL"
    
    # 1. Tenta buscar pela AwesomeAPI
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            dados = res.json()
            if dados:
                return dados
    except Exception as e:
        print(f"[Aviso] AwesomeAPI indisponível na nuvem ({e}). Ativando fallback yfinance...")

    # 2. Fallback via yfinance (Garante chaves normais e com hífen)
    try:
        mapeamento = {
            "USDBRL": "USDBRL=X",
            "EURBRL": "EURBRL=X",
            "GBPBRL": "GBPBRL=X",
            "BTCBRL": "BTC-BRL"
        }
        
        dados_formatados = {}
        for chave, symbol in mapeamento.items():
            try:
                ticker = yf.Ticker(symbol)
                preco = None
                
                # Tenta obter o preço mais recente
                if hasattr(ticker, "fast_info"):
                    preco = ticker.fast_info.get('last_price') or ticker.fast_info.get('previous_close')
                
                # Se for Bitcoin e ainda não capturou preço, busca o histórico recente de 1 dia
                if not preco and "BTC" in chave:
                    hist = ticker.history(period="1d")
                    if not hist.empty:
                        preco = hist['Close'].iloc[-1]

                if preco:
                    valor_str = str(round(float(preco), 2))
                    # Salva no dicionário no formato da AwesomeAPI (ex: 'BTCBRL' e 'BTC-BRL')
                    dados_formatados[chave] = {"bid": valor_str}
                    chave_hifen = f"{chave[:3]}-{chave[3:]}"
                    dados_formatados[chave_hifen] = {"bid": valor_str}
            except Exception as err_inner:
                print(f"Erro ao buscar {chave} via yfinance: {err_inner}")
                
        if dados_formatados:
            return dados_formatados
    except Exception as e:
        print(f"[Erro] Falha geral no fallback yfinance: {e}")

    return None

def converter_moeda(origem, destino, valor):
    """Realiza a conversão de moedas entre dois pares com suporte a fallback."""
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

    # 2. Fallback via yfinance para conversões
    try:
        if origem == "BRL":
            ticker = yf.Ticker(f"{destino}BRL=X")
            preco = ticker.fast_info.get('last_price') or ticker.fast_info.get('previous_close')
            taxa = 1 / float(preco)
        elif destino == "BRL":
            ticker = yf.Ticker(f"{origem}BRL=X")
            preco = ticker.fast_info.get('last_price') or ticker.fast_info.get('previous_close')
            taxa = float(preco)
        else:
            ticker = yf.Ticker(f"{origem}{destino}=X")
            preco = ticker.fast_info.get('last_price') or ticker.fast_info.get('previous_close')
            taxa = float(preco)

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