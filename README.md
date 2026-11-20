# ⚖️ Judicial Case Scraper & Analyzer (Pereplanirovka Parser)

A high-performance Python data extraction, NLP linking, and reporting engine designed to parse, chain, and structure judicial court decisions on property redevelopment and apartment remodeling cases (*деле о перепланировке*). The system scrapes judicial rulings across all four instances—from district courts through regional appeal, cassation, and the Supreme Court of the Russian Federation—links legal case trajectories, extracts key litigation entities, and compiles multi-sheet Excel workbooks alongside categorized Word (.docx) archives.

---

## 🚀 Features

- **🏛️ Four-Instance Case Chaining**: Automatically discovers and chains decisions across the entire Russian court hierarchy:
  - **1st Instance**: District courts (e.g., Nizhny Novgorod regional districts).
  - **2nd Instance**: Regional Appeal Court (`oblsud--nnov.sudrf.ru`).
  - **3rd Instance**: First Cassation Court of General Jurisdiction (`1kas.sudrf.ru`).
  - **4th Instance**: Supreme Court of the Russian Federation (`vsrf.ru`).
- **🔗 Intelligent Cross-Source Entity Linking**: Associates fragmented case numbers, appeal references, and party identifiers into unified `CaseChain` models.
- **🔍 Legal Entity Extraction**:
  - Full names of judges, plaintiffs, legal representatives, and defendants.
  - Identification of structural modifications (e.g., load-bearing wall alterations, wet zone expansions).
  - Identification of specialized architectural and forensic examination organizations (*экспертные организации*).
  - Case outcomes (Satisfied, Partially Satisfied, Rejected, Dismissed).
- **📊 Formatted Excel Workbooks**: Generates structured, colored multi-sheet `.xlsx` reports with formulas, auto-fitted columns, and district-by-district aggregations using `openpyxl`.
- **📁 Categorized Word (.docx) Dossiers**: Downloads and formats full court texts into clean Word documents organized into `Won/` and `Lost/` directory archives via `python-docx`.
- **⚡ Concurrent Asynchronous Scraping**: Multi-threaded and headless browser scraping utilizing Playwright, Requests, and BeautifulSoup4 with source fallback.
- **🔄 Local Cache & Instant Rebuild**: Raw HTML and JSON payloads are cached locally (`data/raw/`), allowing zero-network report regeneration via `src.rebuild`.

---

## 🛠️ Tech Stack

- **Language**: Python 3.11 / 3.12
- **Headless Browser & Scraping**: [Playwright](https://playwright.dev/python/), [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/), [LXML](https://lxml.de/), and [Requests](https://requests.readthedocs.io/)
- **Spreadsheet & Document Generation**: [OpenPyXL](https://openpyxl.readthedocs.io/) (Excel `.xlsx`) and [python-docx](https://python-docx.readthedocs.io/) (Word `.docx`)
- **Data Modeling & Serialization**: Python Dataclasses, PyYAML, and JSON
- **Concurrency**: `concurrent.futures.ThreadPoolExecutor`

---

## 📦 Installation

### Prerequisites
- Python 3.11 or 3.12 (recommended)
- [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) (Windows users only, for Greenlet/Playwright)

### Step-by-Step Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/glebanya13/pereplanirovka-parser.git
   cd pereplanirovka-parser
   ```

2. **Create and activate a virtual environment**:
   ```bash
   # macOS / Linux
   python3 -m venv venv
   source venv/bin/activate

   # Windows (Command Prompt)
   python -m venv venv
   venv\Scripts\activate.bat

   # Windows (PowerShell)
   python -m venv venv
   venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Verify source connectivity**:
   ```bash
   python scripts/check_sources.py
   ```

---

## 💻 Usage

### Demo Run (Pipeline & Template Validation)
Run a synthetic mock generation to test Excel formatting and Word document generation without network requests:
```bash
python3 -m src.main --demo
```

### Full Production Scraping
Scrape and process judicial decisions for the specified date range:
```bash
python3 -m src.main --scrape --date-from 2020-01-01 --date-to 2026-12-31
```

### Target a Single District
Scrape 1st-instance cases for a specific district (appeals and higher instances will be resolved automatically):
```bash
python3 -m src.main --scrape --district "Автозаводский район"
```

### Advanced Options
```bash
# Adjust worker concurrency threads
python3 -m src.main --scrape --workers 4

# Skip cross-source personal name resolution
python3 -m src.main --scrape --no-full-names

# Rebuild Excel reports and Word dossiers directly from local raw cache
python3 -m src.rebuild
```

---

## 📂 Project Structure

```markdown
pereplanirovka-parser/
|-- config/
|    `-- regions.yaml               # Court mappings, district codes, and endpoints
|-- data/
|    `-- raw/                       # Cached raw responses (HTML / JSON) for offline rebuilds
|-- docs/                           # Architecture notes and legal requirement specifications
|-- output/                         # Generated delivery files (XLSX reports & DOCX folders)
|-- scripts/
|    `-- check_sources.py           # Connectivity and anti-bot verification diagnostic tool
|-- src/
|    |-- __init__.py
|    |-- config.py                  # YAML loader and region configuration resolver
|    |-- linking.py                 # Multi-instance case chaining & identity matching
|    |-- main.py                    # Main CLI entry point & argument orchestrator
|    |-- markers.py                 # Text mining regex for bearing walls, outcomes, experts
|    |-- models.py                  # Core domain models (CaseChain, Decision, Instance, Outcome)
|    |-- pipeline.py                # End-to-end extraction, transformation & save flow
|    |-- rebuild.py                 # Offline report generator from raw data cache
|    |-- report/                    # Output builders
|    |    |-- archive_builder.py    # Word document structure generator (Won/Lost folders)
|    |    `-- xlsx_builder.py       # OpenPyXL multi-sheet Excel generator & styles
|    `-- scrapers/                  # Target court crawlers
|         |-- base.py               # Abstract base crawler interface
|         |-- parsers.py            # HTML text and metadata sanitizers
|         |-- sudact.py             # SudAct court aggregator scraper
|         |-- sudreshenia.py        # SudResheniya aggregator crawler
|         |-- sudrf_cms.py          # State automated court system (GAS Pravosudie / CMS)
|         |-- sudrf_district.py     # District court scraper module
|         `-- vsrf.py               # Supreme Court of the Russian Federation scraper
|-- requirements.txt                # Python package dependencies
|-- tz.md                           # Original technical specification document
`-- HANDOFF.md                      # Operational handover documentation
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:
1. Fork the repository: `git fork https://github.com/glebanya13/pereplanirovka-parser.git`
2. Create your feature branch: `git checkout -b feature/new-court-scraper`
3. Commit your changes: `git commit -m "feat: Add support for arbitration courts"`
4. Push to branch: `git push origin feature/new-court-scraper`
5. Open a Pull Request.

---

## 📝 License

This project is licensed under the **MIT License**.

---

## 📬 Contact

For questions, bug reports, or integration inquiries:
- **Author**: [@glebanya13](https://github.com/glebanya13)
- **Email**: [glebanya.com@gmail.com](mailto:glebanya.com@gmail.com)
- **Issues**: [GitHub Issues](https://github.com/glebanya13/pereplanirovka-parser/issues)
