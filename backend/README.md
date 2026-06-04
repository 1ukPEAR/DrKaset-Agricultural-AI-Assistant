# DrKaset โ€” Backend

RAG-based agricultural assistant API for Thai farmers.
Stack: FastAPI ยท Ollama (Python lib) ยท FAISS ยท MySQL ยท JWT

---

## เนเธเธฃเธเธชเธฃเนเธฒเธเนเธเธฅเนเธ—เธตเนเธชเธฃเนเธฒเธ

```
backend/
  main.py
  config.py
  database.py
  dependencies.py
  requirements.txt

  api/
    auth.py
    chat.py
    ingest.py
    health.py

  auth/
    security.py

  db/
    models.py

  schemas/
    auth.py
    chat.py
    ingest.py
    health.py

  rag/
    service.py
    retriever.py
    embedder.py
    constants.py

  data/
    faiss_index/
```

---

## เธงเธดเธเธตเธ•เธดเธ”เธ•เธฑเนเธเนเธฅเธฐเธฃเธฑเธ

### 1. เธ•เธดเธ”เธ•เธฑเนเธ Ollama เนเธฅเธฐ pull model

```
backend/
  main.py
  config.py
  database.py
  dependencies.py
  requirements.txt

  api/
    auth.py
    chat.py
    ingest.py
    health.py

  auth/
    security.py

  db/
    models.py

  schemas/
    auth.py
    chat.py
    ingest.py
    health.py

  rag/
    service.py
    retriever.py
    embedder.py
    constants.py

  data/
    faiss_index/
```

### 2. เธ•เธฑเนเธเธเนเธฒ MySQL

เธฃเธฑเธ MAMP / XAMPP / brew services เธซเธฃเธทเธญ mysql.server start เนเธฅเนเธง:

```
backend/
  main.py
  config.py
  database.py
  dependencies.py
  requirements.txt

  api/
    auth.py
    chat.py
    ingest.py
    health.py

  auth/
    security.py

  db/
    models.py

  schemas/
    auth.py
    chat.py
    ingest.py
    health.py

  rag/
    service.py
    retriever.py
    embedder.py
    constants.py

  data/
    faiss_index/
```

script เธเธตเนเธเธฐ:
- เธชเธฃเนเธฒเธ database `drkaset_db`
- เธชเธฃเนเธฒเธ user `drkaset_user` / password `drkaset_pass`
- เธชเธฃเนเธฒเธ tables เธ—เธฑเนเธเธซเธกเธ” (users, chat_sessions, chat_messages, ingestion_logs)

> **เธซเธกเธฒเธขเน€เธซเธ•เธธ:** เธ–เนเธฒเนเธเน MAMP password เธเธญเธ root เธญเธฒเธเน€เธเนเธ `root`
> เนเธเนเนเธ `.env` เนเธซเนเธ•เธฃเธเธเธฑเธ MySQL เธ—เธตเนเนเธเน

### 3. เธชเธฃเนเธฒเธ virtual environment เนเธฅเธฐเธ•เธดเธ”เธ•เธฑเนเธ dependencies

```
backend/
  main.py
  config.py
  database.py
  dependencies.py
  requirements.txt

  api/
    auth.py
    chat.py
    ingest.py
    health.py

  auth/
    security.py

  db/
    models.py

  schemas/
    auth.py
    chat.py
    ingest.py
    health.py

  rag/
    service.py
    retriever.py
    embedder.py
    constants.py

  data/
    faiss_index/
```

### 4. เธ•เธฑเนเธเธเนเธฒ .env

เนเธเนเนเธเนเธเธฅเน `.env` เธ—เธตเน root เธเธญเธ project:

```
backend/
  main.py
  config.py
  database.py
  dependencies.py
  requirements.txt

  api/
    auth.py
    chat.py
    ingest.py
    health.py

  auth/
    security.py

  db/
    models.py

  schemas/
    auth.py
    chat.py
    ingest.py
    health.py

  rag/
    service.py
    retriever.py
    embedder.py
    constants.py

  data/
    faiss_index/
```

### 5. เธงเธฒเธ FAISS index

เธซเธฅเธฑเธเธเธฒเธเธฃเธฑเธ data_preparation pipeline เน€เธชเธฃเนเธเนเธฅเนเธง:

```
backend/
  main.py
  config.py
  database.py
  dependencies.py
  requirements.txt

  api/
    auth.py
    chat.py
    ingest.py
    health.py

  auth/
    security.py

  db/
    models.py

  schemas/
    auth.py
    chat.py
    ingest.py
    health.py

  rag/
    service.py
    retriever.py
    embedder.py
    constants.py

  data/
    faiss_index/
```

เนเธเธฅเนเธ—เธตเนเธ•เนเธญเธเธกเธตเนเธ `backend/data/faiss_index/`:
- `index.faiss`
- `index.pkl`

### 6. เธฃเธฑเธ Backend

```
backend/
  main.py
  config.py
  database.py
  dependencies.py
  requirements.txt

  api/
    auth.py
    chat.py
    ingest.py
    health.py

  auth/
    security.py

  db/
    models.py

  schemas/
    auth.py
    chat.py
    ingest.py
    health.py

  rag/
    service.py
    retriever.py
    embedder.py
    constants.py

  data/
    faiss_index/
```

เธ•เธฃเธงเธเธชเธญเธเธงเนเธฒ API เธ—เธณเธเธฒเธเนเธ”เน:
```
backend/
  main.py
  config.py
  database.py
  dependencies.py
  requirements.txt

  api/
    auth.py
    chat.py
    ingest.py
    health.py

  auth/
    security.py

  db/
    models.py

  schemas/
    auth.py
    chat.py
    ingest.py
    health.py

  rag/
    service.py
    retriever.py
    embedder.py
    constants.py

  data/
    faiss_index/
```

---

## API Endpoints

| Method | Path | เธเธณเธญเธเธดเธเธฒเธข |
|--------|------|----------|
| POST | /auth/register | เธชเธกเธฑเธเธฃเธชเธกเธฒเธเธดเธ |
| POST | /auth/login | เน€เธเนเธฒเธชเธนเนเธฃเธฐเธเธ โ’ เธฃเธฑเธ JWT |
| POST | /auth/refresh | เธ•เนเธญเธญเธฒเธขเธธ token |
| POST | /chat | เธชเนเธเธเนเธญเธเธงเธฒเธก โ’ SSE stream เธ•เธญเธเธเธฅเธฑเธ |
| GET | /chat/sessions | เธ”เธนเธเธฃเธฐเธงเธฑเธ•เธด sessions |
| GET | /chat/sessions/{id}/messages | เธ”เธนเธเนเธญเธเธงเธฒเธกเนเธ session |
| POST | /ingest/upload | เธญเธฑเธเนเธซเธฅเธ”เนเธเธฅเนเธเนเธญเธกเธนเธฅเนเธเธขเธฑเธ data/raw |
| GET | /ingest/logs | เธ”เธน log เธเธฒเธฃเธญเธฑเธเนเธซเธฅเธ” |
| GET | /health | เธ•เธฃเธงเธเธชเธญเธเธชเธ–เธฒเธเธฐ DB + Ollama + FAISS |

### เธ•เธฑเธงเธญเธขเนเธฒเธเธเธฒเธฃเน€เธฃเธตเธขเธ Chat API (SSE)

```
backend/
  main.py
  config.py
  database.py
  dependencies.py
  requirements.txt

  api/
    auth.py
    chat.py
    ingest.py
    health.py

  auth/
    security.py

  db/
    models.py

  schemas/
    auth.py
    chat.py
    ingest.py
    health.py

  rag/
    service.py
    retriever.py
    embedder.py
    constants.py

  data/
    faiss_index/
```

---

## เธเธฒเธฃเน€เธเธดเนเธก FAISS Index เนเธซเธกเน (เธซเธฅเธฑเธ data_preparation)

เน€เธกเธทเนเธญเนเธ”เนเธเธธเธ”เธเนเธญเธกเธนเธฅเนเธซเธกเนเนเธฅเธฐเธฃเธฑเธ pipeline เนเธฅเนเธง เนเธเน copy เธ—เธฑเธ:

```
backend/
  main.py
  config.py
  database.py
  dependencies.py
  requirements.txt

  api/
    auth.py
    chat.py
    ingest.py
    health.py

  auth/
    security.py

  db/
    models.py

  schemas/
    auth.py
    chat.py
    ingest.py
    health.py

  rag/
    service.py
    retriever.py
    embedder.py
    constants.py

  data/
    faiss_index/
```

เธเธฒเธเธเธฑเนเธ restart backend เน€เธเธทเนเธญเนเธซเธฅเธ” index เนเธซเธกเน:
```
backend/
  main.py
  config.py
  database.py
  dependencies.py
  requirements.txt

  api/
    auth.py
    chat.py
    ingest.py
    health.py

  auth/
    security.py

  db/
    models.py

  schemas/
    auth.py
    chat.py
    ingest.py
    health.py

  rag/
    service.py
    retriever.py
    embedder.py
    constants.py

  data/
    faiss_index/
```

---

## เธซเธกเธฒเธขเน€เธซเธ•เธธเธชเธณเธเธฑเธ

- **Ollama เนเธเน Python lib** (`import ollama`) เนเธกเนเนเธเน HTTP request เธ•เธฃเธ
- **เนเธกเนเธกเธต Celery / Redis / Docker** โ€” เธ—เธธเธเธญเธขเนเธฒเธเธฃเธฑเธเนเธ process เน€เธ”เธตเธขเธง
- **เนเธกเนเธกเธตเธเธฒเธฃ fetch เธฃเธฒเธเธฒ/เธญเธฒเธเธฒเธจเธเธฒเธ API เธ เธฒเธขเธเธญเธ** โ€” เธเนเธญเธกเธนเธฅเธ—เธฑเนเธเธซเธกเธ”เธกเธฒเธเธฒเธ FAISS เธ—เธตเนเธชเธฃเนเธฒเธเธเธฒเธ dataset เธเธญเธเธเธธเธ“
- **Tables เธชเธฃเนเธฒเธเธญเธฑเธ•เนเธเธกเธฑเธ•เธด** เธ•เธญเธ startup เธเนเธฒเธ `Base.metadata.create_all()` เนเธ•เนเนเธเธฐเธเธณเนเธซเนเธฃเธฑเธ `db/init.sql` เธเนเธญเธเน€เธเธทเนเธญเธชเธฃเนเธฒเธ user เนเธฅเธฐ database

