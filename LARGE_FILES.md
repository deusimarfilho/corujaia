# Arquivos Grandes

Para arquivos grandes, o melhor fluxo e quebrar a planilha em partes menores antes do upload no AnythingLLM.

## Como usar

Para um `.xlsx` ou `.xls`:

```bash
python "E:\xampp\htdocs\corujaia\tools\prepare_large_tabular.py" "CAMINHO_DO_ARQUIVO.xlsx"
```

Para controlar o tamanho de cada parte:

```bash
python "E:\xampp\htdocs\corujaia\tools\prepare_large_tabular.py" "CAMINHO_DO_ARQUIVO.xlsx" --rows-per-file 2000 --output-dir "E:\xampp\htdocs\corujaia\prepared_uploads"
```

## O que o script faz

- preserva todas as linhas
- repete o cabecalho em cada parte
- gera `.csv` menores, melhores para RAG
- cria um `manifest.json` com o resumo da divisao

## Fluxo recomendado

1. Rodar o script no `.xls`, `.xlsx` ou `.csv` grande
2. Subir os `.csv` gerados para o workspace no AnythingLLM
3. Fazer perguntas especificas no chat

## Observacao

Para `.xls` antigo, isso e ainda mais importante: o AnythingLLM tende a tratar esse formato como texto bruto, gerando milhares de trechos e deixando o upload muito lento. Dividir antes do upload e a forma mais confiavel de fazer o sistema "ler tudo" ao longo das consultas.
