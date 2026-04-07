# FitScore
FitScore is an AI- Powered recruitment intelligence platform that quantifies how well a candidate fits a job using data-driven scoring , resume analysis, and analytics.


Live Link: https://salmon-forest-0355c5300.2.azurestaticapps.net/
1. Product Vision
FitScore is an AI-powered recruitment intelligence platform that quantifies how well a candidate
fits a job using data-driven scoring, resume analysis, and analytics dashboards.

2. Core Value Proposition
Measure candidate-job fit with a single intelligent score. Helps candidates optimize resumes and
recruiters hire faster.

3. Problem Statement
Candidates receive no ATS feedback and recruiters spend excessive time screening irrelevant
applicants. No unified scoring exists.

4. User Personas
Candidate (Arjun): Final-year student aiming for job. Recruiter (Priya): Talent lead aiming to hire
quickly.

5. Candidate Module
Resume Upload & Parsing, FitScore Engine, Resume Enhancer, Tailored Resume Generator,
Profile Aggregator.

6. Recruiter Module
Job Posting, Candidate Ranking System, Recruiter Analytics Dashboard.

7. Core Algorithms
Resume parsing via spaCy, FitScore weighted scoring, TF-IDF + Cosine Similarity for matching.

8. System Architecture
Frontend: React/Streamlit | Backend: FastAPI | Database: PostgreSQL | ML: scikit-learn | NLP:
spaCy

9. Data Analytics Layer
Candidate insights (score trends, skill gaps) and recruiter dashboards (funnel, skill distribution).

10. Build Plan
Phase 1: MVP | Phase 2: Core Features | Phase 3: Advanced | Phase 4: Polish & Deploy.

11. Success Metrics
FitScore accuracy ±5, parsing >95%, precision@10 >80%, load time <2s

12. Elevator Pitch
FitScore quantifies candidate-job fit using AI-driven resume analysis, scoring, and analytics






FitScore Initial Implementation Walkthrough
What was built
FastAPI Core: A lightweight Python REST API (
main.py
) serving static assets and providing mocked JSON endpoints for jobs and telemetry.
AntiGravity UI System: A rich Vanilla CSS3 aesthetic featuring:
Deep dark background mapping (--bg-base).
Pulsing animated background gradients (the .bg-gradient-orb overlays).
Floating glass-panel layers providing layout structure with heavy blur effects.
Smooth hover states with glowing drop shadows.
Automation Hub: Successfully integrated 
Drawflow
 via CDN into the DOM without React compilation. Supports dropping components from the palette to the screen, complete with dark mode overrides for the nodes and glowing connection paths.
Dashboards: Mock Candidate dashboard setup using Chart.js for "Your Skills vs Market Demand" radar charts and custom SVG donut charts for the overall FitScore.
Manual Verification
Access the deployment at http://127.0.0.1:8000.
Verify the glowing SVG background and depth of the floating center app-container.
Use the sidebar to seamlessly switch between the Dashboard, Jobs (simulating an API call), and the Automation Hub.
In the Automation Hub, try dragging a "Job Scraper" node from the left palette into the center Canvas area.
TIP

Use this initial prototype as the visual baseline. You can easily modify colors in 
public/css/style.css
 since they are centralized in :root CSS variables.
