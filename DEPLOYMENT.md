# Deployment Guide

How to get the calculator from your laptop to a live, public URL anyone can visit. Free, no credit card required.

## Step 1: Create the GitHub repository

1. Go to [github.com/new](https://github.com/new)
2. **Repository name:** `solar-calculator`
3. **Description:** "Solar PV calculator for Irish domestic roofs — Streamlit app with PVGIS integration"
4. **Public** (this is required for free Streamlit Cloud deployment)
5. **Do NOT** tick "Add a README" or "Add a license" — you already have those locally
6. Click **Create repository**

GitHub will show you a page with quick setup instructions. Keep that tab open.

## Step 2: Push the project to GitHub

From your project folder in the terminal:

```bash
cd solar_calculator_project   # or wherever you put it

# First time only — initialise git and connect to GitHub
git init
git add .
git commit -m "Initial commit: solar calculator with multi-face support and PVGIS integration"
git branch -M main
git remote add origin https://github.com/Ciaran-Carroll/solar-calculator.git
git push -u origin main
```

Refresh your GitHub repository page — you should see all the files.

## Step 3: Sign up for Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **Sign up** and use **Continue with GitHub**
3. Authorise Streamlit to access your GitHub repositories

That's it for sign-up.

## Step 4: Deploy the app

1. From the Streamlit Cloud dashboard, click **New app**
2. Fill in:
   - **Repository:** `Ciaran-Carroll/solar-calculator`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL:** something memorable like `solar-calculator-ie` (this becomes `solar-calculator-ie.streamlit.app`)
3. Click **Deploy**

Streamlit will pull the repo, install dependencies from `requirements.txt`, and start the app. First deployment takes 1–3 minutes.

When it finishes, you'll have a live URL. Test it works.

## Step 5: Update the README badge

Once deployed, edit your `README.md` to point to the real URL:

```markdown
[![Live Demo](https://img.shields.io/badge/Streamlit-Live%20Demo-FF4B4B?logo=streamlit&logoColor=white)](https://your-actual-url.streamlit.app)
```

Replace `https://your-deployment-url-here.streamlit.app` with your actual URL.

Commit and push:

```bash
git add README.md
git commit -m "Update README with live demo URL"
git push
```

The Streamlit Cloud app will auto-redeploy when you push to `main` — no manual redeploy needed.

## Step 6: Add the project to your portfolio

Update [ciaran-carroll.github.io](https://ciaran-carroll.github.io) with the project. Suggested entry:

> **Solar Panel Calculator** — Python, Streamlit
>
> A web-based estimating tool for Irish domestic solar PV projects. Multi-face roof support, PVGIS satellite-derived yield data, SEAI grant calculation, and battery economics. Built and deployed end-to-end with 52 passing unit tests covering trigonometric edge cases, financial tier logic, and mocked HTTP integration.
>
> [Live demo](https://your-actual-url.streamlit.app) · [Source code](https://github.com/Ciaran-Carroll/solar-calculator)

## Maintaining the deployment

A few things to know going forward:

- **Auto-redeploy on push.** Any commit to `main` triggers a redeploy. Useful for fixing bugs and adding features.
- **Streamlit Cloud free tier limits.** 1 GB RAM per app, public repos only, can be put to sleep after 7 days of inactivity (wakes on first visit). Plenty for this project.
- **Custom domain.** Possible but requires paid plan. The default `*.streamlit.app` URL is fine for portfolio use.
- **Logs and debugging.** Click your app in the Streamlit Cloud dashboard, then "Manage app" → "Logs" to see runtime output. Useful when the deployed app behaves differently from local.

## Troubleshooting

**App fails to start with "ModuleNotFoundError"**
The most likely cause is a path issue — Streamlit Cloud runs `app.py` from the project root. Make sure `app.py` does `sys.path.insert(0, str(Path(__file__).parent / "src"))` before importing from `solar_calculator`. The version in this project does.

**App times out on PVGIS calls**
PVGIS is occasionally slow (1–5 seconds is normal; 10+ seconds means an outage). The default 10-second timeout in `pvgis.py` should be enough. If outages are long, the calculator falls back to the offline model automatically.

**Changes pushed but not visible on live app**
Streamlit Cloud needs ~30–90 seconds to redeploy. Check the "Manage app" panel for current status. Hard-refresh your browser (Ctrl+Shift+R / Cmd+Shift+R) to bypass cached versions.

**Want to test the deployment locally before pushing**
```bash
streamlit run app.py
```
Streamlit Cloud's environment is essentially the same as your local setup, so if it works locally it'll almost certainly work deployed.

## What you've just done

Built and deployed a multi-module Python project with:

- A web UI accessible to anyone with a URL
- Real API integration with graceful fallback
- 52 unit tests including mocked HTTP calls
- Proper documentation, license, and project structure
- Continuous deployment via Git push

That's a genuine portfolio piece. Mention it on your CV and in interviews — it demonstrates not just the engineering knowledge but the discipline to take a project from concept to live deployment.
