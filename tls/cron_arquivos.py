import os
import time
import json
import importlib
import requests
import shutil

try:
    psycopg2 = importlib.import_module("psycopg2")
except ImportError as exc:
    raise ImportError(
        "A biblioteca psycopg2 e obrigatoria para conectar ao PostgreSQL. "
        "Instale com: pip install psycopg2-binary"
    ) from exc

# ---------------------------------------------------------------------------
# CONFIGURAÇÕES DA INTEGRAÇÃO
# ---------------------------------------------------------------------------
API_BASE_URL = "http://localhost:3001/api/v1"
API_KEY = "YEYBJBE-HZ24RMS-GGCSCM2-Z4JR33C"
# Slug real do workspace no AnythingLLM/PostgreSQL. Slug e case-sensitive.
WORKSPACE_SLUG = "sbdi_coin"

# Configuração do PostgreSQL do projeto
PGHOST = "127.0.0.1"
PGPORT = 55432
PGDATABASE = "corujaia"
PGUSER = "corujaia"
PGPASSWORD = "corujaia_pgvector_2026"

# Configuração de Diretórios (Hot Folder)
BASE_DIR = r"E:\xampp\htdocs\corujaia\arquivos\sbdi"
DIR_PENDENTES = os.path.join(BASE_DIR, "pendentes")
DIR_PROCESSADOS = os.path.join(BASE_DIR, "processados")

# ---------------------------------------------------------------------------
# INICIALIZAÇÃO DO BANCO DE DADOS
# ---------------------------------------------------------------------------
def inicializar_banco():
    """Conecta ao PostgreSQL e cria a tabela de sincronismo."""
    conn = psycopg2.connect(
        host=PGHOST,
        port=PGPORT,
        dbname=PGDATABASE,
        user=PGUSER,
        password=PGPASSWORD,
    )
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sincronismo (
            nome_arquivo TEXT PRIMARY KEY,
            data_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ent_id TEXT,
            rel_id TEXT,
            tipo TEXT,
            data_producao DATE,
            local_anything TEXT
        )
    ''')
    conn.commit()
    cursor.close()
    return conn

def registrar_arquivo(conn, nome_arquivo, ent_id, rel_id, tipo, data_producao, local_anything):
    """Insere os dados completos no banco após o sucesso."""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sincronismo (
            nome_arquivo, ent_id, rel_id, tipo, data_producao, local_anything
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (nome_arquivo) DO UPDATE SET
            ent_id = EXCLUDED.ent_id,
            rel_id = EXCLUDED.rel_id,
            tipo = EXCLUDED.tipo,
            data_producao = EXCLUDED.data_producao,
            local_anything = EXCLUDED.local_anything
    ''', (nome_arquivo, ent_id, rel_id, tipo, data_producao, local_anything))
    conn.commit()
    cursor.close()

# ---------------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ---------------------------------------------------------------------------
def extrair_metadados_nome(nome_arquivo):
    """
    Exemplo: 1_RT_85_2026_05_15.pdf
    Retorna: ent_id='1', tipo='RT', rel_id='85', data_producao='2026-05-15'
    """
    # Remove a extensão (.pdf ou .txt)
    nome_sem_extensao, _ = os.path.splitext(nome_arquivo)
    
    # Dá o split pelo underline
    partes = nome_sem_extensao.split('_')
    
    # Valida se o arquivo segue o padrão esperado
    if len(partes) >= 6:
        ent_id = partes[0]
        tipo = partes[1]
        rel_id = partes[2]
        # Pega as partes da data e converte para o formato DATE do PostgreSQL
        ano = partes[3]
        mes = partes[4]
        dia = partes[5]
        data_producao = f"{ano}-{mes}-{dia}"
        return ent_id, rel_id, tipo, data_producao
    else:
        return None, None, None, None

def descobrir_mime_type(nome_arquivo):
    """Retorna o tipo MIME correto para a API do AnythingLLM."""
    if nome_arquivo.lower().endswith('.pdf'):
        return 'application/pdf'
    elif nome_arquivo.lower().endswith('.txt'):
        return 'text/plain'
    return 'application/octet-stream'

# ---------------------------------------------------------------------------
# LÓGICA DE UPLOAD E VETORIZAÇÃO (ANYTHINGLLM)
# ---------------------------------------------------------------------------
def processar_arquivo_anythingllm(caminho_completo, nome_arquivo):
    """Executa o upload e a vinculação, retornando o local interno se sucesso."""
    headers_auth = {"Authorization": f"Bearer {API_KEY}"}
    mime_type = descobrir_mime_type(nome_arquivo)
    
    # 1. Upload
    url_upload = f"{API_BASE_URL}/document/upload"
    try:
        with open(caminho_completo, 'rb') as f:
            files = {'file': (nome_arquivo, f, mime_type)}
            res_upload = requests.post(url_upload, headers=headers_auth, files=files)
            
        if res_upload.status_code != 200:
            print(f"[-] Falha no upload de {nome_arquivo}: {res_upload.text}")
            return None
            
        dados = res_upload.json()
        local_anything = dados["documents"][0]["location"]
    except Exception as e:
        print(f"[-] Erro ao enviar {nome_arquivo}: {e}")
        return None

    # 2. Update Embeddings (Vincular ao Workspace)
    url_workspace = f"{API_BASE_URL}/workspace/{WORKSPACE_SLUG}/update-embeddings"
    headers_json = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"adds": [local_anything]}
    
    try:
        res_vector = requests.post(url_workspace, headers=headers_json, json=payload)
        if res_vector.status_code == 200:
            print(f"[+] Sucesso na vetorização de {nome_arquivo}.")
            return local_anything # Retorna o local para salvar no banco
        else:
            print(
                f"[-] Falha na vetorização de {nome_arquivo}: "
                f"HTTP {res_vector.status_code} - {res_vector.text}"
            )
            return None
    except Exception as e:
        print(f"[-] Erro de conexão na vetorização para {nome_arquivo}: {e}")
        return None

# ---------------------------------------------------------------------------
# LOOP PRINCIPAL (O WATCHER)
# ---------------------------------------------------------------------------
def iniciar_monitoramento():
    # Cria as pastas fisicamente caso não existam no Windows
    os.makedirs(DIR_PENDENTES, exist_ok=True)
    os.makedirs(DIR_PROCESSADOS, exist_ok=True)
    
    print(f"[*] Monitorando a pasta: {DIR_PENDENTES}")
    print("[*] Pressione Ctrl+C para parar.\n")
    
    conn = inicializar_banco()

    try:
        while True:
            # Pega todos os arquivos da pasta PENDENTES
            arquivos = [f for f in os.listdir(DIR_PENDENTES) if os.path.isfile(os.path.join(DIR_PENDENTES, f))]
            
            for nome_arquivo in arquivos:
                # Processa apenas extensões válidas
                if not (nome_arquivo.lower().endswith('.pdf') or nome_arquivo.lower().endswith('.txt')):
                    continue
                
                caminho_pendente = os.path.join(DIR_PENDENTES, nome_arquivo)
                caminho_processado = os.path.join(DIR_PROCESSADOS, nome_arquivo)
                
                print(f"\n[*] Analisando: {nome_arquivo}")
                
                # Extrai as informações do nome do arquivo
                ent_id, rel_id, tipo, data_producao = extrair_metadados_nome(nome_arquivo)
                
                if not ent_id:
                    print(f"[-] O arquivo {nome_arquivo} não segue o padrão ID_TIPO_RELID_ANO_MES_DIA. Ignorando.")
                    continue

                # Tenta enviar para o AnythingLLM
                local_anything = processar_arquivo_anythingllm(caminho_pendente, nome_arquivo)
                
                # Se tudo deu certo no AnythingLLM: salva no banco e move de pasta
                if local_anything:
                    try:
                        # 1. Salva no banco com todos os metadados
                        registrar_arquivo(conn, nome_arquivo, ent_id, rel_id, tipo, data_producao, local_anything)
                        
                        # 2. Move o arquivo fisicamente para a pasta de processados
                        shutil.move(caminho_pendente, caminho_processado)
                        
                        print(f"[>] Arquivo movido para: {DIR_PROCESSADOS}")
                    except Exception as e:
                        print(f"[-] Erro ao salvar no banco ou mover o arquivo {nome_arquivo}: {e}")
            
            # Pausa de 20 segundos antes de olhar a pasta pendentes novamente
            time.sleep(20)
            
    except KeyboardInterrupt:
        print("\n[*] Monitoramento encerrado pelo usuário.")
    finally:
        conn.close()

if __name__ == "__main__":
    iniciar_monitoramento()