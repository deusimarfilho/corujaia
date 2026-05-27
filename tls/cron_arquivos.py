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
    "Voce e um assistente de cruzamento investigativo de alta precisao. "
    "Responda SOMENTE com base nos arquivos indexados deste workspace e nas fontes estruturadas recuperadas. "
    "Sempre cruze informacoes: use juntos o contexto dos documentos (trechos recuperados) e o indice estruturado de entidades. "
    "Quando o contexto trouxer sourceType structured_entity_index, titulo iniciando com [CRUZAMENTO] ou o texto "
    "Resumo estruturado para cruzamento, trate como evidencia primaria extraida dos documentos indexados. "
    "Para qualquer pergunta (pessoa, local, crime, CPF, telefone, processo, inquerito, endereco), "
    "liste TODAS as entidades relevantes do bloco [CRUZAMENTO] Cruzamento entre documentos ou [CRUZAMENTO] Pessoas encontradas, "
    "mantendo o agrupamento por tipo (PESSOAS, LOCAIS, CRIMES, etc.) quando existir. "
    "Nao omita nem ignore itens presentes nesse cruzamento; complemente com trechos dos arquivos quando ajudar a contextualizar. "
    "Cite sempre o nome do arquivo de origem quando disponivel. "
    "Nao diga que nao ha dados se o cruzamento estruturado listar entidades, mesmo que outro trecho do contexto seja incompleto. "
    "Se o contexto contiver INSTRUCAO OBRIGATORIA ou [CONTEXT 0] com bloco PESSOAS, essa e a fonte principal: copie a lista de nomes na resposta. "
    "Nunca contradiga o bloco PESSOAS do cruzamento estruturado. "
    "Quando o usuario perguntar sobre documento novo, ultimo documento ou arquivo recente, "
    "procure nos arquivos indexados e nas entidades estruturadas. "
    "Se a resposta nao estiver sustentada pelos documentos indexados, diga explicitamente que nao encontrou evidencia suficiente. "
    "Nao invente fatos, nao complete lacunas com conhecimento externo e nao misture suposicoes com informacoes documentais. "
    "Responda de forma objetiva, completa e fiel ao conteudo encontrado."
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

PADRAO_NOME_PESSOA = r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:[ \t]+(?:DA|DE|DO|DAS|DOS|E))?(?:[ \t]+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){1,4}"
PADROES_PESSOA = [
    re.compile(
        rf"\b(?:NOME|VULGO|ALCUNHA|ALVO|INVESTIGADO|INVESTIGADA|ENVOLVIDO|ENVOLVIDA|INDIVIDUO|INDIVÍDUO|SUSPEITO|SUSPEITA|AUTOR|VITIMA|VÍTIMA|QUALIFICADO|QUALIFICADA|PESSOA)\s*(?:DE|DA|DO)?\s*[:\-]?\s*({PADRAO_NOME_PESSOA})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b({PADRAO_NOME_PESSOA})\b[\s,.;:-]{{0,40}}(?:CPF|RG|NASCIDO|NASCIDA|FILHO|FILHA|VULGO|QUALIFICAÇÃO|QUALIFICACAO)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:HOMIC[IÍ]DIO DE|AMEA[CÇ]A A|CONTRA|EM DESFAVOR DE)\s+({PADRAO_NOME_PESSOA})\b",
        re.IGNORECASE,
    ),
]
PALAVRAS_NAO_PESSOA = {
    "ACESSO",
    "ACOMPANHADO",
    "ACOMPANHADOS",
    "ALEM",
    "ALÉM",
    "ADMINISTRATIVAS",
    "ANEXO",
    "ANO",
    "ANOTACOES",
    "ANOTAÇÕES",
    "APARELHO",
    "ARQUIVO",
    "BAIRRO",
    "BASE",
    "BATALHAO",
    "BATALHÃO",
    "BOLETIM",
    "CADERNO",
    "CADASTRADO",
    "CANCELAMENTO",
    "CARTEIRA",
    "CELULAR",
    "CERTIDAO",
    "CERTIDÃO",
    "CERTIFICADOS",
    "CHAVE",
    "CIVIS",
    "COM",
    "COMPANHIA",
    "COMPROVANTES",
    "CONDUTAS",
    "CONFORME",
    "CONSTA",
    "CONSTAVAM",
    "CONSTITUEM",
    "CONTATO",
    "CONTIDOS",
    "CONTRA",
    "CONCORDA",
    "COORDENADORIA",
    "CORPORACAO",
    "CORPORAÇÃO",
    "CRIME",
    "CRIANCA",
    "CRIANÇA",
    "DADOS",
    "DEFESA",
    "DEPOIMENTO",
    "DESTA",
    "DOCUMENTO",
    "ESTADO",
    "FALASSE",
    "FALSIFICACAO",
    "FALSIFICAÇÃO",
    "FALSIFICACOES",
    "FALSIFICAÇÕES",
    "FILHAS",
    "FONTE",
    "GOVERNO",
    "ILEGIVEL",
    "ILEGÍVEL",
    "ILICITAS",
    "ILÍCITAS",
    "IMAGEM",
    "INDEVIDOS",
    "INFOSEG",
    "INGRESSO",
    "INTEGRAR",
    "INTELIGENCIA",
    "INTELIGÊNCIA",
    "MILITAR",
    "MUITO",
    "MUNICIPIO",
    "MUNICÍPIO",
    "NACIONAL",
    "NUMEROS",
    "NÚMEROS",
    "OBITO",
    "ÓBITO",
    "PELA",
    "PELO",
    "POLICIA",
    "POLÍCIA",
    "POSSIVEL",
    "POSSÍVEL",
    "QUALIFICACAO",
    "QUALIFICAÇÃO",
    "RATIFICA",
    "PUBLICA",
    "PÚBLICA",
    "REFERENTES",
    "RELATORIO",
    "RELATÓRIO",
    "RESERVADO",
    "RESPONSABILIDADES",
    "SECRETARIA",
    "SECRETO",
    "SEGURANCA",
    "SEGURANÇA",
    "SEXUAL",
    "SISTEMA",
    "SITE",
    "SOCIAL",
    "SOFRIDO",
    "SOLICITACAO",
    "SOLICITAÇÃO",
    "SUA",
    "VEZ",
    "CEARA",
    "CEARÁ",
    "POR",
    "COMO",
    "PARA",
    "SOBRE",
    "MAE",
    "PAI",
    "TIPO",
    "CODIGO",
    "ENVOLVIDO",
    "PRINCIPAIS",
    "FREQUENTES",
    "NATURAL",
    "JURIDICA",
    "COLOCA",
    "GALOS",
    "COMPETICAO",
    "DEUS",
    "ACIMA",
    "TUDO",
    "NESSA",
    "ATIVIDADE",
    "ILICITA",
    "DESCUMPRIR",
    "SEGUE",
    "EXPLICANDO",
    "DEVE",
    "SER",
    "ABRIU",
    "CONTA",
    "CORRENTE",
    "AGENCIA",
    "QUERENDO",
    "MORRE",
    "RESPONDENDO",
    "AMEACAS",
    "TRATAR",
    "SITUACAO",
    "INTERLOCUTORA",
    "IZADAS",
    "JUDICIALMENTE",
    "USO",
    "INDEVIDO",
    "RIAM",
    "TDN",
    "MEI",
    "PAO",
    "COAGE",
    "DEG",
    "EMISSAO",
    "POSSE",
    "IZACAO",
    "PRA",
    "POSSA",
    "CANCELAR",
    "FUNCAO",
    "FUNÇÃO",
    "OBSERVADOS",
    "MENSAGENS",
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
    texto = unicodedata.normalize("NFD", str(valor or "").replace("\x00", ""))
    texto = "".join(char for char in texto if unicodedata.category(char) != "Mn")
    texto = re.sub(r"\s+", " ", texto.upper()).strip()
    return texto

def contexto_do_match(texto, inicio, fim, tamanho=180):
    """Recorta uma janela curta ao redor da entidade encontrada."""
    esquerda = max(0, inicio - tamanho)
    direita = min(len(texto), fim + tamanho)
    contexto = texto[esquerda:direita].replace("\x00", "")
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
    conectivos = {"DE", "DA", "DO", "DAS", "DOS", "E"}
    if len(palavras) < 2 or len(palavras) > 6:
        return False
    if any(palavra in PALAVRAS_NAO_PESSOA for palavra in palavras):
        return False
    if any(char.isdigit() for char in normalizado):
        return False
    substantivos = [palavra for palavra in palavras if palavra not in conectivos]
    if len(substantivos) < 2:
        return False
    if any(len(palavra) < 3 for palavra in substantivos):
        return False
    return True

def limpar_nome_pessoa(valor):
    """Remove marcadores que podem vir grudados no nome pelo OCR."""
    nome = re.sub(
        r"^(?:NOME|VULGO|ALCUNHA|ALVO|INVESTIGADO|INVESTIGADA|ENVOLVIDO|ENVOLVIDA|INDIVIDUO|INDIVÍDUO|SUSPEITO|SUSPEITA|AUTOR|VITIMA|VÍTIMA|PESSOA)\s+",
        "",
        valor.strip(),
        flags=re.IGNORECASE,
    )
    nome = re.sub(
        r"\s+(?:SUA|MAE|MÃE|PAI|RG|CPF|DN|ENDERECO|ENDEREÇO|QUALIFICACAO|QUALIFICAÇÃO)\b.*$",
        "",
        nome,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", nome).strip()

def extrair_entidades_texto(texto):
    """Extrai entidades úteis para cruzamento investigativo."""
    entidades = []
    vistos = set()

    for tipo, padrao in PADROES_ENTIDADES.items():
        for match in padrao.finditer(texto):
            valor = match.group(0).replace("\x00", "").strip(" .,;:\n\r\t")
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
    for padrao in PADROES_PESSOA:
        for match in padrao.finditer(texto_upper):
            valor = limpar_nome_pessoa(match.group(1).replace("\x00", "").strip(" .,;:\n\r\t"))
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
                "contexto": contexto_do_match(texto, match.start(1), match.end(1)),
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

def reprocessar_entidades_indexadas():
    """Reextrai entidades de todos os documentos já presentes em sincronismo."""
    conn = inicializar_banco()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT nome_arquivo, local_anything FROM sincronismo ORDER BY nome_arquivo"
        )
        registros = cursor.fetchall()
    finally:
        cursor.close()

    total = len(registros)
    processados = 0
    sem_texto = 0
    erros = 0
    print(f"[*] Reprocessando entidades de {total} documento(s)...")

    for indice, (nome_arquivo, local_anything) in enumerate(registros, start=1):
        try:
            texto = carregar_texto_anything(local_anything)
            if not texto.strip():
                sem_texto += 1
                continue
            registrar_entidades_documento(conn, nome_arquivo, local_anything)
            processados += 1
        except Exception as e:
            erros += 1
            print(f"[-] Falha em {nome_arquivo}: {e}")

        if indice % 100 == 0 or indice == total:
            print(f"[~] Progresso: {indice}/{total} | ok={processados} | sem_texto={sem_texto} | erros={erros}")

    conn.close()
    print(
        f"[+] Reprocessamento concluído: {processados} documento(s) atualizado(s), "
        f"{sem_texto} sem texto, {erros} erro(s)."
    )

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--reprocessar-entidades":
        reprocessar_entidades_indexadas()
    else:
        iniciar_monitoramento()