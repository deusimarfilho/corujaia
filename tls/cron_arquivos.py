import os
import time
import json
import importlib
import re
import unicodedata
from datetime import date
from collections import Counter
import requests
import shutil

try:
    psycopg2 = importlib.import_module("psycopg2")
except ImportError as exc:
    raise ImportError(
        "A biblioteca psycopg2 e obrigatoria para conectar ao PostgreSQL. "
        "Instale com: pip install psycopg2-binary"
    ) from exc

# PDF -> texto (para extrair entidades localmente)
try:
    pypdf = importlib.import_module("pypdf")
except ImportError:
    pypdf = None

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
# Nomes longos em caixa alta (4+ palavras, ex: CÍCERO PEREIRA LIMA DE SOUSA)
PADRAO_NOME_LONGO = re.compile(
    r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?:\s+(?:DE|DA|DO|DAS|DOS|E))?(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}){3,6})\b"
)
PALAVRAS_NAO_PESSOA = {
    "ACESSO", "ACOMPANHADO", "ACOMPANHADOS", "ALEM", "ALÉM", "ADMINISTRATIVAS", "ANEXO", "ANO",
    "ANOTACOES", "ANOTAÇÕES", "APARELHO", "ARQUIVO", "BAIRRO", "BASE", "BATALHAO", "BATALHÃO",
    "BOLETIM", "CADERNO", "CADASTRADO", "CANCELAMENTO", "CARTEIRA", "CELULAR", "CERTIDAO",
    "CERTIDÃO", "CERTIFICADOS", "CHAVE", "CIVIS", "COM", "COMPANHIA", "COMPROVANTES", "CONDUTAS",
    "CONFORME", "CONSTA", "CONSTAVAM", "CONSTITUEM", "CONTATO", "CONTIDOS", "CONTRA", "CONCORDA",
    "COORDENADORIA", "CORPORACAO", "CORPORAÇÃO", "CRIME", "CRIANCA", "CRIANÇA", "DADOS", "DEFESA",
    "DEPOIMENTO", "DESTA", "DOCUMENTO", "ESTADO", "FALASSE", "FALSIFICACAO", "FALSIFICAÇÃO",
    "FALSIFICACOES", "FALSIFICAÇÕES", "FILHAS", "FONTE", "GOVERNO", "ILEGIVEL", "ILEGÍVEL",
    "ILICITAS", "ILÍCITAS", "IMAGEM", "INDEVIDOS", "INFOSEG", "INGRESSO", "INTEGRAR", "INTELIGENCIA",
    "INTELIGÊNCIA", "MILITAR", "MUITO", "MUNICIPIO", "MUNICÍPIO", "NACIONAL", "NUMEROS", "NÚMEROS",
    "OBITO", "ÓBITO", "PELA", "PELO", "POLICIA", "POLÍCIA", "POSSIVEL", "POSSÍVEL", "QUALIFICACAO",
    "QUALIFICAÇÃO", "RATIFICA", "PUBLICA", "PÚBLICA", "REFERENTES", "RELATORIO", "RELATÓRIO",
    "RESERVADO", "RESPONSABILIDADES", "SECRETARIA", "SECRETO", "SEGURANCA", "SEGURANÇA", "SEXUAL",
    "SISTEMA", "SITE", "SOCIAL", "SOFRIDO", "SOLICITACAO", "SOLICITAÇÃO", "SUA", "VEZ", "CEARA",
    "CEARÁ", "POR", "COMO", "PARA", "SOBRE", "MAE", "PAI", "TIPO", "CODIGO", "ENVOLVIDO",
    "PRINCIPAIS", "FREQUENTES", "NATURAL", "JURIDICA", "COLOCA", "GALOS", "COMPETICAO", "DEUS",
    "ACIMA", "TUDO", "NESSA", "ATIVIDADE", "ILICITA", "DESCUMPRIR", "SEGUE", "EXPLICANDO", "DEVE",
    "SER", "ABRIU", "CONTA", "CORRENTE", "AGENCIA", "QUERENDO", "MORRE", "RESPONDENDO", "AMEACAS",
    "TRATAR", "SITUACAO", "INTERLOCUTORA", "IZADAS", "JUDICIALMENTE", "USO", "INDEVIDO", "RIAM",
    "TDN", "MEI", "PAO", "COAGE", "DEG", "EMISSAO", "POSSE", "IZACAO", "PRA", "POSSA", "CANCELAR",
    "FUNCAO", "FUNÇÃO", "OBSERVADOS", "MENSAGENS",
}
INICIOS_INVALIDOS_PESSOA = {
    "CIDADE", "FATOS", "APOIO", "ATESTA", "REPRODUCAO", "REPRODUÇÃO", "EM",
    "PARA", "COM", "SEM", "POR", "QUE", "QUEM", "QUAL", "QUAIS", "TODO",
    "TODA", "TODOS", "TODAS", "OUTROS", "OUTRAS", "LOCAL", "LOCAIS", "APOS",
    "APÓS", "ANTES", "DURANTE", "SEGUNDO", "TERCEIRO", "PRIMEIRO",
}
PALAVRAS_INVALIDAS_PESSOA = {
    "POLICIAIS", "POLICIAL", "DESTACAMENTO", "DILIGENCIAS", "DILIGÊNCIAS",
    "SUPERVENIENTE", "IMEDIACOES", "IMEDIAÇÕES", "DESAUTORIZADA", "CONTEUDO",
    "CONTEÚDO", "REPRODUCAO", "REPRODUÇÃO", "REALIZAR", "BRAÇO",
    "DIREITO", "CAMISA", "FARDAMENTO", "UNIDADE", "BATALHAO", "BATALHÃO",
    "COMPANHIA", "COORDENADORIA", "SECRETARIA", "RELATORIO", "RELATÓRIO",
    "RESERVADO", "SIGILO", "ANEXO", "PAGINA", "PÁGINA", "DIGITALIZADO",
    # termos de narrativa (não são parte de nome)
    "QUE", "QUEM", "QUAL", "QUAIS", "COMO", "ONDE", "QUANDO", "PORQUE",
    "OS", "AS", "UM", "UMA", "UNS", "UMAS", "ESTAVA", "ESTAVAM", "ESTE",
    "ESTA", "ESTES", "ESTAS", "FOI", "FORAM", "ERA", "ERAM", "SER", "SENDO",
    "TEM", "TINHA", "TINHAM", "HA", "HÁ", "HAVIA", "SEU", "SUA", "SEUS",
    "SUAS", "ELES", "ELAS", "AQUI", "ALI", "NESTE", "NESTA", "NESSE", "NESSA",
    "TODO", "TODA", "TODOS", "TODAS", "OUTRO", "OUTRA", "OUTROS", "OUTRAS",
    "CARRO", "VEICULO", "VEÍCULO", "CELTA", "PRETO", "BRANCO", "MOTO",
    "CHEGANDO", "SAINDO", "ENTRANDO", "TIVERAM", "INFORMACOES", "INFORMAÇÕES",
    "DIRIGINDO", "CONDUZINDO", "DISSE", "DISSERAM", "RELATOU", "APONTOU",
    "LOCAL", "LOCAIS", "ENDERECO", "ENDEREÇO", "BAIRRO", "RUA", "AVENIDA",
    "EQUIPE", "SGT", "SD", "CB", "TEN", "CAP", "MAJ", "CEL", "FEZ", "ENTAO",
    "ENTÃO", "FIAT", "UNO", "COR", "VER", "MELHOR", "VISUALIZACAO", "VISUALIZAÇÃO",
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
    cursor.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
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

def nuvem_de_palavras(texto, top_k=40):
    """Gera uma nuvem de palavras simples (top termos) para busca/cruzamento."""
    if not texto:
        return []

    normalized = unicodedata.normalize("NFD", str(texto))
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.upper()

    tokens = re.findall(r"[A-Z0-9]{3,}", normalized)

    stop = set(PALAVRAS_NAO_PESSOA) | {
        "PARTE", "PAGINA", "PÁGINA", "DIGITALIZADO", "CAMSCANNER", "ASSINATURA",
        "ASSINADO", "DOCUMENTO", "DOCUMENTOS", "RELATORIO", "RELATÓRIO", "ANEXO",
        "OFICIO", "OFÍCIO", "DATA",
    }

    filtered = [
        t for t in tokens
        if t not in stop and not t.isdigit() and len(t) <= 40
    ]

    counts = Counter(filtered)
    most = counts.most_common(top_k)
    return [{"termo": termo, "count": int(count)} for termo, count in most]

def contexto_do_match(texto, inicio, fim, tamanho=180):
    """Recorta uma janela curta ao redor da entidade encontrada."""
    esquerda = max(0, inicio - tamanho)
    direita = min(len(texto), fim + tamanho)
    contexto = texto[esquerda:direita].replace("\x00", "")
    return re.sub(r"\s+", " ", contexto).strip()

def extrair_texto_pdf(caminho_pdf):
    """Extrai texto do PDF localmente para criar o JSON de entidades."""
    if pypdf is None:
        raise ImportError(
            "Dependencia ausente para ler PDF. Instale com: pip install pypdf"
        )
    try:
        reader = pypdf.PdfReader(caminho_pdf)
        partes = []
        for page in reader.pages:
            try:
                partes.append(page.extract_text() or "")
            except Exception:
                partes.append("")
        return "\n".join(partes)
    except Exception as e:
        raise RuntimeError(f"Falha ao extrair texto do PDF {caminho_pdf}: {e}") from e

def parece_nome_pessoa(valor):
    normalizado = normalizar_texto(valor)
    palavras = normalizado.split()
    conectivos = {"DE", "DA", "DO", "DAS", "DOS", "E"}
    if len(palavras) < 2 or len(palavras) > 8:
        return False
    if palavras[0] in INICIOS_INVALIDOS_PESSOA:
        return False
    if any(palavra in PALAVRAS_NAO_PESSOA for palavra in palavras):
        return False
    if any(palavra in PALAVRAS_INVALIDAS_PESSOA for palavra in palavras):
        return False
    if any(char.isdigit() for char in normalizado):
        return False
    # Frases institucionais comuns em relatórios (não são nomes)
    frases_invalidas = (
        "CIDADE DE ",
        "FATOS ",
        "APOIO DOS ",
        "REPRODUCAO ",
        "REPRODUÇÃO ",
        "ATESTA QUE ",
        "EM DESFAVOR DE ",
    )
    if any(normalizado.startswith(frase) for frase in frases_invalidas):
        return False
    substantivos = [palavra for palavra in palavras if palavra not in conectivos]
    if len(substantivos) < 2:
        return False
    if any(len(palavra) < 3 for palavra in substantivos):
        return False
    return True

def limpar_nome_pessoa(valor):
    """Remove marcadores que podem vir grudados no nome pelo OCR."""
    nome = valor.strip()
    nome = re.sub(
        r"^(?:EM\s+)?DESFAVOR\s+DE\s+",
        "",
        nome,
        flags=re.IGNORECASE,
    )
    nome = re.sub(
        r"^(?:HOMIC[IÍ]DIO\s+DE|AMEA[CÇ]A\s+A|CONTRA)\s+",
        "",
        nome,
        flags=re.IGNORECASE,
    )
    nome = re.sub(
        r"^(?:EQUIPE\s+DO\s+)?(?:SGT|SD|CB|TEN|CAP|MAJ|CEL)\s+",
        "",
        nome,
        flags=re.IGNORECASE,
    )
    nome = re.sub(
        r"^(?:NOME|VULGO|ALCUNHA|ALVO|INVESTIGADO|INVESTIGADA|ENVOLVIDO|ENVOLVIDA|INDIVIDUO|INDIVÍDUO|SUSPEITO|SUSPEITA|AUTOR|VITIMA|VÍTIMA|PESSOA)\s+",
        "",
        nome,
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

    for match in PADRAO_NOME_LONGO.finditer(texto_upper):
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

def caminho_json_entidades(caminho_pdf):
    base, _ = os.path.splitext(caminho_pdf)
    return base + ".json"

# Texto mínimo no PDF para tentar gerar JSON de entidades
MIN_CARACTERES_TEXTO_PDF = 80

# ---------------------------------------------------------------------------
# ADAPTAÇÃO: GERAÇÃO DO JSON REESTRUTURADO COM RESUMO
# ---------------------------------------------------------------------------
def criar_json_entidades_para_pdf(caminho_pdf, nome_arquivo_pdf):
    """
    Gera JSON achatado para RAG somente quando o PDF tiver texto legível
    e pelo menos uma entidade extraída. Caso contrário retorna None (só PDF).
    """
    texto = extrair_texto_pdf(caminho_pdf)
    texto_limpo = (texto or "").strip()
    if len(texto_limpo) < MIN_CARACTERES_TEXTO_PDF:
        return None

    entidades = extrair_entidades_texto(texto)
    if not entidades:
        return None

    word_cloud = nuvem_de_palavras(texto, top_k=50)
    
    # Agrupa valores brutos únicos em buckets (usando set para remover duplicatas)
    buckets = {}
    for ent in entidades:
        tipo = ent.get("tipo") or "outros"
        valor_ent = (ent.get("valor") or "").strip()
        if valor_ent:
            buckets.setdefault(tipo, set()).add(valor_ent)

    # --- LÓGICA DE RESUMO RESTAURADA ---
    resumo_partes = []
    for tipo in sorted(buckets.keys()):
        valores = sorted(list(buckets[tipo]))
        if not valores:
            continue
        # Limita a 50 itens por categoria no resumo formatado
        resumo_partes.append(f"{tipo.upper()}:\n" + "\n".join(f"- {v}" for v in valores[:50]))
    resumo = "\n\n".join(resumo_partes)
    # -----------------------------------

    pessoas = sorted(list(buckets.get("pessoa", [])))
    indice_nomes = (
        "\n".join(f"NOME: {nome}" for nome in pessoas)
        if pessoas
        else "Nenhuma pessoa identificada."
    )
    texto_busca_nomes = (
        "INDICE DE NOMES PARA BUSCA: " + " | ".join(pessoas)
        if pessoas
        else "INDICE DE NOMES PARA BUSCA: nenhum."
    )

    # Converte os sets em strings limpas separadas por vírgula e insere o resumo
    saida = {
        "arquivo_origem": nome_arquivo_pdf,
        "metadados_gerais": f"Entidades identificadas no relatório {nome_arquivo_pdf}.",
        "indice_nomes_completo": indice_nomes,
        "texto_busca_nomes": texto_busca_nomes,
        "resumo_estruturado": resumo if resumo else "Nenhuma entidade para resumir.",
        "pessoas_identificadas": ", ".join(pessoas) or "Nenhuma identificada.",
        "documentos_cpf": ", ".join(sorted(list(buckets.get("cpf", [])))) or "Nenhum identificado.",
        "telefones_e_contatos": ", ".join(sorted(list(buckets.get("telefone", [])))) or "Nenhum identificado.",
        "processos_judiciais": ", ".join(sorted(list(buckets.get("processo", [])))) or "Nenhum identificado.",
        "inqueritos_e_bos": ", ".join(sorted(list(buckets.get("inquerito", [])))) or "Nenhum identificado.",
        "enderecos_e_logradouros": ", ".join(sorted(list(buckets.get("endereco", [])))) or "Nenhum endereço identificado.",
        "municipios_citados": ", ".join(sorted(list(buckets.get("local", [])))) or "Nenhum município identificado.",
        "crimes_e_faccoes": ", ".join(sorted(list(buckets.get("crime", [])))) or "Nenhum indício criminal mapeado.",
        "termos_frequentes_nuvem": ", ".join([f"{w['termo']}({w['count']})" for w in word_cloud]) if word_cloud else "Nenhum.",
        "total_entidades_unicas": len(entidades),
    }

    caminho_json = caminho_json_entidades(caminho_pdf)
    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    return caminho_json

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

def extrair_metadados_nome(nome_arquivo):
    """
    Exemplo: 1_RT_85_2026_05_15.pdf
    Retorna: ent_id='1', tipo='RT', rel_id='85', data_producao='2026-05-15'
    """
    nome_sem_extensao, _ = os.path.splitext(nome_arquivo)
    partes = nome_sem_extensao.split('_')
    
    if len(partes) >= 6:
        ent_id = partes[0]
        tipo = partes[1]
        rel_id = partes[2]
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
    elif nome_arquivo.lower().endswith('.json'):
        return 'application/json'
    return 'application/octet-stream'

def processar_arquivo_anythingllm(caminho_completo, nome_arquivo):
    """Executa o upload e a vinculação, retornando o local interno se sucesso."""
    headers_auth = {"Authorization": f"Bearer {API_KEY}"}
    mime_type = descobrir_mime_type(nome_arquivo)
    
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
            return local_anything
        else:
            print(f"[-] Falha na vetorização de {nome_arquivo}: HTTP {res_vector.status_code} - {res_vector.text}")
            return None
    except Exception as e:
        print(f"[-] Erro de conexão na vetorização para {nome_arquivo}: {e}")
        return None

# ---------------------------------------------------------------------------
# LOOP PRINCIPAL (O WATCHER)
# ---------------------------------------------------------------------------
def iniciar_monitoramento():
    os.makedirs(DIR_PENDENTES, exist_ok=True)
    os.makedirs(DIR_PROCESSADOS, exist_ok=True)
    
    print(f"[*] Monitorando a pasta: {DIR_PENDENTES}")
    print("[*] Pressione Ctrl+C para parar.\n")
    
    conn = inicializar_banco()

    try:
        while True:
            arquivos = [f for f in os.listdir(DIR_PENDENTES) if os.path.isfile(os.path.join(DIR_PENDENTES, f))]
            
            for nome_arquivo in arquivos:
                if not nome_arquivo.lower().endswith('.pdf'):
                    continue
                
                caminho_pendente = os.path.join(DIR_PENDENTES, nome_arquivo)
                caminho_processado = os.path.join(DIR_PROCESSADOS, nome_arquivo)
                
                print(f"\n[*] Analisando: {nome_arquivo}")
                
                ent_id, rel_id, tipo, data_producao = extrair_metadados_nome(nome_arquivo)
                
                if not ent_id:
                    print(f"[-] O arquivo {nome_arquivo} não segue o padrão ID_TIPO_RELID_ANO_MES_DIA. Ignorando.")
                    continue

                nome_json = os.path.splitext(nome_arquivo)[0] + ".json"
                caminho_json_candidato = caminho_json_entidades(caminho_pendente)
                caminho_json = None
                try:
                    caminho_json = criar_json_entidades_para_pdf(caminho_pendente, nome_arquivo)
                    if caminho_json:
                        print(f"[+] JSON de entidades criado: {caminho_json}")
                    else:
                        if os.path.exists(caminho_json_candidato):
                            os.remove(caminho_json_candidato)
                        print(
                            f"[*] Sem entidades extraídas de {nome_arquivo} "
                            f"(texto vazio ou ilegível). Enviando apenas o PDF."
                        )
                except Exception as e:
                    if os.path.exists(caminho_json_candidato):
                        os.remove(caminho_json_candidato)
                    print(f"[!] Falha ao ler PDF para extração de {nome_arquivo}: {e}")
                    print("[!] Enviando apenas o PDF (sem JSON de entidades).")

                substituir = True
                for nome_para_remover in [nome_arquivo, nome_json]:
                    local_anterior = buscar_arquivo_registrado(conn, nome_para_remover)
                    if local_anterior:
                        print(f"[~] Arquivo já enviado anteriormente. Substituindo: {nome_para_remover}")
                        if not remover_arquivo_anythingllm(local_anterior, nome_para_remover):
                            print(
                                f"[-] Não foi possível remover a versão anterior de {nome_para_remover}. "
                                f"Ignorando {nome_arquivo} neste ciclo."
                            )
                            substituir = False
                            break

                if not substituir:
                    continue

                local_pdf = processar_arquivo_anythingllm(caminho_pendente, nome_arquivo)
                local_json = None
                if caminho_json and os.path.exists(caminho_json):
                    local_json = processar_arquivo_anythingllm(caminho_json, nome_json)
                
                if local_pdf:
                    try:
                        registrar_arquivo(conn, nome_arquivo, ent_id, rel_id, tipo, data_producao, local_pdf)
                        if local_json:
                            registrar_arquivo(conn, nome_json, ent_id, rel_id, tipo, data_producao, local_json)
                        
                        if os.path.exists(caminho_processado):
                            os.remove(caminho_processado)
                        shutil.move(caminho_pendente, caminho_processado)

                        if caminho_json and os.path.exists(caminho_json):
                            destino_json = os.path.join(DIR_PROCESSADOS, nome_json)
                            if os.path.exists(destino_json):
                                os.remove(destino_json)
                            shutil.move(caminho_json, destino_json)
                        
                        print(f"[>] Arquivos movidos com sucesso para: {DIR_PROCESSADOS}")
                    except Exception as e:
                        print(f"[-] Erro ao salvar no banco ou mover o arquivo {nome_arquivo}: {e}")
            
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n[*] Monitoramento encerrado pelo usuário.")
    finally:
        conn.close()

def reprocessar_entidades_indexadas():
    raise RuntimeError(
        "Este modo foi descontinuado. As entidades agora são extraídas diretamente do PDF "
        "e gravadas em um JSON ao lado do arquivo."
    )

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--reprocessar-entidades":
        reprocessar_entidades_indexadas()
    else:
        iniciar_monitoramento()