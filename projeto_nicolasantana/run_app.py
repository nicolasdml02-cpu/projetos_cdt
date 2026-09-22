import os
import sys
import time
import threading
import webbrowser
import streamlit.web.cli as stcli

def resolve_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def open_browser():
    # Aguarda 2 segundos para o servidor Streamlit iniciar
    time.sleep(2)
    webbrowser.open_new_tab("http://localhost:8501")

if __name__ == "__main__":
    script_path = resolve_path("app_web.py")
    
    # Inicia a abertura do navegador em uma thread separada
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Configura os argumentos para executar o Streamlit
    sys.argv = ["streamlit", "run", script_path, "--global.developmentMode=false"]
    
    sys.exit(stcli.main())