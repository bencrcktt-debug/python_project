# Python Project

Streamlit app for exploring the TPPF lobby data.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   ```

2. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Data configuration

The app expects a parquet file named `TFL Webstite books - combined.parquet`.

Provide the file using one of these options:
- Set `DATA_PATH` to an absolute path or URL.
- Add `.streamlit/secrets.toml` with `DATA_PATH = "..."` (recommended for Streamlit Cloud).
- Place the file at `./data/TFL Webstite books - combined.parquet` in the repo.

## Running the app

```bash
streamlit run main.py
```
