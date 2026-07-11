"""SWE-bench Lite adapter for improved_harness.

Pipeline:
  1. Load instances from HuggingFace (princeton-nlp/SWE-bench_Lite)
  2. Clone repo @ base_commit into a workspace
  3. Run our agent_loop (WORKDIR = workspace)
  4. Collect ``git diff`` as model_patch → predictions.jsonl
  5. Optionally score with official swebench harness (Docker / Linux)

Windows note: the ``swebench`` package imports Unix ``resource`` and cannot be
imported natively. Prediction works on Windows; official resolve scoring runs
inside a Docker Linux container when ``--eval`` is set.
"""

from __future__ import annotations
