import os
import time
import json
import importlib
import re
import unicodedata
from datetime import date
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
WORKSPACE_PROMPT = (
    "Responda priorizando os arquivos indexados deste workspace. "
    "Use como fonte principal apenas o contexto recuperado dos documentos indexados. "
    "Os documentos fixados no contexto foram atualizados pelo cron e devem ser tratados como "
    "documentos disponiveis no workspace, mesmo que o usuario use termos como documento novo, "
    "ultimo documento, arquivo recente ou arquivo anexado pelo cron. "
    "Quando o usuario perguntar sobre documento novo ou recente, use primeiro o documento fixado "
    "no contexto e cite o nome do arquivo quando ele estiver disponivel. "
    "Se a resposta nao estiver claramente sustentada pelos arquivos indexados, diga explicitamente "
    "que nao encontrou evidencia suficiente nos documentos deste workspace. "
    "Nao invente fatos, nao complete lacunas com conhecimento externo e nao misture suposicoes "
    "com informacoes documentais. Quando possivel, responda de forma objetiva e fiel ao conteudo encontrado."
)

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
ANYTHING_DOCS_DIR = r"E:\xampp\htdocs\corujaia\data\anythingllm\documents"

PADROES_ENTIDADES = {
    "cpf": re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "telefone": re.compile(r"\b(?:\+?55)?\s?(?:\(?\d{2}\)?\s?)?(?:9\d{4}|\d{4})[-\s]?\d{4}\b"),
    "processo": re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b"),
    "inquerito": re.compile(r"\b(?:IP|INQUERITO|INQUÉRITO|BO|B\.O\.|ATO)\s*(?:N[ºO°.]*)?\s*[:\-]?\s*\d{1,6}[-/]\d{1,6}/\d{4}\b", re.IGNORECASE),
    "endereco": re.compile(r"\b(?:RUA|AVENIDA|AV\.|TRAVESSA|TV\.|RODOVIA|ESTRADA)\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 .,'ºª/-]{5,120}", re.IGNORECASE),
    "local": re.compile(r"\b(?:CAUCAIA|FORTALEZA|MARACANAU|MARACANAÚ|EUSEBIO|EUSÉBIO|AQUIRAZ|SOBRAL|ITAPIPOCA|CANINDE|CANINDÉ|JUAZEIRO DO NORTE|MARANGUAPE|PACAJUS|HORIZONTE|RUSSAS|QUIXADA|QUIXADÁ)\b", re.IGNORECASE),
    "crime": re.compile(r"\b(?:HOMIC[IÍ]DIO|TR[AÁ]FICO|ROUBO|FURTO|EXTORS[AÃ]O|AMEA[CÇ]A|FAC[CÇ][AÃ]O|ORCRIM|DROGAS?|ARMA DE FOGO|DESLOCAMENTO FOR[CÇ]ADO|TENTATIVA DE HOMIC[IÍ]DIO)\b", re.IGNORECASE),
}

PADRAO_PESSOA = re.compile(
    r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+(?:DA|DE|DO|DAS|DOS|E))?(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,5}\b"
)
PALAVRAS_NAO_PESSOA = {
    "RELATORIO",
    "RELATÓRIO",
    "SECRETARIA",
    "SEGURANCA",
    "SEGURANÇA",
    "PUBLICA",
    "PÚBLICA",
    "DEFESA",
    "SOCIAL",
    "COORDENADORIA",
    "INTELIGENCIA",
    "INTELIGÊNCIA",
    "DOCUMENTO",
    "RESERVADO",
    "SECRETO",
    "GOVERNO",
    "ESTADO",
    "CEARA",
    "CEARÁ",
}

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
    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sincronismo_entidades (
            id SERIAL PRIMARY KEY,
            nome_arquivo TEXT NOT NULL,
            local_anything TEXT,
            tipo_entidade TEXT NOT NULL,
            valor TEXT NOT NULL,
            valor_normalizado TEXT NOT NULL,
            contexto TEXT,
            data_extracao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (nome_arquivo, tipo_entidade, valor_normalizado)
        )
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_sincronismo_entidades_tipo_valor
        ON sincronismo_entidades (tipo_entidade, valor_normalizado)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_sincronismo_entidades_valor_trgm
        ON sincronismo_entidades USING gin (valor_normalizado gin_trgm_ops)
    ''')
    conn.commit()
    cursor.close()
    return conn

def registrar_arquivo(conn, nome_arquivo, ent_id, rel_id, tipo, data_producao, local_anything):
    """Insere os dados completos no banco após o sucesso."""
    cursor = conn.cursor()
    try:
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
                local_anything = EXCLUDED.local_anything,
                data_envio = CURRENT_TIMESTAMP
        ''', (nome_arquivo, ent_id, rel_id, tipo, data_producao, local_anything))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()

def buscar_arquivo_registrado(conn, nome_arquivo):
    """Retorna o local do documento salvo anteriormente, se existir."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT local_anything FROM sincronismo WHERE nome_arquivo = %s",
            (nome_arquivo,),
        )
        resultado = cursor.fetchone()
        return resultado[0] if resultado else None
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()

def normalizar_texto(valor):
    """Normaliza entidades para busca e cruzamento sem depender de acentos."""
    texto = unicodedata.normalize("NFD", str(valor or ""))
    texto = "".join(char for char in texto if unicodedata.category(char) != "Mn")
    texto = re.sub(r"\s+", " ", texto.upper()).strip()
    return texto

def contexto_do_match(texto, inicio, fim, tamanho=180):
    """Recorta uma janela curta ao redor da entidade encontrada."""
    esquerda = max(0, inicio - tamanho)
    direita = min(len(texto), fim + tamanho)
    contexto = texto[esquerda:direita]
    return re.sub(r"\s+", " ", contexto).strip()

def caminho_documento_anything(local_anything):
    """Converte o local interno do AnythingLLM para o caminho JSON no Windows."""
    if not local_anything:
        return None
    partes = local_anything.replace("\\", "/").split("/")
    return os.path.join(ANYTHING_DOCS_DIR, *partes)

def carregar_texto_anything(local_anything):
    """Lê o texto processado pelo AnythingLLM para alimentar o índice estruturado."""
    caminho = caminho_documento_anything(local_anything)
    if not caminho or not os.path.exists(caminho):
        print(f"[-] JSON processado não encontrado para extrair entidades: {local_anything}")
        return ""

    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados.get("pageContent") or ""
    except Exception as e:
        print(f"[-] Erro ao carregar JSON processado {caminho}: {e}")
        return ""

def parece_nome_pessoa(valor):
    normalizado = normalizar_texto(valor)
    palavras = normalizado.split()
    if len(palavras) < 2:
        return False
    if any(palavra in PALAVRAS_NAO_PESSOA for palavra in palavras):
        return False
    if any(char.isdigit() for char in normalizado):
        return False
    return True

def extrair_entidades_texto(texto):
    """Extrai entidades úteis para cruzamento investigativo."""
    entidades = []
    vistos = set()

    for tipo, padrao in PADROES_ENTIDADES.items():
        for match in padrao.finditer(texto):
            valor = match.group(0).strip(" .,;:\n\r\t")
            normalizado = normalizar_texto(valor)
            chave = (tipo, normalizado)
            if not normalizado or chave in vistos:
                continue
            vistos.add(chave)
            entidades.append({
                "tipo": tipo,
                "valor": valor,
                "valor_normalizado": normalizado,
                "contexto": contexto_do_match(texto, match.start(), match.end()),
            })

    texto_upper = texto.upper()
    for match in PADRAO_PESSOA.finditer(texto_upper):
        valor = match.group(0).strip(" .,;:\n\r\t")
        if not parece_nome_pessoa(valor):
            continue
        normalizado = normalizar_texto(valor)
        chave = ("pessoa", normalizado)
        if chave in vistos:
            continue
        vistos.add(chave)
        entidades.append({
            "tipo": "pessoa",
            "valor": valor,
            "valor_normalizado": normalizado,
            "contexto": contexto_do_match(texto, match.start(), match.end()),
        })

    return entidades

def registrar_entidades_documento(conn, nome_arquivo, local_anything):
    """Atualiza o índice estruturado de entidades do documento."""
    texto = carregar_texto_anything(local_anything)
    if not texto.strip():
        print(f"[~] Sem texto útil para extrair entidades: {nome_arquivo}")
        return

    entidades = extrair_entidades_texto(texto)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM sincronismo_entidades WHERE nome_arquivo = %s",
            (nome_arquivo,),
        )
        for entidade in entidades:
            cursor.execute(
                '''
                    INSERT INTO sincronismo_entidades (
                        nome_arquivo, local_anything, tipo_entidade, valor, valor_normalizado, contexto
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (nome_arquivo, tipo_entidade, valor_normalizado) DO UPDATE SET
                        local_anything = EXCLUDED.local_anything,
                        valor = EXCLUDED.valor,
                        contexto = EXCLUDED.contexto,
                        data_extracao = CURRENT_TIMESTAMP
                ''',
                (
                    nome_arquivo,
                    local_anything,
                    entidade["tipo"],
                    entidade["valor"],
                    entidade["valor_normalizado"],
                    entidade["contexto"],
                ),
            )
        conn.commit()
        print(f"[+] Entidades estruturadas extraídas: {len(entidades)} em {nome_arquivo}")
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()

def remover_arquivo_anythingllm(local_anything, nome_arquivo):
    """Remove o documento antigo do workspace e do armazenamento do AnythingLLM."""
    if not local_anything:
        return True

    headers_json = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    url_workspace = f"{API_BASE_URL}/workspace/{WORKSPACE_SLUG}/update-embeddings"
    payload_workspace = {"deletes": [local_anything]}

    try:
        res_workspace = requests.post(url_workspace, headers=headers_json, json=payload_workspace)
        if res_workspace.status_code != 200:
            print(
                f"[-] Falha ao remover {nome_arquivo} do workspace: "
                f"HTTP {res_workspace.status_code} - {res_workspace.text}"
            )
            return False
    except Exception as e:
        print(f"[-] Erro ao remover {nome_arquivo} do workspace: {e}")
        return False

    url_documentos = f"{API_BASE_URL}/system/remove-documents"
    payload_documentos = {"names": [local_anything]}

    try:
        res_documentos = requests.delete(url_documentos, headers=headers_json, json=payload_documentos)
        if res_documentos.status_code != 200:
            print(
                f"[-] Falha ao remover {nome_arquivo} do AnythingLLM: "
                f"HTTP {res_documentos.status_code} - {res_documentos.text}"
            )
            return False
    except Exception as e:
        print(f"[-] Erro ao remover {nome_arquivo} do AnythingLLM: {e}")
        return False

    print(f"[~] Documento anterior removido do AnythingLLM: {nome_arquivo}")
    return True

def atualizar_prompt_workspace():
    """Garante que o chat interprete documentos do cron como contexto indexado."""
    url_workspace = f"{API_BASE_URL}/workspace/{WORKSPACE_SLUG}/update"
    headers_json = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "openAiPrompt": WORKSPACE_PROMPT,
        "chatMode": "query",
        "openAiHistory": 20,
    }

    try:
        res_workspace = requests.post(url_workspace, headers=headers_json, json=payload)
        if res_workspace.status_code != 200:
            print(
                f"[-] Falha ao atualizar prompt do workspace: "
                f"HTTP {res_workspace.status_code} - {res_workspace.text}"
            )
    except Exception as e:
        print(f"[-] Erro ao atualizar prompt do workspace: {e}")

def fixar_documento_recente_no_workspace(conn, local_anything, nome_arquivo):
    """Fixa o documento mais recente no workspace para entrar direto no contexto do chat."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM workspaces WHERE slug = %s",
            (WORKSPACE_SLUG,),
        )
        workspace = cursor.fetchone()
        if not workspace:
            print(f"[-] Workspace {WORKSPACE_SLUG} não encontrado para fixar {nome_arquivo}.")
            return

        workspace_id = workspace[0]
        cursor.execute(
            'UPDATE workspace_documents SET pinned = FALSE WHERE "workspaceId" = %s',
            (workspace_id,),
        )
        cursor.execute(
            '''
                UPDATE workspace_documents
                SET pinned = TRUE, "lastUpdatedAt" = CURRENT_TIMESTAMP
                WHERE "workspaceId" = %s AND docpath = %s
            ''',
            (workspace_id, local_anything),
        )

        if cursor.rowcount == 0:
            print(f"[-] Documento {nome_arquivo} foi vetorizado, mas não foi encontrado para fixar.")
        else:
            cursor.execute(
                'UPDATE workspaces SET "lastUpdatedAt" = CURRENT_TIMESTAMP WHERE id = %s',
                (workspace_id,),
            )
            print(f"[+] Documento fixado como contexto recente do chat: {nome_arquivo}")

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[-] Erro ao fixar {nome_arquivo} no workspace: {e}")
    finally:
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
        try:
            data_producao = date(int(ano), int(mes), int(dia)).isoformat()
        except ValueError:
            data_producao = None
            print(f"[!] Data inválida no nome {nome_arquivo}. Salvando data_producao como NULL.")
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

def arquivo_txt_vazio(caminho_completo):
    """Evita enviar TXT sem conteúdo útil, pois o AnythingLLM gera 0 snippets."""
    try:
        with open(caminho_completo, "r", encoding="utf-8", errors="ignore") as arquivo:
            return arquivo.read().strip() == ""
    except Exception as e:
        print(f"[-] Erro ao ler TXT {caminho_completo}: {e}")
        return True

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
    atualizar_prompt_workspace()

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

                if nome_arquivo.lower().endswith('.txt') and arquivo_txt_vazio(caminho_pendente):
                    print(f"[~] TXT sem conteúdo útil. Ignorando indexação: {nome_arquivo}")
                    try:
                        if os.path.exists(caminho_processado):
                            os.remove(caminho_processado)
                        shutil.move(caminho_pendente, caminho_processado)
                        print(f"[>] TXT vazio movido para: {DIR_PROCESSADOS}")
                    except Exception as e:
                        print(f"[-] Erro ao mover TXT vazio {nome_arquivo}: {e}")
                    continue
                
                # Extrai as informações do nome do arquivo
                ent_id, rel_id, tipo, data_producao = extrair_metadados_nome(nome_arquivo)
                
                if not ent_id:
                    print(f"[-] O arquivo {nome_arquivo} não segue o padrão ID_TIPO_RELID_ANO_MES_DIA. Ignorando.")
                    continue

                local_anterior = buscar_arquivo_registrado(conn, nome_arquivo)
                if local_anterior:
                    print(f"[~] Arquivo já enviado anteriormente. Substituindo: {nome_arquivo}")
                    if not remover_arquivo_anythingllm(local_anterior, nome_arquivo):
                        print(f"[-] Não foi possível remover a versão anterior de {nome_arquivo}. Ignorando.")
                        continue

                # Tenta enviar para o AnythingLLM
                local_anything = processar_arquivo_anythingllm(caminho_pendente, nome_arquivo)
                
                # Se tudo deu certo no AnythingLLM: salva no banco e move de pasta
                if local_anything:
                    try:
                        # 1. Salva no banco com todos os metadados
                        registrar_arquivo(conn, nome_arquivo, ent_id, rel_id, tipo, data_producao, local_anything)
                        registrar_entidades_documento(conn, nome_arquivo, local_anything)
                        fixar_documento_recente_no_workspace(conn, local_anything, nome_arquivo)
                        
                        # 2. Move o arquivo fisicamente para a pasta de processados
                        if os.path.exists(caminho_processado):
                            os.remove(caminho_processado)
                        shutil.move(caminho_pendente, caminho_processado)
                        
                        print(f"[>] Arquivo movido para: {DIR_PROCESSADOS}")
                    except Exception as e:
                        print(f"[-] Erro ao salvar no banco ou mover o arquivo {nome_arquivo}: {e}")
            
            # Pausa de 20 segundos antes de olhar a pasta pendentes novamente
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n[*] Monitoramento encerrado pelo usuário.")
    finally:
        conn.close()

if __name__ == "__main__":
    iniciar_monitoramento()