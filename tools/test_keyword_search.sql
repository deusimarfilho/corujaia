SELECT COUNT(*) AS phrase_hits
FROM anythingllm_vectors
WHERE namespace = 'sbdi_coin'
  AND unaccent(metadata::text) ILIKE unaccent('%CICERO PEREIRA LIMA DE SOUSA%');
