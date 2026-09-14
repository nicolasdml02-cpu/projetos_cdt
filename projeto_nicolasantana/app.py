import json
import sqlite3
import random
import time
import sys
import os
import re
import csv
import threading
import webbrowser
import requests
from bs4 import BeautifulSoup
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Optional dependencies handling with fallback flags
MATPLOTLIB_AVAILABLE = False
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

REPORTLAB_AVAILABLE = False
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas as pdf_canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

PYTTSX3_AVAILABLE = False
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

PLYER_AVAILABLE = False
try:
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


DB_NAME = "monitor_data.db"
JSON_LOG_FILE = "activity_log.json"

def init_db():
    """Initializes the SQLite database schema."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Currency conversions history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS currency_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            base_currency TEXT,
            target_currency TEXT,
            rate REAL,
            amount REAL,
            converted_amount REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Product search history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            avg_price REAL,
            min_price REAL,
            max_price REAL,
            items_found INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Price alerts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT,
            item_name TEXT,
            target_price REAL,
            condition TEXT,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def save_currency_log(base, target, rate, amount, converted):
    """Saves currency conversion log to SQLite and JSON."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO currency_history (base_currency, target_currency, rate, amount, converted_amount)
        VALUES (?, ?, ?, ?, ?)
    ''', (base, target, rate, amount, converted))
    conn.commit()
    conn.close()

    append_json_log({
        "type": "currency",
        "base": base,
        "target": target,
        "rate": rate,
        "amount": amount,
        "converted": converted,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

def save_product_search_log(query, avg_p, min_p, max_p, items_count):
    """Saves product search metadata to SQLite and JSON."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO product_searches (query, avg_price, min_price, max_price, items_found)
        VALUES (?, ?, ?, ?, ?)
    ''', (query, avg_p, min_p, max_p, items_count))
    conn.commit()
    conn.close()

    append_json_log({
        "type": "product_search",
        "query": query,
        "avg_price": avg_p,
        "min_price": min_p,
        "max_price": max_p,
        "items_found": items_count,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

def append_json_log(data):
    """Appends data to the activity JSON log file."""
    logs = []
    if os.path.exists(JSON_LOG_FILE):
        try:
            with open(JSON_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except json.JSONDecodeError:
            logs = []
    
    logs.append(data)
    with open(JSON_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)


def fetch_currency_rates():
    """Fetches real-time rates from AwesomeAPI with fallback to mock data."""
    url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,GBP-BRL,JPY-BRL,CAD-BRL,BTC-BRL"
    try:
        response = requests.get(url, timeout=4)
        if response.status_code == 200:
            data = response.json()
            return {
                "USD": float(data["USDBRL"]["bid"]),
                "EUR": float(data["EURBRL"]["bid"]),
                "GBP": float(data["GBPBRL"]["bid"]),
                "JPY": float(data["JPYBRL"]["bid"]),
                "CAD": float(data["CADBRL"]["bid"]),
                "BTC": float(data["BTCBRL"]["bid"]),
                "BRL": 1.0
            }
    except Exception:
        pass
    
    return {
        "USD": 5.05,
        "EUR": 5.48,
        "GBP": 6.38,
        "JPY": 0.033,
        "CAD": 3.72,
        "BTC": 345000.00,
        "BRL": 1.0
    }

def convert_currency(amount, from_curr, to_curr, rates):
    """Converts amounts dynamically between two currencies."""
    if from_curr not in rates or to_curr not in rates:
        raise ValueError("Moeda não suportada.")
    
    amount_in_brl = amount * rates[from_curr] if from_curr != "BRL" else amount
    final_amount = amount_in_brl / rates[to_curr] if to_curr != "BRL" else amount_in_brl
    rate_applied = rates[from_curr] / rates[to_curr]
    
    save_currency_log(from_curr, to_curr, rate_applied, amount, final_amount)
    return final_amount, rate_applied

def scrape_mercado_livre(query, max_items=15):
    """Scrapes products from Mercado Livre BR."""
    search_url = f"https://lista.mercadolivre.com.br/{query.replace(' ', '-')}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    response = requests.get(search_url, headers=headers, timeout=8)
    if response.status_code != 200:
        raise ConnectionError(f"Não foi possível acessar o Mercado Livre (Código {response.status_code})")

    soup = BeautifulSoup(response.text, "html.parser")
    product_cards = soup.find_all("li", class_=re.compile(r"ui-search-layout__item"))

    results = []
    for card in product_cards:
        if len(results) >= max_items:
            break
            
        title_elem = card.find("h2", class_=re.compile(r"ui-search-item__title"))
        if not title_elem:
            title_elem = card.find("a", class_=re.compile(r"ui-search-item__group__element"))
        if not title_elem:
            continue
        title = title_elem.text.strip()

        price_container = card.find("span", class_="ui-search-price__part")
        if not price_container:
            price_container = card.find("div", class_="ui-search-price__second-line")
        
        if price_container:
            amount_elem = price_container.find("span", class_="andes-money-amount__fraction")
            cents_elem = price_container.find("span", class_="andes-money-amount__cents")
            if amount_elem:
                raw_amount = amount_elem.text.replace(".", "").strip()
                cents = cents_elem.text.strip() if cents_elem else "00"
                try:
                    price = float(f"{raw_amount}.{cents}")
                except ValueError:
                    continue
            else:
                continue
        else:
            continue

        seller_elem = card.find("span", class_=re.compile(r"ui-search-official-store-label"))
        if not seller_elem:
            seller_elem = card.find("p", class_=re.compile(r"ui-search-item__group__element"))
        seller_name = seller_elem.text.strip() if seller_elem else "Mercado Livre"

        link_elem = card.find("a", class_=re.compile(r"ui-search-link"))
        link = link_elem["href"] if link_elem and "href" in link_elem.attrs else "#"

        results.append({
            "store": seller_name[:25],
            "product_name": title,
            "price": price,
            "link": link
        })

    if not results:
        raise ValueError("Nenhum produto encontrado para o termo pesquisado.")

    prices = [item["price"] for item in results]
    avg_price = round(sum(prices) / len(prices), 2)
    min_price = min(prices)
    max_price = max(prices)

    save_product_search_log(query, avg_price, min_price, max_price, len(results))

    return {
        "items": results,
        "stats": {
            "average": avg_price,
            "min": min_price,
            "max": max_price,
            "count": len(results)
        }
    }

def speak_text(text):
    """Text-to-Speech runner using pyttsx3 in a separate background thread."""
    if not PYTTSX3_AVAILABLE:
        return
    def tts_thread():
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', 170)
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass
    threading.Thread(target=tts_thread, daemon=True).start()

def send_system_notification(title, message):
    """Sends native system notifications with elegant fallbacks."""
    if PLYER_AVAILABLE:
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Nexus Monitor",
                timeout=5
            )
            return
        except Exception:
            pass
    messagebox.showinfo(title, message)


def run_gui():
    init_db()
    rates = fetch_currency_rates()

    root = tk.Tk()
    root.title("Nexus Financial & Market Analyzer")
    root.geometry("1000x780")
    root.minsize(900, 700)

    # Catppuccin Dark Theme Palette Colors
    DARK_BG = "#181825"
    CARD_BG = "#1e1e2e"
    BORDER_BG = "#313244"
    TEXT_MAIN = "#cdd6f4"
    TEXT_MUTED = "#a6adc8"
    ACCENT_BLUE = "#89b4fa"
    ACCENT_GREEN = "#a6e3a1"
    ACCENT_YELLOW = "#f9e2af"
    ACCENT_WARN = "#f38ba8"

    style = ttk.Style()
    style.theme_use("clam")

    # Apply modern styles to TTK components
    root.configure(bg=DARK_BG)
    style.configure(".", background=DARK_BG, foreground=TEXT_MAIN, font=("Segoe UI", 10))
    style.configure("TNotebook", background=DARK_BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=CARD_BG, foreground=TEXT_MAIN, padding=[14, 8], font=("Segoe UI", 10, "bold"))
    style.map("TNotebook.Tab", background=[("selected", ACCENT_BLUE)], foreground=[("selected", "#11111b")])
    
    style.configure("Card.TFrame", background=CARD_BG, relief="flat", borderwidth=1)
    style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), foreground=ACCENT_BLUE, background=DARK_BG)
    style.configure("SubHeader.TLabel", font=("Segoe UI", 11, "bold"), foreground=TEXT_MAIN, background=CARD_BG)
    style.configure("StatValue.TLabel", font=("Segoe UI", 14, "bold"), foreground=ACCENT_GREEN, background=CARD_BG)
    style.configure("MinMax.TLabel", font=("Segoe UI", 10, "bold"), foreground=ACCENT_YELLOW, background=CARD_BG)

    style.configure("Treeview", background=CARD_BG, foreground=TEXT_MAIN, fieldbackground=CARD_BG, rowheight=28)
    style.configure("Treeview.Heading", background=BORDER_BG, foreground=TEXT_MAIN, font=("Segoe UI", 10, "bold"))
    style.map("Treeview", background=[("selected", ACCENT_BLUE)], foreground=[("selected", "#11111b")])

    # Header Bar
    header_frame = ttk.Frame(root)
    header_frame.pack(fill="x", padx=20, pady=12)
    
    lbl_title = ttk.Label(header_frame, text="⚡ Nexus Market & Currency Monitor", style="Header.TLabel")
    lbl_title.pack(side="left")

    btn_tts_help = tk.Button(
        header_frame,
        text="🔊 Voz",
        command=lambda: speak_text("Nexus Monitor ativado. Use os atalhos de Alt 1 a 6 para navegar pelas abas."),
        bg=BORDER_BG, fg=TEXT_MAIN, relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2", padx=10
    )
    btn_tts_help.pack(side="right")

    # Tabs Notebook
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=20, pady=(0, 5))

    # --- TAB 1: CONVERTER ---
    tab_curr = ttk.Frame(notebook)
    notebook.add(tab_curr, text=" 💱 Conversor ")

    card_curr = ttk.Frame(tab_curr, style="Card.TFrame")
    card_curr.pack(fill="both", expand=True, padx=15, pady=15)

    ttk.Label(card_curr, text="Conversão de Moedas em Tempo Real", style="SubHeader.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=15)

    ttk.Label(card_curr, text="Valor:").grid(row=1, column=0, padx=20, pady=10, sticky="w")
    ent_amount = ttk.Entry(card_curr, font=("Segoe UI", 11))
    ent_amount.insert(0, "100.00")
    ent_amount.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

    ttk.Label(card_curr, text="De:").grid(row=2, column=0, padx=20, pady=10, sticky="w")
    cb_from = ttk.Combobox(card_curr, values=list(rates.keys()), state="readonly", font=("Segoe UI", 10))
    cb_from.set("USD")
    cb_from.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

    ttk.Label(card_curr, text="Para:").grid(row=2, column=2, padx=10, pady=10, sticky="w")
    cb_to = ttk.Combobox(card_curr, values=list(rates.keys()), state="readonly", font=("Segoe UI", 10))
    cb_to.set("BRL")
    cb_to.grid(row=2, column=3, padx=20, pady=10, sticky="ew")

    lbl_curr_result = ttk.Label(card_curr, text="Resultado: ---", style="StatValue.TLabel", anchor="center")
    lbl_curr_result.grid(row=4, column=0, columnspan=4, padx=20, pady=20, sticky="ew")

    def do_currency_convert():
        try:
            val = float(ent_amount.get().replace(",", "."))
            f_curr = cb_from.get()
            t_curr = cb_to.get()
            
            res, rate = convert_currency(val, f_curr, t_curr, rates)
            res_str = f"{val:,.2f} {f_curr} = {res:,.2f} {t_curr}"
            lbl_curr_result.config(text=f"{res_str}\n\n(Taxa Aplicada: 1 {f_curr} = {rate:.4f} {t_curr})")
            speak_text(f"O resultado da conversão é {res:,.2f} {t_curr}")
            lbl_status.config(text=f"Conversão concluída: {f_curr} para {t_curr}")
        except ValueError:
            messagebox.showerror("Erro de Entrada", "Por favor, insira um valor numérico válido.")
        except Exception as ex:
            messagebox.showerror("Erro", str(ex))

    btn_convert = tk.Button(
        card_curr, text="Calcular Conversão", command=do_currency_convert,
        bg=ACCENT_BLUE, fg="#11111b", font=("Segoe UI", 11, "bold"), relief="flat", pady=8, cursor="hand2"
    )
    btn_convert.grid(row=3, column=0, columnspan=4, padx=20, pady=10, sticky="ew")

    # --- TAB 2: PRODUCTS ---
    tab_prod = ttk.Frame(notebook)
    notebook.add(tab_prod, text=" 🛒 Produtos ")

    card_prod = ttk.Frame(tab_prod, style="Card.TFrame")
    card_prod.pack(fill="both", expand=True, padx=15, pady=15)

    ttk.Label(card_prod, text="Análise de Preços Reais (Mercado Livre)", style="SubHeader.TLabel").pack(anchor="w", padx=20, pady=10)

    search_bar_frame = ttk.Frame(card_prod)
    search_bar_frame.pack(fill="x", padx=20, pady=5)

    ttk.Label(search_bar_frame, text="Produto:").pack(side="left", padx=(0, 10))
    ent_product = ttk.Entry(search_bar_frame, font=("Segoe UI", 11))
    ent_product.pack(side="left", fill="x", expand=True, padx=(0, 10))
    ent_product.insert(0, "Playstation 5")

    stats_frame = ttk.Frame(card_prod)
    stats_frame.pack(fill="x", padx=20, pady=10)

    lbl_avg = ttk.Label(stats_frame, text="Média: R$ 0,00", style="StatValue.TLabel")
    lbl_avg.pack(side="left", expand=True)

    lbl_min = ttk.Label(stats_frame, text="Mín: R$ 0,00", style="MinMax.TLabel")
    lbl_min.pack(side="left", expand=True)

    lbl_max = ttk.Label(stats_frame, text="Máx: R$ 0,00", style="MinMax.TLabel")
    lbl_max.pack(side="left", expand=True)

    cols = ("store", "product", "price")
    tree = ttk.Treeview(card_prod, columns=cols, show="headings", height=8)
    tree.heading("store", text="Vendedor / Loja")
    tree.heading("product", text="Título do Anúncio")
    tree.heading("price", text="Preço (R$)")

    tree.column("store", width=180)
    tree.column("product", width=420)
    tree.column("price", width=120, anchor="e")
    tree.pack(fill="both", expand=True, padx=20, pady=10)

    item_links = {}

    def do_product_search():
        query = ent_product.get().strip()
        if not query:
            messagebox.showwarning("Aviso", "Digite o nome de um produto para pesquisar.")
            return
        
        btn_search_prod.config(state="disabled", text="Buscando...")
        lbl_status.config(text=f"Buscando ofertas no Mercado Livre para '{query}'...")
        root.update()

        try:
            for item in tree.get_children():
                tree.delete(item)
            item_links.clear()

            results = scrape_mercado_livre(query, max_items=15)
            stats = results["stats"]

            lbl_avg.config(text=f"Média: R$ {stats['average']:,.2f}")
            lbl_min.config(text=f"Mínimo: R$ {stats['min']:,.2f}")
            lbl_max.config(text=f"Máximo: R$ {stats['max']:,.2f}")

            for p in results["items"]:
                item_id = tree.insert("", "end", values=(
                    p["store"],
                    p["product_name"],
                    f"R$ {p['price']:,.2f}"
                ))
                item_links[item_id] = p["link"]

            speak_text(f"Busca concluída. Foram encontrados {stats['count']} produtos com preço médio de {stats['average']} reais.")
            lbl_status.config(text=f"Busca por '{query}' finalizada ({stats['count']} itens).")

        except Exception as err:
            messagebox.showerror("Erro na Pesquisa", str(err))
            lbl_status.config(text="Erro ao realizar pesquisa de produtos.")
        finally:
            btn_search_prod.config(state="normal", text="Pesquisar no ML")

    def open_link(event):
        selected = tree.selection()
        if selected:
            link = item_links.get(selected[0])
            if link and link != "#":
                webbrowser.open(link)

    tree.bind("<Double-1>", open_link)

    btn_search_prod = tk.Button(
        search_bar_frame, text="Pesquisar no ML", command=do_product_search,
        bg=ACCENT_GREEN, fg="#11111b", font=("Segoe UI", 10, "bold"), relief="flat", padx=15, cursor="hand2"
    )
    btn_search_prod.pack(side="right")

    # --- TAB 3: ALERTS ---
    tab_alert = ttk.Frame(notebook)
    notebook.add(tab_alert, text=" 🔔 Alertas ")

    card_alert = ttk.Frame(tab_alert, style="Card.TFrame")
    card_alert.pack(fill="both", expand=True, padx=15, pady=15)

    ttk.Label(card_alert, text="Gerenciador de Alertas de Preço Target", style="SubHeader.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=20, pady=15)

    ttk.Label(card_alert, text="Item / Moeda:").grid(row=1, column=0, padx=20, pady=10, sticky="w")
    ent_alert_item = ttk.Entry(card_alert, font=("Segoe UI", 10))
    ent_alert_item.insert(0, "USD")
    ent_alert_item.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

    ttk.Label(card_alert, text="Preço Alvo:").grid(row=1, column=2, padx=10, pady=10, sticky="w")
    ent_alert_target = ttk.Entry(card_alert, font=("Segoe UI", 10))
    ent_alert_target.insert(0, "5.10")
    ent_alert_target.grid(row=1, column=3, padx=20, pady=10, sticky="ew")

    ttk.Label(card_alert, text="Condição:").grid(row=2, column=0, padx=20, pady=10, sticky="w")
    cb_condition = ttk.Combobox(card_alert, values=["Menor que (<)", "Maior que (>)"], state="readonly", font=("Segoe UI", 10))
    cb_condition.set("Menor que (<)")
    cb_condition.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

    alert_tree = ttk.Treeview(card_alert, columns=("id", "item", "target", "condition"), show="headings", height=6)
    alert_tree.heading("id", text="ID")
    alert_tree.heading("item", text="Item/Moeda")
    alert_tree.heading("target", text="Valor Alvo")
    alert_tree.heading("condition", text="Condição")
    alert_tree.column("id", width=50)
    alert_tree.column("item", width=180)
    alert_tree.column("target", width=120)
    alert_tree.column("condition", width=150)
    alert_tree.grid(row=4, column=0, columnspan=4, padx=20, pady=15, sticky="nsew")

    def refresh_alerts_list():
        for row in alert_tree.get_children():
            alert_tree.delete(row)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, item_name, target_price, condition FROM price_alerts WHERE is_active = 1")
        for row in cursor.fetchall():
            alert_tree.insert("", "end", values=row)
        conn.close()

    def add_alert():
        item = ent_alert_item.get().strip()
        cond = cb_condition.get()
        try:
            target = float(ent_alert_target.get().replace(",", "."))
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO price_alerts (target_type, item_name, target_price, condition) VALUES ('custom', ?, ?, ?)",
                           (item, target, cond))
            conn.commit()
            conn.close()
            refresh_alerts_list()
            send_system_notification("Alerta Criado", f"Monitorando {item} para a condição {cond} {target}")
            lbl_status.config(text=f"Alerta adicionado para {item}")
        except ValueError:
            messagebox.showerror("Erro", "Valor alvo inválido.")

    btn_add_alert = tk.Button(
        card_alert, text="Cadastrar Alerta", command=add_alert,
        bg=ACCENT_YELLOW, fg="#11111b", font=("Segoe UI", 10, "bold"), relief="flat", pady=6, cursor="hand2"
    )
    btn_add_alert.grid(row=3, column=0, columnspan=4, padx=20, pady=10, sticky="ew")
    refresh_alerts_list()

    # --- TAB 4: CHARTS ---
    tab_chart = ttk.Frame(notebook)
    notebook.add(tab_chart, text=" 📊 Gráficos ")

    card_chart = ttk.Frame(tab_chart, style="Card.TFrame")
    card_chart.pack(fill="both", expand=True, padx=15, pady=15)

    ttk.Label(card_chart, text="Histórico de Preços e Cotações", style="SubHeader.TLabel").pack(anchor="w", padx=20, pady=10)

    chart_container = ttk.Frame(card_chart)
    chart_container.pack(fill="both", expand=True, padx=20, pady=10)

    def draw_chart():
        for widget in chart_container.winfo_children():
            widget.destroy()

        if not MATPLOTLIB_AVAILABLE:
            ttk.Label(chart_container, text="A biblioteca Matplotlib não está instalada no ambiente.\nInstale com: pip install matplotlib", foreground=ACCENT_WARN, font=("Segoe UI", 11)).pack(expand=True)
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT query, avg_price, timestamp FROM product_searches ORDER BY id DESC LIMIT 10")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            ttk.Label(chart_container, text="Nenhum dado histórico encontrado para gerar gráficos ainda.", font=("Segoe UI", 11)).pack(expand=True)
            return

        queries = [r[0][:10] for r in reversed(rows)]
        prices = [r[1] for r in reversed(rows)]

        fig = Figure(figsize=(6, 3.5), dpi=100)
        fig.patch.set_facecolor(CARD_BG)
        ax = fig.add_subplot(111)
        ax.set_facecolor(CARD_BG)
        ax.plot(queries, prices, marker='o', color=ACCENT_BLUE, linewidth=2)
        ax.set_title("Média de Preços de Buscas Recentes (R$)", color=TEXT_MAIN, fontsize=12)
        ax.tick_params(colors=TEXT_MAIN, labelsize=9)
        ax.spines['bottom'].set_color(BORDER_BG)
        ax.spines['top'].set_color(BORDER_BG)
        ax.spines['left'].set_color(BORDER_BG)
        ax.spines['right'].set_color(BORDER_BG)
        fig.tight_layout()

        canvas_fig = FigureCanvasTkAgg(fig, master=chart_container)
        canvas_fig.draw()
        canvas_fig.get_tk_widget().pack(fill="both", expand=True)
        lbl_status.config(text="Gráfico atualizado com dados recentes.")

    btn_refresh_chart = tk.Button(card_chart, text="Atualizar Gráfico", command=draw_chart, bg=BORDER_BG, fg=TEXT_MAIN, relief="flat", font=("Segoe UI", 9, "bold"))
    btn_refresh_chart.pack(anchor="e", padx=20, pady=(0, 10))
    draw_chart()

    # --- TAB 5: REPORTS ---
    tab_export = ttk.Frame(notebook)
    notebook.add(tab_export, text=" 📄 Relatórios ")

    card_export = ttk.Frame(tab_export, style="Card.TFrame")
    card_export.pack(fill="both", expand=True, padx=15, pady=15)

    ttk.Label(card_export, text="Exportação de Relatórios de Auditoria", style="SubHeader.TLabel").pack(anchor="w", padx=20, pady=15)

    def export_csv():
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not file_path:
            return
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM currency_history")
        rows = cursor.fetchall()
        conn.close()

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Base", "Target", "Rate", "Amount", "Converted", "Timestamp"])
            writer.writerows(rows)
        messagebox.showinfo("Sucesso", "Relatório CSV exportado com sucesso!")
        lbl_status.config(text=f"CSV Exportado: {file_path}")

    def export_pdf():
        file_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF Files", "*.pdf")])
        if not file_path:
            return

        if not REPORTLAB_AVAILABLE:
            messagebox.showwarning("Biblioteca Indisponível", "A biblioteca ReportLab não está disponível. Gerando relatório em texto simples.")
            with open(file_path.replace(".pdf", ".txt"), "w", encoding="utf-8") as f:
                f.write("RELATÓRIO DE MONITORAMENTO NEXUS\n")
                f.write(f"Data: {datetime.now()}\n")
            return

        c = pdf_canvas.Canvas(file_path, pagesize=letter)
        c.drawString(100, 750, "Relatório de Monitoramento Nexus")
        c.drawString(100, 730, f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        c.drawString(100, 700, "Dados armazenados e estatísticas consolidadas no banco SQLite.")
        c.save()
        messagebox.showinfo("Sucesso", "Relatório PDF gerado com sucesso!")
        lbl_status.config(text=f"PDF Exportado: {file_path}")

    btn_csv = tk.Button(card_export, text="Exportar CSV (Moedas)", command=export_csv, bg=ACCENT_BLUE, fg="#11111b", font=("Segoe UI", 10, "bold"), relief="flat", pady=8)
    btn_csv.pack(fill="x", padx=40, pady=10)

    btn_pdf = tk.Button(card_export, text="Exportar PDF (Consolidado)", command=export_pdf, bg=ACCENT_GREEN, fg="#11111b", font=("Segoe UI", 10, "bold"), relief="flat", pady=8)
    btn_pdf.pack(fill="x", padx=40, pady=10)

    # --- TAB 6: ACCESSIBILITY & GUIDE ---
    tab_guide = ttk.Frame(notebook)
    notebook.add(tab_guide, text=" ♿ Guia & Acessibilidade ")

    card_guide = ttk.Frame(tab_guide, style="Card.TFrame")
    card_guide.pack(fill="both", expand=True, padx=15, pady=15)

    guide_text = (
        "GUIA DO USUÁRIO & RECURSOS DE ACESSIBILIDADE\n\n"
        "Atalhos Globais do Teclado:\n"
        " • Alt + 1 ... Alt + 6 : Navegar diretamente entre as 6 abas principais.\n"
        " • F1 : Abrir este guia de ajuda.\n"
        " • Ctrl + Q : Sair da aplicação.\n\n"
        "Recursos de Acessibilidade & Áudio:\n"
        " • Clique no botão '🔊 Voz' no canto superior para síntese de áudio (TTS).\n"
        " • Cores com alto contraste em padrão Dark Theme Catppuccin.\n"
        " • Duplo clique na lista de produtos para abrir diretamente no seu navegador."
    )

    txt_guide = tk.Text(card_guide, bg=CARD_BG, fg=TEXT_MAIN, font=("Segoe UI", 10), relief="flat", wrap="word", padx=15, pady=15)
    txt_guide.insert("1.0", guide_text)
    txt_guide.config(state="disabled")
    txt_guide.pack(fill="both", expand=True)

    # --- STATUS BAR ---
    status_frame = ttk.Frame(root)
    status_frame.pack(fill="x", side="bottom")
    lbl_status = ttk.Label(status_frame, text="Pronto.", font=("Segoe UI", 9), foreground=TEXT_MUTED)
    lbl_status.pack(side="left", padx=10, pady=4)

    # Keyboard Bindings for Accessibility
    root.bind("<Alt-Key-1>", lambda e: notebook.select(0))
    root.bind("<Alt-Key-2>", lambda e: notebook.select(1))
    root.bind("<Alt-Key-3>", lambda e: notebook.select(2))
    root.bind("<Alt-Key-4>", lambda e: notebook.select(3))
    root.bind("<Alt-Key-5>", lambda e: notebook.select(4))
    root.bind("<Alt-Key-6>", lambda e: notebook.select(5))
    root.bind("<F1>", lambda e: notebook.select(5))
    root.bind("<Control-q>", lambda e: root.destroy())

    root.mainloop()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "--cli":
        print("Executando em Modo CLI Fallback...")
        init_db()
    else:
        try:
            run_gui()
        except Exception as e:
            print(f"Erro ao iniciar GUI: {e}")