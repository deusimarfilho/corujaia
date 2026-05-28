BEGIN;

-- SBDI sync
TRUNCATE TABLE sincronismo;

-- Workspace index (mantém workspaces, usuários e API keys)
TRUNCATE TABLE
  workspace_agent_invocations,
  workspace_chats,
  workspace_documents,
  workspace_parsed_files,
  workspace_suggested_messages,
  workspace_threads,
  workspace_users,
  document_vectors,
  embed_chats,
  embed_configs,
  prompt_history,
  cache_data,
  document_sync_executions,
  document_sync_queues,
  event_logs
CASCADE;

DROP TABLE IF EXISTS anythingllm_vectors;

COMMIT;
