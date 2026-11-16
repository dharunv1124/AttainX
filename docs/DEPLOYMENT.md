# Deployment Guide

This guide deploys the OBE Exam Analysis System with a React frontend, FastAPI backend, PostgreSQL database, and Alembic migrations. It does not assume a particular server operating system.

## 1. Prerequisites

Install on the college server or approved hosting environment:

- Python 3.11 or newer
- Node.js 20 or newer and npm
- PostgreSQL 14 or newer
- Git or another approved source delivery method

Install backend packages from the repository root:

```bash
python -m pip install -r backend/requirements.txt
```

Install frontend packages:

```bash
npm install
```

## 2. PostgreSQL Setup

Create a PostgreSQL database and an application role using the college database administration process. Grant the role access only to the application database and its schema.

The application must use a PostgreSQL connection string. SQLite is for isolated tests only and is not a production database.

Example shape, with real values supplied only through the server environment:

```text
postgresql://DB_USER:DB_PASSWORD@DB_HOST:5432/DB_NAME
```

## 3. Environment Variables

Copy `.env.example` to the server's environment configuration. Do not commit the populated file.

Backend variables:

- `ENVIRONMENT=production`
- `DATABASE_URL=postgresql://DB_USER:DB_PASSWORD@DB_HOST:5432/DB_NAME`
- `JWT_SECRET_KEY=<long random secret>`
- `JWT_ALGORITHM=HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES=1440`
- `CORS_ORIGINS=https://FRONTEND_HOST`

Frontend build variable:

- `VITE_API_BASE_URL=https://API_HOST`

For multiple approved frontend origins, separate `CORS_ORIGINS` values with commas. Do not use `*` when authenticated requests are enabled.

The backend reads environment variables directly. The frontend reads `VITE_API_BASE_URL` at build time. When the frontend and backend share one origin, `VITE_API_BASE_URL` may be empty and the frontend can use same-origin `/api` requests.

## 4. Database Migrations

From the `backend/` directory, with the backend environment variables loaded:

```bash
alembic -c alembic.ini upgrade head
```

The Alembic environment reads `DATABASE_URL` from the runtime environment. Run migrations before starting a new backend release. Do not use `Base.metadata.create_all()` in production.

## 5. Backend Startup

From the repository root:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --app-dir backend
```

Use the college server's approved process supervisor to keep this process running and restart it after deployment updates. Do not run development seed commands in production.

## 6. Frontend Production Build

Set `VITE_API_BASE_URL` before building, then run:

```bash
npm run build
```

The generated `dist/` directory contains the static frontend files.

## 7. Serving the Frontend

Serve `dist/` using the college's approved static web server or reverse proxy. Configure it to:

- serve `dist/index.html` for the application entry point;
- serve static assets from `dist/assets`;
- use the deployed backend origin in `VITE_API_BASE_URL` at build time;
- use HTTPS when the server is accessible over a network.

The Vite development proxy is only for local development and is not part of the production deployment.

## 8. Restarting After Updates

1. Deliver the reviewed source revision.
2. Load the production environment variables.
3. Install changed backend packages if required.
4. Run `alembic -c backend/alembic.ini upgrade head`.
5. Build the frontend with `npm run build`.
6. Restart the backend process through the approved process supervisor.
7. Replace the served frontend `dist/` contents.
8. Check `/api/health` and perform an authenticated login smoke test.

## 9. Health and Smoke Checks

Check the backend health endpoint:

```bash
curl -i https://API_HOST/api/health
```

Then verify an authenticated login using an approved account. Do not place passwords or tokens in shell history, deployment files, or source control.

## 10. Troubleshooting

### Database connection failure

- Confirm PostgreSQL is running and reachable from the backend host.
- Confirm `DATABASE_URL` has the correct host, port, database, username, and password.
- Confirm the PostgreSQL role has access to the database.
- Confirm the required migrations have run.

### Frontend cannot reach the API

- Confirm `VITE_API_BASE_URL` was set before `npm run build`.
- Confirm the deployed API URL is reachable over HTTPS.
- Confirm the API allows the deployed frontend origin in `CORS_ORIGINS`.
- Do not rely on the local Vite proxy in production.

### Authentication failures

- Confirm the same non-placeholder `JWT_SECRET_KEY` is used by the running backend process.
- Confirm the account exists in PostgreSQL and its password was created through the approved user-management process.
- Check that the client's system time is accurate because JWT expiration is time-based.

## Production Safety Notes

- `.env` files, SQLite files, and database artifacts are ignored by Git.
- Production startup does not run demo seed data or create database tables.
- PostgreSQL and Alembic are the production database and schema mechanisms.
