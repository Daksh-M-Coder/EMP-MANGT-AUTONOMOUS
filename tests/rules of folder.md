# AI Testing Guidelines & Rules (`tests/`)

To maintain the reliability and accuracy of the FundTrace AI system, strict testing protocols must be followed. Any new feature, route, or logic added to the Python AI agent **must** be validated here before integration with the frontend dashboard.

## 📜 Core Testing Rules

### 1. Test-First Development

Every new AI feature or capability must be tested continuously in Python code within the `ai/tests/` directory **first**. Do not assume the model or backend works until it consistently delivers the expected outcomes in isolated test scripts.

### 2. Dedicated Folders Per Test Module

Tests must not be grouped loosely in a single file or directory. **Every individual test suite must have its own dedicated folder.**
This ensures isolated environments, prevents namespace/import collisions, and keeps results neatly organized by feature.

### 3. Strict Sequential Naming Convention

Every test folder must be prefixed with a unique, sequential number indicating the order of development or execution priority.

**Format:** `test_XX_module_name`

- `test_01_db_query/`
- `test_02_chat_prompts/`
- `test_03_forensic_analysis/`
- `test_04_direct_chat/`
- `test_05_transactions_tab/`
- `test_0n_...`

### 4. Code and Results Co-location

Each test folder must contain at least two primary files:

1.  **The Test Code** (e.g., `test.py` or `run.py`): The actual Python script that executes the API calls or module functions.
2.  **The Results Log** (e.g., `result.txt`): A saved output of the test execution. This allows developers to instantly verify whether the test passed or failed without needing to re-run the entire suite (which may consume expensive AI tokens).

## ✅ Checklist for a New Test

- [ ] Created a new folder following the `test_XX_feature_name` sequence.
- [ ] Written `test.py` to hit the AI endpoints or run internal functions.
- [ ] Written assertions (`check()` methods) to validate the AI returns real database data and not hallucinations.
- [ ] Executed the test successfully with all assertions passing.
- [ ] Saved the output to `result.txt` within the same folder.
