# Execution Steps

## 1. Open the project folder

```powershell
cd C:/Users/KIIT0001/Desktop/new paper for nifty/CodexGuardian
```

## 2. Create a virtual environment

```powershell
python -m venv .venv
```

## 3. Activate the environment

```powershell
.venv\Scripts\Activate.ps1
```

## 4. Install dependencies

```powershell
pip install -r requirements.txt
```

## 5. Run the backend

```powershell
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## 6. Open the dashboard

Open the file:

```text
frontend/index.html
```

## 7. Run the test suite

```powershell
pytest -q
```

## 8. Example API calls

### Health check

```powershell
curl http://localhost:8000/health
```

### Review diff

```powershell
curl -X POST http://localhost:8000/api/v1/review/diff -H "Content-Type: application/json" -d "{\"repository_path\":\"C:/path/to/repo\"}"
```

### Build index

```powershell
curl -X POST http://localhost:8000/api/v1/indexing/build -H "Content-Type: application/json" -d "{\"repository_path\":\"C:/path/to/repo\"}"
```

### Retrieve context

```powershell
curl -X POST http://localhost:8000/api/v1/rag/retrieve -H "Content-Type: application/json" -d "{\"repository_path\":\"C:/path/to/repo\",\"query\":\"Python tests\"}"
```

### AI review

```powershell
curl -X POST http://localhost:8000/api/v1/review/ai -H "Content-Type: application/json" -d "{\"repository_path\":\"C:/path/to/repo\"}"
```
