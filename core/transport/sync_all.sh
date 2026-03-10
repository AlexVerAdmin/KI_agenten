#!/bin/bash
# sync_all.sh: Единый скрипт для запуска синхронизации через Cron

# 1. Запуск экспорта на VDS
echo "[$(date)] Phase 1: Exporting from VDS..."
ssh -p 31117 -i ~/.ssh/vds alexadmin@10.8.0.1 "python3 ~/stack/Agents/core/transport/export_vds_batch.py"

# 2. PULL и очистка VDS
echo "[$(date)] Phase 2: Pulling batches and cleaning VDS..."
python3 core/transport/pull_snapshot_from_vds.py

# 3. Обработка локально (маршрутизация и Ollama)
echo "[$(date)] Phase 3: Processing batches (Ollama)..."
python3 core/transport/process_incoming_batch.py

# 4. PUSH результатов на VDS
echo "[$(date)] Phase 4: Pushing summaries back to VDS..."
python3 core/transport/push_summary_to_vds.py

echo "[$(date)] Sync Completed Successfully."
