# EmailIntelligence: A Research Software Implementation for Transformer-Enhanced Phishing Detection

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?style=for-the-badge&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Scikit-Learn](https://img.shields.io/badge/scikit--learn-1.6.1-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)
![Hugging Face](https://img.shields.io/badge/Hugging%20Face-Models-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

Developed as an undergraduate research project exploring transformer-based natural language processing and ensemble learning for phishing email detection.

`EmailIntelligence` is an open-source research implementation for real-time phishing email detection using contextual text embeddings and ensemble classification. The system integrates a Python Flask backend, Google OAuth 2.0 authentication, Gmail API data ingestion, PostgreSQL relational storage, and a soft-voting ensemble of 25 trained estimators on 768-dimensional transformer embeddings (`microsoft/deberta-v3-base`). Model artifacts are versioned on Hugging Face Hub and synchronized automatically during deployment via `huggingface_hub.snapshot_download()`, enabling lightweight repositories through decoupled model artifact storage.

---

## 🔬 Research Motivation

Phishing remains one of the primary vectors for credential theft, corporate espionage, and financial fraud. Although modern transformer language models achieve strong semantic representation of text, deploying them in operational cybersecurity systems requires balancing predictive performance, computational efficiency, and infrastructure reproducibility.

`EmailIntelligence` explores the application of contextual transformer embeddings combined with classical ensemble learning for accurate and deployable phishing email detection in operational environments.

---

## 🎯 Key Contributions

- **Transformer-Enhanced Feature Pipeline**: Development of an embedding pipeline using `microsoft/deberta-v3-base` 768-dimensional `[CLS]` token representations.
- **25-Estimator Soft-Voting Ensemble**: Design and training of a soft-voting ensemble comprising 25 estimators across 5 supervised learning algorithms using stratified 5-fold cross-validation.
- **Real-World Message Ingestion**: Integration of Google OAuth 2.0 and Gmail APIs for MIME email parsing, text cleaning, and user authentication.
- **Automated MLOps Synchronization**: Model artifact versioning and auto-sync using Hugging Face Hub (`huggingface_hub`) for decoupled model artifact storage.
- **Portable Deployment Architecture**: Deployment-ready Flask application supporting dual-database persistence (PostgreSQL for cloud production, SQLite for local research).

---

## 🏗️ System Architecture

```mermaid
graph TD
    User([User Browser]) -->|Google OAuth 2.0| Auth[Flask Auth Engine / app.py]
    Auth -->|Fetch Messages| GmailAPI[Google Gmail API]
    GmailAPI -->|Raw MIME / Text| Preprocessing[Email Preprocessing Pipeline]
    
    Preprocessing -->|Concatenated full_text| Transformer[DeBERTa-v3 Contextual Embedding]
    Transformer -->|768-dim CLS Vector| Scaler[StandardScaler Feature Normalization]
    
    HF[Hugging Face Hub: Ainaops/email-intelligence-models] -.->|Auto-Sync Weights| Models[25-Estimator Ensemble Classifier]
    
    Scaler --> Models
    Models -->|Soft Voting Probabilities| Evaluator[Phishing Classification Evaluator]
    
    Evaluator -->|Log Results| DB[(PostgreSQL Database)]
    Evaluator --> UI[Flask Web Dashboard]
```

---

## Dataset & Machine Learning Methodology

### 1. Dataset Characteristics & Compilation
The composite dataset comprises **105,051 email records** assembled by combining four open-source phishing email datasets sourced from Zenodo: **CEAS_8**, **Nigerian_5**, **SpamAssassin**, and **TREK_07**.

- **Total Samples**: 105,051 emails
- **Class Breakdown**: 
  - **Phishing (`1`)**: 56,291 emails (53.6%)
  - **Legitimate (`0`)**: 48,760 emails (46.4%)
- **Data Preprocessing & Cleaning**:
  - Removed 3,802 missing values across sender, recipient, date, subject, and body fields.
  - Eliminated 1,800 identical duplicate rows to prevent generalization bias and overfitting.
  - Concatenated `subject` and `body` fields into a unified `full_text` column (`full_text = subject + " " + body`) to provide complete semantic context for transformer embeddings.

### 2. Feature Extraction Using DeBERTa-v3
- **Transformer Encoder**: `microsoft/deberta-v3-base` initialized via Hugging Face Transformers.
- **Tokenization**: Sequences tokenized with maximum sequence length of 512 tokens with attention masks, padding, and truncation.
- **Vector Dimension**: 768-dimensional dense representations extracted from the final hidden state `[CLS]` token (first token).
- **Feature Scaling**: Feature values normalized using `StandardScaler` fitted on training splits.

### 3. Model Architecture & Ensemble Strategy
The classification engine evaluates five supervised machine learning algorithms: **Random Forest**, **XGBoost**, **Logistic Regression**, **Gradient Boosting**, and **Extra Trees Classifier**.

- **Cross-Validation**: Models were trained using **stratified 5-fold cross-validation** (5 fold estimators per algorithm family, totaling 25 trained estimators).
- **Probability Averaging**: For an incoming email embedding vector, each estimator outputs class probability distributions \( P_i(\text{phishing}) \). Final predictions are computed by averaging class probabilities across all estimators:
  \[
  P_{\text{final}} = \frac{1}{N} \sum_{i=1}^{N} P_i(\text{phishing})
  \]

---

## Experimental Results

Performance metrics are reported as the mean ± standard deviation across stratified 5-fold cross-validation unless otherwise stated:

| Model | Accuracy (Mean ± Std) | Precision (Mean ± Std) | Recall (Mean ± Std) | F1-Score (Mean ± Std) |
| :--- | :---: | :---: | :---: | :---: |
| **XGBoost** | 0.9869 ± 0.0008 | 0.9857 ± 0.0010 | 0.9904 ± 0.0008 | **0.9881 ± 0.0007** |
| **Logistic Regression** | 0.9875 ± 0.0008 | 0.9882 ± 0.0004 | 0.9889 ± 0.0013 | **0.9886 ± 0.0008** |
| **Random Forest** | 0.9761 ± 0.0009 | 0.9766 ± 0.0006 | 0.9797 ± 0.0019 | 0.9781 ± 0.0008 |
| **Extra Trees** | 0.9759 ± 0.0010 | 0.9778 ± 0.0008 | 0.9781 ± 0.0017 | 0.9779 ± 0.0010 |
| **Gradient Boosting** | 0.9659 ± 0.0016 | 0.9668 ± 0.0018 | 0.9708 ± 0.0025 | 0.9688 ± 0.0015 |
| **Soft Voting Ensemble** | **0.9984 (99.84%)** | **0.9980 (99.80%)** | **0.9990 (99.90%)** | **0.9985 (99.85%)** |

On the evaluation dataset, the probability-averaging ensemble achieved higher performance than each individual base estimator, reaching **99.84% accuracy**, **99.80% precision**, **99.90% recall**, and **99.85% F1-score**.

---

## 🔁 Inference & Benchmark Reproducibility

This repository supports reproducible model evaluation and inference execution:

- **Benchmark Metric Logging**: Raw 5-fold cross-validation metrics for each estimator family are recorded in [`model_metrics.csv`](file:///c:/Users/FLUX%20LOGISTIX/Desktop/EmailIntelligence/EmailIntelligence/model_metrics.csv).
- **Training Pipeline & Notebooks**: Dataset preprocessing, DeBERTa-v3 embedding extraction, and 5-fold ensemble cross-validation workflow are documented in [`notebooks/Final year Project.ipynb`](file:///c:/Users/FLUX%20LOGISTIX/Desktop/EmailIntelligence/EmailIntelligence/notebooks/Final%20year%20Project.ipynb).
- **Decoupled Model Weights**: Serialized model fold artifacts are hosted on Hugging Face Hub (`Ainaops/email-intelligence-models`) and auto-synchronized at boot via `huggingface_hub.snapshot_download()`.
- **Environment Consistency**: Dependencies are explicitly pinned in [`requirements.txt`](file:///c:/Users/FLUX%20LOGISTIX/Desktop/EmailIntelligence/EmailIntelligence/requirements.txt) with a fixed Python runtime ([`runtime.txt`](file:///c:/Users/FLUX%20LOGISTIX/Desktop/EmailIntelligence/EmailIntelligence/runtime.txt)).
- **Database Flexibility**: Local development defaults to SQLite (`sqlite:///email_intelligence.db`), while production deployments use PostgreSQL.

---

## ⚠️ Limitations

Current limitations of the framework include:

- **Dataset Scope**: Evaluation is presently limited to publicly available phishing datasets sourced from Zenodo benchmarks.
- **Provider Support**: The live ingestion client currently supports Gmail accounts via OAuth 2.0; broader IMAP/EWS support is planned.
- **Adversarial Evaluation**: Robustness against intentional adversarial perturbations (such as homograph attacks or zero-width character insertions) has not yet been systematically benchmarked.

---

## 🔮 Future Work

- [ ] **SHAP Feature Attribution**: Integration of TreeSHAP / KernelSHAP for exact game-theoretic feature contribution plots.
- [ ] **Model Card & Hugging Face Documentation**: Detailed model card outlining dataset distributions and evaluation limits on Hugging Face Hub.
- [ ] **Microsoft Outlook / Exchange Support**: Microsoft Entra ID (Azure AD) OAuth 2.0 integration for enterprise M365 feeds.
- [ ] **Containerization & Orchestration**: Production `Dockerfile` and Kubernetes Deployment manifests (`k8s/`).
- [ ] **Adversarial Robustness Benchmarking**: Evaluation under Unicode homograph and adversarial text perturbations.
- [ ] **Continuous Integration Pipeline**: GitHub Actions workflow for automated testing and model validation.

---

## Project Structure

```text
EmailIntelligence/
├── app.py                      # Flask application initialization & blueprint registration
├── main.py                     # Entry point for production execution
├── phishing_detector.py        # ML inference engine, embedding pipeline & ensemble voting
├── email_processor.py          # Gmail API integration, message fetching & text parsing
├── google_auth.py              # Google OAuth 2.0 authentication service & token handling
├── db_init.py                  # SQLAlchemy database initialization
├── models.py                   # ORM models (User, Email, UserProgress, PhishingClassification)
├── csv_exporter.py             # Export route for processed classification data
├── user_progress.py            # User stats & session progress tracking
├── model_metrics.csv           # Benchmark results from 5-fold cross-validation
├── scaler.pkl                  # Serialized StandardScaler instance
├── requirements.txt            # Python dependencies
├── runtime.txt                 # Python runtime version pin (3.12.10)
├── README.md                   # Technical documentation
├── models/                     # Directory for 25 fold .pkl model artifacts (git-ignored)
├── notebooks/                  # Training notebooks and DeBERTa tokenizer/model references
├── static/                     # CSS stylesheets, UI assets, icons
└── templates/                  # Jinja2 HTML templates (dashboard, login, index)
```

---

## Environment Variables

| Variable | Description |
| :--- | :--- |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth 2.0 Client ID for OpenID Connect |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth 2.0 Client Secret |
| `GOOGLE_REDIRECT_URI` | Authorized OAuth 2.0 callback URL |
| `SESSION_SECRET` | Secret key for Flask session cookie signing |
| `HF_TOKEN` | Optional Hugging Face Read Access Token (required only if model repo is private) |
| `DATABASE_URL` | PostgreSQL connection URI (`postgresql://user:pass@host:5432/dbname`) |

---

## Installation & Setup

### 1. Prerequisites
- Python 3.12.10
- Git

### 2. Local Environment Setup
```bash
# Clone repository
git clone https://github.com/Ainaops/EmailIntelligence.git
cd EmailIntelligence

# Initialize virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Local Execution (SQLite)
By default, omitting `DATABASE_URL` initializes a local SQLite database (`sqlite:///email_intelligence.db`):
```bash
python main.py
```

### 4. Production Deployment Notes (Render & PostgreSQL)
- **Database**: Supply `DATABASE_URL` pointing to a PostgreSQL instance.
- **Model Storage**: On startup, `phishing_detector.py` invokes `huggingface_hub.snapshot_download()` to pull the 25 model weights from `Ainaops/email-intelligence-models`.

---

## 📜 Citation

If you use `EmailIntelligence` in your research or project, please cite this repository:

```bibtex
@software{favour2026emailintelligence,
  author = {Aina, Abolaji Favour},
  title = {EmailIntelligence: A Research Software Implementation for Transformer-Enhanced Phishing Detection},
  version = {1.0.0},
  year = {2026},
  publisher = {GitHub},
  url = {https://github.com/Ainaops/EmailIntelligence}
}
```

---

## Author & Research Background

**Aina Abolaji Favour**  
B.Sc. Computer Science, Redeemer's University  

**Research Interests**:
- Cybersecurity
- Machine Learning
- Natural Language Processing
- Explainable AI (XAI)
- Trustworthy AI
- Adversarial Machine Learning
