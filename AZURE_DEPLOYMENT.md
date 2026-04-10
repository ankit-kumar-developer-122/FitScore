# Azure Deployment

This project is best deployed as two Azure services:

- Frontend: Azure Static Web Apps
- Backend: Azure App Service (Python/FastAPI)

## 1. Frontend on Azure Static Web Apps

The existing GitHub Actions workflow already deploys the static frontend from [`public`](C:/Users/ayush/FitScore/public).

Before deploying, update [`public/js/config.js`](C:/Users/ayush/FitScore/public/js/config.js):

```js
window.FITSCORE_CONFIG = Object.assign(
    {
        apiBaseUrl: "https://YOUR-BACKEND-NAME.azurewebsites.net"
    },
    window.FITSCORE_CONFIG || {}
);
```

If the frontend and backend are served from the same origin locally, you can leave `apiBaseUrl` blank.

## 2. Backend on Azure App Service

Create a Linux Python App Service and deploy the repo root, not just the `public` folder.

Required files:

- [`main.py`](C:/Users/ayush/FitScore/main.py)
- [`requirements.txt`](C:/Users/ayush/FitScore/requirements.txt)
- [`startup.sh`](C:/Users/ayush/FitScore/startup.sh)

Set the App Service startup command to:

```bash
bash startup.sh
```

## 3. Backend environment variables

In Azure App Service, set:

```text
ALLOWED_ORIGINS=https://YOUR-STATIC-WEB-APP.azurestaticapps.net
```

For multiple allowed origins, use a comma-separated list.

## 4. Health check

After deployment, confirm the backend is live:

```text
https://YOUR-BACKEND-NAME.azurewebsites.net/api/health
```

Expected response:

```json
{"status":"ok"}
```

## 5. Notes

- The current SQLite database and local `uploads/` folder are fine for local testing.
- For production Azure hosting, move resume files to Blob Storage and move data to PostgreSQL or Azure SQL.
- Azure Static Web Apps `api_location` is for Azure Functions, not FastAPI, so keep it empty when using App Service for the backend.
