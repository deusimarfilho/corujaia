import base64
import os
import time

import requests


API_GET_DOCUMENTOS = "https://seispcentral.sspds.ce.gov.br/sbdi/index.php/Api/getDocumentosIa/5"
API_SET_DOCUMENTO = "https://seispcentral.sspds.ce.gov.br/sbdi/index.php/Api/setIaDocumento/{rel_id}/{rm_id}"
API_AUTH = ("suporte", "coin@2023#$")
DIR_PENDENTES = r"E:\xampp\htdocs\corujaia\arquivos\sbdi\pendentes"
INTERVALO_SEGUNDOS = 10


def nome_seguro(nome_arquivo):
    """Impede que a API grave arquivos fora da pasta pendentes."""
    if not nome_arquivo:
        return None

    nome = os.path.basename(str(nome_arquivo).strip())
    if nome in ("", ".", ".."):
        return None

    return nome


def id_informado(valor):
    """Aceita 0 e "0"; rejeita apenas valor ausente ou texto vazio."""
    return valor is not None and str(valor).strip() != ""


def texto_util(texto):
    """Retorna True apenas quando existe texto real para indexar."""
    return texto is not None and str(texto).strip() != ""


def decodificar_base64(conteudo_base64):
    """Decodifica base64 puro ou no formato data:application/pdf;base64,..."""
    if not conteudo_base64:
        return None

    conteudo = str(conteudo_base64).strip()
    if "," in conteudo and ";base64" in conteudo.split(",", 1)[0]:
        conteudo = conteudo.split(",", 1)[1]

    return base64.b64decode(conteudo, validate=True)


def salvar_arquivo_binario(nome_arquivo, conteudo_base64):
    nome = nome_seguro(nome_arquivo)
    if not nome:
        print("[-] Nome do arquivo binario invalido. Ignorando documento.")
        return False

    dados = decodificar_base64(conteudo_base64)
    if dados is None:
        print(f"[-] Documento {nome} sem conteudo base64.")
        return False

    caminho = os.path.join(DIR_PENDENTES, nome)
    with open(caminho, "wb") as arquivo:
        arquivo.write(dados)

    print(f"[+] Arquivo criado: {caminho}")
    return True


def salvar_arquivo_texto(nome_arquivo_txt, texto):
    if not texto_util(texto):
        print("[~] Campo texto vazio. TXT nao sera criado.")
        return True

    nome = nome_seguro(nome_arquivo_txt)
    if not nome:
        print("[-] Nome do arquivo TXT invalido. Ignorando TXT.")
        return False

    caminho = os.path.join(DIR_PENDENTES, nome)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        arquivo.write(str(texto))

    print(f"[+] TXT criado: {caminho}")
    return True


def confirmar_documento(rel_id, rm_id):
    url = API_SET_DOCUMENTO.format(rel_id=rel_id, rm_id=rm_id)
    resposta = requests.get(url, auth=API_AUTH, timeout=30)

    if resposta.status_code == 200:
        print(f"[>] Documento confirmado no SBDI: rel_id={rel_id}, rm_id={rm_id}")
        return True

    print(
        f"[-] Falha ao confirmar documento rel_id={rel_id}, rm_id={rm_id}: "
        f"HTTP {resposta.status_code} - {resposta.text}"
    )
    return False


def processar_documento(documento):
    rel_id = documento.get("rel_id")
    rm_id = documento.get("rm_id", 0)
    nome_arquivo = documento.get("nome_arquivo")
    arquivo_base64 = documento.get("arquivo")

    if not id_informado(rel_id):
        print("[-] Documento sem rel_id. Ignorando.")
        return

    if not id_informado(rm_id):
        rm_id = 0

    try:
        criou_pdf = salvar_arquivo_binario(nome_arquivo, arquivo_base64)
        if criou_pdf:
            confirmar_documento(rel_id, rm_id)
        else:
            print(f"[-] Documento rel_id={rel_id}, rm_id={rm_id} nao foi confirmado por falha ao criar o PDF.")
    except Exception as e:
        print(f"[-] Erro ao processar documento rel_id={rel_id}, rm_id={rm_id}: {e}")


def buscar_documentos():
    resposta = requests.get(API_GET_DOCUMENTOS, auth=API_AUTH, timeout=60)
    if resposta.status_code != 200:
        print(f"[-] Falha ao buscar documentos: HTTP {resposta.status_code} - {resposta.text}")
        return []

    dados = resposta.json()
    if dados.get("error"):
        print(f"[-] API retornou erro: {dados.get('msg')}")
        return []

    documentos = dados.get("documentos") or []
    if not isinstance(documentos, list):
        print("[-] Campo documentos nao veio como lista.")
        return []

    return documentos


def iniciar_monitoramento():
    os.makedirs(DIR_PENDENTES, exist_ok=True)
    print(f"[*] Buscando documentos do SBDI em: {API_GET_DOCUMENTOS}")
    print(f"[*] Salvando arquivos em: {DIR_PENDENTES}")
    print("[*] Pressione Ctrl+C para parar.\n")

    while True:
        try:
            documentos = buscar_documentos()
            if documentos:
                print(f"[*] Documentos recebidos: {len(documentos)}")
                for documento in documentos:
                    processar_documento(documento)
            else:
                print("[*] Nenhum documento novo retornado.")
        except KeyboardInterrupt:
            print("\n[*] Monitoramento encerrado pelo usuario.")
            break
        except Exception as e:
            print(f"[-] Erro no loop principal: {e}")

        time.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    iniciar_monitoramento()
