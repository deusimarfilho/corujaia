CREATE OR REPLACE FUNCTION set_workspace_default_prompt()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  stock_prompt text := 'Given the following conversation, relevant context, and a follow up question, reply with an answer to the current question the user is asking. Return only your response to the question given the above information following the users instructions as needed.';
  default_prompt text := 'Responda priorizando os arquivos indexados deste workspace. Use como fonte principal apenas o contexto recuperado dos documentos indexados. Se a resposta nao estiver claramente sustentada pelos arquivos indexados, diga explicitamente que nao encontrou evidencia suficiente nos documentos deste workspace. Nao invente fatos, nao complete lacunas com conhecimento externo e nao misture suposicoes com informacoes documentais. Quando possivel, responda de forma objetiva e fiel ao conteudo encontrado.';
  default_model text := 'qwen2.5-7b-instruct-20250329';
BEGIN
  IF NEW."openAiPrompt" IS NULL OR btrim(NEW."openAiPrompt") = '' OR NEW."openAiPrompt" = stock_prompt THEN
    NEW."openAiPrompt" := default_prompt;
  END IF;

  IF NEW."chatMode" IS NULL OR btrim(NEW."chatMode") = '' OR NEW."chatMode" IN ('chat', 'automatic') THEN
    NEW."chatMode" := 'query';
  END IF;

  IF NEW."chatProvider" IS NULL OR btrim(NEW."chatProvider") = '' THEN
    NEW."chatProvider" := 'lmstudio';
  END IF;

  IF NEW."chatModel" IS NULL OR btrim(NEW."chatModel") = '' THEN
    NEW."chatModel" := default_model;
  END IF;

  IF NEW."agentProvider" IS NULL OR btrim(NEW."agentProvider") = '' THEN
    NEW."agentProvider" := 'lmstudio';
  END IF;

  IF NEW."agentModel" IS NULL OR btrim(NEW."agentModel") = '' THEN
    NEW."agentModel" := default_model;
  END IF;

  IF NEW."topN" IS NULL OR NEW."topN" <> 6 THEN
    NEW."topN" := 6;
  END IF;

  IF NEW."similarityThreshold" IS NULL OR NEW."similarityThreshold" >= 0.25 THEN
    NEW."similarityThreshold" := 0.15;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_workspace_default_prompt ON workspaces;

CREATE TRIGGER trg_workspace_default_prompt
BEFORE INSERT ON workspaces
FOR EACH ROW
EXECUTE FUNCTION set_workspace_default_prompt();

UPDATE workspaces
SET "openAiPrompt" = 'Responda priorizando os arquivos indexados deste workspace. Use como fonte principal apenas o contexto recuperado dos documentos indexados. Se a resposta nao estiver claramente sustentada pelos arquivos indexados, diga explicitamente que nao encontrou evidencia suficiente nos documentos deste workspace. Nao invente fatos, nao complete lacunas com conhecimento externo e nao misture suposicoes com informacoes documentais. Quando possivel, responda de forma objetiva e fiel ao conteudo encontrado.'
WHERE "openAiPrompt" IS NULL
   OR btrim("openAiPrompt") = ''
   OR "openAiPrompt" = 'Given the following conversation, relevant context, and a follow up question, reply with an answer to the current question the user is asking. Return only your response to the question given the above information following the users instructions as needed.';

UPDATE workspaces
SET "chatMode" = 'query'
WHERE "chatMode" IS NULL
   OR btrim("chatMode") = ''
   OR "chatMode" IN ('chat', 'automatic');

UPDATE workspaces
SET "chatProvider" = 'lmstudio'
WHERE "chatProvider" IS NULL
   OR btrim("chatProvider") = '';

UPDATE workspaces
SET "chatModel" = 'qwen2.5-7b-instruct-20250329'
WHERE "chatModel" IS NULL
   OR btrim("chatModel") = '';

UPDATE workspaces
SET "agentProvider" = 'lmstudio'
WHERE "agentProvider" IS NULL
   OR btrim("agentProvider") = '';

UPDATE workspaces
SET "agentModel" = 'qwen2.5-7b-instruct-20250329'
WHERE "agentModel" IS NULL
   OR btrim("agentModel") = '';

UPDATE workspaces
SET "topN" = 6
WHERE "topN" IS DISTINCT FROM 6;

UPDATE workspaces
SET "similarityThreshold" = 0.15
WHERE "similarityThreshold" IS NULL
   OR "similarityThreshold" >= 0.25;
