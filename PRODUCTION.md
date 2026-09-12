# İstehsal rejimi

Lokal təqdimat üçün heç nə dəyişmir: `WORKER_MODE=embedded` və SQLite işləyir.

İstehsalda `.env` faylında güclü `POSTGRES_PASSWORD` təyin edin, sonra:

```powershell
docker compose -f docker-compose.production.yml up -d --build
docker compose -f docker-compose.production.yml ps
Invoke-WebRequest http://127.0.0.1:8800/health
```

Servislər:

- `web`: yalnız FastAPI və WebSocket;
- `worker`: agent, gecə növbəsi və outbound işlərini görür;
- `beat`: periodik tick-ləri Redis növbəsinə qoyur;
- `postgres`: əsas daimi məlumat bazası;
- `redis`: Celery broker/backend və paylanmış tick kilidi.

Backup nümunəsi:

```powershell
docker compose -f docker-compose.production.yml exec postgres pg_dump -U agency -d agency -Fc -f /tmp/agency.dump
docker compose -f docker-compose.production.yml cp postgres:/tmp/agency.dump ./backups/agency.dump
```

İlk real deploy-dan əvvəl SQLite məlumatı ayrıca ixrac/migrate edilməlidir; compose boş PostgreSQL
bazası yaradır və mövcud `agency.db` faylını avtomatik köçürmür.

## Lokal SQLite backup və bərpa sınağı

```powershell
.venv\Scripts\python.exe scripts\backup_sqlite.py
```

Skript SQLite online-backup API-sindən istifadə edir və yaranan nüsxədə `integrity_check` aparır.
`backups/` Git-ə daxil edilmir. Bərpa zamanı əvvəl serveri dayandırın, cari `agency.db` faylını
ayrıca saxlayın və yoxlanmış backup nüsxəsini `agency.db` adı ilə yerləşdirin.

Production üçün əlavə məcburi dəyişənlər: `APP_ENV=production`, `WORKER_MODE=celery`, HTTPS
`PUBLIC_BASE_URL` və ən az 32 simvolluq `AGENCY_API_KEY`. Bunlardan biri səhvdirsə tətbiq
qəsdən başlamır.
