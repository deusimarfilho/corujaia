# Arquivos Grandes

Para arquivos grandes, o melhor fluxo e quebrar a planilha em partes menores antes do upload no AnythingLLM.

## Como usar

Para um `.xlsx`:

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

1. Rodar o script no `.xlsx` grande
2. Subir os `.csv` gerados para o workspace no AnythingLLM
3. Fazer perguntas especificas no chat

## Observacao

Mesmo com modelo grande, o chat nao consegue colocar uma planilha inteira enorme em uma unica resposta. Dividir o arquivo antes do upload e a forma mais confiavel de fazer o sistema "ler tudo" ao longo das consultas.
