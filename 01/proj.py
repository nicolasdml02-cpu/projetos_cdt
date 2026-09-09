import tkinter as tk
from tkinter import ttk, messagebox
import requests
from urllib.parse import quote_plus

class SmartValueApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SmartValue Pro - Monitor & Conversor Inteligente")
        self.geometry("860x640")
        self.resizable(False, False)
        
        # Paleta de Cores Estilo Dashboard / Dark Mode
        self.colors = {
            "bg_dark": "#0f172a",       # Slate 900 (Fundo principal)
            "card_bg": "#1e293b",       # Slate 800 (Cards e containers)
            "card_border": "#334155",   # Slate 700 (Bordas sutis)
            "accent_purple": "#7c3aed", # Roxo vibrante (Destaque principal)
            "accent_cyan": "#06b6d4",   # Ciano (Estatísticas secundárias)
            "accent_green": "#10b981",  # Verde Esmeralda (Valores e confirmação)
            "accent_amber": "#f59e0b",  # Âmbar (Alertas e moedas)
            "text_light": "#f8fafc",    # Texto claro principal
            "text_muted": "#94a3b8",    # Texto secundário/esquecido
            "input_bg": "#0f172a",      # Fundo de inputs
            "hover_btn": "#6d28d9"      # Efeito hover no botão
        }
        
        self.configure(bg=self.colors["bg_dark"])
        self.currency_rates = {}
        
        self._setup_styles()
        self._build_ui()
        self._fetch_currency_rates()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Estilização das Abas (Notebook)
        style.configure('TNotebook', background=self.colors["bg_dark"], borderwidth=0)
        style.configure('TNotebook.Tab', 
                        background=self.colors["card_bg"], 
                        foreground=self.colors["text_muted"], 
                        font=('Helvetica', 11, 'bold'),
                        padding=[20, 10], 
                        borderwidth=0)
        style.map('TNotebook.Tab', 
                  background=[('selected', self.colors["accent_purple"])],
                  foreground=[('selected', self.colors["text_light"])])

    def _build_ui(self):
        # Cabeçalho Superior
        header = tk.Frame(self, bg=self.colors["card_bg"], height=70)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        
        title_lbl = tk.Label(header, text="⚡ SmartValue Pro", font=("Helvetica", 22, "bold"),
                             fg=self.colors["accent_cyan"], bg=self.colors["card_bg"])
        title_lbl.pack(side="left", padx=25)
        
        subtitle_lbl = tk.Label(header, text="Pesquisa de Mercado & Conversor Financeiro", 
                                font=("Helvetica", 10), fg=self.colors["text_muted"], bg=self.colors["card_bg"])
        subtitle_lbl.pack(side="left", padx=5, pady=(8, 0))
        
        # Container de Abas
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=15)
        
        # Aba 1: Busca de Produtos
        self.tab_products = tk.Frame(self.notebook, bg=self.colors["bg_dark"])
        self.notebook.add(self.tab_products, text="🔍 Média de Preço (Produtos)")
        self._build_products_tab()
        
        # Aba 2: Conversor de Moedas
        self.tab_currencies = tk.Frame(self.notebook, bg=self.colors["bg_dark"])
        self.notebook.add(self.tab_currencies, text="💱 Cotação & Conversão")
        self._build_currencies_tab()

    def _build_products_tab(self):
        # Card de Busca
        search_card = tk.Frame(self.tab_products, bg=self.colors["card_bg"], 
                               highlightbackground=self.colors["card_border"], highlightthickness=1)
        search_card.pack(fill="x", padx=10, pady=15, ipady=10)
        
        lbl = tk.Label(search_card, text="Qual produto você deseja pesquisar na internet?", 
                       font=("Helvetica", 11, "bold"), fg=self.colors["text_light"], bg=self.colors["card_bg"])
        lbl.pack(anchor="w", padx=15, pady=(10, 5))
        
        input_frame = tk.Frame(search_card, bg=self.colors["card_bg"])
        input_frame.pack(fill="x", padx=15, pady=5)
        
        self.entry_product = tk.Entry(input_frame, font=("Helvetica", 12), 
                                      bg=self.colors["input_bg"], fg=self.colors["text_light"],
                                      insertbackground=self.colors["text_light"], relief="flat", 
                                      highlightthickness=1, highlightbackground=self.colors["card_border"])
        self.entry_product.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 10))
        self.entry_product.insert(0, "ex: Smartphone Samsung Galaxy")
        self.entry_product.bind("<FocusIn>", lambda e: self.entry_product.delete(0, 'end') if self.entry_product.get().startswith("ex:") else None)
        
        btn_search = tk.Button(input_frame, text="🔍 Buscar Média", font=("Helvetica", 11, "bold"),
                               bg=self.colors["accent_purple"], fg="white", activebackground=self.colors["hover_btn"],
                               activeforeground="white", relief="flat", cursor="hand2", padx=15,
                               command=self._search_product)
        btn_search.pack(side="right")
        
        # Áreas de Métrica / Resultados (Cards)
        results_frame = tk.Frame(self.tab_products, bg=self.colors["bg_dark"])
        results_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Métrica 1: Média Calculada
        self.card_avg = tk.Frame(results_frame, bg=self.colors["card_bg"], highlightbackground=self.colors["card_border"], highlightthickness=1)
        self.card_avg.place(relx=0, rely=0, relwidth=0.48, relheight=0.35)
        
        tk.Label(self.card_avg, text="MÉDIA DE PREÇO ESTIMADA", font=("Helvetica", 9, "bold"), 
                 fg=self.colors["text_muted"], bg=self.colors["card_bg"]).pack(pady=(12, 0))
        self.lbl_avg_val = tk.Label(self.card_avg, text="R$ --,--", font=("Helvetica", 22, "bold"), 
                                     fg=self.colors["accent_green"], bg=self.colors["card_bg"])
        self.lbl_avg_val.pack(pady=5)
        self.lbl_count_val = tk.Label(self.card_avg, text="Aguardando busca...", font=("Helvetica", 9), 
                                       fg=self.colors["text_muted"], bg=self.colors["card_bg"])
        self.lbl_count_val.pack()

        # Métrica 2: Menor Preço Encontrado
        self.card_min = tk.Frame(results_frame, bg=self.colors["card_bg"], highlightbackground=self.colors["card_border"], highlightthickness=1)
        self.card_min.place(relx=0.52, rely=0, relwidth=0.48, relheight=0.35)
        
        tk.Label(self.card_min, text="MENOR PREÇO ENCONTRADO", font=("Helvetica", 9, "bold"), 
                 fg=self.colors["text_muted"], bg=self.colors["card_bg"]).pack(pady=(12, 0))
        self.lbl_min_val = tk.Label(self.card_min, text="R$ --,--", font=("Helvetica", 22, "bold"), 
                                     fg=self.colors["accent_cyan"], bg=self.colors["card_bg"])
        self.lbl_min_val.pack(pady=5)
        self.lbl_max_val = tk.Label(self.card_min, text="Maior preço: R$ --,--", font=("Helvetica", 9), 
                                     fg=self.colors["text_muted"], bg=self.colors["card_bg"])
        self.lbl_max_val.pack()

        # Lista de Detalhes dos Anúncios
        list_card = tk.Frame(results_frame, bg=self.colors["card_bg"], highlightbackground=self.colors["card_border"], highlightthickness=1)
        list_card.place(relx=0, rely=0.40, relwidth=1.0, relheight=0.60)
        
        tk.Label(list_card, text="Amostra de Anúncios Encontrados na Internet:", font=("Helvetica", 10, "bold"), 
                 fg=self.colors["text_light"], bg=self.colors["card_bg"]).pack(anchor="w", padx=10, pady=(8, 2))
        
        self.text_details = tk.Text(list_card, font=("Consolas", 9), bg=self.colors["input_bg"], 
                                    fg=self.colors["text_light"], relief="flat", highlightthickness=0)
        self.text_details.pack(fill="both", expand=True, padx=10, pady=8)

    def _build_currencies_tab(self):
        # Card Superior: Cotações do Momento
        overview_card = tk.Frame(self.tab_currencies, bg=self.colors["card_bg"], 
                                 highlightbackground=self.colors["card_border"], highlightthickness=1)
        overview_card.pack(fill="x", padx=10, pady=15, ipady=10)
        
        tk.Label(overview_card, text="📊 Cotação Atual das Principais Moedas (Valor em R$)", 
                 font=("Helvetica", 12, "bold"), fg=self.colors["accent_amber"], bg=self.colors["card_bg"]).pack(anchor="w", padx=15, pady=(5, 10))
        
        rates_frame = tk.Frame(overview_card, bg=self.colors["card_bg"])
        rates_frame.pack(fill="x", padx=15)
        
        self.lbl_rates = {}
        currencies_info = [("USD", "🇺🇸 Dólar"), ("EUR", "🇪🇺 Euro"), ("GBP", "🇬🇧 Libra"), ("JPY", "🇯🇵 Iene")]
        
        for idx, (code, label_text) in enumerate(currencies_info):
            box = tk.Frame(rates_frame, bg=self.colors["input_bg"], padx=10, pady=8, 
                           highlightbackground=self.colors["card_border"], highlightthickness=1)
            box.grid(row=0, column=idx, padx=5, sticky="ew")
            rates_frame.grid_columnconfigure(idx, weight=1)
            
            tk.Label(box, text=label_text, font=("Helvetica", 10, "bold"), fg=self.colors["text_light"], bg=self.colors["input_bg"]).pack()
            lbl_val = tk.Label(box, text="R$ --,--", font=("Helvetica", 12, "bold"), fg=self.colors["accent_cyan"], bg=self.colors["input_bg"])
            lbl_val.pack(pady=(2, 0))
            self.lbl_rates[code] = lbl_val

        # Card Inferior: Calculadora de Conversão
        calc_card = tk.Frame(self.tab_currencies, bg=self.colors["card_bg"], 
                             highlightbackground=self.colors["card_border"], highlightthickness=1)
        calc_card.pack(fill="both", expand=True, padx=10, pady=(5, 15), ipady=10)
        
        tk.Label(calc_card, text="🔄 Calculadora de Conversão Integrada", 
                 font=("Helvetica", 12, "bold"), fg=self.colors["text_light"], bg=self.colors["card_bg"]).pack(anchor="w", padx=15, pady=(10, 15))
        
        calc_grid = tk.Frame(calc_card, bg=self.colors["card_bg"])
        calc_grid.pack(padx=20, fill="x")
        
        # Valor de Entrada
        tk.Label(calc_grid, text="Valor:", font=("Helvetica", 10, "bold"), fg=self.colors["text_muted"], bg=self.colors["card_bg"]).grid(row=0, column=0, sticky="w", padx=5)
        self.entry_amount = tk.Entry(calc_grid, font=("Helvetica", 12), width=12, bg=self.colors["input_bg"], fg=self.colors["text_light"], insertbackground="white")
        self.entry_amount.grid(row=1, column=0, padx=5, pady=(2, 15), sticky="w")
        self.entry_amount.insert(0, "100.00")
        
        # Moeda Origem
        tk.Label(calc_grid, text="De:", font=("Helvetica", 10, "bold"), fg=self.colors["text_muted"], bg=self.colors["card_bg"]).grid(row=0, column=1, sticky="w", padx=5)
        self.cb_from = ttk.Combobox(calc_grid, values=["BRL", "USD", "EUR", "GBP", "JPY"], state="readonly", width=8, font=("Helvetica", 11))
        self.cb_from.grid(row=1, column=1, padx=5, pady=(2, 15), sticky="w")
        self.cb_from.set("USD")
        
        # Seta decorativa
        tk.Label(calc_grid, text="➔", font=("Helvetica", 14, "bold"), fg=self.colors["accent_cyan"], bg=self.colors["card_bg"]).grid(row=1, column=2, padx=10, pady=(0, 15))
        
        # Moeda Destino
        tk.Label(calc_grid, text="Para:", font=("Helvetica", 10, "bold"), fg=self.colors["text_muted"], bg=self.colors["card_bg"]).grid(row=0, column=3, sticky="w", padx=5)
        self.cb_to = ttk.Combobox(calc_grid, values=["BRL", "USD", "EUR", "GBP", "JPY"], state="readonly", width=8, font=("Helvetica", 11))
        self.cb_to.grid(row=1, column=3, padx=5, pady=(2, 15), sticky="w")
        self.cb_to.set("BRL")
        
        # Botão Converter
        btn_convert = tk.Button(calc_grid, text="Calcular Conversão", font=("Helvetica", 11, "bold"),
                                bg=self.colors["accent_green"], fg=self.colors["bg_dark"],
                                activebackground="#059669", activeforeground="white",
                                relief="flat", cursor="hand2", padx=15, command=self._convert_currency)
        btn_convert.grid(row=1, column=4, padx=15, pady=(0, 15))
        
        # Box de Resultado da Conversão
        self.box_result = tk.Frame(calc_card, bg=self.colors["input_bg"], highlightbackground=self.colors["accent_purple"], highlightthickness=1)
        self.box_result.pack(fill="x", padx=20, pady=10, ipady=12)
        
        self.lbl_calc_result = tk.Label(self.box_result, text="Clique em 'Calcular Conversão' para obter o valor", 
                                        font=("Helvetica", 13, "bold"), fg=self.colors["accent_cyan"], bg=self.colors["input_bg"])
        self.lbl_calc_result.pack()

    def _fetch_currency_rates(self):
        try:
            url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,GBP-BRL,JPY-BRL"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                self.currency_rates = {
                    "BRL": 1.0,
                    "USD": float(data["USDBRL"]["bid"]),
                    "EUR": float(data["EURBRL"]["bid"]),
                    "GBP": float(data["GBPBRL"]["bid"]),
                    "JPY": float(data["JPYBRL"]["bid"])
                }
                for code, val in self.currency_rates.items():
                    if code in self.lbl_rates:
                        fmt = f"R$ {val:.4f}" if code == "JPY" else f"R$ {val:.2f}"
                        self.lbl_rates[code].config(text=fmt)
        except Exception:
            self.currency_rates = {"BRL": 1.0, "USD": 5.0, "EUR": 5.4, "GBP": 6.3, "JPY": 0.033}

    def _convert_currency(self):
        try:
            val = float(self.entry_amount.get().replace(",", "."))
            c_from = self.cb_from.get()
            c_to = self.cb_to.get()
            
            if not self.currency_rates:
                self._fetch_currency_rates()
                
            val_in_brl = val * self.currency_rates[c_from]
            final_val = val_in_brl / self.currency_rates[c_to]
            
            symbols = {"BRL": "R$", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}
            sym = symbols.get(c_to, "")
            
            self.lbl_calc_result.config(
                text=f"{val:,.2f} {c_from}  ➔  {sym} {final_val:,.2f} {c_to}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
        except ValueError:
            messagebox.showerror("Entrada Inválida", "Por favor, digite um valor numérico válido.")

    def _search_product(self):
        query = self.entry_product.get().strip()
        if not query or query.startswith("ex:"):
            messagebox.showwarning("Aviso", "Digite o nome de um produto para buscar.")
            return
            
        self.lbl_avg_val.config(text="Buscando...")
        self.lbl_min_val.config(text="Buscando...")
        self.update()
        
        try:
            url = f"https://api.mercadolibre.com/sites/MLB/search?q={quote_plus(query)}&limit=15"
            res = requests.get(url, timeout=5)
            
            if res.status_code == 200:
                data = res.json()
                results = data.get("results", [])
                
                prices = [item["price"] for item in results if "price" in item]
                
                if prices:
                    avg_price = sum(prices) / len(prices)
                    min_price = min(prices)
                    max_price = max(prices)
                    
                    self.lbl_avg_val.config(text=f"R$ {avg_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    self.lbl_count_val.config(text=f"Baseado em {len(prices)} anúncios")
                    
                    self.lbl_min_val.config(text=f"R$ {min_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    self.lbl_max_val.config(text=f"Maior preço: R$ {max_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                    
                    self.text_details.delete("1.0", tk.END)
                    for item in results[:10]:
                        title = item.get("title", "")[:50]
                        price = item.get("price", 0)
                        self.text_details.insert(tk.END, f"• {title:<52} -> R$ {price:,.2f}\n".replace(",", "X").replace(".", ",").replace("X", "."))
                    return
            
            messagebox.showinfo("Sem Resultados", "Nenhum produto foi encontrado.")
        except Exception as e:
            messagebox.showerror("Erro de Conexão", f"Falha ao realizar busca: {e}")

if __name__ == "__main__":
    app = SmartValueApp()
    app.mainloop()