# Secure NodeJS + Express + MySQL Auth Service

## Folder structure

- `src/routes`
- `src/controllers`
- `src/middleware`
- `src/config`
- `src/utils`
- `src/validators`

## Security features implemented

- Role model: `admin`, `teacher`, `student`.
- `/register` only creates `student` and rejects `role` field.
- Only `admin` can call `/admin/create-teacher`.
- Password hashing with `bcrypt` (`saltRounds = 12`).
- JWT payload includes only `id`, `role`, expires in `1d`.
- JWT secret loaded from `.env`.
- Request validation via `express-validator`.
- Prepared statements via `mysql2/promise` (`pool.execute`).
- No raw SQL errors returned to client.
- Login rate limit: 5 attempts / 15 minutes.

## Run with Docker

```bash
cd node-auth-service
cp .env.example .env
docker compose up --build -d
```

## Seed default admin

```bash
cd node-auth-service
docker compose exec api npm run seed:admin
```

Default account:
- Email: `admin@gmail.com`
- Password: `123456`

## APIs

- `POST /register`
- `POST /login`
- `POST /admin/create-teacher` (Bearer token required, admin role)

## Example requests

```bash
curl -X POST http://localhost:3000/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Student A","email":"student@example.com","password":"123456"}'
```

```bash
curl -X POST http://localhost:3000/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@gmail.com","password":"123456"}'
```
