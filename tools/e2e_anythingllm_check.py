import os
import sys
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tls.cron_arquivos as ca


def main():
    pend = ca.DIR_PENDENTES
    slug = ca.WORKSPACE_SLUG

    pdfs = [f for f in os.listdir(pend) if f.lower().endswith(".pdf")]
    if not pdfs:
        raise SystemExit("No PDF found in pendentes")

    pdf_name = sorted(pdfs)[0]
    pdf_path = os.path.join(pend, pdf_name)
    print("PDF:", pdf_name)

    if ca.pypdf is None:
        raise SystemExit("pypdf not installed. Run: pip install pypdf")

    json_path = ca.criar_json_entidades_para_pdf(pdf_path, pdf_name)
    json_name = os.path.basename(json_path)
    print("JSON:", json_name)

    loc_pdf = ca.processar_arquivo_anythingllm(pdf_path, pdf_name)
    loc_json = ca.processar_arquivo_anythingllm(json_path, json_name)
    print("loc_pdf:", loc_pdf)
    print("loc_json:", loc_json)

    ent_id, rel_id, tipo, data_prod = ca.extrair_metadados_nome(pdf_name)
    conn = ca.inicializar_banco()
    try:
        if loc_pdf:
            ca.registrar_arquivo(conn, pdf_name, ent_id, rel_id, tipo, data_prod, loc_pdf)
        if loc_json:
            ca.registrar_arquivo(conn, json_name, ent_id, rel_id, tipo, data_prod, loc_json)
    finally:
        conn.close()

    headers = {"Authorization": "Bearer " + ca.API_KEY, "Content-Type": "application/json"}
    question = (
        "Liste as entidades (pessoa, cpf, telefone, local, crime) encontradas no arquivo "
        + pdf_name
        + ". Responda somente com base nos arquivos do workspace."
    )

    url = ca.API_BASE_URL + "/workspace/" + slug + "/chat"
    payload = {"message": question, "mode": "query"}

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=120)
        print("chat_status:", r.status_code)
        body = r.text or ""
        print("chat_body_prefix:", body[:1200])
    except Exception as e:
        print("chat_call_failed:", e)

    print("DONE")


if __name__ == "__main__":
    main()

